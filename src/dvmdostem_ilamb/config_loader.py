"""Load YAML configuration files."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(path: Path | str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
