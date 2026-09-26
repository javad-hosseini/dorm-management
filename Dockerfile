# ==============================================================================
# Multi-stage / Secure Production Dockerfile for Dormitory Management System
# Compliant with OWASP & DevSecOps standards (non-root execution, minimal layers)
# ==============================================================================

FROM python:3.12-slim-bookworm

# Set Python environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies required for PostgreSQL and Pillow
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libjpeg62-turbo-dev \
    zlib1g-dev \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Create dedicated non-root user and group
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Set working directory
WORKDIR /app

# Copy dependency definition first for Docker layer caching
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source code
COPY . /app/

# Ensure necessary directories exist and set correct ownership
RUN mkdir -p /app/staticfiles /app/media && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/docker/entrypoint.sh

# Switch to non-root user
USER appuser

# Expose internal application port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Define entrypoint script
ENTRYPOINT ["/app/docker/entrypoint.sh"]
