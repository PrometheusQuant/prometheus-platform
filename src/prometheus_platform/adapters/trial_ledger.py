"""Registro de ensayos compartido y versionado en git (PQ-112). Cumple ``ExperimentRegistry``.

**Por qué.** Con dos carriles, N no puede vivir en un MLflow local: un backtest ejecutado en la
máquina de Boris no sumaría a N y el Deflated Sharpe quedaría inflado. El registro vive en el repo,
en ``docs/estrategias/ensayos/``, y viaja con los PR.

- **Un archivo por carril** (``david.jsonl``, ``boris.jsonl``): cada carril solo agrega a su
  archivo, así dos PR en paralelo nunca chocan. N es la unión de todos.
- **Una fila por ensayo**, con la fecha, el autor, el carril, la familia, la hipótesis, la
  configuración, las métricas, el commit, si cuenta en N y el comando. Las ejecuciones que no son
  ensayos (EDA, estadística descriptiva) dejan también su fila, con ``cuenta_en_n = false``.
- **Append-only con ``fsync``.** Si la fila no se puede escribir, el comando falla: un ensayo sin
  registrar no existe para N y no puede quedar «olvidado».
"""

from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from prometheus_platform.research.carry_evaluation import ExperimentRegistry, TrialRecord

LEDGER_DIR = Path("docs/estrategias/ensayos")
SCHEMA = 1


class LedgerError(RuntimeError):
    """El registro no se pudo leer o escribir: el comando de research no debe seguir."""


@dataclass(frozen=True, slots=True)
class TrialRow:
    fecha: str
    autor: str
    carril: str
    familia: str
    hipotesis: str
    nombre: str
    commit: str
    cuenta_en_n: bool
    comando: str
    params: dict[str, str] = field(default_factory=dict)
    metricas: dict[str, float] = field(default_factory=dict)
    etiquetas: dict[str, str] = field(default_factory=dict)
    esquema: int = SCHEMA

    def to_json(self) -> str:
        return json.dumps(
            {k: getattr(self, k) for k in self.__slots__}, ensure_ascii=False, sort_keys=True
        )

    @staticmethod
    def from_json(raw: dict[str, Any]) -> TrialRow:
        return TrialRow(**{k: raw[k] for k in TrialRow.__slots__ if k in raw})


def git_commit(cwd: Path | None = None) -> str:
    """Commit actual, con ``-sucio`` si hay cambios sin commitear (el ensayo igual cuenta)."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconocido"
    return f"{head}-sucio" if dirty else head


def git_author(cwd: Path | None = None) -> str:
    """``git config user.name``, o «desconocido» si no hay git o no está configurado."""
    try:
        name = subprocess.run(
            ["git", "config", "user.name"],  # noqa: S607
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "desconocido"
    return name or "desconocido"


def read_rows(directory: Path) -> Iterator[TrialRow]:
    """Todas las filas de todos los carriles. Una línea ilegible detiene la lectura."""
    for path in sorted(directory.glob("*.jsonl")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                yield TrialRow.from_json(json.loads(line))
            except (ValueError, TypeError, KeyError) as exc:
                raise LedgerError(f"{path}:{number}: {type(exc).__name__}") from exc


def counts(directory: Path) -> dict[str, int]:
    """Ensayos que cuentan en N por familia, más ``total`` (N global)."""
    result: dict[str, int] = {}
    for row in read_rows(directory):
        if row.cuenta_en_n:
            result[row.familia] = result.get(row.familia, 0) + 1
    result["total"] = sum(result.values())
    return result


class TrialLedger:
    """Escribe las filas de un carril y lee las de todos, filtradas por familia."""

    def __init__(  # noqa: PLR0913 - keyword-only: cada argumento es una columna fija de la fila
        self,
        directory: Path,
        *,
        familia: str,
        carril: str,
        autor: str,
        comando: str,
        commit: str | None = None,
    ) -> None:
        if not carril.strip() or not carril.isidentifier():
            raise ValueError(f"Carril inválido (PQ_RESEARCH_LANE): {carril!r}")
        self._dir = directory
        self._path = directory / f"{carril}.jsonl"
        self.familia, self.carril, self.autor, self.comando = familia, carril, autor, comando
        self.commit = commit or git_commit()

    # --- puerto ExperimentRegistry ---------------------------------------------------------

    def log_trial(self, trial: TrialRecord) -> None:
        self.append(
            TrialRow(
                fecha=datetime.now(UTC).isoformat(timespec="seconds"),
                autor=self.autor,
                carril=self.carril,
                familia=self.familia,
                hipotesis=trial.hypothesis,
                nombre=trial.name,
                commit=self.commit,
                cuenta_en_n=True,
                comando=self.comando,
                params=dict(trial.params),
                metricas={k: float(v) for k, v in trial.metrics.items()},
                etiquetas=dict(trial.tags),
            )
        )

    def trials(self) -> list[TrialRecord]:
        """Los ensayos de la familia que cuentan en N, de **todos** los carriles."""
        return [
            TrialRecord(r.hipotesis, r.nombre, dict(r.params), dict(r.metricas), dict(r.etiquetas))
            for r in read_rows(self._dir)
            if r.familia == self.familia and r.cuenta_en_n
        ]

    # --- extras ----------------------------------------------------------------------------

    def log_execution(self, nombre: str, params: dict[str, str] | None = None) -> None:
        """Una ejecución de research que no es un ensayo: queda registrada, pero no suma a N."""
        self.append(
            TrialRow(
                fecha=datetime.now(UTC).isoformat(timespec="seconds"),
                autor=self.autor,
                carril=self.carril,
                familia=self.familia,
                hipotesis="",
                nombre=nombre,
                commit=self.commit,
                cuenta_en_n=False,
                comando=self.comando,
                params=dict(params or {}),
            )
        )

    def append(self, row: TrialRow) -> None:
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(row.to_json() + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            raise LedgerError(f"No se pudo escribir el registro de ensayos {self._path}") from exc


class RegistryTee:
    """El registro compartido manda (y se escribe primero); MLflow recibe una copia."""

    def __init__(self, ledger: TrialLedger, mirror: ExperimentRegistry) -> None:
        self._ledger = ledger
        self._mirror = mirror

    def log_trial(self, trial: TrialRecord) -> None:
        self._ledger.log_trial(trial)  # si falla, el ensayo no se ejecuta como «registrado»
        self._mirror.log_trial(trial)

    def trials(self) -> list[TrialRecord]:
        return self._ledger.trials()
