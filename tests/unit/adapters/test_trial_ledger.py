"""Registro de ensayos compartido (PQ-112): N global entre carriles y máquinas."""

from __future__ import annotations

from pathlib import Path

import pytest

from prometheus_platform.adapters.mlflow_registry import MlflowRegistry, historical_rows
from prometheus_platform.adapters.trial_ledger import (
    LedgerError,
    RegistryTee,
    TrialLedger,
    counts,
    git_commit,
    read_rows,
)
from prometheus_platform.api import cli
from prometheus_platform.research.carry_evaluation import TrialRecord


def trial(name: str, hypothesis: str = "H2", sharpe: float = 0.1) -> TrialRecord:
    return TrialRecord(
        hypothesis, name, {"k": "9"}, {"sharpe_daily": sharpe}, {"period": "desarrollo"}
    )


def ledger(directory: Path, carril: str = "david", familia: str = "carry") -> TrialLedger:
    return TrialLedger(
        directory,
        familia=familia,
        carril=carril,
        autor="test",
        comando="pq research carry",
        commit="abc",
    )


def test_trials_are_the_union_of_every_lane(tmp_path: Path) -> None:
    """Un ensayo de Boris suma a N aunque lo lea David: es lo que motiva PQ-112."""
    ledger(tmp_path, "david").log_trial(trial("k9-theta20"))
    ledger(tmp_path, "boris").log_trial(trial("k3-theta10"))
    ledger(tmp_path, "boris", "tendencia").log_trial(trial("ma-50", "T1"))
    ledger(tmp_path, "david", "descriptivo").log_execution("eda")

    seen = ledger(tmp_path).trials()

    assert sorted(t.name for t in seen) == ["k3-theta10", "k9-theta20"]
    assert counts(tmp_path) == {"carry": 2, "tendencia": 1, "total": 3}  # eda no cuenta
    assert sorted(p.name for p in tmp_path.iterdir()) == ["boris.jsonl", "david.jsonl"]


def test_rows_keep_who_what_and_with_which_code(tmp_path: Path) -> None:
    ledger(tmp_path).log_trial(trial("k9-theta20", sharpe=0.35))

    (row,) = read_rows(tmp_path)

    assert (row.autor, row.carril, row.familia, row.hipotesis) == ("test", "david", "carry", "H2")
    assert row.commit == "abc"
    assert row.cuenta_en_n
    assert row.metricas == {"sharpe_daily": 0.35}
    assert row.fecha.endswith("+00:00")


def test_a_trial_that_cannot_be_registered_fails_loudly(tmp_path: Path) -> None:
    blocked = tmp_path / "es-un-archivo"
    blocked.write_text("", encoding="utf-8")
    mirror: list[TrialRecord] = []

    class Mirror:
        def log_trial(self, t: TrialRecord) -> None:
            mirror.append(t)

        def trials(self) -> list[TrialRecord]:
            return mirror

    with pytest.raises(LedgerError):
        RegistryTee(ledger(blocked), Mirror()).log_trial(trial("k9-theta20"))
    assert mirror == []  # el registro compartido manda: sin fila, tampoco copia


def test_corrupt_lines_stop_the_count(tmp_path: Path) -> None:
    (tmp_path / "david.jsonl").write_text('{"no": "es una fila"}\n', encoding="utf-8")
    with pytest.raises(LedgerError, match=r"david\.jsonl:1"):
        counts(tmp_path)


def test_lane_must_be_a_simple_name(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Carril"):
        ledger(tmp_path, carril="../fuera")


def test_git_commit_is_a_short_hash_or_unknown(tmp_path: Path) -> None:
    assert git_commit(tmp_path) == "desconocido"  # tmp_path no es un repo
    assert git_commit() != ""


def test_ledger_matches_mlflow_on_historical_runs(tmp_path: Path) -> None:
    """Criterio de PQ-112: importar el MLflow histórico da los mismos ensayos y la misma N."""
    database = tmp_path / "mlflow.db"
    carry = MlflowRegistry(database, "carry-funding")
    for name, sharpe in (("k3-theta10", 0.2), ("k9-theta20", 0.35), ("k21-theta30", 0.1)):
        carry.log_trial(trial(name, sharpe=sharpe))
    MlflowRegistry(database, "funding-model").log_trial(trial("ridge:tuned", "regresion"))
    directory = tmp_path / "ensayos"
    target = ledger(directory)
    for row in historical_rows(database, carril="david", autor="test"):
        target.append(row)

    def key(
        t: TrialRecord,
    ) -> tuple[str, str, tuple[tuple[str, str], ...], tuple[tuple[str, float], ...]]:
        return (
            t.hypothesis,
            t.name,
            tuple(sorted(t.params.items())),
            tuple(sorted(t.metrics.items())),
        )

    assert sorted(map(key, target.trials())) == sorted(map(key, carry.trials()))
    assert counts(directory) == {"carry": 3, "modelo-funding": 1, "total": 4}


def test_cli_import_is_idempotent_and_verify_detects_gaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    registry = MlflowRegistry(tmp_path / "lake/mlflow/mlflow.db", "carry-funding")
    registry.log_trial(trial("k9-theta20"))

    assert cli.main(["research", "registro", "verificar"]) == 1  # falta en el registro
    assert cli.main(["research", "registro", "importar-mlflow"]) == 0
    assert cli.main(["research", "registro", "importar-mlflow"]) == 0
    assert cli.main(["research", "registro", "verificar"]) == 0
    assert cli.main(["research", "registro", "resumen"]) == 0

    out = capsys.readouterr().out
    assert "importadas 1 filas" in out
    assert "importadas 0 filas; ya estaban 1" in out
    assert "carry: N = 1" in out


def test_descriptive_runs_are_registered_before_they_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Aunque el estudio falle (aquí, sin silver), la ejecución ya quedó registrada."""
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lake"))
    ledger_dir = tmp_path / "ensayos-cli"
    monkeypatch.setenv("PQ_RESEARCH_LEDGER_DIR", str(ledger_dir))

    with pytest.raises(Exception):  # noqa: B017, PT011 - cualquier fallo del estudio sirve
        cli.main(["research", "stats"])

    (row,) = read_rows(ledger_dir)
    assert row.familia == "descriptivo"
    assert not row.cuenta_en_n
    assert row.comando == "pq research stats"
