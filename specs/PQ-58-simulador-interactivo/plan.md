# Plan de implementación: simulador interactivo y predicción del día

- **Ticket:** PQ-58 · **Fecha:** 2026-11-06 · **Spec:** [spec.md](spec.md)

| | |
|---|---|
| Lógica | `research/what_if.py` (Monte Carlo «¿y si…?») y `research/nowcast.py` (predicción), sin Streamlit |
| Presentación | Dos pestañas nuevas en `api/dashboard/app.py`, con `st.cache_resource` para ajustar una vez |
| Protocolo | `HOLDOUT_END` en `domain/protocol.py`: la predicción exige datos posteriores |
| Rendimiento | Simulación de 2.000 trayectorias: 0,3 s a 1 año y 1 s a 3 años. Entrenamiento: 1,5 s |

| Riesgo | Mitigación |
|---|---|
| Que el jurado lo tome como recomendación | Aviso «no es asesoramiento financiero» en las dos pestañas |
| Datos de hoy ausentes en la feria (sin internet) | Mensaje con el comando; el simulador funciona sin conexión |
