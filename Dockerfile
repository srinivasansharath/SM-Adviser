# SM-Adviser backend image — Python 3.12, all runtime extras.
# One image serves two roles (see docker-compose.yml):
#   - api          : long-running uvicorn serving widget.json/report to the iOS widget
#   - morning-run  : the daily orchestrator, invoked on a schedule via `compose run`
FROM python:3.12-slim

# curl for the container healthcheck; no build toolchain needed (all deps ship wheels).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# Install dependencies from the package metadata first for layer caching.
# The source is bind-mounted over /app at runtime (see compose), so the editable
# install + PYTHONPATH=/app both resolve to the live code.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --upgrade pip \
    && pip install -e ".[connectors,analytics,marketdata,fundamentals,api,llm,postgres]"

EXPOSE 8787

# Default role is the API; the morning-run service overrides this command.
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8787"]
