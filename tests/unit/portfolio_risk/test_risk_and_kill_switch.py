import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError

from prometheus_platform.adapters.in_memory import InMemoryEventJournal
from prometheus_platform.adapters.jsonl_journal import JournalCorruptError, JsonlEventJournal
from prometheus_platform.api import cli
from prometheus_platform.domain.events import (
    DomainEvent,
    KillSwitchReset,
    KillSwitchTripped,
    OrderSubmitted,
    RiskLimitBreached,
    SignalGenerated,
)
from prometheus_platform.domain.model import InstrumentId, Side, Signal, Venue
from prometheus_platform.ops.settings import Settings
from prometheus_platform.portfolio_risk.kill_switch import KillSwitch, enforce
from prometheus_platform.portfolio_risk.risk import (
    Leg,
    PortfolioSnapshot,
    Position,
    ProposedOrder,
    RiskLimits,
    RiskManager,
    flatten_orders,
)

T0 = datetime(2026, 11, 20, 12, tzinfo=UTC)
SPOT = InstrumentId("SOLUSDT", Venue.BINANCE)
PERP = InstrumentId("SOLUSDT-PERP", Venue.BINANCE)
D = Decimal


class FixedClock:
    def now(self) -> datetime:
        return T0


class RecordingGateway:
    def __init__(self, fail: bool = False) -> None:
        self.cancelled = 0
        self.fail = fail

    def submit(
        self, client_order_id: str, instrument: InstrumentId, side: Side, quantity: D
    ) -> None:
        raise AssertionError("el kill-switch no envía órdenes por su cuenta")

    def cancel_all(self) -> None:
        self.cancelled += 1
        if self.fail:
            raise ConnectionError("exchange caído")


LIMITS = RiskLimits(
    max_notional_symbol=D(500),
    max_notional_total=D(1000),
    max_leverage=D(1),
    hard_leverage=D("1.5"),
    max_daily_loss=D("0.02"),
    max_hedge_imbalance=D("0.15"),
    imbalance_grace_seconds=300,
)
RISK = RiskManager(LIMITS)


def hedged(
    qty: str = "2", price: str = "100", equity: str = "1000", sod: str = "1000"
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        equity=D(equity),
        start_of_day_equity=D(sod),
        positions=(
            Position(SPOT, "SOLUSDT", Leg.SPOT, D(qty), D(price)),
            Position(PERP, "SOLUSDT", Leg.PERP, -D(qty), D(price)),
        ),
    )


def order(
    side: Side, qty: str, instrument: InstrumentId = SPOT, leg: Leg = Leg.SPOT
) -> ProposedOrder:
    return ProposedOrder("carry-h2", instrument, "SOLUSDT", leg, side, D(qty), D(100))


# --- Pre-trade ---------------------------------------------------------------------------------


def test_an_order_within_limits_is_approved() -> None:
    assert RISK.pre_trade(order(Side.BUY, "1"), hedged(), kill_switch_active=False).approved


@pytest.mark.parametrize(
    ("book", "qty", "rule"),
    [
        (hedged(qty="2"), "2", "nocional_simbolo"),  # 400 + 200 > 500
        (hedged(qty="0", equity="10000"), "6", "nocional_simbolo"),
        (hedged(qty="2", equity="300"), "0.5", "apalancamiento"),  # 450 / 300 > 1x
    ],
)
def test_orders_that_breach_a_limit_are_rejected_with_the_rule(
    book: PortfolioSnapshot, qty: str, rule: str
) -> None:
    decision = RISK.pre_trade(order(Side.BUY, qty), book, kill_switch_active=False)
    assert not decision.approved
    assert decision.rule == rule


def test_total_notional_limit_across_symbols() -> None:
    other = InstrumentId("BNBUSDT", Venue.BINANCE)
    book = PortfolioSnapshot(
        equity=D(5000),
        start_of_day_equity=D(5000),
        positions=(
            Position(other, "BNBUSDT", Leg.SPOT, D(5), D(100)),
            Position(InstrumentId("ETHUSDT", Venue.BINANCE), "ETHUSDT", Leg.SPOT, D(2), D(100)),
            Position(SPOT, "SOLUSDT", Leg.SPOT, D(3), D(100)),
        ),  # 1.000 en total: SOL tiene margen por símbolo, pero no queda margen total
    )
    decision = RISK.pre_trade(order(Side.BUY, "1"), book, kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "nocional_total")


def test_reducing_exposure_is_always_allowed_even_above_limits_or_with_kill_switch() -> None:
    over = hedged(qty="9", equity="100")  # muy por encima de todo
    assert RISK.pre_trade(order(Side.SELL, "4"), over, kill_switch_active=True).approved
    close_short = order(Side.BUY, "9", PERP, Leg.PERP)
    assert RISK.pre_trade(close_short, over, kill_switch_active=True).approved


def test_flipping_through_zero_is_not_a_reduction() -> None:
    decision = RISK.pre_trade(order(Side.SELL, "4"), hedged(qty="2"), kill_switch_active=True)
    assert (decision.approved, decision.rule) == (False, "kill_switch")


def test_kill_switch_and_non_positive_equity_block_new_exposure() -> None:
    assert (
        RISK.pre_trade(order(Side.BUY, "1"), hedged(), kill_switch_active=True).rule
        == "kill_switch"
    )
    broke = RISK.pre_trade(order(Side.BUY, "1"), hedged(equity="0"), kill_switch_active=False)
    assert broke.rule == "equity"


def test_proposed_orders_must_be_positive() -> None:
    with pytest.raises(ValueError, match="cantidad de la orden"):
        order(Side.BUY, "0")


# --- Monitor -----------------------------------------------------------------------------------


def test_a_healthy_book_has_no_breaches() -> None:
    assert RISK.monitor(hedged()) == []


def test_daily_loss_and_hard_leverage_trip_the_kill_switch() -> None:
    rules = {b.rule: b.trips_kill_switch for b in RISK.monitor(hedged(equity="970", sod="1000"))}
    assert rules == {"perdida_diaria": True}
    rules = {
        b.rule: b.trips_kill_switch for b in RISK.monitor(hedged(qty="4", equity="500", sod="500"))
    }
    assert rules == {"apalancamiento_duro": True}  # 800 / 500 = 1,6x
    soft = {
        b.rule: b.trips_kill_switch for b in RISK.monitor(hedged(qty="3", equity="500", sod="500"))
    }
    assert soft == {"apalancamiento": False}  # 1,2x: aviso, todavía no para
    assert RISK.monitor(hedged(equity="-1"))[0].rule == "equity"


def test_an_unhedged_leg_only_trips_after_the_grace_period() -> None:
    book = PortfolioSnapshot(
        equity=D(1000),
        start_of_day_equity=D(1000),
        positions=(Position(SPOT, "SOLUSDT", Leg.SPOT, D(2), D(100)),),
        imbalance_age_seconds={"SOLUSDT": 30},
    )
    [fresh] = RISK.monitor(book)
    assert (fresh.rule, fresh.trips_kill_switch) == ("pata_sin_cubrir", False)
    stale = PortfolioSnapshot(
        book.equity,
        book.start_of_day_equity,
        book.positions,
        imbalance_age_seconds={"SOLUSDT": 301},
    )
    assert RISK.monitor(stale)[0].trips_kill_switch


def test_flatten_orders_close_every_leg() -> None:
    orders = flatten_orders(hedged(qty="2"))
    assert [(o.leg, o.side, o.quantity) for o in orders] == [
        (Leg.SPOT, Side.SELL, D(2)),
        (Leg.PERP, Side.BUY, D(2)),
    ]
    assert all(RISK.pre_trade(o, hedged(qty="2"), kill_switch_active=True).approved for o in orders)


# --- Kill-switch -------------------------------------------------------------------------------


def test_kill_switch_trips_once_cancels_journals_and_survives_a_restart(tmp_path: Path) -> None:
    flag = tmp_path / "paper" / "KILL_SWITCH"
    journal, gateway = InMemoryEventJournal(), RecordingGateway()
    switch = KillSwitch(flag, FixedClock(), journal, gateway)
    assert not switch.active
    assert switch.state() is None

    assert switch.trip("pérdida diaria", source="automatico")
    assert not switch.trip("otra vez")  # idempotente: no duplica eventos ni cancelaciones
    assert gateway.cancelled == 1
    [event] = list(journal.replay())
    assert isinstance(event, KillSwitchTripped)
    assert event.reason == "pérdida diaria"

    restarted = KillSwitch(flag, FixedClock(), InMemoryEventJournal())  # nuevo proceso
    assert restarted.active
    assert restarted.state() == {
        "reason": "pérdida diaria",
        "source": "automatico",
        "at": T0.isoformat(),
        "journaled": True,
    }


def test_reset_requires_an_author_and_is_journaled(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = KillSwitch(tmp_path / "KILL_SWITCH", FixedClock(), journal)
    assert not switch.reset("david")  # no estaba activado
    switch.trip("prueba")
    with pytest.raises(ValueError, match="quién"):
        switch.reset("  ")
    assert switch.reset("david")
    assert not switch.active
    assert isinstance(list(journal.replay())[-1], KillSwitchReset)


def test_a_flag_file_created_by_hand_counts_as_tripped(tmp_path: Path) -> None:
    flag = tmp_path / "KILL_SWITCH"
    flag.write_text("", encoding="utf-8")  # p. ej. `touch data/paper/KILL_SWITCH` desde el servidor
    switch = KillSwitch(flag, FixedClock(), InMemoryEventJournal())
    assert switch.active
    assert switch.state() == {
        "reason": "archivo bandera sin detalle",
        "source": "archivo",
        "journaled": False,
    }


def test_a_failing_cancel_still_trips_and_alerts(tmp_path: Path) -> None:
    switch = KillSwitch(
        tmp_path / "K", FixedClock(), InMemoryEventJournal(), RecordingGateway(fail=True)
    )
    assert switch.trip("exchange caído")
    assert switch.active


def test_enforce_journals_every_breach_and_trips_only_on_severe_ones(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = KillSwitch(tmp_path / "K", FixedClock(), journal)
    assert not enforce(
        RISK.monitor(hedged(qty="3", equity="500", sod="500")), switch, journal, FixedClock()
    )
    assert not switch.active
    assert enforce(RISK.monitor(hedged(equity="900")), switch, journal, FixedClock())
    kinds = [type(e).__name__ for e in journal.replay()]
    # Primero se detiene y después se registran las violaciones.
    assert kinds == ["RiskLimitBreached", "KillSwitchTripped", "RiskLimitBreached"]


def test_simulacro_del_runbook(tmp_path: Path) -> None:
    """El simulacro de docs/runbooks/kill-switch.md, de punta a punta."""
    flag, journal = tmp_path / "KILL_SWITCH", JsonlEventJournal(tmp_path / "diario.jsonl")
    gateway = RecordingGateway()
    switch = KillSwitch(flag, FixedClock(), journal, gateway)
    book = hedged(equity="975", sod="1000")  # 1. pérdida del 2,5 % en el día

    assert enforce(RISK.monitor(book), switch, journal, FixedClock())  # 2. se activa solo
    assert gateway.cancelled == 1  # 3. órdenes abiertas canceladas
    assert not RISK.pre_trade(order(Side.BUY, "1"), book, kill_switch_active=switch.active).approved
    closing = flatten_orders(book)  # 4. el runner cierra todo
    assert all(RISK.pre_trade(o, book, kill_switch_active=True).approved for o in closing)
    assert KillSwitch(flag, FixedClock(), journal).active  # 5. sobrevive al reinicio
    assert switch.reset("david")  # 6. rearme manual con autor
    assert [type(e).__name__ for e in journal.replay()] == [
        "KillSwitchTripped",  # primero detener, después registrar la causa
        "RiskLimitBreached",
        "KillSwitchReset",
    ]


# --- Diario persistente ------------------------------------------------------------------------


def test_jsonl_journal_round_trips_typed_events(tmp_path: Path) -> None:
    journal = JsonlEventJournal(tmp_path / "paper" / "diario.jsonl")
    signal = Signal("carry-h2", PERP, T0, D("-0.5"))
    events = [
        SignalGenerated(occurred_at=T0, signal=signal),
        OrderSubmitted(
            occurred_at=T0, client_order_id="c1", instrument=PERP, side=Side.SELL, quantity=D("1.5")
        ),
        RiskLimitBreached(occurred_at=T0, rule="r", detail="d"),
    ]
    for event in events:
        journal.append(event)
    assert list(journal.replay()) == events
    assert list(JsonlEventJournal(tmp_path / "no-existe.jsonl").replay()) == []


def test_jsonl_journal_refuses_to_guess_on_a_corrupt_line(tmp_path: Path) -> None:
    path = tmp_path / "diario.jsonl"
    path.write_text(json.dumps({"type": "EventoInventado"}) + "\n", encoding="utf-8")
    with pytest.raises(JournalCorruptError, match=r"diario\.jsonl:1"):
        list(JsonlEventJournal(path).replay())


# --- Configuración y CLI -----------------------------------------------------------------------


def test_risk_settings_are_validated_at_startup() -> None:
    assert RiskLimits.from_settings(Settings()).max_leverage == D(1)
    with pytest.raises(ValidationError):
        Settings(risk_max_leverage=3.0)
    with pytest.raises(ValidationError, match="HARD_LEVERAGE"):
        Settings(risk_max_leverage=1.5, risk_hard_leverage=1.2)
    with pytest.raises(ValidationError, match="por símbolo"):
        Settings(risk_max_notional_symbol_usd=2000, risk_max_notional_total_usd=1000)


def test_cli_kill_status_and_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PQ_DATA_DIR", str(tmp_path))
    assert cli.main(["paper", "status"]) == 0
    assert "ARMADO" in capsys.readouterr().out
    assert cli.main(["paper", "kill", "--reason", "simulacro"]) == 0
    assert cli.main(["paper", "status"]) == 0
    assert "simulacro" in capsys.readouterr().out
    assert cli.main(["paper", "kill", "--reset"]) == 2  # sin --confirm ni --by
    assert cli.main(["paper", "kill", "--reset", "--confirm", "--by", "david"]) == 0
    events = [
        type(e).__name__ for e in JsonlEventJournal(tmp_path / "paper" / "diario.jsonl").replay()
    ]
    assert events == ["KillSwitchTripped", "KillSwitchReset"]


# --- Regresiones de la revisión adversarial (PQ-53) ---------------------------------------------


class FailingJournal(InMemoryEventJournal):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    def append(self, event: DomainEvent) -> None:
        if self.fail:
            raise OSError("disco lleno")
        super().append(event)


def test_cli_or_hand_made_activation_is_completed_by_the_runner(tmp_path: Path) -> None:
    flag = tmp_path / "KILL_SWITCH"
    flag.write_text("", encoding="utf-8")  # activación a mano: nadie canceló ni registró nada
    journal, gateway = InMemoryEventJournal(), RecordingGateway()
    runner_view = KillSwitch(flag, FixedClock(), journal, gateway)
    assert runner_view.observe()
    assert runner_view.observe()  # cada ciclo vuelve a cancelar; registra una sola vez
    assert gateway.cancelled == 2
    events = list(journal.replay())
    assert len(events) == 1
    assert isinstance(events[0], KillSwitchTripped)
    assert events[0].source == "archivo"


def test_a_failing_journal_does_not_stop_the_trip_and_is_retried(tmp_path: Path) -> None:
    journal, gateway = FailingJournal(), RecordingGateway()
    switch = KillSwitch(tmp_path / "K", FixedClock(), journal, gateway)
    assert switch.trip("pérdida diaria")
    assert switch.active
    assert gateway.cancelled == 1  # se canceló aunque el diario falló
    assert (switch.state() or {})["journaled"] is False
    journal.fail = False
    switch.observe()  # el runner completa el registro
    assert [type(e).__name__ for e in journal.replay()] == ["KillSwitchTripped"]
    assert (switch.state() or {})["journaled"] is True


def test_reset_keeps_the_switch_tripped_if_it_cannot_be_journaled(tmp_path: Path) -> None:
    journal = FailingJournal()
    journal.fail = False
    switch = KillSwitch(tmp_path / "K", FixedClock(), journal)
    switch.trip("prueba")
    journal.fail = True
    with pytest.raises(OSError, match="disco lleno"):
        switch.reset("david")
    assert switch.active  # sin registro no hay rearme


def test_a_doubled_long_is_not_a_hedge() -> None:
    book = PortfolioSnapshot(
        equity=D(1000),
        start_of_day_equity=D(1000),
        positions=(
            Position(SPOT, "SOLUSDT", Leg.SPOT, D(2), D(100)),
            Position(PERP, "SOLUSDT", Leg.PERP, D(2), D(100)),  # error de signo: largo, no corto
        ),
        imbalance_age_seconds={"SOLUSDT": 0},
    )
    [breach] = RISK.monitor(book)
    assert breach.rule == "pata_sin_cubrir"
    assert "200.0%" in breach.detail


def test_missing_imbalance_age_assumes_the_worst() -> None:
    book = PortfolioSnapshot(
        equity=D(1000),
        start_of_day_equity=D(1000),
        positions=(Position(SPOT, "SOLUSDT", Leg.SPOT, D(2), D(100)),),
    )
    assert RISK.monitor(book)[0].trips_kill_switch


def test_pending_orders_count_so_two_closes_cannot_open_a_short() -> None:
    book = hedged(qty="10", equity="10000", sod="10000")
    close = order(Side.SELL, "10")
    assert RISK.pre_trade(close, book, kill_switch_active=True).approved
    after_first = PortfolioSnapshot(
        book.equity, book.start_of_day_equity, book.positions, pending={SPOT: D(-10)}
    )
    second = RISK.pre_trade(close, after_first, kill_switch_active=True)
    assert (second.approved, second.rule) == (False, "kill_switch")
    assert [o.instrument for o in flatten_orders(after_first)] == [PERP]  # el spot ya se cierra


def test_bad_prices_fail_loudly_and_exposure_uses_the_conservative_price() -> None:
    with pytest.raises(ValueError, match="mark_price"):
        Position(SPOT, "SOLUSDT", Leg.SPOT, D(1), D(-900))
    with pytest.raises(ValueError, match="mark_price"):
        Position(SPOT, "SOLUSDT", Leg.SPOT, D(1), D("NaN"))
    cheap = ProposedOrder("x", SPOT, "SOLUSDT", Leg.SPOT, Side.BUY, D(3), D("0.01"))
    decision = RISK.pre_trade(cheap, hedged(qty="2"), kill_switch_active=False)
    assert (decision.approved, decision.rule) == (False, "nocional_simbolo")  # valorado a 100


def test_an_order_must_use_the_symbol_of_its_instrument() -> None:
    wrong = ProposedOrder("x", SPOT, "BTCUSDT", Leg.SPOT, Side.BUY, D(1), D(100))
    assert RISK.pre_trade(wrong, hedged(), kill_switch_active=False).rule == "simbolo_inconsistente"


def test_no_valid_start_of_day_equity_trips() -> None:
    assert RISK.monitor(hedged(sod="0"))[0].rule == "equity_inicio_dia"


def test_journal_isolates_a_truncated_last_line_and_rejects_wrong_types(tmp_path: Path) -> None:
    path = tmp_path / "diario.jsonl"
    journal = JsonlEventJournal(path)
    journal.append(RiskLimitBreached(occurred_at=T0, rule="r", detail="d"))
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"type": "KillSwitchRe')  # corte de luz a mitad de escritura
    assert len(list(journal.replay())) == 1  # la línea a medias final se omite (con alerta)
    journal.append(KillSwitchReset(occurred_at=T0, by="david"))
    with pytest.raises(JournalCorruptError, match=r"diario\.jsonl:2"):
        list(journal.replay())  # ya no es la última: se detiene, pero el evento nuevo no se perdió
    assert (
        path.read_text(encoding="utf-8").splitlines()[-1].startswith('{"type": "KillSwitchReset"')
    )

    bad = tmp_path / "tipos.jsonl"
    record = {
        "type": "KillSwitchReset",
        "occurred_at": T0.isoformat(),
        "by": None,
        "event_id": "00000000-0000-0000-0000-000000000000",
    }
    bad.write_text(json.dumps(record) + "\n", encoding="utf-8")
    with pytest.raises(JournalCorruptError):
        list(JsonlEventJournal(bad).replay())


def test_infinite_limits_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(risk_max_notional_total_usd=float("inf"))
