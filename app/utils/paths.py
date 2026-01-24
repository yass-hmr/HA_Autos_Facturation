from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "HA_Facturation"


def _is_frozen() -> bool:
    # PyInstaller / bundle
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def project_root() -> Path:
    """
    Racine "logique" de l'app.

    - En dev : .../<repo>/ (car ce fichier est .../<repo>/app/utils/paths.py)
    - En frozen : on retourne le dossier du binaire (ou l'exe), mais on N'ÉCRIT PAS dedans
    """
    if _is_frozen():
        # dossier contenant l'exécutable
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def user_data_root() -> Path:
    """
    Dossier utilisateur inscriptible (Linux/ChromeOS/Windows).
    On y stocke DB + exports + backups si besoin.
    """
    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(home)))
        return base / APP_NAME
    # Linux (Crostini) / macOS : standard XDG
    base = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local" / "share")))
    return base / APP_NAME


def app_data_dir() -> Path:
    """
    Choix du dossier data :
    - En dev : <repo>/data (ta racine contient déjà data/)
    - En frozen : dossier user (inscriptible)
    """
    if _is_frozen():
        data = user_data_root() / "data"
    else:
        data = project_root() / "data"

    data.mkdir(parents=True, exist_ok=True)
    return data


def exports_dir() -> Path:
    exports = app_data_dir() / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    return exports
