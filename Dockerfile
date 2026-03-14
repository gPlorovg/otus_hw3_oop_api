# --- Stage 1: Base (Dependencies installation) ---
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-cache --no-install-project

# --- Stage 2: Runtime  ---
FROM base AS run

COPY api.py scoring.py store.py ./

EXPOSE 8080

CMD ["uv", "run", "python", "api.py", "--port", "8080"]

# --- Stage 3: Test ---
FROM base AS test

COPY api.py scoring.py store.py test.py ./

CMD ["uv", "run", "python", "-m", "pytest", "test.py", "-v"]
