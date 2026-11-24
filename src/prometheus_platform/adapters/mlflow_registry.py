"""Registro de experimentos en MLflow (PQ-24). Cumple el puerto ``ExperimentRegistry``.

Cada ensayo de cada hipótesis queda como un *run*: parámetros, métricas y etiquetas. Desde
PQ-112 es una **copia** local: N se cuenta en el registro compartido y versionado
(``adapters/trial_ledger.py``), que suma los ensayos de todos los carriles y máquinas.
El backend es SQLite (el almacén en archivos de MLflow está en modo mantenimiento).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from mlflow.tracking import MlflowClient

from prometheus_platform.adapters.trial_ledger import TrialRow
from prometheus_platform.research.carry_evaluation import TrialRecord

# Experimento de MLflow → familia del registro compartido y comando que lo genera (PQ-112).
FAMILIES = {
    "carry-funding": ("carry", "pq research carry"),
    "funding-model": ("modelo-funding", "pq research funding-model"),
}


class MlflowRegistry:
    def __init__(self, database: Path, experiment: str) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self._uri = f"sqlite:///{database}"
        self._client = MlflowClient(tracking_uri=self._uri)
        found = self._client.get_experiment_by_name(experiment)
        self._experiment_id = (
            found.experiment_id if found else self._client.create_experiment(experiment)
        )

    def log_trial(self, trial: TrialRecord) -> None:
        run = self._client.create_run(
            self._experiment_id,
            run_name=trial.name,
            tags={**trial.tags, "hypothesis": trial.hypothesis},
        )
        run_id = run.info.run_id
        for key, value in trial.params.items():
            self._client.log_param(run_id, key, value)
        for metric, number in trial.metrics.items():
            self._client.log_metric(run_id, metric, number)
        self._client.set_terminated(run_id)

    def trials(self) -> list[TrialRecord]:
        runs = self._client.search_runs([self._experiment_id], max_results=10_000)
        return [
            TrialRecord(
                hypothesis=r.data.tags.get("hypothesis", ""),
                name=r.data.tags.get("mlflow.runName", r.info.run_name or ""),
                params=dict(r.data.params),
                metrics=dict(r.data.metrics),
                tags={k: v for k, v in r.data.tags.items() if not k.startswith("mlflow.")},
            )
            for r in runs
        ]

    @property
    def tracking_uri(self) -> str:
        return self._uri


def historical_rows(database: Path, *, carril: str, autor: str) -> list[TrialRow]:
    """Los ensayos de un MLflow local como filas del registro compartido (importación, PQ-112).

    Se usa una sola vez por máquina para llevar el historial al registro versionado. Cada fila
    guarda el ``run_id`` de MLflow en sus etiquetas, así reimportar no duplica nada.
    """
    client = MlflowClient(tracking_uri=f"sqlite:///{database}")
    rows = []
    for experiment, (familia, comando) in FAMILIES.items():
        found = client.get_experiment_by_name(experiment)
        if found is None:
            continue
        for run in client.search_runs([found.experiment_id], max_results=10_000):
            tags = {k: v for k, v in run.data.tags.items() if not k.startswith("mlflow.")}
            hipotesis = tags.pop("hypothesis", "")
            started = datetime.fromtimestamp(run.info.start_time / 1000, tz=UTC)
            rows.append(
                TrialRow(
                    fecha=started.isoformat(timespec="seconds"),
                    autor=autor,
                    carril=carril,
                    familia=familia,
                    hipotesis=hipotesis,
                    nombre=run.data.tags.get("mlflow.runName", run.info.run_name or ""),
                    commit="desconocido (importado de MLflow)",
                    cuenta_en_n=True,
                    comando=comando,
                    params=dict(run.data.params),
                    metricas=dict(run.data.metrics),
                    etiquetas={**tags, "mlflow_run_id": run.info.run_id},
                )
            )
    return sorted(rows, key=lambda r: r.fecha)
