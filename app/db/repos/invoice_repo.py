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
    subtotal_cents: int
    vat_rate: int
    vat_cents: int
    total_cents: int


@dataclass(frozen=True)
class InvoiceLine:
    id: int
    invoice_id: int
    position: int
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
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute(
            """
            INSERT INTO invoice (number, date, customer_name, customer_address, customer_postal_code,
                                 subtotal_cents, vat_rate, vat_cents, total_cents,
                                 created_at, updated_at)
            VALUES (NULL, ?, 'DRAFT', '', '', '', 0, 20, 0, 0, ?, ?)
            """,
            (date_iso, now, now),
        )
        self.conn.commit()
        return int(cur.lastrowid)

    def get_header(self, invoice_id: int) -> InvoiceHeader:
        cur = self.conn.execute(
            """
            SELECT id, number, date, customer_name, customer_address, customer_postal_code,
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
            subtotal_cents=row["subtotal_cents"],
            vat_rate=row["vat_rate"],
            vat_cents=row["vat_cents"],
            total_cents=row["total_cents"],
        )

    def get_lines(self, invoice_id: int) -> List[InvoiceLine]:
        cur = self.conn.execute(
            """
            SELECT id, invoice_id, position, qty, description,
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
        subtotal_cents: int,
        vat_rate: int,
        vat_cents: int,
        total_cents: int,
        lines: List[Tuple[int, str, int, int]],
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
                int(subtotal_cents),
                int(vat_rate),
                int(vat_cents),
                int(total_cents),
                now,
                int(invoice_id),
            ),
        )

        self.conn.execute("DELETE FROM invoice_line WHERE invoice_id = ?", (invoice_id,))
        for idx, (qty, desc, up_cents, lt_cents) in enumerate(lines, start=1):
            self.conn.execute(
                """
                INSERT INTO invoice_line (invoice_id, position, qty, description, unit_price_cents, line_total_cents)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (invoice_id, idx, int(qty), desc.strip(), int(up_cents), int(lt_cents)),
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
        # Si l'utilisateur force un numéro numérique, on avance le compteur pour éviter collisions
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

    def delete(self, invoice_id: int) -> None:
        header = self.get_header(invoice_id)
        self.conn.execute("DELETE FROM invoice WHERE id = ?", (invoice_id,))
        self.conn.commit()
