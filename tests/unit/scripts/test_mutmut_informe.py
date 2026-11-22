"""Pruebas de scripts/mutmut_informe.py (PQ-99): clasificación de sobrevivientes y score."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).parents[3] / "scripts" / "mutmut_informe.py"


@pytest.fixture(scope="module")
def informe() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutmut_informe", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


RESULTADOS = """\
    prometheus_platform.portfolio_risk.kill_switch.x_enforce__mutmut_1: killed
    prometheus_platform.portfolio_risk.kill_switch.x_enforce__mutmut_2: survived
    prometheus_platform.portfolio_risk.kill_switch.xǁKillSwitchǁ_cancel_all__mutmut_3: survived
    prometheus_platform.portfolio_risk.risk.x_check__mutmut_4: timeout
    prometheus_platform.data_platform.gold.x_build_tables__mutmut_9: not checked
ruido sin formato
"""


def _diff(antes: str, despues: str) -> str:
    return f"--- a.py\n+++ a.py\n@@ -1 +1 @@\n-{antes}\n+{despues}\n"


def test_lee_nombres_estados_modulo_y_funcion(informe: ModuleType) -> None:
    mutantes = informe.leer_resultados(RESULTADOS)
    assert [m.estado for m in mutantes] == [
        "killed",
        "survived",
        "survived",
        "timeout",
        "not checked",
    ]
    assert mutantes[0].modulo == "prometheus_platform.portfolio_risk.kill_switch"
    assert mutantes[0].funcion == "enforce"
    assert mutantes[2].funcion == "KillSwitch._cancel_all"


@pytest.mark.parametrize(
    ("antes", "despues", "clase"),
    [
        ('log.critical("cancel_failed", error=e)', "log.critical(None, error=e)", "log"),
        (
            'raise ValueError(f"tope {x} superado")',
            'raise ValueError(f"XXtope {x} superadoXX")',
            "texto",
        ),
        ("if exposure > limit:", "if exposure >= limit:", "comportamiento"),
        ('raise ValueError("a")', 'raise TypeError("a")', "comportamiento"),
        # Un literal que no es mensaje de error sí es comportamiento (nombres de reglas, niveles).
        ('rule = "max_leverage"', 'rule = "MAX_LEVERAGE"', "comportamiento"),
        (
            '                f"{name}: clave {key} con nulos"',
            '                f"XX{name}: clave {key} con nulosXX"',
            "texto",
        ),
    ],
)
def test_clasifica_el_cambio(informe: ModuleType, antes: str, despues: str, clase: str) -> None:
    assert informe.clasificar(_diff(antes, despues)) == clase


def test_un_diff_vacio_cuenta_como_comportamiento(informe: ModuleType) -> None:
    assert informe.clasificar("") == "comportamiento"


def test_score_bruto_y_ajustado_ignoran_los_no_evaluados(informe: ModuleType) -> None:
    mutantes = informe.leer_resultados(RESULTADOS)
    nombres = [m.nombre for m in mutantes if m.estado == "survived"]
    resultado = informe.Informe(mutantes, {nombres[0]: "comportamiento", nombres[1]: "log"})
    # 4 evaluados: 2 detectados (killed y timeout), 2 sobrevivientes, 1 de ellos de log.
    assert len(resultado.evaluados) == 4
    assert resultado.score(ajustado=False) == pytest.approx(50.0)
    assert resultado.score(ajustado=True) == pytest.approx(100 * 2 / 3)
    texto = resultado.markdown(umbral=80)
    assert "Score ajustado (sin sobrevivientes de log o texto): **66.7 %**" in texto
    assert "| `prometheus_platform.portfolio_risk.kill_switch` | `enforce` | 2 |" in texto
    assert "Descontados (log o texto): 1." in texto
    assert f"- log: `{nombres[1]}`" in texto


def test_un_argumento_de_un_log_en_varias_lineas_es_log(informe: ModuleType) -> None:
    diff = (
        "--- a.py\n+++ a.py\n@@ -1,3 +1,3 @@\n"
        "         log.critical(\n"
        '-            "kill_switch_active", reason=state.get("reason")\n'
        '+            "kill_switch_active", reason=None\n'
        "         )\n"
    )
    assert informe.clasificar(diff) == "log"


def test_un_argumento_de_otra_llamada_en_varias_lineas_es_comportamiento(
    informe: ModuleType,
) -> None:
    diff = (
        "--- a.py\n+++ a.py\n@@ -1,3 +1,3 @@\n"
        "         self._journal_trip(\n"
        '-            str(state.get("reason", "")), at\n'
        "+            None, at\n"
        "         )\n"
    )
    assert informe.clasificar(diff) == "comportamiento"
