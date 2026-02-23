# Multi-stage build for OpenTA Backend on Render.com
# Cache-busted version to force fresh dependency install

# Stage 1: Builder - Compile dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /build

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# CACHE BUST: Change this value to force a full pip reinstall
RUN echo "cachebust-2026-02-23-23:32" > /tmp/cachebust

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies to a temporary location
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --prefix=/install packaging && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime - Minimal production image
FROM python:3.11-slim

# Set labels for Render
LABEL maintainer="Emirsyah & OpenTA Team"
LABEL description="OpenTA Backend API - Telkom University Paper Research Platform"

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for running the application
RUN groupadd -r appuser && useradd -r -g appuser -u 1000 appuser

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app/logs

# Switch to non-root user
USER appuser

# Expose the port (Render uses environment variable PORT, default 8000)
EXPOSE 8000

# Health check for Render
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Run the application with uvicorn
# Render expects the app to listen on the PORT environment variable
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
