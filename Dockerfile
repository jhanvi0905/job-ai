# Product API + worker image (one image, two Fly process groups; see fly.toml).
# Runtime deps only (requirements.txt); tests/dev tools live in requirements-dev.txt.

FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install -r requirements.txt

FROM python:3.13-slim
ARG GIT_SHA=unknown
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH="/opt/venv/bin:$PATH" \
    GIT_SHA=${GIT_SHA} \
    PORT=8080

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
# .dockerignore keeps out .env*, data/, tests/, docs/, frontend/ and VCS files.
COPY . .

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data && chown -R app:app /app/data
USER app

EXPOSE 8080
# Default process = the API. Fly overrides per process group (app / worker);
# docker-compose overrides with its own command.
CMD ["sh", "-c", "exec uvicorn jobai.product.api.app:create_app --factory --host 0.0.0.0 --port ${PORT} --no-server-header --timeout-graceful-shutdown 20"]
