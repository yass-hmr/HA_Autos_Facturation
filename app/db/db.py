from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _resource_path(rel: str) -> Path:
    """
    Résout un fichier "ressource" :
    - en dev : depuis la racine du projet (dossier contenant app/)
    - en exe PyInstaller : depuis sys._MEIPASS
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / rel  # type: ignore[attr-defined]

    # __file__ = app/db/db.py -> parents[2] = racine du projet
    # (db.py -> db -> app -> racine)
    project_root = Path(__file__).resolve().parents[2]
    return project_root / rel


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 3000;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    schema_path = _resource_path("app/db/schema.sql")
    schema = schema_path.read_text(encoding="utf-8")
    conn.executescript(schema)
    _migrate(conn)
    conn.commit()


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r["name"] == column for r in cur.fetchall())


def _invoice_table_allows_paid(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='invoice'"
    ).fetchone()
    if not row or not row["sql"]:
        return False
    return "PAID" in row["sql"].upper()


def _migrate_invoice_add_paid(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF;")
    try:
        conn.execute("BEGIN;")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invoice_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              number TEXT UNIQUE,
              date TEXT NOT NULL,
              customer_name TEXT NOT NULL DEFAULT '',
              customer_address TEXT NOT NULL DEFAULT '',
              customer_postal_code TEXT NOT NULL DEFAULT '',
              subtotal_cents INTEGER NOT NULL DEFAULT 0,
              vat_rate INTEGER NOT NULL DEFAULT 20,
              vat_cents INTEGER NOT NULL DEFAULT 0,
              total_cents INTEGER NOT NULL DEFAULT 0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )

        if _has_column(conn, "invoice", "customer_postal_code"):
            conn.execute(
                """
                INSERT INTO invoice_new (
                  id, number, date,
                  customer_name, customer_address, customer_postal_code,
                  subtotal_cents, vat_rate, vat_cents, total_cents,
                  created_at, updated_at
                )
                SELECT
                  id, number, date,
                  customer_name, customer_address, customer_postal_code,
                  subtotal_cents, vat_rate, vat_cents, total_cents,
                  created_at, updated_at
                FROM invoice;
                """
            )
        else:
            conn.execute(
                """
                INSERT INTO invoice_new (
                  id, number, date,
                  customer_name, customer_address, customer_postal_code,
                  subtotal_cents, vat_rate, vat_cents, total_cents,
                  created_at, updated_at
                )
                SELECT
                  id, number, date,
                  customer_name, customer_address, '',
                  subtotal_cents, vat_rate, vat_cents, total_cents,
                  created_at, updated_at
                FROM invoice;
                """
            )

        conn.execute("DROP TABLE invoice;")
        conn.execute("ALTER TABLE invoice_new RENAME TO invoice;")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_invoice_date ON invoice(date);")

        conn.execute("COMMIT;")
    except Exception:
        conn.execute("ROLLBACK;")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON;")


def _migrate(conn: sqlite3.Connection) -> None:
    # Colonnes manquantes (DB ancienne)
    if not _has_column(conn, "invoice", "customer_postal_code"):
        conn.execute("ALTER TABLE invoice ADD COLUMN customer_postal_code TEXT NOT NULL DEFAULT ''")

    if not _has_column(conn, "settings", "garage_postal_code"):
        conn.execute("ALTER TABLE settings ADD COLUMN garage_postal_code TEXT NOT NULL DEFAULT ''")

    if not _has_column(conn, "settings", "garage_siret"):
        conn.execute("ALTER TABLE settings ADD COLUMN garage_siret TEXT NOT NULL DEFAULT ''")

    # Table PDF exports + index unique (sécurité si DB existante)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pdf_export (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          invoice_id INTEGER NOT NULL,
          filename TEXT NOT NULL,
          rel_path TEXT NOT NULL,
          created_at TEXT NOT NULL,
          kind TEXT NOT NULL DEFAULT 'INVOICE',
          FOREIGN KEY (invoice_id) REFERENCES invoice(id) ON DELETE CASCADE
        );
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_export_invoice_id ON pdf_export(invoice_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pdf_export_created_at ON pdf_export(created_at);")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_pdf_export_invoice_filename
        ON pdf_export(invoice_id, filename);
        """
    )
