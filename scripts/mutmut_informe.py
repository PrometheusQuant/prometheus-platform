"""Informe de mutation testing y gate del mutation score (PQ-99).

Se ejecuta después de `make mutation` (o del job semanal de la CI):

    uv run python scripts/mutmut_informe.py --umbral 80 --salida informe-mutmut.md

Lee los resultados de mutmut y clasifica cada mutante que sobrevive:

- **log:** solo cambia una llamada de log (texto o argumentos). No es comportamiento, así que se
  descuenta del score.
- **texto:** solo cambia el texto del mensaje de una excepción: la línea es un `raise`, construye un
  `...Error(` o es solo un literal (continuación de un mensaje en varias líneas). También se
  descuenta, y el informe lista cada descontado para auditarlo.
- **comportamiento:** todo lo demás. Cada uno se mata con un test o se justifica en
  `docs/metodologia/mutation-testing.md`.

El score ajustado es `muertos / (evaluados - sobrevivientes de log o texto)`. El script sale con
código 1 si queda por debajo del umbral. No modifica nada salvo el archivo de `--salida`.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

# Estados de mutmut 3 que cuentan como detectados por los tests.
MUERTOS = frozenset({"killed", "timeout", "segfault"})
# Estados que no se evaluaron en esta ejecución (filtrados por patrón o sin tests).
NO_EVALUADOS = frozenset({"not checked", "skipped"})
LOG = re.compile(r"\blog\.(debug|info|warning|error|critical|exception)\(")
MENSAJE = re.compile(r"^\s*(raise\s|.*Error\(|[rbfu]{0,2}[\"']).*")
LITERAL = re.compile(r"""(?:[rbfu]{0,2})("([^"\\]|\\.)*"|'([^'\\]|\\.)*')""")


@dataclass(frozen=True)
class Mutante:
    nombre: str
    estado: str

    @property
    def modulo(self) -> str:
        return self.nombre.rsplit(".", 1)[0]

    @property
    def funcion(self) -> str:
        # mutmut nombra «x_<función>» o «xǁ<Clase>ǁ<método>», seguido de «__mutmut_<n>».
        sufijo = self.nombre.rsplit(".", 1)[-1].rsplit("__mutmut_", 1)[0]
        if sufijo.startswith("xǁ"):
            return sufijo.removeprefix("xǁ").replace("ǁ", ".")
        return sufijo.removeprefix("x_")


def leer_resultados(texto: str) -> list[Mutante]:
    """Parsea la salida de `mutmut results --all true` («    nombre: estado»)."""
    mutantes = []
    for linea in texto.splitlines():
        if ": " not in linea or "__mutmut_" not in linea:
            continue
        nombre, estado = linea.strip().rsplit(": ", 1)
        mutantes.append(Mutante(nombre, estado.strip()))
    return mutantes


def _en_llamada_de_log(diff: str) -> bool:
    """Cada línea cambiada es una llamada de log o un argumento de una partida en varias líneas."""
    lineas = [linea for linea in diff.splitlines() if not linea.startswith(("---", "+++", "@@"))]
    cambiadas = [i for i, linea in enumerate(lineas) if linea[:1] in "-+"]
    if not cambiadas:
        return False
    for i in cambiadas:
        if LOG.search(lineas[i]):
            continue
        # Sube por el contexto (sin la otra versión de la línea) mientras la sentencia siga abierta.
        j = i - 1
        while j >= 0 and lineas[j][:1] in "-+":
            j -= 1
        while j >= 0 and lineas[j].rstrip().endswith(("(", ",")) and not LOG.search(lineas[j]):
            j -= 1
        if j < 0 or not LOG.search(lineas[j]) or not lineas[j].rstrip().endswith(("(", ",")):
            return False
    return True


def clasificar(diff: str) -> str:
    """'log', 'texto' o 'comportamiento' según las líneas que cambia el mutante."""
    quitadas = [
        linea[1:]
        for linea in diff.splitlines()
        if linea.startswith("-") and not linea.startswith("---")
    ]
    puestas = [
        linea[1:]
        for linea in diff.splitlines()
        if linea.startswith("+") and not linea.startswith("+++")
    ]
    if not quitadas or not puestas:
        return "comportamiento"
    if _en_llamada_de_log(diff):
        return "log"

    def sin_literales(lineas: list[str]) -> list[str]:
        return [LITERAL.sub('""', linea).strip() for linea in lineas]

    if all(MENSAJE.match(linea) for linea in quitadas + puestas) and sin_literales(
        quitadas
    ) == sin_literales(puestas):
        return "texto"
    return "comportamiento"


@dataclass
class Informe:
    mutantes: list[Mutante]
    clases: dict[str, str]  # sobreviviente → clase

    @property
    def evaluados(self) -> list[Mutante]:
        return [m for m in self.mutantes if m.estado not in NO_EVALUADOS]

    @property
    def muertos(self) -> int:
        return sum(m.estado in MUERTOS for m in self.evaluados)

    @property
    def descontados(self) -> int:
        return sum(clase in {"log", "texto"} for clase in self.clases.values())

    def score(self, *, ajustado: bool) -> float:
        base = len(self.evaluados) - (self.descontados if ajustado else 0)
        return 100.0 * self.muertos / base if base else 100.0

    def markdown(self, umbral: float) -> str:
        estados = Counter(m.estado for m in self.evaluados)
        resumen = ", ".join(f"{k}: {v}" for k, v in sorted(estados.items()))
        ajustado = self.score(ajustado=True)
        lineas = [
            "# Informe de mutation testing",
            "",
            f"- Evaluados: {len(self.evaluados)} ({resumen})",
            f"- Score bruto: {self.score(ajustado=False):.1f} %",
            f"- Score ajustado (sin sobrevivientes de log o texto): **{ajustado:.1f} %**"
            f" (umbral {umbral:.0f} %)",
            "",
            "## Sobrevivientes de comportamiento por módulo y función",
            "",
            "| Módulo | Función | Mutantes |",
            "|---|---|---|",
        ]
        grupos: dict[tuple[str, str], list[str]] = defaultdict(list)
        for mutante in self.evaluados:
            if self.clases.get(mutante.nombre) == "comportamiento":
                grupos[(mutante.modulo, mutante.funcion)].append(mutante.nombre.rsplit("_", 1)[-1])
        for (modulo, funcion), numeros in sorted(grupos.items()):
            lineas.append(f"| `{modulo}` | `{funcion}` | {', '.join(numeros)} |")
        if not grupos:
            lineas.append("| — | — | ninguno |")
        lineas += ["", f"Descontados (log o texto): {self.descontados}.", ""]
        for nombre, clase in sorted(self.clases.items()):
            if clase != "comportamiento":
                lineas.append(f"- {clase}: `{nombre}`")
        return "\n".join(lineas) + "\n"


def _mutmut(*args: str) -> str:
    resultado = subprocess.run(  # noqa: S603 - argumentos fijos, sin entrada del usuario
        [sys.executable, "-m", "mutmut", *args], capture_output=True, text=True, check=True
    )
    return resultado.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--umbral", type=float, default=80.0, help="score ajustado mínimo (%%)")
    parser.add_argument("--salida", type=Path, help="archivo Markdown del informe")
    args = parser.parse_args(argv)

    mutantes = leer_resultados(_mutmut("results", "--all", "true"))
    if not any(m.estado not in NO_EVALUADOS for m in mutantes):
        print("No hay resultados de mutmut: ejecuta antes `make mutation`.", file=sys.stderr)
        return 2
    clases = {
        m.nombre: clasificar(_mutmut("show", m.nombre)) for m in mutantes if m.estado == "survived"
    }
    informe = Informe(mutantes, clases)
    texto = informe.markdown(args.umbral)
    if args.salida:
        args.salida.write_text(texto, encoding="utf-8")
    print(texto)
    if informe.score(ajustado=True) < args.umbral:
        print(f"Score ajustado por debajo del umbral ({args.umbral:.0f} %).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
