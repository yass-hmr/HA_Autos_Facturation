from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass(frozen=True)
class PdfExportItem:
    id: int
    invoice_id: int
    filename: str
    rel_path: str
    created_at: str
    kind: str

class PdfExportRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_all(self) -> List[PdfExportItem]:
        cur = self.conn.execute(
            """
            SELECT id, invoice_id, filename, rel_path, created_at, kind
            FROM pdf_export
            ORDER BY created_at DESC, id DESC
            """
        )
        return [
            PdfExportItem(
                id=r["id"],
                invoice_id=r["invoice_id"],
                filename=r["filename"],
                rel_path=r["rel_path"],
                created_at=r["created_at"],
                kind=r["kind"],
            )
            for r in cur.fetchall()
        ]

    def get_by_id(self, pdf_id: int) -> Optional[PdfExportItem]:
        r = self.conn.execute(
            """
            SELECT id, invoice_id, filename, rel_path, created_at, kind
            FROM pdf_export
            WHERE id = ?
            """,
            (pdf_id,),
        ).fetchone()
        if not r:
            return None
        return PdfExportItem(
            id=r["id"],
            invoice_id=r["invoice_id"],
            filename=r["filename"],
            rel_path=r["rel_path"],
            created_at=r["created_at"],
            kind=r["kind"],
        )

    def add_or_touch(self, *, invoice_id: int, filename: str, rel_path: str, kind: str = "INVOICE") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """
            UPDATE pdf_export
            SET created_at = ?, rel_path = ?, kind = ?
            WHERE invoice_id = ? AND filename = ?
            """,
            (now, rel_path, kind, invoice_id, filename),
        )
        if cur.rowcount == 0:
            self.conn.execute(
                """
                INSERT INTO pdf_export (invoice_id, filename, rel_path, created_at, kind)
                VALUES (?, ?, ?, ?, ?)
                """,
                (invoice_id, filename, rel_path, now, kind),
            )
        self.conn.commit()

    def delete(self, pdf_id: int) -> None:
        self.conn.execute("DELETE FROM pdf_export WHERE id = ?", (pdf_id,))
        self.conn.commit()

    def replace_invoice_export(self, *, invoice_id: int, filename: str, rel_path: str) -> None:
        now = datetime.now().isoformat(timespec="seconds")

        # Supprimer l'ancien export INVOICE de cette facture
        self.conn.execute(
            "DELETE FROM pdf_export WHERE invoice_id = ? AND kind = 'INVOICE'",
            (invoice_id,),
        )

        # Insérer le nouveau
        self.conn.execute(
            """
            INSERT INTO pdf_export (invoice_id, filename, rel_path, created_at, kind)
            VALUES (?, ?, ?, ?, 'INVOICE')
            """,
            (invoice_id, filename, rel_path, now),
        )
        self.conn.commit()

