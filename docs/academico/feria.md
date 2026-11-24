# Feria: póster y video de la demo (PQ-77)

## Póster A3

[**Descargar el póster (PDF, A3)**](poster-feria.pdf)

Una página con:

- el problema y el protocolo como respuesta;
- la evidencia: H1 y H2 contra sus benchmarks, el exceso sobre el 4 % y el holdout cerrado;
- el riesgo de quiebra del exchange;
- la arquitectura y lo que sigue;
- un QR a la [página de resultados](../resultados.md).

**Ninguna cifra va a mano:** sale de los mismos artefactos que el informe final y la página
pública. Se regenera con:

```bash
make poster      # pq report inputs + Typst → docs/academico/poster-feria.pdf
```

Fuente: `reports/poster/poster.typ`. El QR (`reports/poster/qr-resultados.svg`) apunta a
`https://prometheusquant.github.io/prometheus-platform/resultados/`.

**Para imprimir:** A3 vertical, a color, sin escalar («tamaño real»). Antes de imprimir, comprueba
con el celular que el QR abre la página.

## Video de la demo (2 a 3 minutos)

Es el **plan B** si en la feria falla internet o el dashboard: se reproduce desde la laptop, sin
red. Se graba con la demo real: el runner, el vigilante y el dashboard corriendo, y el celular con
el grupo de Telegram.

**Cómo grabarlo:**

- **Pantalla:** en Windows, `Win + Alt + R` (Xbox Game Bar) graba la ventana del navegador; o
  `Win + Shift + S` → *Grabar*.
- **Celular:** su grabador de pantalla, para la parte de Telegram. Después se unen los dos clips.
- **Navegador:** abre el dashboard en <http://localhost:8501/?modo=feria>, para que la letra se lea
  en la pantalla grande.

| Tiempo | Toma | Qué se ve | Qué se dice |
|---|---|---|---|
| 0:00–0:15 | 1 | Título del tablero en modo feria | «PrometheusQuant cobra el funding de los perpetuos sin apostar al precio, y solo opera lo que pasa un protocolo contra el sobreajuste.» |
| 0:15–0:40 | 2 | «¿Funciona? Carry y gates»: H1 y H2 | «H1 parecía rentable, pero no le ganaba a estar siempre invertido: la descartamos. H2 pasa los cuatro gates.» |
| 0:40–1:00 | 3 | «¿Qué riesgo hay? Simulación» | «El riesgo que manda es que quiebre el exchange: con ese número calibramos el límite de capital.» |
| 1:00–1:30 | 4 | «¿Cómo va en vivo?»: equity, posiciones y último latido | «Esto corre ahora mismo: dinero simulado sobre precios reales de Binance, con un ciclo por minuto.» |
| 1:30–1:50 | 5 | «¿Qué predice hoy?» y «¿Y si invierto?» con un monto | «El modelo dice qué tan probable es un funding alto hoy; y cualquiera puede simular su inversión.» |
| 1:50–2:30 | 6 | Celular: `/estado`, después `/kill` con su código, y la alerta en el grupo | «Desde el celular vemos el estado y, si algo va mal, detenemos todo: el bot pide un código para que un toque accidental no lo active.» |
| 2:30–2:45 | 7 | Dashboard: el kill-switch activado | «El kill-switch quedó activado; rearmarlo exige la terminal y un nombre.» |
| 2:45–3:00 | 8 | Póster o página de resultados con el QR | «Los resultados están en esta página, actualizados. No prometemos rentabilidad: prometemos no engañarnos.» |

**Después de grabar:** rearma el kill-switch con
`uv run pq paper kill --reset --confirm --by <nombre>` y comprueba con `/estado` que quedó
*ARMADO*.

**Dónde guardarlo:** el archivo de video **no va en git** (pesa demasiado). Súbelo a la carpeta
compartida del equipo y pon el enlace en esta página, en lugar de esta línea.
