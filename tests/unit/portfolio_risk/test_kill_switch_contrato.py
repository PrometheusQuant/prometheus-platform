"""Contrato detallado del kill-switch: lo que dejaban pasar los mutantes de mutmut (PQ-99).

Complementa test_risk_and_kill_switch.py. Cada prueba fija un dato que el runner, la CLI o el
runbook leen del archivo bandera o del diario, no solo que «se activó».
"""

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from prometheus_platform.adapters.in_memory import InMemoryEventJournal
from prometheus_platform.domain.events import DomainEvent, KillSwitchReset, KillSwitchTripped
from prometheus_platform.portfolio_risk.kill_switch import MAX_REASON_CHARS, KillSwitch

T0 = datetime(2026, 1, 5, 12, tzinfo=UTC)
T_MANUAL = datetime(2026, 1, 4, 8, 30, tzinfo=UTC)


class Clock:
    def now(self) -> datetime:
        return T0


class Gateway:
    def __init__(self) -> None:
        self.cancelled = 0

    def submit(self, *args: object) -> None:
        raise AssertionError("el kill-switch no envía órdenes")

    def cancel_all(self) -> None:
        self.cancelled += 1


class FailingJournal(InMemoryEventJournal):
    def __init__(self) -> None:
        super().__init__()
        self.fail = False

    def append(self, event: DomainEvent) -> None:
        if self.fail:
            raise OSError("disco lleno")
        super().append(event)


def _switch(tmp_path: Path, journal: InMemoryEventJournal | None = None) -> KillSwitch:
    journal = journal if journal is not None else InMemoryEventJournal()  # vacío es falsy
    return KillSwitch(tmp_path / "paper" / "KILL_SWITCH", Clock(), journal)


def test_trip_escribe_la_bandera_completa_con_permisos_600_y_crea_la_carpeta(
    tmp_path: Path,
) -> None:
    switch = _switch(tmp_path)
    assert switch.trip("pérdida diaria", source="cli")
    contenido = json.loads(switch.flag_path.read_text(encoding="utf-8"))
    # journaled pasa a True en cuanto el diario registra el disparo.
    assert contenido == {
        "reason": "pérdida diaria",
        "source": "cli",
        "at": T0.isoformat(),
        "journaled": True,
    }
    assert stat.S_IMODE(switch.flag_path.stat().st_mode) == 0o600
    assert switch.state() == contenido


def test_trip_por_defecto_es_automatico_recorta_el_motivo_y_no_se_repite(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = _switch(tmp_path, journal)
    assert switch.trip("x" * (MAX_REASON_CHARS + 50))
    assert not switch.trip("otra vez")
    eventos = list(journal.replay())
    assert len(eventos) == 1
    assert isinstance(eventos[0], KillSwitchTripped)
    assert eventos[0].source == "automatico"
    assert eventos[0].reason == "x" * MAX_REASON_CHARS
    assert eventos[0].occurred_at == T0
    assert (switch.state() or {})["reason"] == "x" * MAX_REASON_CHARS


def test_observe_registra_el_motivo_la_via_y_la_hora_de_una_bandera_manual(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = _switch(tmp_path, journal)
    switch.flag_path.parent.mkdir(parents=True)
    # Sin clave «journaled»: la escribió una persona o una herramienta externa.
    switch.flag_path.write_text(
        json.dumps({"reason": "mantenimiento", "source": "operador", "at": T_MANUAL.isoformat()}),
        encoding="utf-8",
    )
    assert switch.observe()
    (evento,) = journal.replay()
    assert isinstance(evento, KillSwitchTripped)
    assert (evento.reason, evento.source, evento.occurred_at) == (
        "mantenimiento",
        "operador",
        T_MANUAL,
    )
    estado = switch.state() or {}
    assert estado["journaled"] is True
    assert estado["reason"] == "mantenimiento"  # marcar como registrado no pisa el resto


def test_observe_de_una_bandera_sin_campos_usa_valores_por_defecto(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = _switch(tmp_path, journal)
    switch.flag_path.parent.mkdir(parents=True)
    switch.flag_path.write_text(json.dumps({"at": "no es una fecha"}), encoding="utf-8")
    assert switch.observe()
    (evento,) = journal.replay()
    assert isinstance(evento, KillSwitchTripped)
    assert (evento.reason, evento.source, evento.occurred_at) == ("", "archivo", T0)


def test_observe_no_registra_dos_veces_una_bandera_ya_registrada(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = _switch(tmp_path, journal)
    switch.trip("manual")
    assert switch.observe()
    assert switch.observe()
    assert len(list(journal.replay())) == 1


def test_el_aviso_de_activo_sale_una_vez_por_activacion(tmp_path: Path) -> None:
    gateway = Gateway()
    switch = KillSwitch(tmp_path / "K", Clock(), InMemoryEventJournal(), gateway)
    switch.trip("prueba")
    with capture_logs() as eventos:
        switch.observe()
        switch.observe()
        assert switch.reset("david")
        assert not switch.observe()  # armado: ningún aviso y no cancela
        switch.trip("otra")
        switch.observe()
    activos = [e for e in eventos if e["event"] == "kill_switch_active"]
    assert [(e["reason"], e["source"], e["log_level"]) for e in activos] == [
        ("prueba", "automatico", "critical"),
        ("otra", "automatico", "critical"),
    ]
    # trip cancela 2 veces y cada observe activado cancela 1 (3): 5 en total.
    assert gateway.cancelled == 5


def test_state_de_contenidos_raros(tmp_path: Path) -> None:
    switch = _switch(tmp_path)
    assert switch.state() is None
    switch.flag_path.parent.mkdir(parents=True)
    switch.flag_path.write_text("[1, 2]", encoding="utf-8")
    assert switch.state() == {"reason": "[1, 2]", "source": "archivo", "journaled": False}
    switch.flag_path.write_text("{roto", encoding="utf-8")
    assert switch.state() == {
        "reason": "archivo bandera sin detalle",
        "source": "archivo",
        "journaled": False,
    }


def test_reset_registra_autor_y_hora_y_borra_el_archivo_apartado(tmp_path: Path) -> None:
    journal = InMemoryEventJournal()
    switch = _switch(tmp_path, journal)
    assert not switch.reset("david")  # armado: no hay nada que rearmar
    switch.trip("prueba")
    assert switch.reset("david")
    assert not switch.active
    assert not switch.flag_path.with_name("KILL_SWITCH.rearmando").exists()
    ultimo = list(journal.replay())[-1]
    assert isinstance(ultimo, KillSwitchReset)
    assert (ultimo.by, ultimo.occurred_at) == ("david", T0)


@pytest.mark.parametrize("autor", ["", "   "])
def test_reset_sin_autor_no_rearma(tmp_path: Path, autor: str) -> None:
    switch = _switch(tmp_path)
    switch.trip("prueba")
    with pytest.raises(ValueError, match="quién"):
        switch.reset(autor)
    assert switch.active


def test_reset_de_un_directorio_bandera_exige_revisarlo_a_mano(tmp_path: Path) -> None:
    switch = _switch(tmp_path)
    switch.flag_path.mkdir(parents=True)
    with pytest.raises(IsADirectoryError):
        switch.reset("david")
    assert switch.active


def test_si_el_diario_falla_al_disparar_la_bandera_queda_sin_registrar(tmp_path: Path) -> None:
    journal = FailingJournal()
    journal.fail = True
    switch = _switch(tmp_path, journal)
    with capture_logs() as eventos:
        assert switch.trip("prueba")
    assert (switch.state() or {})["journaled"] is False
    assert not switch.flag_path.with_name("KILL_SWITCH.tmp").exists()
    assert [e["event"] for e in eventos if e["log_level"] == "critical"] == [
        "kill_switch_tripped",
        "kill_switch_journal_failed",
    ]
