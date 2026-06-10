ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 用 pip 安装 uv，避免访问 ghcr.io
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/

WORKDIR /app

COPY svr/pyproject.toml svr/uv.lock* /app/api
COPY svr/api/pyproject.toml /app/api
COPY svr/pub/pyproject.toml /app/pub/README.md /app/pub/
COPY svr/pub/src /app/pub/src/

RUN uv sync --no-dev --no-install-project

COPY svr/api/app /app/svr/api/app

RUN uv sync --no-dev

ENV PATH="/app/svr/.venv/bin:$PATH"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
