FROM python:3.12-slim

# Copy uv binary
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

# --- Layer 1: Dependencies (cached unless pyproject.toml changes) ---
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# --- Layer 2: Application Code ---
COPY . .

# --- Production: add Gunicorn ---
RUN uv add gunicorn

# Make entrypoint executable
RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

# Production entrypoint — handles migrate, collectstatic, gunicorn
ENTRYPOINT ["docker/entrypoint.sh"]