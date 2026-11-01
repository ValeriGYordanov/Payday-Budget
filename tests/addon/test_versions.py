"""The version must match everywhere it is declared (add-on, UI, integration)."""

import json
import re
from pathlib import Path

from app.main import create_app

ROOT = Path(__file__).resolve().parents[2]


def test_versions_match(tmp_path: Path) -> None:
    config = (ROOT / "payday_budget" / "config.yaml").read_text()
    match = re.search(r'^version: "([^"]+)"', config, re.MULTILINE)
    assert match is not None
    version = match.group(1)
    package = json.loads((ROOT / "frontend" / "package.json").read_text())
    assert package["version"] == version
    manifest = json.loads(
        (ROOT / "custom_components" / "payday_budget" / "manifest.json").read_text()
    )
    assert manifest["version"] == version
    app = create_app(tmp_path, announce=lambda _t: None)
    assert app.version == version
    app.state.engine.dispose()
