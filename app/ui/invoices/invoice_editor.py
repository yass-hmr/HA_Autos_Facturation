from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date as _date
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QLabel,
    QAbstractItemView,
)

from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.pdf_repo import PdfExportRepository
from app.utils.paths import exports_dir
from app.pdf.render_invoice import render_invoice_pdf
from app.utils.dates import today_fr, fr_to_iso, iso_to_fr



# =========================
# Helpers date FR <-> ISO
# =========================

def _safe_filename_part(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def wrap_n_chars(text: str, n: int) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    if len(text) <= n:
        return text
    out = []
    for i in range(0, len(text), n):
        out.append(text[i : i + n])
    return "\n".join(out)


@dataclass
class _Line:
    qty: int
    reference: str
    description: str
    unit_price_eur: str  # saisie utilisateur
    total_eur: str       # affichage


class InvoiceEditorWidget(QWidget):
    """
    Éditeur de facture (onglet).
    - Date saisissable en jj/mm/aaaa, auto si vide
    - Champs client: nom, adresse, CP, email, téléphone
    - Lignes: Qté, Référence, Description, Prix unitaire (HT), Total
    """

    # Optionnel : si tu veux mettre à jour le titre d’onglet depuis MainWindow
    tab_title_changed = Signal(str)
    invoice_persisted = Signal(int)
    closed = Signal()

    def __init__(
        self,
        *,
        repo: InvoiceRepository,
        pdf_repo: PdfExportRepository,
        backup_scheduler,
        invoice_id: Optional[int] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repo = repo
        self.pdf_repo = pdf_repo
        self.backup = backup_scheduler
        self.invoice_id: Optional[int] = invoice_id

        self._build_ui()
        self._load_or_create()

    # -------------------------
    # UI
    # -------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Header fields
        form_row = QHBoxLayout()
        left_form = QFormLayout()
        right_form = QFormLayout()

        self.number_edit = QLineEdit()
        self.number_edit.setPlaceholderText("ex: 001")
        left_form.addRow("N° de facture", self.number_edit)

        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("jj/mm/aaaa")
        left_form.addRow("Date", self.date_edit)

        self.customer_name = QLineEdit()
        left_form.addRow("Nom client", self.customer_name)

        self.customer_address = QLineEdit()
        left_form.addRow("Adresse", self.customer_address)

        self.customer_postal_code = QLineEdit()
        self.customer_postal_code.setPlaceholderText("Code postal")
        left_form.addRow("Code postal", self.customer_postal_code)

        self.customer_phone = QLineEdit()
        self.customer_phone.setPlaceholderText("Téléphone")
        right_form.addRow("Téléphone", self.customer_phone)

        self.customer_email = QLineEdit()
        self.customer_email.setPlaceholderText("Email")
        right_form.addRow("E-mail", self.customer_email)

        form_row.addLayout(left_form, 2)
        form_row.addSpacing(16)
        form_row.addLayout(right_form, 1)
        root.addLayout(form_row)

        # --- Table lines
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Qté", "Référence", "Description", "Prix unitaire", "Total"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

        # Wrap + hauteur auto (pour référence/description)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)

        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 120)

        self.table.itemChanged.connect(self._recalc_from_table)

        root.addWidget(self.table, 1)

        # --- Actions lines
        line_actions = QHBoxLayout()
        btn_add = QPushButton("Ajouter ligne")
        btn_add.clicked.connect(self._append_line)
        btn_del = QPushButton("Supprimer ligne")
        btn_del.clicked.connect(self._delete_selected_line)

        line_actions.addWidget(btn_add)
        line_actions.addWidget(btn_del)
        line_actions.addStretch()
        root.addLayout(line_actions)

        # --- Totals
        totals_row = QHBoxLayout()
        self.lbl_subtotal = QLabel("Sous-total (HT) : 0.00 €")
        self.lbl_vat = QLabel("TVA (20%) : 0.00 €")
        self.lbl_total = QLabel("Total (TTC) : 0.00 €")
        totals_row.addWidget(self.lbl_subtotal)
        totals_row.addSpacing(18)
        totals_row.addWidget(self.lbl_vat)
        totals_row.addSpacing(18)
        totals_row.addWidget(self.lbl_total)
        totals_row.addStretch()
        root.addLayout(totals_row)

        # --- Bottom actions
        bottom = QHBoxLayout()
        self.btn_save = QPushButton("Enregistrer")
        self.btn_save.clicked.connect(self._save_draft)

        self.btn_export = QPushButton("Exporter PDF")
        self.btn_export.clicked.connect(self._export_pdf)

        bottom.addWidget(self.btn_save)
        bottom.addWidget(self.btn_export)
        bottom.addStretch()
        root.addLayout(bottom)

    # -------------------------
    # Load / create
    # -------------------------
    def _load_or_create(self) -> None:
        if self.invoice_id is None:
            # crée une facture vide avec date du jour ISO
            new_id = self.repo.create_draft(_date.today().isoformat())
            self.invoice_id = new_id
            self.invoice_persisted.emit(new_id)

        self._load_invoice()
        self._emit_title()

    def _load_invoice(self) -> None:
        assert self.invoice_id is not None
        h = self.repo.get_header(self.invoice_id)

        self.number_edit.setText((h.number or "").strip())
        self.date_edit.setText(iso_to_fr(h.date))

        self.customer_name.setText(h.customer_name or "")
        self.customer_address.setText(h.customer_address or "")
        self.customer_postal_code.setText(h.customer_postal_code or "")
        self.customer_email.setText(getattr(h, "customer_email", "") or "")
        self.customer_phone.setText(getattr(h, "customer_phone", "") or "")

        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for ln in self.repo.get_lines(self.invoice_id):
            self._insert_line_row(
                qty=str(ln.qty),
                reference=getattr(ln, "reference", "") or "",
                description=ln.description or "",
                unit_price=f"{ln.unit_price_cents/100:.2f}",
                total=f"{ln.line_total_cents/100:.2f}",
            )
        self.table.blockSignals(False)

        self._recalc_totals()
        self.table.resizeRowsToContents()

    # -------------------------
    # Table helpers
    # -------------------------
    def _insert_line_row(
        self,
        *,
        qty: str,
        reference: str,
        description: str,
        unit_price: str,
        total: str,
    ) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)

        it_qty = QTableWidgetItem(qty)
        it_ref = QTableWidgetItem(wrap_n_chars(reference, 18))
        it_desc = QTableWidgetItem(wrap_n_chars(description, 40))
        it_unit = QTableWidgetItem(unit_price)
        it_total = QTableWidgetItem(total)

        # Tooltips = valeur brute
        it_ref.setToolTip(reference)
        it_desc.setToolTip(description)

        # Align
        it_qty.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        it_unit.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        it_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Total non éditable
        it_total.setFlags(it_total.flags() & ~Qt.ItemIsEditable)

        self.table.setItem(r, 0, it_qty)
        self.table.setItem(r, 1, it_ref)
        self.table.setItem(r, 2, it_desc)
        self.table.setItem(r, 3, it_unit)
        self.table.setItem(r, 4, it_total)

    def _append_line(self) -> None:
        self.table.blockSignals(True)
        self._insert_line_row(qty="1", reference="", description="", unit_price="0.00", total="0.00")
        self.table.blockSignals(False)
        self.table.resizeRowsToContents()

    def _delete_selected_line(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            return
        self.table.blockSignals(True)
        self.table.removeRow(row)
        self.table.blockSignals(False)
        self._recalc_totals()

    # -------------------------
    # Recalc
    # -------------------------
    def _recalc_from_table(self) -> None:
        # recalcul ligne modifiée + totaux
        self._recalc_totals()

    @staticmethod
    def _parse_qty(s: str) -> int:
        s = (s or "").strip()
        if not s:
            return 0
        try:
            return max(0, int(s))
        except Exception:
            return 0

    @staticmethod
    def _parse_eur_to_cents(s: str) -> int:
        s = (s or "").strip().replace(",", ".")
        if not s:
            return 0
        try:
            v = float(s)
        except Exception:
            return 0
        # pas d'arrondi “comptable” : on convertit au centime
        return int(round(v * 100))

    def _recalc_totals(self) -> None:
        subtotal_cents = 0

        self.table.blockSignals(True)
        for r in range(self.table.rowCount()):
            qty = self._parse_qty(self._item_text(r, 0))
            up_cents = self._parse_eur_to_cents(self._item_text(r, 3))
            line_total_cents = qty * up_cents
            subtotal_cents += line_total_cents

            it_total = self.table.item(r, 4)
            if it_total is None:
                it_total = QTableWidgetItem()
                it_total.setFlags(it_total.flags() & ~Qt.ItemIsEditable)
                it_total.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, 4, it_total)
            it_total.setText(f"{line_total_cents/100:.2f}")
        self.table.blockSignals(False)

        vat_rate = 20
        vat_cents = (subtotal_cents * vat_rate) // 100
        total_cents = subtotal_cents + vat_cents

        self.lbl_subtotal.setText(f"Sous-total (HT) : {subtotal_cents/100:.2f} €")
        self.lbl_vat.setText(f"TVA (20%) : {vat_cents/100:.2f} €")
        self.lbl_total.setText(f"Total (TTC) : {total_cents/100:.2f} €")

        self.table.resizeRowsToContents()

    def _item_text(self, row: int, col: int) -> str:
        it = self.table.item(row, col)
        return (it.text() if it else "").strip()

    # -------------------------
    # Save
    # -------------------------
    def _ensure_persisted(self) -> None:
        if self.invoice_id is None:
            self.invoice_id = self.repo.create_draft(_date.today().isoformat())

    def _collect_lines_for_save(self) -> List[Tuple[int, str, str, int, int]]:
        """
        Retourne une liste de lignes pour repo.save_invoice, format:
        (qty, reference, description, unit_price_cents, line_total_cents)
        """
        out: List[Tuple[int, str, str, int, int]] = []
        for r in range(self.table.rowCount()):
            qty = self._parse_qty(self._item_text(r, 0))

            # IMPORTANT: on enregistre le TEXTE ACTUEL (celui édité), pas le tooltip
            reference = self._item_text(r, 1).strip()
            description = self._item_text(r, 2).strip()

            up_cents = self._parse_eur_to_cents(self._item_text(r, 3))
            lt_cents = qty * up_cents

            if qty == 0 and not reference and not description and up_cents == 0:
                continue

            out.append((qty, reference, description, up_cents, lt_cents))
        return out

    def _save_draft(self) -> None:
        try:
            self._ensure_persisted()
            assert self.invoice_id is not None

            # Date FR -> ISO ; si vide, on auto-remplit
            if not self.date_edit.text().strip():
                self.date_edit.setText(today_fr())
            date_iso = fr_to_iso(self.date_edit.text())

            lines = self._collect_lines_for_save()

            # Calcul totaux cohérents avec table
            subtotal_cents = 0
            for qty, _ref, _desc, up_cents, lt_cents in lines:
                subtotal_cents += lt_cents

            vat_rate = 20
            vat_cents = (subtotal_cents * vat_rate) // 100
            total_cents = subtotal_cents + vat_cents

            self.repo.save_invoice(
                self.invoice_id,
                number=self.number_edit.text(),
                date_iso=date_iso,
                customer_name=self.customer_name.text(),
                customer_address=self.customer_address.text(),
                customer_postal_code=self.customer_postal_code.text(),
                customer_email=self.customer_email.text(),
                customer_phone=self.customer_phone.text(),
                subtotal_cents=subtotal_cents,
                vat_rate=vat_rate,
                vat_cents=vat_cents,
                total_cents=total_cents,
                lines=lines,  # type: ignore[arg-type]
            )
            
            QMessageBox.information(
                self,
                "Facture",
                "✅ Facture enregistrée avec succès."
            )
            self.backup.mark_dirty()
            self._emit_title()
            self.invoice_persisted.emit(self.invoice_id)
        except Exception as e:
            QMessageBox.warning(self, "Enregistrer", str(e))

    # -------------------------
    # PDF
    # -------------------------
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

            # Écrase si déjà existant
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

            self.pdf_repo.replace_invoice_export(
                invoice_id=self.invoice_id,
                filename=pdf_path.name,
                rel_path=f"exports/{pdf_path.name}",
            )

            self.backup.mark_dirty()

            # Ouvrir le dossier exports
            try:
                import os
                os.startfile(str(pdf_path.parent.resolve()))
            except Exception:
                pass

            QMessageBox.information(self, "PDF", f"PDF généré :\n{pdf_path.resolve()}")
        except Exception as e:
            QMessageBox.warning(self, "PDF", str(e))

    # -------------------------
    # Tab title
    # -------------------------
    def _emit_title(self) -> None:
        # Onglet = "Facture" par défaut, puis "Facture - <num>" si dispo
        num = (self.number_edit.text() or "").strip()
        title = "Facture" if not num else f"Facture - {num}"
        self.tab_title_changed.emit(title)



    def closeEvent(self, event) -> None:
        try:
            self.closed.emit()
        finally:
            super().closeEvent(event)
