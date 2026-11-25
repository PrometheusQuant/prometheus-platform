"""Modo feria del dashboard (PQ-102): recorrido de 7 pasos, tipografía grande y sin internet."""

from __future__ import annotations

import os
import socket
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from prometheus_platform.api.dashboard import app as dashboard_app
from prometheus_platform.api.dashboard import tour

from .test_dashboard import APP, app_labels


def test_fair_mode_only_with_modo_feria() -> None:
    assert tour.is_fair_mode({"modo": "feria"})
    assert tour.is_fair_mode({"modo": " FERIA "})
    assert tour.is_fair_mode({"modo": ["normal", "feria"]})  # gana el último valor
    assert not tour.is_fair_mode({})
    assert not tour.is_fair_mode({"modo": "normal"})
    assert not tour.is_fair_mode({"modo": []})


def test_the_tour_follows_the_seven_sections_of_the_pitch() -> None:
    assert [s.title for s in tour.STEPS] == [
        "El problema",
        "Por qué fallan los minoristas",
        "Nuestra respuesta",
        "La evidencia",
        "Demo en vivo",
        "Viabilidad",
        "Cierre",
    ]
    assert all(s.say and s.show for s in tour.STEPS)


def test_every_tab_the_tour_opens_exists_in_the_dashboard() -> None:
    assert {s.tab for s in tour.STEPS if s.tab} <= set(app_labels())


def test_the_tour_text_has_no_hardcoded_figures() -> None:
    """Las cifras salen de los artefactos; el guion solo nombra lo que se muestra."""
    allowed = {
        "1",
        "4",
        "G1",
        "G4",
        "H1",
        "H2",
    }  # nombres de gates e hipótesis, y el 4 % del hurdle
    for step in tour.STEPS:
        words = f"{step.say} {step.show}".replace(",", " ").replace(".", " ").split()
        numbers = {w for w in words if any(c.isdigit() for c in w)}
        assert numbers <= allowed, f"{step.title}: {numbers - allowed}"


def test_clamp_keeps_the_step_inside_the_tour() -> None:
    assert tour.clamp(-3) == 0
    assert tour.clamp(3) == 3
    assert tour.clamp(99) == len(tour.STEPS) - 1


def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fair: bool) -> AppTest:
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lago"))
    at = AppTest.from_file(str(APP), default_timeout=60)
    if fair:
        at.query_params["modo"] = "feria"
    return at.run()


def live_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, fair: bool) -> AppTest:
    """La página en vivo suelta; el modo feria se recuerda en la sesión (PQ-127)."""
    monkeypatch.chdir(tmp_path)
    for name in [n for n in os.environ if n.startswith("PQ_")]:
        monkeypatch.delenv(name)
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path / "lago"))
    script = "from prometheus_platform.api.dashboard import app\napp.render_page('paper-trading')"
    at = AppTest.from_string(script, default_timeout=60)
    if fair:
        at.session_state[dashboard_app.FAIR_KEY] = True
    return at.run()


def sidebar_text(at: AppTest) -> str:
    return " ".join(m.value for m in at.sidebar.markdown)


def test_fair_mode_guides_the_seven_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    at = app(tmp_path, monkeypatch, fair=True)
    assert not at.exception
    assert "paso 1 de 7" in sidebar_text(at)
    back, forward = at.sidebar.button
    assert back.disabled
    for expected in range(2, 8):
        forward.click().run()
        assert f"paso {expected} de 7" in sidebar_text(at)
        back, forward = at.sidebar.button
    assert forward.disabled  # último paso
    assert "**Abre:**" not in sidebar_text(at)  # el cierre no abre ninguna pestaña
    back.click().run()
    assert "paso 6 de 7" in sidebar_text(at)
    assert "¿Y si invierto? Simula tu inversión" in sidebar_text(at)
    assert any("font-size: 22px" in m.value for m in at.markdown)  # tipografía grande


def test_normal_mode_has_no_tour_and_no_big_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at = app(tmp_path, monkeypatch, fair=False)
    assert not at.exception
    assert not at.sidebar.markdown
    assert not any("font-size: 22px" in m.value for m in at.markdown)


def test_fair_mode_works_without_internet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan B de PQ-63: con la red cortada, el tablero abre y lee solo datos locales."""

    def no_network(*_args: object, **_kwargs: object) -> None:
        raise OSError("sin internet (prueba)")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    at = app(tmp_path, monkeypatch, fair=True)
    assert not at.exception
    assert at.title[0].value == "PrometheusQuant"


def test_fair_mode_live_tab_refreshes_by_itself(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime  # noqa: PLC0415
    from decimal import Decimal  # noqa: PLC0415

    from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal  # noqa: PLC0415
    from prometheus_platform.domain.events import PortfolioValued, RunnerStarted  # noqa: PLC0415

    now = datetime.now(UTC)
    journal = JsonlEventJournal(tmp_path / "lago/paper/diario.jsonl")
    journal.append(
        RunnerStarted(
            occurred_at=now, broker="simulado", strategy_id="carry-h2", symbols="SOLUSDT", params=""
        )
    )
    journal.append(
        PortfolioValued(
            occurred_at=now, equity=Decimal(1000), cash=Decimal(1000), gross_notional=Decimal(0)
        )
    )
    fair = live_page(tmp_path, monkeypatch, fair=True)
    assert not fair.exception
    captions = " ".join(c.value for c in fair.caption)
    assert f"Se actualiza sola cada {tour.LIVE_REFRESH.seconds} s." in captions
    normal = live_page(tmp_path, monkeypatch, fair=False)
    assert "Recarga la página para ver el último ciclo." in " ".join(
        c.value for c in normal.caption
    )
