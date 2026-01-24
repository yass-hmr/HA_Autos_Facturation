from __future__ import annotations

import sqlite3


class SettingsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self._ensure_columns()

    def _has_column(self, table: str, column: str) -> bool:
        cur = self.conn.execute(f"PRAGMA table_info({table})")
        return any(r[1] == column for r in cur.fetchall())  # r[1] = name

    def _ensure_columns(self) -> None:
        """
        Rend le repo tolérant aux anciennes DB :
        - ajoute garage_email si absent
        """
        if not self._has_column("settings", "garage_email"):
            self.conn.execute(
                "ALTER TABLE settings ADD COLUMN garage_email TEXT NOT NULL DEFAULT ''"
            )
            self.conn.commit()

    def get(self) -> dict[str, str]:
        row = self.conn.execute(
            """
            SELECT
              garage_name,
              garage_address,
              garage_postal_code,
              garage_phone,
              garage_siret,
              garage_email,
              onedrive_backup_dir,
              COALESCE(last_backup_at,'') AS last_backup_at
            FROM settings
            WHERE id = 1
            """
        ).fetchone()

        if not row:
            self.conn.execute("INSERT OR IGNORE INTO settings (id) VALUES (1)")
            self.conn.commit()
            return {
                "garage_name": "",
                "garage_address": "",
                "garage_postal_code": "",
                "garage_phone": "",
                "garage_siret": "",
                "garage_email": "",
                "onedrive_backup_dir": "",
                "last_backup_at": "",
            }

        return {
            "garage_name": row["garage_name"] or "",
            "garage_address": row["garage_address"] or "",
            "garage_postal_code": row["garage_postal_code"] or "",
            "garage_phone": row["garage_phone"] or "",
            "garage_siret": row["garage_siret"] or "",
            "garage_email": row["garage_email"] or "",
            "onedrive_backup_dir": row["onedrive_backup_dir"] or "",
            "last_backup_at": row["last_backup_at"] or "",
        }

    def update_last_backup(self, created_at_iso: str) -> None:
        self.conn.execute(
            "UPDATE settings SET last_backup_at = ? WHERE id = 1",
            (created_at_iso,),
        )
        self.conn.commit()

    def update(
        self,
        *,
        garage_name: str,
        garage_address: str,
        garage_postal_code: str,
        garage_phone: str,
        garage_email: str,
        garage_siret: str,
        onedrive_backup_dir: str,
    ) -> None:
        self.conn.execute(
            """
            UPDATE settings
            SET garage_name = ?,
                garage_address = ?,
                garage_postal_code = ?,
                garage_phone = ?,
                garage_email = ?,
                garage_siret = ?,
                onedrive_backup_dir = ?
            WHERE id = 1
            """,
            (
                (garage_name or "").strip(),
                (garage_address or "").strip(),
                (garage_postal_code or "").strip(),
                (garage_phone or "").strip(),
                (garage_email or "").strip(),
                (garage_siret or "").strip(),
                (onedrive_backup_dir or "").strip(),
            ),
        )
        self.conn.commit()
