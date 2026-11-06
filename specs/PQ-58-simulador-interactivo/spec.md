# Especificación: simulador interactivo y predicción del día (cap. 7.3)

- **Ticket:** PQ-58 (5 puntos) · **Rama:** `feature/PQ-58-simulador-interactivo` · **Fecha:** 2026-11-06 · **Estado:** aprobada
- **Formato:** plantilla `spec-template.md` de Spec Kit, adaptada (ADR-0008)
- **Entrada:** ítem 7.3, que pide una «interfaz gráfica consumiendo el algoritmo para que el usuario o jurado pueda interactuar con él»

## Escenarios

### Historia 1: el jurado simula su propia inversión (P1)

1. **Dado** el dashboard, **cuando** el jurado elige capital, horizonte (1 o 3 años), probabilidad
   anual de quiebra y θ, **entonces** en menos de 3 segundos ve:
   - el capital final mediano frente a la stablecoin al 4 %;
   - P(pérdida) y P(ganarle a la stablecoin);
   - la distribución y el CVaR.
2. **Dado** el control de θ, **entonces** solo ofrece los umbrales pre-registrados (10, 20 y 30 %).
   Un control libre invitaría a optimizar en vivo, que es justo lo que el protocolo prohíbe.

### Historia 2: el modelo «consume» datos de hoy (P1)

1. **Dados** datos posteriores al fin del holdout (ingesta de la API, PQ-65), **cuando** se abre
   «¿Qué predice hoy?», **entonces** muestra por símbolo la última liquidación, el funding actual y
   P(funding ≥ 20 %), con el clasificador del cap. 5 entrenado solo con el desarrollo.
2. **Dados** datos que no pasan del fin del holdout, **entonces** no predice y explica cómo traer
   los datos de hoy: predecir sobre fechas del holdout sería mirarlo.

### Casos límite

- Sin silver, o sin el artefacto del modelo: aviso con el comando que lo genera, nunca una excepción.
- Un símbolo con el dato viejo y otros con datos de hoy: solo se predicen los de hoy.

## Requisitos

- **FR-001** El simulador reutiliza el modelo v3 del cap. 6 (bloques de 21 días, solo desarrollo)
  sin cambiarlo. Nada de lo que se hace en él es un ensayo ni suma a N.
- **FR-002** La predicción usa los hiperparámetros del artefacto del estudio; no se reajustan.
- **FR-003** `AppTest`, Playwright (6 pestañas) y tests unitarios con datos sintéticos.
