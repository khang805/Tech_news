"""Paths and YAML loading."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
DOCS_DIR = ROOT / "docs"
LOG_FILE = ROOT / "logs" / "newsintel.log"


def _load_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings(config_dir: Path = CONFIG_DIR) -> dict:
    return _load_yaml(config_dir / "settings.yaml")


def load_feeds(config_dir: Path = CONFIG_DIR) -> list[dict]:
    feeds = _load_yaml(config_dir / "feeds.yaml").get("feeds", []) or []
    return [f for f in feeds if f.get("enabled", True)]
