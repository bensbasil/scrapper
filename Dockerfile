# ==============================================================================
# Production Dockerfile for Business Opportunity Intelligence Platform API
# Python 3.11 / FastAPI / Non-root execution
# ==============================================================================

FROM python:3.11-slim AS runtime

# Configure Python execution behavior for container environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

# Install curl for container HEALTHCHECK
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Create dedicated non-root application user and group
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy dependency lockfile and install pinned wheels as root into system environment
COPY requirements.lock /app/requirements.lock
RUN pip install -r /app/requirements.lock

# Copy application source code (secrets, caches, tests excluded by .dockerignore)
COPY --chown=appuser:appgroup . /app

# Ensure runtime directories exist and have appuser permissions
RUN mkdir -p /app/logs /app/data && chown -R appuser:appgroup /app/logs /app/data

# Switch to unprivileged non-root user
USER appuser

EXPOSE 8000

# Health check probe against unauthenticated public liveness endpoint (Phase 5E)
# Docker monitors process liveness to prevent cascading restarts during remote DB outages.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/live || exit 1

# Production server startup command
# Runs uvicorn bound to 0.0.0.0 inside the container
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]
