"""Respaldos cifrados del paper trading (PQ-73)."""

import io
import tarfile
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pyrage
import pytest
import structlog

from prometheus_platform.api import cli
from prometheus_platform.api.paper.backup import (
    BackupError,
    create_backup,
    generate_identity,
    prune,
    restore_backup,
)
from prometheus_platform.api.paper.compose import (
    PaperPaths,
    RunnerAlreadyRunningError,
    single_instance,
)

NOW = datetime(2026, 11, 21, 23, 0, tzinfo=UTC)
STATE = {
    "diario.jsonl": '{"evento": 1}\n',
    "broker-simulado.json": '{"cash": "1000"}',
    "heartbeat.json": '{"ok": true}',
    "KILL_SWITCH": '{"reason": "x"}',
}
NOT_STATE = {"runner.lock": "", "diario.jsonl.tmp": "a medias", "runner.log": "log"}


@pytest.fixture
def paper(tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    folder.mkdir()
    for name, text in {**STATE, **NOT_STATE}.items():
        (folder / name).write_text(text)
    return folder


@pytest.fixture
def keys(tmp_path: Path) -> tuple[Path, str]:
    private = tmp_path / "claves" / "respaldos.key"
    return private, generate_identity(private)


def test_round_trip_restores_only_the_state(
    paper: Path, keys: tuple[Path, str], tmp_path: Path
) -> None:
    private, public = keys
    archive = create_backup(paper, tmp_path / "respaldos", public, NOW)
    assert archive.name == "paper-20261121T230000Z.tar.gz.age"
    assert b'"evento"' not in archive.read_bytes()  # cifrado: nada en claro

    target = tmp_path / "restaurado"
    target.mkdir()
    assert sorted(restore_backup(archive, private, target)) == sorted(STATE)
    for name, text in STATE.items():
        assert (target / name).read_text() == text
    for name in NOT_STATE:
        assert not (target / name).exists() or name == "runner.lock"  # el candado lo crea restore


def test_private_key_file_is_private_and_never_overwritten(keys: tuple[Path, str]) -> None:
    private, public = keys
    assert public.startswith("age1")
    assert private.stat().st_mode & 0o777 == 0o600
    with pytest.raises(BackupError, match="ya existe"):
        generate_identity(private)


def test_a_different_key_cannot_decrypt(
    paper: Path, keys: tuple[Path, str], tmp_path: Path
) -> None:
    archive = create_backup(paper, tmp_path / "r", keys[1], NOW)
    intruder = tmp_path / "otra.key"
    generate_identity(intruder)
    target = tmp_path / "t"
    target.mkdir()
    with pytest.raises(BackupError, match="descifrar"):
        restore_backup(archive, intruder, target)


def test_restore_refuses_to_overwrite_a_journal_without_force(
    paper: Path, keys: tuple[Path, str], tmp_path: Path
) -> None:
    archive = create_backup(paper, tmp_path / "r", keys[1], NOW)
    (paper / "diario.jsonl").write_text("estado nuevo\n")
    with pytest.raises(BackupError, match="--force"):
        restore_backup(archive, keys[0], paper)
    restore_backup(archive, keys[0], paper, force=True)
    assert (paper / "diario.jsonl").read_text() == STATE["diario.jsonl"]


def test_restore_refuses_while_the_runner_holds_the_lock(
    paper: Path, keys: tuple[Path, str], tmp_path: Path
) -> None:
    archive = create_backup(paper, tmp_path / "r", keys[1], NOW)
    with single_instance(PaperPaths(paper)), pytest.raises(RunnerAlreadyRunningError):
        restore_backup(archive, keys[0], paper, force=True)


def test_a_tampered_archive_cannot_write_outside_the_folder(
    keys: tuple[Path, str], tmp_path: Path
) -> None:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        data = b"malicioso"
        info = tarfile.TarInfo("../fuera.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    archive = tmp_path / "paper-20261121T230000Z.tar.gz.age"
    archive.write_bytes(
        pyrage.encrypt(buffer.getvalue(), [pyrage.x25519.Recipient.from_str(keys[1])])
    )
    target = tmp_path / "t"
    target.mkdir()
    with pytest.raises(BackupError, match="no permitidas"):
        restore_backup(archive, keys[0], target)
    assert not (tmp_path / "fuera.txt").exists()


def test_create_needs_a_valid_public_key_and_some_state(paper: Path, tmp_path: Path) -> None:
    with pytest.raises(BackupError, match="falta"):
        create_backup(paper, tmp_path / "r", " ", NOW)
    with pytest.raises(BackupError, match="no es una clave"):
        create_backup(paper, tmp_path / "r", "age1noesunaclave", NOW)
    empty = tmp_path / "vacio"
    empty.mkdir()
    with pytest.raises(BackupError, match="no tiene archivos"):
        create_backup(empty, tmp_path / "r", generate_identity(tmp_path / "k"), NOW)


def test_prune_keeps_the_window_and_always_the_newest(tmp_path: Path) -> None:
    def backup(age_days: int) -> Path:
        stamp = NOW - timedelta(days=age_days)
        path = tmp_path / f"paper-{stamp:%Y%m%dT%H%M%SZ}.tar.gz.age"
        path.write_bytes(b"x")
        return path

    old, edge, recent = backup(20), backup(14), backup(1)
    other = tmp_path / "notas.txt"
    other.write_text("no es un respaldo")
    assert prune(tmp_path, timedelta(days=14), NOW) == [old]
    assert edge.exists()
    assert recent.exists()
    assert other.exists()

    lonely = tmp_path / "solo"
    lonely.mkdir()
    newest = lonely / "paper-20260101T000000Z.tar.gz.age"
    newest.write_bytes(b"x")
    assert prune(lonely, timedelta(days=14), NOW) == []  # aunque sea viejo, es el único


@pytest.fixture
def reset_structlog() -> Iterator[None]:
    yield
    structlog.reset_defaults()


@pytest.mark.usefixtures("reset_structlog")
def test_cli_keygen_create_and_restore(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    lake = tmp_path / "lake"
    (lake / "paper").mkdir(parents=True)
    (lake / "paper" / "diario.jsonl").write_text("uno\n")
    monkeypatch.setenv("PQ_DATA_DIR", str(lake))
    key = tmp_path / "k.key"
    assert cli.main(["paper", "backup", "keygen", "--out", str(key)]) == 0
    public = capsys.readouterr().out.split("PQ_BACKUP_AGE_RECIPIENT del servidor): ")[1].strip()

    assert cli.main(["paper", "backup", "create", "--out", str(tmp_path / "r")]) == 2  # sin clave
    monkeypatch.setenv("PQ_BACKUP_AGE_RECIPIENT", public)
    assert cli.main(["paper", "backup", "create", "--out", str(tmp_path / "r")]) == 0
    [archive] = (tmp_path / "r").glob("paper-*.tar.gz.age")

    (lake / "paper" / "diario.jsonl").unlink()  # el simulacro: se pierde el diario
    restore = ["paper", "backup", "restore", str(archive), "--identity", str(key)]
    assert cli.main(restore) == 0
    assert (lake / "paper" / "diario.jsonl").read_text() == "uno\n"
