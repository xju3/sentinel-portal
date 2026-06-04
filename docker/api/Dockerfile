ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install uv using the official installer (pip may not have uv available)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/services/api

# Copy workspace root configuration and lock file
COPY services/pyproject.toml services/uv.lock* /app/services/

# Copy api pyproject.toml
COPY services/api/pyproject.toml /app/services/api/

# Copy pub workspace member (api depends on pub)
COPY services/pub/pyproject.toml services/pub/README.md /app/services/pub/
COPY services/pub/src /app/services/pub/src/

RUN uv sync --no-dev --no-install-project

# Copy api application source code
COPY services/api/app /app/services/api/app

# 安装项目自身和本地工作区依赖 (pub)
RUN uv sync --no-dev

ENV PATH="/app/services/.venv/bin:$PATH"

EXPOSE 8000

# 改这里
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
