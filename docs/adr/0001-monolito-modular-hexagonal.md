# ADR-0001: Monolito modular con arquitectura hexagonal

- **Estado:** Aceptada
- **Fecha:** 2026-10-16

## Contexto y problema

Dos desarrolladores construyen una plataforma multiestrategia que debe crecer durante años.
La máquina de desarrollo tiene ~5,7 GB de RAM y el presupuesto inicial es 0–20 USD/mes.
El sistema necesita paridad entre backtest, paper y vivo, y una auditoría completa de decisiones.

## Opciones consideradas

1. Microservicios comunicados por un broker (Kafka/NATS).
2. Monolito sin límites internos.
3. **Monolito modular con puertos y adaptadores (hexagonal).**

## Decisión

Opción 3. Fowler documenta que casi todos los sistemas de microservicios exitosos empezaron como
monolito y que los límites correctos se descubren con el tiempo (*MonolithFirst*); Shopify sostiene
su núcleo como monolito modular. Para dos personas, los microservicios añaden red, serialización y
operación sin un beneficio que lo justifique.

- **Dominio** (`domain`): value objects, eventos y puertos (`typing.Protocol`). Solo librería estándar.
- **Aplicación**: `strategies`, `portfolio_risk`, `execution`, `data_platform`, `research`.
- **Adaptadores** (`adapters`): Binance, paper, persistencia. Intercambiables.
- **Entrada y operación**: `api`, `ops`.
- **Journal append-only** de eventos (señal, orden, fill, riesgo) para auditoría y *replay*.
- **CQRS** solo para vistas de lectura del dashboard.

Los límites se verifican en CI con `import-linter`: un import que viole la arquitectura rompe el build.

## Consecuencias

- Positivas: un solo despliegue; las estrategias se prueban sin exchange; añadir un venue es
  escribir un adaptador (OCP).
- Negativas: hay que mantener la disciplina de los contratos.
- Qué la revertiría: un módulo que necesite escalar o desplegarse por separado (p. ej. un nodo
  de ejecución cerca del exchange). Entonces se extrae ese módulo detrás de NATS JetStream.
