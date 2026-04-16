# Slim Python image. matplotlib + numpy wheels are large but build-step-free.
FROM python:3.12-slim

# System deps for matplotlib font rendering. libffi for cryptography (used
# transitively by anthropic + slack-sdk). Kept minimal so the image stays small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# uv: deterministic, fast installs from the lockfile we already commit.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy lockfile + project metadata first so dependency installation caches
# cleanly when only application code changes.
COPY pyproject.toml uv.lock ./

# --no-dev: skip pytest/pytest-asyncio in production images.
# --frozen: enforce that uv.lock is up to date with pyproject.toml.
RUN uv sync --frozen --no-dev

# Copy the rest of the application.
COPY src ./src
COPY web_main.py ./

# Render injects $PORT at runtime; the entrypoint already honors it.
EXPOSE 8000

CMD ["uv", "run", "--no-dev", "python", "web_main.py"]
