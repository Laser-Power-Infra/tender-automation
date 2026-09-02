# ============================================================
# Builder
# ============================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Dependency layer
COPY pyproject.toml uv.lock ./

# RUN uv sync --frozen --no-install-project
# AFTER (🟢 Add the cache mount):
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Install Chromium
# RUN apt-get update \
#     && apt-get install -y --no-install-recommends \
#        chromium \
#        ca-certificates \
#        fonts-liberation \
#     && rm -rf /var/lib/apt/lists/*

# Application
COPY . .

# RUN uv sync --frozen
# AFTER (🟢 Add the cache mount):
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# ============================================================
# Runtime
# ============================================================
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1 \
#     PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
#     PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Playwright/Chromium runtime dependencies
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
    libpango-1.0-0 \
    libcairo2 \
    fonts-liberation \
      chromium \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python environment
COPY --from=builder /app/.venv /app/.venv

# Chromium
# COPY --from=builder /ms-playwright /ms-playwright

# Application

COPY --from=builder /app /app
# Make sure the venv is used
ENV PATH="/app/.venv/bin:$PATH"
# Default worker
CMD ["python", "manage.py", "consume_tender_tasks"]