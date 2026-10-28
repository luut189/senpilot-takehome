FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.29
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project \
    && .venv/bin/python -m playwright install --with-deps chromium \
    && useradd --uid 10001 --create-home agent \
    && mkdir -p /data /tmp/senpilot \
    && chown -R agent:agent /data /app /ms-playwright
COPY --chown=agent:agent README.md ./
COPY --chown=agent:agent src ./src
RUN uv sync --frozen --no-dev
USER agent
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "senpilot.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--limit-concurrency", "20"]
