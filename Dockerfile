# Stage 1: builder
FROM python:3.12-slim AS builder
WORKDIR /build

# Install build dependencies for psycopg2, cryptography
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency spec FIRST (cache layer — only re-runs if pyproject.toml changes)
COPY pyproject.toml .

# Create virtual environment and install runtime deps only (no [dev] extras)
RUN python -m venv /venv && \
    /venv/bin/pip install --no-cache-dir --upgrade pip && \
    /venv/bin/pip install --no-cache-dir .

# Stage 2: runtime — minimal image
FROM python:3.12-slim AS runtime

# Install tini for proper signal handling (PID 1 problem)
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user (uid 999)
RUN groupadd -g 999 lablink && useradd -r -u 999 -g lablink lablink

WORKDIR /app

# Copy venv from builder (only runtime packages, no build tools)
COPY --from=builder /venv /venv

# Copy application source
COPY --chown=lablink:lablink src/ src/

USER lablink

ENV PATH="/venv/bin:$PATH" \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "lablink.main:create_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
