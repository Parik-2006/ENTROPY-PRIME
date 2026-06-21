# ============================================================
#  ENTROPY PRIME — Production Dockerfile
#  Multi-stage build: SDK bundle → Frontend → Backend → Final
# ============================================================

# ── Stage 1: SDK bundler ─────────────────────────────────────
FROM node:20-alpine AS sdk-builder

WORKDIR /sdk

# Copy frontend source for SDK extraction
COPY package*.json ./
COPY vite.config.* ./
COPY tsconfig*.json ./
COPY src/ ./src/
COPY scripts/ ./scripts/

RUN npm ci --ignore-scripts

# Run the SDK bundle script (produces dist/entropy.min.js)
RUN chmod +x scripts/bundle-sdk.sh && \
    scripts/bundle-sdk.sh

# ── Stage 2: Frontend builder ─────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app

COPY package*.json ./
RUN npm ci --ignore-scripts

COPY . .
# Inject the pre-built SDK into the public folder for the demo page
COPY --from=sdk-builder /sdk/dist/entropy.min.js ./public/entropy.min.js
COPY --from=sdk-builder /sdk/dist/entropy.min.js.map ./public/entropy.min.js.map

ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

RUN npm run build

# ── Stage 3: Backend builder ──────────────────────────────────
FROM python:3.11-slim AS backend-builder

WORKDIR /backend

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# ── Stage 4: Production image ─────────────────────────────────
FROM python:3.11-slim AS production

LABEL org.opencontainers.image.title="Entropy Prime"
LABEL org.opencontainers.image.description="Zero-Trust Behavioral Biometrics Engine"
LABEL org.opencontainers.image.version="1.0.0"

# Non-root user for security
RUN groupadd -r entropy && useradd -r -g entropy -d /app entropy

WORKDIR /app

# Runtime OS deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages from builder
COPY --from=backend-builder /install /usr/local

# Copy backend source
COPY backend/ ./backend/

# Copy pre-trained model checkpoints (if present)
COPY --chown=entropy:entropy checkpoints/ ./checkpoints/ 2>/dev/null || true

# Copy built frontend static files
COPY --from=frontend-builder /app/dist ./frontend/dist

# Copy SDK artifact for separate serving
COPY --from=sdk-builder /sdk/dist/entropy.min.js ./frontend/dist/entropy.min.js
COPY --from=sdk-builder /sdk/dist/entropy.min.js.map ./frontend/dist/entropy.min.js.map

# ── Security hardening ────────────────────────────────────────
# Generate a fresh session secret at build time (override in production via env)
RUN python3 -c "import secrets; print(secrets.token_hex(64))" > /app/session.secret
RUN chmod 600 /app/session.secret && chown entropy:entropy /app/session.secret

USER entropy

EXPOSE 8000

# ── Healthcheck ───────────────────────────────────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    EP_ENV=production

CMD ["python3", "-m", "uvicorn", "backend.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "4", \
     "--loop", "uvloop", \
     "--http", "h11", \
     "--no-access-log"]