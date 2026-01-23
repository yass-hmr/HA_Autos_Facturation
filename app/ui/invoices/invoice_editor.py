from __future__ import annotations

import re

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QLabel,
    QMessageBox,
    QComboBox,
    QHeaderView,
)

from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.pdf_repo import PdfExportRepository
from app.pdf.render_invoice import render_invoice_pdf
from app.utils.paths import exports_dir

def _safe_filename_part(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

@dataclass(frozen=True)
class _LineUI:
    qty: int
    description: str
    unit_price_eur: str  # saisi en HT


class InvoiceEditorWidget(QWidget):
    tab_title_changed = Signal(str)
    invoice_persisted = Signal(int)
    closed = Signal()

    def __init__(
        self,
        *,
        repo: InvoiceRepository,
        backup_scheduler,
        pdf_repo: PdfExportRepository,
        invoice_id: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.pdf_repo = pdf_repo
        self.backup = backup_scheduler

        self.invoice_id: Optional[int] = invoice_id

        self._build_ui()
        self._load_or_init()
        self._refresh_totals()
        self._emit_tab_title()

    # ---------------- UI ----------------
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Entête facture
        form = QFormLayout()
        self.in_number = QLineEdit()
        self.in_date = QLineEdit()
        self.in_date.setText(date.today().isoformat())

        self.in_customer_name = QLineEdit()
        self.in_customer_address = QTextEdit()
        self.in_customer_address.setFixedHeight(60)
        self.in_customer_cp = QLineEdit()

        form.addRow("N° de facture", self.in_number)
        form.addRow("Date", self.in_date)
        form.addRow("Destinataire", self.in_customer_name)
        form.addRow("Adresse", self.in_customer_address)
        form.addRow("Code postal", self.in_customer_cp)

        layout.addLayout(form)

        # Lignes
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Qté", "Description", "Prix unitaire", "Total"])
        self.table.setEditTriggers(QTableWidget.AllEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 120)
        layout.addWidget(self.table, stretch=1)

        # Totaux
        totals = QHBoxLayout()
        self.lbl_subtotal = QLabel("Sous-total (HT) : 0.00 €")
        self.lbl_vat = QLabel("TVA (20%) : 0.00 €")
        self.lbl_total = QLabel("Total (TTC) : 0.00 €")
        totals.addWidget(self.lbl_subtotal)
        totals.addWidget(self.lbl_vat)
        totals.addWidget(self.lbl_total)
        totals.addStretch()
        layout.addLayout(totals)
        
        # Boutons lignes
        line_actions = QHBoxLayout()
        btn_add = QPushButton("Ajouter ligne")
        btn_del = QPushButton("Supprimer ligne")
        btn_add.clicked.connect(self._add_line)
        btn_del.clicked.connect(self._remove_selected_line)
        line_actions.addWidget(btn_add)
        line_actions.addWidget(btn_del)
        line_actions.addStretch()
        layout.addLayout(line_actions)

        # Actions
        actions = QHBoxLayout()
        self.btn_save = QPushButton("Enregistrer")
        self.btn_export = QPushButton("Exporter PDF")
        self.btn_close = QPushButton("Fermer")

        self.btn_save.clicked.connect(self._save_draft)
        self.btn_export.clicked.connect(self._export_pdf)
        self.btn_close.clicked.connect(self._on_close)

        actions.addWidget(self.btn_save)
        actions.addWidget(self.btn_export)
        actions.addStretch()
        actions.addWidget(self.btn_close)
        layout.addLayout(actions)

        self.table.itemChanged.connect(lambda *_: self._refresh_totals())
        self.in_number.textChanged.connect(lambda *_: self._emit_tab_title())

    # ---------------- Data load/save ----------------
    def _load_or_init(self) -> None:
        if self.invoice_id is None:
            # Nouveau brouillon en mémoire; persisté au premier Enregistrer/Exporter
            return
        h = self.repo.get_header(self.invoice_id)
        self.in_number.setText(h.number or "")
        self.in_date.setText(h.date or "")
        self.in_customer_name.setText(h.customer_name or "")
        self.in_customer_address.setPlainText(h.customer_address or "")
        self.in_customer_cp.setText(h.customer_postal_code or "")

        self.table.setRowCount(0)
        for ln in self.repo.get_lines(self.invoice_id):
            self._append_line(qty=ln.qty, description=ln.description, unit_price_cents=ln.unit_price_cents)

    def _ensure_persisted(self) -> None:
        if self.invoice_id is not None:
            return

        date_iso = (self.in_date.text().strip() or date.today().isoformat())
        self.invoice_id = self.repo.create_draft(date_iso)

        self.invoice_persisted.emit(self.invoice_id)
        self.backup.mark_dirty()

    def _collect_lines(self) -> list[_LineUI]:
        out: list[_LineUI] = []
        for r in range(self.table.rowCount()):
            qty_item = self.table.item(r, 0)
            desc_item = self.table.item(r, 1)
            unit_item = self.table.item(r, 2)

            qty = int(qty_item.text()) if qty_item and qty_item.text().strip().isdigit() else 0
            desc = (desc_item.text() if desc_item else "").strip()
            unit = (unit_item.text() if unit_item else "").strip()
            out.append(_LineUI(qty=qty, description=desc, unit_price_eur=unit))
        return out

    def _eur_to_cents(self, s: str) -> int:
        s = (s or "").replace("€", "").strip().replace(",", ".")
        if not s:
            return 0
        try:
            v = float(s)
        except ValueError:
            return 0
        return int(round(v * 100))
    
    def _compute_totals_from_table(self) -> tuple[int, int, int, list[tuple[int, str, int, int]]]:
        """
        Retourne: (subtotal_cents, vat_cents, total_cents, lines_payload)
        lines_payload: List[(qty, desc, unit_price_cents, line_total_cents)]
        """
        vat_rate = 20
        lines_payload: list[tuple[int, str, int, int]] = []
        subtotal_cents = 0

        for r in range(self.table.rowCount()):
            qty_item = self.table.item(r, 0)
            desc_item = self.table.item(r, 1)
            unit_item = self.table.item(r, 2)

            qty = int(qty_item.text()) if qty_item and qty_item.text().strip().isdigit() else 0
            desc = (desc_item.text() if desc_item else "").strip()
            unit_cents = self._eur_to_cents(unit_item.text() if unit_item else "")

            line_total_cents = qty * unit_cents
            subtotal_cents += line_total_cents
            lines_payload.append((qty, desc, unit_cents, line_total_cents))

        vat_cents = (subtotal_cents * vat_rate) // 100  # 20% => exact en cents
        total_cents = subtotal_cents + vat_cents
        return subtotal_cents, vat_cents, total_cents, lines_payload
    def _save_draft(self) -> None:
        try:
            self._ensure_persisted()
            assert self.invoice_id is not None

            # 1) Calcul totaux depuis le tableau (PU saisi en HT)
            subtotal_cents, vat_cents, total_cents, lines_payload = self._compute_totals_from_table()

            # 2) Sauvegarde en base (en-tête + lignes)
            number = (self.in_number.text() or "").strip() or None
            date_iso = (self.in_date.text().strip() or date.today().isoformat())

            self.repo.save_invoice(
                self.invoice_id,
                number=number,
                date_iso=date_iso,
                customer_name=(self.in_customer_name.text() or "").strip(),
                customer_address=(self.in_customer_address.toPlainText() or "").strip(),
                customer_postal_code=(self.in_customer_cp.text() or "").strip(),
                subtotal_cents=subtotal_cents,
                vat_rate=20,
                vat_cents=vat_cents,
                total_cents=total_cents,
                lines=lines_payload,
            )

            # 4) UI
            self.backup.mark_dirty()
            self._refresh_totals()
            self._emit_tab_title()

            QMessageBox.information(self, "Facture", "Enregistrée.")
        except Exception as e:
            QMessageBox.warning(self, "Facture", str(e))

    # ---------------- PDF ----------------
    def _export_pdf(self) -> None:
        try:
            self._ensure_persisted()
            self._save_draft()
            assert self.invoice_id is not None

            header = self.repo.get_header(self.invoice_id)
            inv_number = (header.number or "").strip() or "SANS_NUMERO"
            client_name = _safe_filename_part(header.customer_name) or "Client"

            filename = f"Facture_{_safe_filename_part(inv_number)}_{client_name}.pdf"
            out_path = exports_dir() / filename

            # Écrase si existe déjà (facture mise à jour)
            try:
                if out_path.exists():
                    out_path.unlink()
            except Exception:
                pass

            result = render_invoice_pdf(
                conn=self.repo.conn,
                invoice_id=self.invoice_id,
                out_path=out_path,
            )

            pdf_path = Path(result.pdf_path)
            if not pdf_path.exists():
                raise RuntimeError(f"PDF non trouvé après génération : {pdf_path.resolve()}")

            # Remplacer l'export INVOICE pour cette facture (pas de doublons en base)
            self.pdf_repo.replace_invoice_export(
                invoice_id=self.invoice_id,
                filename=pdf_path.name,
                rel_path=f"exports/{pdf_path.name}",
            )

            self.backup.mark_dirty()

            try:
                import os
                os.startfile(str(pdf_path.parent.resolve()))
            except Exception:
                pass

            QMessageBox.information(self, "PDF", f"PDF généré :\n{pdf_path.resolve()}")
        except Exception as e:
            QMessageBox.warning(self, "PDF", str(e))


    # ---------------- Helpers ----------------
    def _append_line(self, *, qty: int, description: str, unit_price_cents: int) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)

        self.table.setItem(r, 0, QTableWidgetItem(str(qty)))
        self.table.setItem(r, 1, QTableWidgetItem(description))
        self.table.setItem(r, 2, QTableWidgetItem(f"{unit_price_cents/100:.2f}"))
        self.table.setItem(r, 3, QTableWidgetItem(f"{(qty*unit_price_cents)/100:.2f}"))

    def _add_line(self) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("1"))
        self.table.setItem(r, 1, QTableWidgetItem(""))
        self.table.setItem(r, 2, QTableWidgetItem("0.00"))
        self.table.setItem(r, 3, QTableWidgetItem("0.00"))

    def _remove_selected_line(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)
        self._refresh_totals()

    def _refresh_totals(self) -> None:
        if self.invoice_id is None:
            subtotal = vat = total = 0
        else:
            h = self.repo.get_header(self.invoice_id)
            subtotal = h.subtotal_cents
            vat = h.vat_cents
            total = h.total_cents

        self.lbl_subtotal.setText(f"Sous-total (HT) : {subtotal/100:.2f} €")
        self.lbl_vat.setText(f"TVA (20%) : {vat/100:.2f} €")
        self.lbl_total.setText(f"Total (TTC) : {total/100:.2f} €")

    def current_tab_title(self) -> str:
        base = self.in_number.text().strip()

    def _emit_tab_title(self) -> None:
        self.tab_title_changed.emit(self.current_tab_title())

    def _on_close(self) -> None:
        self.closed.emit()
