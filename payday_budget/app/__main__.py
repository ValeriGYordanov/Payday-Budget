"""Add-on entry point: `python -m app`."""

import logging

import uvicorn

from app import config
from app.main import create_app


def main() -> None:
    base = config.data_dir()
    level = config.configure_logging(config.load_options(base).get("log_level", "info"))
    app = create_app(base)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=config.PORT,
        log_config=None,
        log_level=level,
        access_log=level <= logging.DEBUG,
        proxy_headers=False,  # the Ingress check relies on the real peer address
        timeout_graceful_shutdown=5,  # open SSE streams must not block shutdown
    )


if __name__ == "__main__":
    main()
