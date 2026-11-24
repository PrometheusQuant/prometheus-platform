"""Respaldos cifrados del paper trading (PQ-73).

``data/paper/`` guarda lo que no se puede regenerar: el diario de eventos, el estado del bróker
simulado, el kill-switch y el heartbeat. Este módulo lo empaqueta (``tar.gz``), lo cifra con
`age <https://age-encryption.org>`_ (``pyrage``) y lo deja en una carpeta; subirlo fuera del
servidor lo hace ``deploy/respaldos/respaldar.sh`` (repo privado ``paper-respaldos``).

**El servidor solo tiene la clave pública** (``PQ_BACKUP_AGE_RECIPIENT``): puede cifrar, pero no
descifrar. La clave privada vive en la máquina de quien restaura. Si alguien entra al servidor o al
repo de respaldos, no puede leer los respaldos.

Restaurar exige que el runner esté detenido (toma el mismo candado que ``pq paper run``) y, si la
carpeta ya tiene un diario, ``--force``. Solo extrae archivos regulares con nombres simples: un
respaldo manipulado no puede escribir fuera de ``data/paper/``.
"""

from __future__ import annotations

import io
import os
import re
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyrage

from prometheus_platform.api.paper.compose import PaperPaths, single_instance

PREFIX = "paper-"
SUFFIX = ".tar.gz.age"
_STAMP = "%Y%m%dT%H%M%SZ"
_NAME = re.compile(rf"^{re.escape(PREFIX)}(\d{{8}}T\d{{6}}Z){re.escape(SUFFIX)}$")
# Lo que no se respalda: el candado del proceso, temporales y logs que no son estado.
_SKIP = re.compile(r"^(runner\.lock|.*\.tmp|.*\.rearmando|.*\.log)$")
_SAFE_MEMBER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class BackupError(RuntimeError):
    """Un respaldo que no se puede crear o restaurar sin riesgo."""


def generate_identity(path: Path) -> str:
    """Crea un par de claves age. Escribe la privada en ``path`` (0600) y devuelve la pública."""
    if path.exists():
        raise BackupError(f"{path} ya existe: no se sobrescribe una clave")
    identity = pyrage.x25519.Identity.generate()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"{identity}\n")
    return str(identity.to_public())


def _stamp_of(path: Path) -> datetime | None:
    match = _NAME.match(path.name)
    return datetime.strptime(match.group(1), _STAMP).replace(tzinfo=UTC) if match else None


def _pack(paper_dir: Path) -> tuple[bytes, list[str]]:
    buffer = io.BytesIO()
    names = []
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in sorted(paper_dir.iterdir()):
            if not path.is_file() or _SKIP.match(path.name):
                continue
            tar.add(path, arcname=path.name, recursive=False)
            names.append(path.name)
    return buffer.getvalue(), names


def create_backup(paper_dir: Path, out_dir: Path, recipient: str, now: datetime) -> Path:
    """Cifra el estado de ``paper_dir`` en ``out_dir/paper-<UTC>.tar.gz.age``."""
    if not recipient.strip():
        raise BackupError("falta PQ_BACKUP_AGE_RECIPIENT (la clave pública age)")
    try:
        key = pyrage.x25519.Recipient.from_str(recipient.strip())
    except Exception as exc:  # pyrage lanza su propio tipo, según la versión
        raise BackupError("PQ_BACKUP_AGE_RECIPIENT no es una clave pública age válida") from exc
    if not paper_dir.is_dir():
        raise BackupError(f"no existe {paper_dir}: no hay nada que respaldar")
    payload, names = _pack(paper_dir)
    if not names:
        raise BackupError(f"{paper_dir} no tiene archivos de estado")
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{PREFIX}{now.astimezone(UTC):{_STAMP}}{SUFFIX}"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(pyrage.encrypt(payload, [key]))
    os.replace(tmp, target)  # nunca queda un respaldo a medias con el nombre final
    return target


def prune(out_dir: Path, keep: timedelta, now: datetime) -> list[Path]:
    """Borra los respaldos más viejos que ``keep``. Nunca borra el más reciente."""
    dated = sorted(
        (stamp, path)
        for path in out_dir.glob(f"{PREFIX}*{SUFFIX}")
        if (stamp := _stamp_of(path)) is not None
    )
    removed = []
    for stamp, path in dated[:-1]:
        if now - stamp > keep:
            path.unlink()
            removed.append(path)
    return removed


def restore_backup(
    archive: Path, identity_file: Path, paper_dir: Path, *, force: bool = False
) -> list[str]:
    """Descifra ``archive`` y restaura sus archivos en ``paper_dir``. Devuelve sus nombres."""
    paths = PaperPaths(paper_dir)
    if paths.journal.exists() and not force:
        raise BackupError(f"{paths.journal} ya existe: usa --force para reemplazar el estado")
    try:
        identity = pyrage.x25519.Identity.from_str(
            identity_file.read_text(encoding="utf-8").strip().splitlines()[-1]
        )
        payload = pyrage.decrypt(archive.read_bytes(), [identity])
    except OSError:
        raise
    except Exception as exc:
        raise BackupError("no se pudo descifrar: ¿clave privada equivocada?") from exc
    with single_instance(paths), tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as tar:
        members = tar.getmembers()
        unsafe = [m.name for m in members if not (m.isfile() and _SAFE_MEMBER.match(m.name))]
        if unsafe:
            raise BackupError(f"el respaldo trae entradas no permitidas: {unsafe}")
        for member in members:
            source = tar.extractfile(member)
            if source is None:
                raise BackupError(f"no se pudo leer {member.name} del respaldo")
            tmp = paper_dir / f"{member.name}.tmp"
            tmp.write_bytes(source.read())
            os.replace(tmp, paper_dir / member.name)
    return [m.name for m in members]
