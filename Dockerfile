# ============================================================
# Stage 1: Builder (with UV cache enabled)
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 1. Copy dependency definitions first
COPY pyproject.toml uv.lock ./

# 2. 🟢 Cache UV downloads so dependencies aren't re-downloaded from scratch
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# 3. Copy source code and install project
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# ============================================================
# Stage 2: Lean Runtime
# ============================================================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install Playwright/Chromium runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libgl1 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libdbus-1-3 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libatspi2.0-0 \
    libgtk-3-0 \
    libpango-1-0-0 \
    libcairo2 \
    fonts-liberation \
    chromium \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment and app from builder
COPY --from=builder /app /app

# Default command (overridden by docker-compose commands)
CMD ["python", "manage.py", "consume_tender_tasks"]