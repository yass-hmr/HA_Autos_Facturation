from __future__ import annotations

from pathlib import Path


def app_data_dir() -> Path:
    # Racine projet (stable en dev)
    base = Path(__file__).resolve().parents[2]
    data = base / "app" / "data"
    data.mkdir(parents=True, exist_ok=True)
    return data


def exports_dir() -> Path:
    exports = app_data_dir() / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    return exports