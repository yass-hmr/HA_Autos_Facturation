from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QTimer

from app.backup.backup_manager import BackupManager, BackupError
from app.db.repos.settings_repo import SettingsRepository


class BackupScheduler(QObject):
    """
    Gère la sauvegarde automatique :
    - périodique (toutes les X minutes) si db_dirty
    - à la fermeture (si db_dirty)
    - extensible plus tard : après validation facture (mark_dirty + try_backup)
    """

    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        settings_repo: SettingsRepository,
        backup_manager: BackupManager,
        interval_minutes: int = 30,
        on_status: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__()
        self.conn = conn
        self.settings_repo = settings_repo
        self.backup_manager = backup_manager
        self.on_status = on_status

        self.db_dirty = False

        self.timer = QTimer(self)
        self.timer.setInterval(interval_minutes * 60 * 1000)
        self.timer.timeout.connect(self._on_timer)

    def start(self) -> None:
        self.timer.start()

    def stop(self) -> None:
        self.timer.stop()

    def mark_dirty(self) -> None:
        self.db_dirty = True

    def try_backup_now(self, *, force: bool = False) -> bool:
        """
        Retourne True si une sauvegarde a été effectuée.
        """
        if not force and not self.db_dirty:
            self._emit("Sauvegarde auto : aucune modification, rien à faire.")
            return False

        settings = self.settings_repo.get()
        target_dir = (settings.get("onedrive_backup_dir") or "").strip()
        if not target_dir:
            self._emit("Sauvegarde : dossier OneDrive non configuré.")
            return False

        try:
            result = self.backup_manager.create_backup(self.conn, Path(target_dir))
            self.settings_repo.update_last_backup(result.created_at_iso)
            self.db_dirty = False
            self._emit(f"Sauvegarde OK : {result.backup_path.name}")
            return True
        except BackupError as e:
            self._emit(f"Sauvegarde impossible : {e}")
            return False
        self.settings_repo.update_last_backup(result.created_at_iso)


    def _on_timer(self) -> None:
        self.try_backup_now(force=False)

    def _emit(self, msg: str) -> None:
        if self.on_status:
            self.on_status(msg)
