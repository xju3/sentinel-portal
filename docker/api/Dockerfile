ARG PYTHON_IMAGE=python:3.14-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/services/api

COPY services/pyproject.toml services/uv.lock* /app/services/
COPY services/api/pyproject.toml /app/services/api/
COPY services/pub/pyproject.toml services/pub/README.md /app/services/pub/

# 只安装第三方依赖，不安装本地 workspace 项目
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev --frozen --no-install-workspace

# 业务代码最后 COPY
COPY services/pub/src /app/services/pub/src/
COPY services/api/app /app/services/api/app

ENV PATH="/app/services/.venv/bin:$PATH"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]