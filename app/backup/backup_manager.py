from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class BackupResult:
    backup_path: Path
    created_at_iso: str


class BackupError(RuntimeError):
    pass


class BackupManager:
    """
    Sauvegarde cohérente SQLite via API .backup() (robuste, compatible).
    Écrit un fichier dans un dossier OneDrive (local), OneDrive se charge de sync.
    """

    def __init__(
        self,
        keep_last: int = 10,
        prefix: str = "backup",
    ) -> None:
        self.keep_last = keep_last
        self.prefix = prefix

    def create_backup(
        self,
        source_conn: sqlite3.Connection,
        target_dir: Path,
        *,
        invoice_prefix: str = "FAC",
    ) -> BackupResult:
        if not target_dir:
            raise BackupError("Dossier OneDrive non configuré.")

        target_dir = Path(target_dir)
        if not target_dir.exists() or not target_dir.is_dir():
            raise BackupError("Le dossier OneDrive sélectionné est introuvable ou invalide.")

        created_at = datetime.now()
        created_at_iso = created_at.isoformat(timespec="seconds")
        stamp = created_at.strftime("%Y-%m-%d_%H-%M-%S")

        # Nom de fichier simple + triable + unique
        backup_name = f"{self.prefix}_{stamp}.db"
        backup_path = target_dir / backup_name

        # Éviter d’écraser quoi que ce soit
        if backup_path.exists():
            raise BackupError("Un fichier de sauvegarde du même nom existe déjà.")

        # Snapshot cohérent
        dest_conn: Optional[sqlite3.Connection] = None
        try:
            dest_conn = sqlite3.connect(str(backup_path))
            # Copie atomique du contenu via l'API sqlite3
            source_conn.backup(dest_conn)
            dest_conn.commit()
        except Exception as e:
            # Nettoyage si création partielle
            try:
                if dest_conn:
                    dest_conn.close()
            finally:
                if backup_path.exists():
                    try:
                        backup_path.unlink()
                    except Exception:
                        pass
            raise BackupError(f"Échec de sauvegarde SQLite : {e}") from e
        finally:
            if dest_conn:
                dest_conn.close()

        # Rotation
        self._rotate_backups(target_dir)

        return BackupResult(backup_path=backup_path, created_at_iso=created_at_iso)

    def _rotate_backups(self, target_dir: Path) -> None:
        # On conserve les N fichiers les plus récents correspondant au préfixe
        backups = sorted(
            target_dir.glob(f"{self.prefix}_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[self.keep_last :]:
            try:
                old.unlink()
            except Exception:
                # En cas de verrouillage OneDrive/AV, on n’échoue pas la sauvegarde
                pass
