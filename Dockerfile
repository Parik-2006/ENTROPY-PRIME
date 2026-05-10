# syntax=docker/dockerfile:1
# Entropy Prime v3.2 — Production-grade multi-stage build
#
# Stages:
#   1. sdk-builder     — transpile & minify entropy.js → entropy.min.js
#   2. frontend-builder — Vite build React SPA with injected SDK
#   3. backend-builder  — pip install Python deps into clean prefix
#   4. production       — lean final image with uvicorn + uvloop

FROM node:20-alpine AS sdk-builder
LABEL stage="sdk-builder"
WORKDIR /build

# Copy SDK source and bundler script
COPY public/sdk/ ./sdk-src/
COPY scripts/bundle-sdk.sh ./
RUN chmod +x bundle-sdk.sh && ./bundle-sdk.sh

# Verify outputs
RUN ls -lh entropy.* || echo "Warning: SDK bundle incomplete"


FROM node:20-alpine AS frontend-builder
LABEL stage="frontend-builder"
WORKDIR /build

# Install dependencies
COPY package*.json ./
RUN npm ci --omit=dev

# Copy source
COPY src/ ./src/
COPY public/ ./public/
COPY vite.config.js index.html ./

# Inject minified SDK from previous stage
COPY --from=sdk-builder /build/entropy.min.js ./public/sdk/entropy.min.js
COPY --from=sdk-builder /build/entropy.esm.min.js ./public/sdk/entropy.esm.min.js

# Build with Vite
RUN npm run build

# Verify outputs
RUN ls -lh dist/ || echo "Warning: Vite build incomplete"


FROM python:3.13-slim AS backend-builder
LABEL stage="backend-builder"
WORKDIR /tmp/pip

# Install build dependencies (gcc, etc. for compiling C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create clean prefix for pip installs (no system cruft)
RUN mkdir -p /opt/backend-deps

# Install dependencies into the clean prefix
COPY backend/requirements.txt ./
RUN pip install \
    --target=/opt/backend-deps \
    --no-cache-dir \
    -r requirements.txt

# Verify key packages
RUN python -c "import fastapi, torch, motor; print('✓ Core deps installed')" || exit 1


FROM python:3.13-slim AS production
LABEL maintainer="Entropy Prime Team" \
      version="3.2.0" \
      description="Zero-trust biometric authentication SaaS platform"

# Install runtime dependencies (no dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user with minimal privileges
RUN groupadd -r entropy && useradd -r -g entropy entropy

# Set up working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=backend-builder /opt/backend-deps /opt/backend-deps
ENV PYTHONPATH=/opt/backend-deps:$PYTHONPATH

# Copy backend code
COPY backend/ ./backend/
COPY --chown=entropy:entropy . .

# Copy built frontend assets
COPY --from=frontend-builder /build/dist ./static/

# Copy SDK assets for serving
COPY --from=sdk-builder /build/entropy.min.js ./static/entropy.min.js
COPY --from=sdk-builder /build/entropy.esm.min.js ./static/entropy.esm.min.js
COPY --from=sdk-builder /build/sdk-manifest.json ./static/sdk-manifest.json

# Security: read-only root filesystem + tmpfs for transient writes
RUN chmod 555 / && \
    chown -R entropy:entropy /app && \
    chmod 755 /app

# Switch to non-root user
USER entropy

# Create tmpfs-mounted directories for app writes (logs, temp files)
VOLUME ["/tmp", "/app/logs"]

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Expose API port
EXPOSE 8000

# Production: uvicorn with uvloop, 4 workers
ENV PYTHONUNBUFFERED=1 \
    EP_LOG_LEVEL=INFO \
    EP_WORKERS=4

CMD ["python", "-m", "uvicorn", \
     "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--no-access-log"]
