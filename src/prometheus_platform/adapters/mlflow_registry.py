"""Registro de experimentos en MLflow (PQ-24). Cumple el puerto ``ExperimentRegistry``.

Cada ensayo de cada hipótesis queda como un *run*: parámetros, métricas y etiquetas. El número
de ensayos N del Deflated Sharpe se cuenta desde aquí, así que un ensayo no puede "olvidarse".
El backend es SQLite (el almacén en archivos de MLflow está en modo mantenimiento).
"""

from __future__ import annotations

from pathlib import Path

from mlflow.tracking import MlflowClient

from prometheus_platform.research.carry_evaluation import TrialRecord


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
