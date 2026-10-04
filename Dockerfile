FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /bin/uv

# venv 는 /app 밖(/opt/venv)에 둔다 — docker-compose 의 `.:/app` bind mount 가 가리지 않도록.
# 이미지의 python 으로 만들어야 runtime 스테이지에서도 venv 의 python 심볼릭 링크가 유효하다.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
# --locked: pyproject.toml 과 uv.lock 이 어긋나면 빌드를 실패시킨다.
RUN uv sync --locked --no-dev --no-cache


FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd -r -u 1001 appuser

WORKDIR /app

COPY --chown=appuser . .

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
