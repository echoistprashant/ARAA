# ==============================================================================
# Multi-Stage Production Dockerfile for ARAA (Autonomous Research & Analysis Agent)
# Zero-Cost, Minimal Attack Surface, Unprivileged Non-Root Runtime
# ==============================================================================

# Stage 1: Build Dependencies
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Minimal Production Image
FROM python:3.12-slim AS runner

WORKDIR /app

# Create unprivileged system user
RUN groupadd -g 10001 araagroup && \
    useradd -u 10001 -g araagroup -s /bin/sh -m araauser

# Copy installed site-packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=araauser:araagroup app/ /app/app/
COPY --chown=araauser:araagroup pyproject.toml /app/

USER araauser

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
