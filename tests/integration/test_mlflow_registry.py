from pathlib import Path

from prometheus_platform.adapters.mlflow_registry import MlflowRegistry
from prometheus_platform.research.carry_evaluation import ExperimentRegistry, TrialRecord


def test_trials_persist_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "mlflow" / "mlflow.db"
    first = MlflowRegistry(db, "carry")
    first.log_trial(
        TrialRecord("H1", "k3-theta10", {"k": "3"}, {"sharpe_daily": 0.05}, {"costs": "principal"})
    )
    registry: ExperimentRegistry = MlflowRegistry(db, "carry")
    [trial] = registry.trials()
    assert trial.hypothesis == "H1"
    assert trial.name == "k3-theta10"
    assert trial.params == {"k": "3"}
    assert trial.metrics == {"sharpe_daily": 0.05}
    assert trial.tags["costs"] == "principal"
    assert first.tracking_uri.startswith("sqlite:///")
