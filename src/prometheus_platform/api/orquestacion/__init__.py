"""Orquestación del lakehouse con Dagster (PQ-22, ADR-0010).

Es un punto de entrada, como la CLI y el dashboard: envuelve funciones puras de ``data_platform``
y nada de la plataforma depende de él (contrato de import-linter «Solo api.orquestacion importa
Dagster»). El trading en vivo nunca pasa por aquí.
"""
