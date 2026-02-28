# ── Build stage: install dependencies ────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools needed by some native dependencies (e.g. neo4j driver)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

LABEL org.opencontainers.image.title="HackForge"
LABEL org.opencontainers.image.description="Autonomous Tool Discovery & Integration Engine"
LABEL org.opencontainers.image.source="https://github.com/your-org/hackforge"

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY hackforge/ ./hackforge/
COPY pyproject.toml ./

# Non-root user for security
RUN useradd -m -u 1000 appuser
USER appuser

# Render injects $PORT at runtime; default to 8000 for local use
ENV PORT=8000
EXPOSE 8000

# Uvicorn with live-reload disabled for production
CMD uvicorn hackforge.api:app \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --workers 1 \
        --log-level info \
        --no-access-log
