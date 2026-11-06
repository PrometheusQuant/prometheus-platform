# Dashboard de PrometheusQuant (PQ-34). Solo lectura: los datos se montan en /data.
#   docker compose up --build   ->   http://127.0.0.1:8501
FROM python:3.12-slim-bookworm AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
# Primero solo las dependencias, para aprovechar la caché de capas.
COPY pyproject.toml uv.lock README.md LICENSE NOTICE ./
RUN uv sync --frozen --no-default-groups --group dashboard --no-install-project
COPY src ./src
RUN uv sync --frozen --no-default-groups --group dashboard --no-editable

FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 10001 pq
COPY --from=build --chown=pq:pq /app/.venv /app/.venv
COPY --chown=pq:pq src/prometheus_platform/api/dashboard/app.py /app/app.py
ENV PATH="/app/.venv/bin:$PATH" \
    PQ_ENVIRONMENT=dev \
    PQ_DATA_DIR=/data \
    HOME=/tmp \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true
USER pq
WORKDIR /app
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=4)"]
CMD ["streamlit", "run", "/app/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
