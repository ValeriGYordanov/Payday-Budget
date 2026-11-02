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

# s6-overlay v3 clears the environment for CMD; with-contenv restores the container
# environment (SUPERVISOR_TOKEN, TZ and the ENV values above).
CMD ["/usr/bin/with-contenv", "python3", "-m", "app"]

LABEL \
    io.hass.version="${BUILD_VERSION}" \
    io.hass.type="app" \
    io.hass.arch="aarch64|amd64" \
    org.opencontainers.image.title="Payday Budget" \
    org.opencontainers.image.description="Budgeting with periods that start on payday, not on the 1st." \
    org.opencontainers.image.source="https://github.com/ValeriGYordanov/Payday-Budget" \
    org.opencontainers.image.licenses="MIT"
