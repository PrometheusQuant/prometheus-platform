"""Métricas del runner de paper trading para Prometheus (PQ-71).

Un *collector* que, en cada consulta a ``/metrics``, lee el diario y el heartbeat con las mismas
funciones que el dashboard y los resúmenes de Telegram (``report.py``): las cifras de Grafana nunca
difieren de las del dashboard. La vista del diario se reconstruye solo cuando el archivo cambia.

El servidor escucha **solo en 127.0.0.1**: Prometheus corre en la misma VM y se llega a Grafana por
túnel SSH (``docs/runbooks/observabilidad.md``).

| Métrica | Tipo | Qué es |
|---|---|---|
| ``pq_paper_equity_usd`` | gauge | Equity de la última valoración |
| ``pq_paper_pnl_usd`` | gauge | Equity menos la de la primera valoración |
| ``pq_paper_drawdown_ratio`` | gauge | Caída desde el máximo de la equity |
| ``pq_paper_exposure_usd{instrument,symbol,leg}`` | gauge | Nocional por pata, a la última marca |
| ``pq_paper_hedge_imbalance_ratio{symbol}`` | gauge | Desbalance spot/perp (``hedge_imbalances``) |
| ``pq_paper_funding_usd`` | gauge | Funding neto acumulado (se cobra o se paga) |
| ``pq_paper_costs_usd_total`` | counter | Comisiones más slippage |
| ``pq_paper_orders_filled_total`` | counter | Órdenes ejecutadas |
| ``pq_paper_order_latency_seconds`` | histogram | De la orden enviada a su fill |
| ``pq_paper_risk_rejections_total{rule}`` | counter | Órdenes rechazadas por el riesgo pre-trade |
| ``pq_paper_heartbeat_timestamp_seconds`` | gauge | Hora del último heartbeat (época Unix) |
| ``pq_paper_heartbeat_ok`` | gauge | 1 si el último ciclo terminó bien |
| ``pq_paper_kill_switch_active`` | gauge | 1 si la bandera global del kill-switch existe |
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from decimal import Decimal
from wsgiref.simple_server import WSGIServer

from prometheus_client import CollectorRegistry, start_http_server
from prometheus_client.core import (
    CounterMetricFamily,
    GaugeMetricFamily,
    HistogramMetricFamily,
    Metric,
)
from prometheus_client.registry import Collector

from prometheus_platform.adapters.jsonl_journal import JsonlEventJournal
from prometheus_platform.api.paper.compose import PaperPaths
from prometheus_platform.api.paper.report import PaperView, build_view, read_heartbeat
from prometheus_platform.domain.events import OrderFilled, OrderSubmitted, RiskLimitBreached
from prometheus_platform.portfolio_risk.risk import Leg, Position, hedge_imbalances
from prometheus_platform.strategies.carry import is_perp, symbol_of

LATENCY_BUCKETS = (0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 300.0)
LOOPBACK = "127.0.0.1"


class PaperCollector(Collector):
    def __init__(self, paths: PaperPaths) -> None:
        self._paths = paths
        self._stamp: tuple[int, int] | None = None
        self._view = PaperView()
        self._latencies: list[float] = []
        self._rejections: Counter[str] = Counter()

    def _journal_stamp(self) -> tuple[int, int] | None:
        try:
            stat = self._paths.journal.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def _rebuild(self) -> None:
        events = (
            list(JsonlEventJournal(self._paths.journal).replay())
            if self._paths.journal.exists()
            else []
        )
        self._view = build_view(events)
        submitted = {e.client_order_id: e for e in events if isinstance(e, OrderSubmitted)}
        self._latencies = [
            (e.occurred_at - submitted[e.client_order_id].occurred_at).total_seconds()
            for e in events
            if isinstance(e, OrderFilled) and e.client_order_id in submitted
        ]
        self._rejections = Counter(e.rule for e in events if isinstance(e, RiskLimitBreached))

    def collect(self) -> Iterator[Metric]:
        stamp = self._journal_stamp()
        if stamp != self._stamp or self._stamp is None:
            self._rebuild()
            self._stamp = stamp
        yield from self._portfolio()
        yield from self._orders()
        yield from self._runner_state()

    def _portfolio(self) -> Iterator[Metric]:
        view = self._view
        if view.equity is not None and view.initial_equity is not None:
            yield _gauge("pq_paper_equity_usd", "Equity de la última valoración", view.equity)
            yield _gauge(
                "pq_paper_pnl_usd", "Equity menos la inicial", view.equity - view.initial_equity
            )
            yield _gauge("pq_paper_drawdown_ratio", "Caída desde el máximo", view.drawdown)
        yield _gauge("pq_paper_funding_usd", "Funding neto acumulado", view.funding)
        costs = CounterMetricFamily("pq_paper_costs_usd", "Comisiones más slippage")
        costs.add_metric([], float(view.costs))
        yield costs

        exposure = GaugeMetricFamily(
            "pq_paper_exposure_usd",
            "Nocional abierto por pata a la última marca",
            labels=["instrument", "symbol", "leg"],
        )
        positions = []
        for instrument, quantity in sorted(view.positions.items(), key=lambda kv: str(kv[0])):
            mark = view.marks.get(instrument)
            if mark is None or mark <= 0:
                continue  # sin marca no se valora: no se inventa un precio
            leg = Leg.PERP if is_perp(instrument) else Leg.SPOT
            symbol = symbol_of(instrument)
            exposure.add_metric([str(instrument), symbol, leg.value], float(abs(quantity) * mark))
            positions.append(Position(instrument, symbol, leg, quantity, mark))
        yield exposure
        imbalance = GaugeMetricFamily(
            "pq_paper_hedge_imbalance_ratio",
            "Desbalance de la cobertura spot/perp",
            labels=["symbol"],
        )
        for symbol, value in sorted(hedge_imbalances(positions).items()):
            imbalance.add_metric([symbol], float(value))
        yield imbalance

    def _orders(self) -> Iterator[Metric]:
        filled = CounterMetricFamily("pq_paper_orders_filled", "Órdenes ejecutadas")
        filled.add_metric([], len(self._view.fills))
        yield filled
        buckets, count = [], 0
        for bound in LATENCY_BUCKETS:
            count = sum(1 for latency in self._latencies if latency <= bound)
            buckets.append((str(bound), count))
        buckets.append(("+Inf", len(self._latencies)))
        yield HistogramMetricFamily(
            "pq_paper_order_latency_seconds",
            "De la orden enviada a su fill",
            buckets=buckets,
            sum_value=sum(self._latencies),
        )
        rejected = CounterMetricFamily(
            "pq_paper_risk_rejections", "Órdenes rechazadas por el riesgo", labels=["rule"]
        )
        for rule, n in sorted(self._rejections.items()):
            rejected.add_metric([rule], n)
        yield rejected

    def _runner_state(self) -> Iterator[Metric]:
        beat = read_heartbeat(self._paths.heartbeat)
        if beat is not None:
            yield _gauge(
                "pq_paper_heartbeat_timestamp_seconds",
                "Hora del último heartbeat",
                Decimal(str(beat["at"].timestamp())),
            )
        ok = beat is not None and bool(beat.get("ok"))
        yield _gauge("pq_paper_heartbeat_ok", "1 si el último ciclo terminó bien", Decimal(ok))
        active = Decimal(self._paths.kill_switch.exists())
        yield _gauge(
            "pq_paper_kill_switch_active", "1 si el kill-switch global está activo", active
        )


def _gauge(name: str, documentation: str, value: Decimal) -> GaugeMetricFamily:
    return GaugeMetricFamily(name, documentation, value=float(value))


def serve_metrics(paths: PaperPaths, port: int) -> WSGIServer:
    """Sirve ``/metrics`` en 127.0.0.1:``port`` en un hilo aparte. Devuelve el servidor."""
    registry = CollectorRegistry()
    registry.register(PaperCollector(paths))
    server, _thread = start_http_server(port, addr=LOOPBACK, registry=registry)
    return server
