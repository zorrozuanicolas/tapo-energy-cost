# Backend image for amd64 and arm64 (Raspberry Pi with a 64-bit OS).
# Build it with `backend/` as the context: docker build -t tapo-backend backend

# --- Build stage: install the locked dependencies into a virtual environment ---
FROM python:3.12-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /bin/uv

# Compile .pyc files now, copy packages instead of linking them, and use the image's Python.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never

WORKDIR /srv/backend
# Only the dependency files, so this layer is rebuilt only when they change.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev

# --- Final stage: Python, the virtual environment and the app ---
FROM python:3.12-slim

# The database and the config files come from outside the image, mounted at these paths.
ENV PYTHONUNBUFFERED=1 \
    PATH=/srv/backend/.venv/bin:$PATH \
    DATABASE_URL=sqlite+aiosqlite:////srv/data/tapo.db \
    CONFIG_DIR=/srv/config

# Run as an ordinary user that can write only to the data folder.
RUN useradd --create-home --uid 1000 app && mkdir -p /srv/data /srv/config && chown app /srv/data

WORKDIR /srv/backend
COPY --from=build /srv/backend/.venv ./.venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# One process: the live stream keeps its state in memory. Open streams never end by themselves, so
# on shutdown they are cut after 2 s, so the app can stop cleanly before Docker kills the process
# (measured on Docker Desktop: about 3 s after asking it to stop).
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--timeout-graceful-shutdown", "2"]
