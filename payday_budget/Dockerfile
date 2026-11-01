# Pinned multi-arch base (aarch64, amd64). Supervisor >= 2026.04 no longer passes BUILD_FROM.
FROM ghcr.io/home-assistant/base-python:3.12-alpine3.24-2026.10.3

ARG BUILD_VERSION=dev
ARG BUILD_ARCH

WORKDIR /opt/payday_budget

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY app ./app
COPY migrations ./migrations

ENV PAYDAY_BUDGET_DATA=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

CMD ["python3", "-m", "app"]

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64"
