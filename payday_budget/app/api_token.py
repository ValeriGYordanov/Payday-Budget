"""Integration bearer token (§6.2): generated on first start, stored in the data dir."""

import os
import secrets
from pathlib import Path

TOKEN_FILE = "token"


def load_or_create(base: Path) -> str:
    path = base / TOKEN_FILE
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(token)
    return token
