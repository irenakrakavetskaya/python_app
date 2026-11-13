FROM python:3.15-slim
# Pin to the version from `uv --version` on your machine
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_NO_DEV=1 \
    PATH="/app/.venv/bin:$PATH"

# 1. Dependencies only (cached unless pyproject.toml or uv.lock change)
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# 2. Source, migrations + project install
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Add --proxy-headers if running behind Nginx/Traefik
CMD ["fastapi", "run", "src/my_first_app/main.py", "--host", "0.0.0.0"]