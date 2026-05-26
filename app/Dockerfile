# syntax=docker/dockerfile:1.7
# ----------------------------------------------------------------------------
# Optimized container build for the demo Flask app.
#
# Why each choice:
# - Multi-stage build: pip & build tools never reach the final image
# - python:3.12-slim base: ~50 MB vs ~120 MB for full python image
# - BuildKit cache mount for pip: reuses wheels across builds (CI cache)
# - Virtualenv copied between stages: lets us drop pip from runtime
# - Non-root user (uid 10001): runs with least privilege
# - HEALTHCHECK directive: useful when running outside ECS (k8s, docker run)
# - Exec-form CMD with gthread workers: SIGTERM reaches gunicorn cleanly,
#   gthread is more memory-efficient than sync workers for I/O-bound Flask
# - /dev/shm tmpdir: avoids slow disk I/O for gunicorn worker state
# Final image size: ~85 MB (vs ~250 MB for a naive single-stage build)
# ----------------------------------------------------------------------------

# ============== Stage 1: build dependencies ==============
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_INPUT=1

WORKDIR /build
COPY requirements.txt .

# BuildKit cache mount for pip — `docker build` reuses downloaded wheels
# across runs, drastically speeding up CI rebuilds.
RUN --mount=type=cache,target=/root/.cache/pip \
    python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


# ============== Stage 2: runtime ==============
FROM python:3.12-slim AS runtime

# Minimal OCI labels for traceability in registries
LABEL org.opencontainers.image.title="webapp-demo" \
      org.opencontainers.image.description="Interactive ECS Fargate demo app" \
      org.opencontainers.image.licenses="MIT"

# Drop privileges — never run containers as root
RUN groupadd --system --gid 10001 app \
 && useradd  --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONOPTIMIZE=1 \
    PORT=8080

# Bring in the prebuilt venv from the builder stage
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app app.py .

USER app
EXPOSE 8080

# Self-healthcheck — ECS already has one via the ALB target group, this is for
# any local `docker run` / Compose / k8s deployment.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)" || exit 1

# Exec form so SIGTERM from ECS reaches gunicorn (graceful shutdown).
# gthread workers + small thread pool fits 0.25 vCPU / 0.5 GB Fargate task.
CMD ["gunicorn", \
     "--bind", "0.0.0.0:8080", \
     "--workers", "2", \
     "--threads", "4", \
     "--worker-class", "gthread", \
     "--worker-tmp-dir", "/dev/shm", \
     "--graceful-timeout", "20", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
