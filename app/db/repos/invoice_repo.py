from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class InvoiceListItem:
    id: int
    number: Optional[str]
    date: str
    customer_name: str
    total_cents: int


@dataclass(frozen=True)
class InvoiceHeader:
    id: int
    number: Optional[str]
    date: str
    customer_name: str
    customer_address: str
    customer_postal_code: str
    customer_email: str
    customer_phone: str
    subtotal_cents: int
    vat_rate: int
    vat_cents: int
    total_cents: int


@dataclass(frozen=True)
class InvoiceLine:
    id: int
    invoice_id: int
    position: int
    reference: str
    qty: int
    description: str
    unit_price_cents: int
    line_total_cents: int


class InvoiceRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def list_invoices(self, search: str = "") -> List[InvoiceListItem]:
        search = search.strip()
        if search:
            like = f"%{search}%"
            cur = self.conn.execute(
                """
                SELECT id, number, date, customer_name, total_cents
                FROM invoice
                WHERE number LIKE ? OR customer_name LIKE ? OR date LIKE ?
                ORDER BY id DESC
                """,
                (like, like, like),
            )
        else:
            cur = self.conn.execute(
                """
                SELECT id, number, date, customer_name, total_cents
                FROM invoice
                ORDER BY id DESC
                """
            )

        return [
            InvoiceListItem(
                id=row["id"],
                number=row["number"],
                date=row["date"],
                customer_name=row["customer_name"],
                total_cents=row["total_cents"],
            )
            for row in cur.fetchall()
        ]

    def create_draft(self, date_iso: str) -> int:
        """
        Crée une facture en brouillon.
        Version robuste : construit l'INSERT selon les colonnes réellement présentes
        dans la table invoice (évite mismatch colonnes/valeurs).
        """
        now = datetime.now().isoformat(timespec="seconds")

        cols_in_db = {
            r["name"] for r in self.conn.execute("PRAGMA table_info(invoice)").fetchall()
        }

        defaults = {
            "number": None,
            "date": date_iso,
            "customer_name": "",
            "customer_address": "",
            "customer_postal_code": "",
            "customer_phone": "",
            "customer_email": "",
            "subtotal_cents": 0,
            "vat_rate": 20,
            "vat_cents": 0,
            "total_cents": 0,
            "created_at": now,
            "updated_at": now,
        }

        cols = [c for c in defaults.keys() if c in cols_in_db]
        values = [defaults[c] for c in cols]

        placeholders = ", ".join(["?"] * len(cols))
        col_list = ", ".join(cols)

        cur = self.conn.execute(
            f"INSERT INTO invoice ({col_list}) VALUES ({placeholders})",
            tuple(values),
        )
        self.conn.commit()
        return int(cur.lastrowid)


    def get_header(self, invoice_id: int) -> InvoiceHeader:
        cur = self.conn.execute(
            """
            SELECT
                id, number, date,
                customer_name, customer_address, customer_postal_code,
                customer_email, customer_phone,
                subtotal_cents, vat_rate, vat_cents, total_cents
            FROM invoice
            WHERE id = ?
            """,
            (invoice_id,),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Facture introuvable.")
        return InvoiceHeader(
            id=row["id"],
            number=row["number"],
            date=row["date"],
            customer_name=row["customer_name"],
            customer_address=row["customer_address"],
            customer_postal_code=row["customer_postal_code"],
            customer_email=row["customer_email"],
            customer_phone=row["customer_phone"],
            subtotal_cents=row["subtotal_cents"],
            vat_rate=row["vat_rate"],
            vat_cents=row["vat_cents"],
            total_cents=row["total_cents"],
        )

    def get_lines(self, invoice_id: int) -> List[InvoiceLine]:
        cur = self.conn.execute(
            """
            SELECT id, invoice_id, position, reference, qty, description,
                   unit_price_cents, line_total_cents
            FROM invoice_line
            WHERE invoice_id = ?
            ORDER BY position ASC
            """,
            (invoice_id,),
        )
        return [
            InvoiceLine(
                id=row["id"],
                invoice_id=row["invoice_id"],
                position=row["position"],
                reference=row["reference"],
                qty=row["qty"],
                description=row["description"],
                unit_price_cents=row["unit_price_cents"],
                line_total_cents=row["line_total_cents"],
            )
            for row in cur.fetchall()
        ]

    def save_invoice(
        self,
        invoice_id: int,
        *,
        number: str | None,
        date_iso: str,
        customer_name: str,
        customer_address: str,
        customer_postal_code: str,
        customer_email: str,
        customer_phone: str,
        subtotal_cents: int,
        vat_rate: int,
        vat_cents: int,
        total_cents: int,
        lines: List[Tuple[int, str, str, int, int]],
    ) -> None:
        now = datetime.now().isoformat(timespec="seconds")

        number = (number or "").strip()
        number_db = number if number else None

        self.conn.execute(
            """
            UPDATE invoice
            SET number = ?,
                date = ?,
                customer_name = ?,
                customer_address = ?,
                customer_postal_code = ?,
                customer_email = ?,
                customer_phone = ?,
                subtotal_cents = ?,
                vat_rate = ?,
                vat_cents = ?,
                total_cents = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                number_db,
                date_iso,
                customer_name.strip(),
                customer_address.strip(),
                customer_postal_code.strip(),
                customer_email.strip(),
                customer_phone.strip(),
                int(subtotal_cents),
                int(vat_rate),
                int(vat_cents),
                int(total_cents),
                now,
                int(invoice_id),
            ),
        )

        # Remplacer toutes les lignes (simple et fiable)
        self.conn.execute("DELETE FROM invoice_line WHERE invoice_id = ?", (invoice_id,))

        for idx, (qty, reference, desc, up_cents, lt_cents) in enumerate(lines, start=1):
            self.conn.execute(
                """
                INSERT INTO invoice_line (
                    invoice_id, position, qty, reference, description, unit_price_cents, line_total_cents
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(invoice_id),
                    int(idx),
                    int(qty),
                    (reference or "").strip(),
                    (desc or "").strip(),
                    int(up_cents),
                    int(lt_cents),
                ),
            )

        self.conn.commit()

    def _next_number(self) -> str:
        cur = self.conn.execute("SELECT value FROM counter WHERE key = 'invoice_number'")
        row = cur.fetchone()
        if not row:
            raise ValueError("Compteur de factures introuvable.")
        n = int(row["value"])
        return f"{n:03d}"

    def _advance_counter_if_needed(self, used_number: str) -> None:
        try:
            used = int(used_number)
        except Exception:
            return

        cur = self.conn.execute("SELECT value FROM counter WHERE key = 'invoice_number'")
        row = cur.fetchone()
        if not row:
            return
        current = int(row["value"])
        target = max(current, used + 1)
        if target != current:
            self.conn.execute(
                "UPDATE counter SET value = ? WHERE key = 'invoice_number'",
                (target,),
            )

    def finalize(self, invoice_id: int) -> str:
        header = self.get_header(invoice_id)

        number = (header.number or "").strip()
        auto_generated = False

        if auto_generated:
            cur = self.conn.execute("SELECT value FROM counter WHERE key = 'invoice_number'")
            n = int(cur.fetchone()["value"])
            self.conn.execute(
                "UPDATE counter SET value = ? WHERE key = 'invoice_number'",
                (n + 1,),
            )
        else:
            self._advance_counter_if_needed(number)

        self.conn.commit()
        return number

    def delete(self, invoice_id: int) -> None:
        self.conn.execute("DELETE FROM invoice WHERE id = ?", (invoice_id,))
        self.conn.commit()
