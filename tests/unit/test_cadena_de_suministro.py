"""Coherencia entre las piezas de la cadena de suministro (PQ-81).

La firma, la verificación y el cifrado viven en archivos distintos (workflow, script de la VM y
`.sops.yaml`). Si uno cambia de nombre o de ruta sin los otros, la VM rechazaría toda imagen o
sops no encontraría su regla: estas pruebas lo detectan antes de desplegar.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
WORKFLOW = RAIZ / ".github/workflows/imagen.yml"
VERIFICAR = RAIZ / "deploy/verificar-imagen.sh"
SECRETOS = RAIZ / "deploy/secretos.sh"
SOPS = RAIZ / ".sops.yaml"


def _identidad() -> re.Pattern[str]:
    patron = re.search(r"^identidad='([^']+)'$", VERIFICAR.read_text(), re.MULTILINE)
    assert patron, "verificar-imagen.sh debe declarar identidad='...'"
    return re.compile(patron.group(1))


def test_la_identidad_acepta_solo_el_workflow_de_imagen_en_develop_o_main() -> None:
    identidad = _identidad()
    base = "https://github.com/PrometheusQuant/prometheus-platform/.github/workflows/"
    assert WORKFLOW.exists()
    assert identidad.match(f"{base}{WORKFLOW.name}@refs/heads/develop")
    assert identidad.match(f"{base}{WORKFLOW.name}@refs/heads/main")
    # Ni otras ramas (un PR), ni otros workflows del repo, ni forks.
    assert not identidad.match(f"{base}{WORKFLOW.name}@refs/heads/feature/PQ-1-x")
    assert not identidad.match(f"{base}ci.yml@refs/heads/develop")
    assert not identidad.match(
        "https://github.com/otro/prometheus-platform/.github/workflows/imagen.yml@refs/heads/main"
    )


def test_el_workflow_firma_y_verifica_con_el_mismo_script() -> None:
    texto = WORKFLOW.read_text()
    assert "id-token: write" in texto
    assert "cosign sign --yes" in texto
    assert "--type cyclonedx" in texto
    assert "deploy/verificar-imagen.sh" in texto
    # En el workflow solo se firma lo publicado desde develop o main.
    ramas = re.search(r"push:\n\s+branches: \[([^\]]+)\]", texto)
    assert ramas
    assert {r.strip() for r in ramas.group(1).split(",")} == {"develop", "main"}


def test_sops_cifra_el_archivo_que_usa_el_script_solo_para_claves_age_publicas() -> None:
    config = SOPS.read_text()
    assert "AGE-SECRET-KEY" not in config.upper()
    regla = re.search(r"path_regex: (\S+)", config)
    destinatarios = re.search(r"^\s+age: (\S+)$", config, re.MULTILINE)
    cifrado = re.search(r"^cifrado=(\S+)$", SECRETOS.read_text(), re.MULTILINE)
    assert regla
    assert destinatarios
    assert cifrado
    assert re.match(regla.group(1), cifrado.group(1))
    for clave in destinatarios.group(1).split(","):
        assert re.fullmatch(r"age1[02-9ac-hj-np-z]{58}", clave), clave
