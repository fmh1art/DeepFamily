FROM ghcr.io/astral-sh/uv:0.11.1@sha256:fc93e9ecd7218e9ec8fba117af89348eef8fd2463c50c13347478769aaedd0ce AS uv

FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS build

COPY --from=uv /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app/backend

COPY backend/pyproject.toml backend/uv.lock backend/README.md ./
COPY backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/backend/.venv/bin:$PATH" \
    ASKDU_DATA_ROOT=/data/environment \
    ASKDU_RUNTIME_ROOT=/runtime

WORKDIR /app/backend

COPY --from=build /app/backend/.venv /app/backend/.venv
COPY backend/deployment ./deployment
COPY data/manifests/coda-public-source-provenance-v1.json \
     data/manifests/coda-bench-v1-open-release.json \
     data/manifests/coda-community-43-csv.sha256 \
     data/manifests/coda-community-52-csv.sha256 \
     /app/data/manifests/
RUN groupadd --gid 10001 askdu \
    && useradd --uid 10001 --gid askdu --no-create-home --shell /usr/sbin/nologin askdu \
    && mkdir -p /runtime /data/environment \
    && chown -R askdu:askdu /runtime

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=2)" || exit 1

CMD ["uvicorn", "deployment.api:app", "--host", "0.0.0.0", "--port", "8000", "--limit-concurrency", "16", "--timeout-keep-alive", "10", "--no-access-log"]
