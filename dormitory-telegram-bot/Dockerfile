FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set work directory
WORKDIR /app

# Optimize uv performance in container
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Copy dependency definitions first to maximize Docker layer cache
COPY pyproject.toml uv.lock ./

# Install locked dependencies without project code
RUN uv sync --frozen --no-install-project --no-dev

# Copy project source and configuration
COPY README.md .python-version ./
COPY config/ ./config/
COPY src/ ./src/

# Install the application into virtual environment
RUN uv sync --frozen --no-dev

# Put virtual environment on PATH
ENV PATH="/app/.venv/bin:$PATH"

# Create directory structure for persistent volume
RUN mkdir -p /app/data/sessions /app/data/uploads /app/data/reports /app/incoming_spreadsheets

VOLUME ["/app/data"]

CMD ["python", "-m", "src.main"]

