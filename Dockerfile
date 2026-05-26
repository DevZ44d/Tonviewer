# ─────────────────────────────────────────────────────────────────────────────
#  Tonviewer — Dockerfile
#  Multi-stage build: keeps the final image lean (~120 MB).
#  Stage 1 (builder) : installs all deps into a venv
#  Stage 2 (runtime) : copies only the venv + source — no build tools
# ─────────────────────────────────────────────────────────────────────────────

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS builder

# Keeps Python from writing .pyc files and enables unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Copy dependency manifests first (layer cache-friendly)
COPY requirements.txt .

# Create an isolated virtual environment inside the image
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install all dependencies into the venv
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Copy source and install the package itself (editable-less, wheel install)
COPY . .
RUN pip install --no-deps .


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.13-slim AS runtime

LABEL maintainer="AhMed <alexcrow221@gmail.com>" \
      org.opencontainers.image.title="Tonviewer" \
      org.opencontainers.image.description="TON blockchain wallet intelligence SDK & CLI" \
      org.opencontainers.image.source="https://github.com/DevZ44d/Tonviewer" \
      org.opencontainers.image.version="1.1.10" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# Non-root user for security
RUN addgroup --system tonviewer \
 && adduser  --system --ingroup tonviewer --no-create-home tonuser

# Copy only the built venv from the builder stage
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app

# Drop to non-root
USER tonuser

# Default: show help. Override with any Tonviewer CLI flags.
ENTRYPOINT ["Tonviewer"]
CMD ["--help"]
