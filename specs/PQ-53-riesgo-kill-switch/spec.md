# Especificación: gestión de riesgo pre-trade y kill-switch

- **Ticket:** PQ-53 (5 puntos) · **Rama:** `feature/PQ-53-riesgo-kill-switch` · **Fecha:** 2026-11-06 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** historia PQ-53; gate de la fase 5 de CRISP-ML(Q): «kill-switch probado»
  ([DoD](../../docs/metodologia/definicion-de-listo-y-terminado.md))

## Escenarios de usuario y pruebas

### Historia 1: ninguna orden sale sin pasar los límites (P1)

Como operador, quiero que toda orden propuesta por una estrategia pase por los límites de riesgo
para que un error de software no se convierta en pérdida.

1. **Dada** una orden que dejaría el nocional de un símbolo por encima del límite, **cuando** se
   evalúa, **entonces** se rechaza con la regla que la bloqueó y queda un `RiskLimitBreached` en el
   diario.
2. **Dada** una orden que **reduce** la exposición, **cuando** se evalúa, **entonces** se acepta
   aunque se esté por encima de un límite. Es la forma de volver dentro de los límites.
3. **Dados** los límites de nocional por símbolo, nocional total y apalancamiento, **cuando** una
   orden los excede después de ejecutarse, **entonces** se rechaza **antes** de enviarse.

### Historia 2: el kill-switch detiene todo y no se rearma solo (P1)

1. **Dada** una pérdida diaria mayor que el límite, una pata sin cubrir más allá de la tolerancia o
   un apalancamiento por encima del tope duro, **cuando** el monitor evalúa la cartera, **entonces**
   se activa el kill-switch automáticamente.
2. **Dado** el kill-switch activado, por cualquiera de sus tres vías (automática, CLI o archivo
   bandera), **entonces** ocurre lo siguiente:
   - se cancelan las órdenes abiertas;
   - se rechaza toda orden que aumente la exposición;
   - se proponen las órdenes de cierre;
   - queda un `KillSwitchTripped` en el diario;
   - sale una alerta CRITICAL.
3. **Dado** un reinicio del proceso con el kill-switch activado, **cuando** arranca, **entonces**
   sigue activado. Solo se rearma con `pq paper kill --reset --confirm`, que deja un
   `KillSwitchReset` con el autor.

### Casos límite

- La orden de cierre de una pata cuando la otra ya está cerrada siempre se permite.
- Si la equity es 0 o negativa, el apalancamiento se trata como infinito y se activa el kill-switch.
- Los límites inválidos (negativos, apalancamiento > 2) hacen fallar el arranque, como el resto de
  la configuración.

## Requisitos

- **FR-001** Límites configurables en `Settings` (`PQ_RISK_*`), validados al arrancar:
  - nocional máximo por símbolo y total (USD);
  - apalancamiento máximo (por defecto 1x) y tope duro;
  - pérdida diaria máxima;
  - desbalance máximo entre las patas.
- **FR-002** `RiskManager.pre_trade` es una función pura de (orden, cartera, límites, kill-switch).
  Devuelve la decisión y la regla.
- **FR-003** `RiskManager.monitor` evalúa la cartera y devuelve las violaciones. Las graves activan
  el kill-switch.
- **FR-004** El kill-switch persiste en un archivo bandera, que sobrevive a reinicios, y registra
  los eventos de dominio.
- **FR-005** CLI `pq paper kill`, `pq paper kill --reset --confirm` y `pq paper status`.
- **FR-006** `portfolio_risk` no importa `strategies` ni `execution` (contrato de independencia).

## Criterios de éxito

- Cada límite y cada vía del kill-switch con su prueba. El simulacro está documentado en el runbook.
- Cobertura ≥ 80 % y los contratos de arquitectura intactos.
