"""Fechas del protocolo pre-registrado del carry (`docs/estrategias/01-carry/pre-registro.md` §7).

Viven en ``domain`` porque varias capas deben respetarlas: research no simula después del fin del
desarrollo y gold no expone ningún hecho del holdout mientras siga cerrado.
"""

from __future__ import annotations

from datetime import UTC, datetime

DEV_END = datetime(2024, 6, 30, 23, 59, 59, tzinfo=UTC)  # fin del periodo de desarrollo
HOLDOUT_START = datetime(2024, 7, 1, tzinfo=UTC)  # un solo uso (pre-registro §7, enmienda 1.11)
