# Multi-stage Dockerfile for Production
ARG PYTHON_VERSION=3.11

# Build stage
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

COPY requirements.txt .

RUN pip install --user --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:${PYTHON_VERSION}-slim

# Security: Use non-root user
RUN useradd -m -u 1000 entropy && \
    mkdir -p /app && \
    chown -R entropy:entropy /app

WORKDIR /app

COPY --chown=entropy:entropy --from=builder /root/.local /home/entropy/.local
COPY --chown=entropy:entropy . /app

# Set Python to use user's local pip packages
ENV PATH=/home/entropy/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

USER entropy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]

