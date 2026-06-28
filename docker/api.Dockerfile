# Backend image: installs the coruscant package and serves the API / runs ingestion.
# Build context is the repository root.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CORUSCANT_DATA_DIR=/data \
    CORUSCANT_DATABASE_URL=sqlite:////data/coruscant.db \
    CORUSCANT_CONFIG_DIR=/app/config

WORKDIR /app

# Install dependencies first (better layer caching), then the package itself.
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install .

# Runtime configuration the app reads at startup.
COPY config ./config

# Non-root runtime user; /data is a mounted volume for ingested artifacts.
RUN useradd --create-home --uid 1000 coruscant \
    && mkdir -p /data \
    && chown -R coruscant:coruscant /app /data
USER coruscant

EXPOSE 8000

# Default: serve the API. The compose `ingest` service overrides this command.
CMD ["uvicorn", "coruscant.apps.api:app", "--host", "0.0.0.0", "--port", "8000"]
