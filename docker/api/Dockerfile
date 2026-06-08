ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 用 pip 安装 uv，避免访问 ghcr.io
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app/services/api

COPY services/pyproject.toml services/uv.lock* /app/services/
COPY services/api/pyproject.toml /app/services/api/
COPY services/pub/pyproject.toml services/pub/README.md /app/services/pub/
COPY services/pub/src /app/services/pub/src/

RUN uv sync --no-dev --no-install-project

COPY services/api/app /app/services/api/app

RUN uv sync --no-dev

ENV PATH="/app/services/.venv/bin:$PATH"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]