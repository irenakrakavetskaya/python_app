FROM python:3.15-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_NO_DEV=1

# 1. Install dependencies only (cached unless pyproject.toml or uv.lock change)
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

# 2. Copy the source and install your package
COPY src ./src
RUN uv sync --frozen

CMD ["uv", "run", "fastapi", "run", "src/my_first_app/main.py", "--host", "0.0.0.0"]