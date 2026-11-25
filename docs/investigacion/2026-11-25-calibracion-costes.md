# Calibración de costes con fills reales en Binance Demo

- **Ticket:** PQ-95 · **Carril:** David · **Agentes:** Claude A (diseño y primer código) y Claude B
  (lo terminó)
- **Fecha del muestreo:** 2026-11-25, de 12:26 a 12:28 UTC, 42 órdenes
- **Reproducible con:** `uv run pq paper muestreo-costes` y luego `uv run pq paper costes`
  (runbook de paper trading)

## Conclusión

**Lo medido no es peor que lo que suponen los backtests**, ni en slippage ni en comisión. **No
corresponde ninguna enmienda de costes.** El muestreo se hizo en Binance Demo, cuyo libro tiene
otra liquidez que el real: es una cota orientativa, no una calibración definitiva.

## Qué se midió

El runner de Binance Demo (PQ-52) todavía no ha operado: con el funding bajo, el carry H2 sigue
fuera. Por eso se hicieron **idas y vueltas pequeñas** de 250 USDT por orden, en spot (compra y
venta) y en el perpetuo (venta y recompra). Se registraron en un diario propio
(`data/paper-binance-demo/muestreo-costes.jsonl`), separado del del runner.

- **Símbolos:** BTC y ETH (supuesto de 2 pb) y DOGE (supuesto de 5 pb, el de las altcoins). **No**
  se usaron SOL, BNB ni XRP: los opera el runner en la misma cuenta, y una posición abierta a mitad
  de su ciclo le descuadraría la conciliación. El comando los rechaza.
- **Slippage:** frente al punto medio del libro justo antes de cada orden. Incluye medio spread
  más el impacto, con signo, y un valor positivo es coste.
- **Comisión:** la que cobró el exchange, en USDT, como fracción del nocional.
- **Comprobación:** al terminar, ninguna posición de perpetuo quedó abierta y el runner de Demo
  siguió sano.

## Resultado

| Pata | Supuesto de slippage | Órdenes | Slippage mediano | Medio | p90 | Comisión medida | Comisión supuesta |
|---|---|---|---|---|---|---|---|
| Spot | 2 pb (BTC, ETH) | 16 | 0,00 pb | 0,07 pb | 0,18 pb | 0,100 % | 0,100 % |
| Spot | 5 pb (DOGE) | 6 | 0,93 pb | 0,93 pb | 0,93 pb | 0,100 % | 0,100 % |
| Perpetuo | 2 pb (BTC, ETH) | 14 | 0,58 pb | 1,26 pb | 3,66 pb | 0,040 % | 0,050 % |
| Perpetuo | 5 pb (DOGE) | 6 | 0,93 pb | 0,93 pb | 0,93 pb | 0,040 % | 0,050 % |

- **El slippage queda por debajo del supuesto en las cuatro filas.** El peor caso es el p90 del
  perpetuo de BTC y ETH, con 3,66 pb, frente a 2 pb supuestos: hay órdenes peores que el supuesto,
  pero la mediana (0,58 pb) y la media (1,26 pb) quedan dentro.
- **DOGE da siempre 0,93 pb.** Es medio tick: con un precio de unos 0,10 USDT, el paso mínimo de
  precio ya equivale a casi 2 pb de spread.
- **La comisión spot medida es 0,10005 %**, y no 0,1 % exacto, porque se cobra en el activo
  comprado y se convierte a USDT al precio del fill. La regla de «peor» tolera un 1 % relativo
  por ese redondeo.
- **La comisión del perpetuo en Demo es 0,040 %**, menor que el 0,050 % taker VIP0 que suponen los
  backtests. Que Demo cobre lo mismo que la cuenta real está por verificar: no se usa para
  rebajar el supuesto.

## Límites

- **Liquidez de Demo.** El libro de Binance Demo no es el real. El slippage de la cuenta real puede
  ser mayor, sobre todo en tamaños grandes o en momentos de estrés.
- **Muestra pequeña.** Son 42 órdenes en dos minutos, de 250 USDT cada una. No mide el impacto de
  órdenes grandes ni la variación a lo largo del día.
- **Las altcoins del runner no se midieron.** SOL, BNB y XRP solo se pueden medir con los fills del
  propio runner, cuando el carry entre, o con el runner de Demo detenido
  (`--incluir-simbolos-del-runner`).

## Qué sigue

`pq paper costes` mide también el diario del runner de Demo. Cuando el carry opere, conviene
repetirlo con esos fills, que son los que importan. Si entonces lo medido supera lo supuesto, se
abre un ticket de enmienda para los backtests siguientes, sin tocar los ya evaluados. El dashboard
muestra estas cifras en la página del paper, en «Costes reales frente a los supuestos».
