from __future__ import annotations

import os
import re
import shutil
import sqlite3
from pathlib import Path
from urllib.parse import quote

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QFileDialog,
)

from app.db.repos.pdf_repo import PdfExportRepository
from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.settings_repo import SettingsRepository
from app.utils.paths import exports_dir


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _safe_filename_part(s: str) -> str:
    s = (s or "").strip()
    # remplace caractères interdits Windows: \ / : * ? " < > |
    s = re.sub(r'[\\/:*?"<>|]+', "-", s)
    # compresser espaces
    s = re.sub(r"\s+", " ", s).strip()
    return s

class ShareEmailDialog(QDialog):
    def __init__(self, parent=None, *, default_folder: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle("Partager par e-mail")

        self.email = QLineEdit()
        self.email.setPlaceholderText("ex: client@gmail.com")

        layout = QFormLayout(self)
        layout.addRow("Destinataire", self.email)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_email(self) -> str:
        return self.email.text().strip()

class PdfListWidget(QWidget):
    def __init__(self, repo: PdfExportRepository, *, conn: sqlite3.Connection, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.conn = conn
        self.invoice_repo = InvoiceRepository(conn)
        self.settings_repo = SettingsRepository(conn)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "Facture", "Fichier", "Date", "Type"])
        self.table.setColumnHidden(0, True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.doubleClicked.connect(self._open_selected)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(3, 170)
        self.table.setColumnWidth(4, 90)

        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()

        btn_open = QPushButton("Ouvrir")
        btn_open.clicked.connect(self._open_selected)

        btn_delete = QPushButton("Supprimer")
        btn_delete.clicked.connect(self._delete_selected)

        btn_refresh = QPushButton("Rafraîchir")
        btn_refresh.clicked.connect(self.refresh)

        btn_share = QPushButton("Partager")
        btn_share.clicked.connect(self._share_selected)
        
        btn_print = QPushButton("Imprimer")
        btn_print.clicked.connect(self._print_selected)
        actions.addWidget(btn_print)

        actions.addWidget(btn_open)
        actions.addWidget(btn_delete)
        actions.addWidget(btn_refresh)
        actions.addWidget(btn_share)
        actions.addStretch()

        layout.addLayout(actions)

    def refresh(self) -> None:
        items = self.repo.list_all()
        self.table.setRowCount(0)

        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, QTableWidgetItem(str(it.id)))
            self.table.setItem(r, 1, QTableWidgetItem(str(it.invoice_id)))
            self.table.setItem(r, 2, QTableWidgetItem(it.filename))
            self.table.setItem(r, 3, QTableWidgetItem(it.created_at))
            self.table.setItem(r, 4, QTableWidgetItem(it.kind))

    def _selected_row(self) -> int | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        return sel[0].row()

    def _selected_pdf_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        return int(self.table.item(row, 0).text())

    def _selected_invoice_id(self) -> int | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self.table.item(row, 1)
        if not item:
            return None
        try:
            return int(item.text())
        except Exception:
            return None

    def _selected_filename(self) -> str | None:
        row = self._selected_row()
        if row is None:
            return None
        item = self.table.item(row, 2)  # colonne "Fichier"
        return item.text().strip() if item else None

    def _open_selected(self) -> None:
        filename = self._selected_filename()
        if not filename:
            QMessageBox.information(self, "Ouvrir", "Sélectionnez un PDF.")
            return

        pdf_path = exports_dir() / filename
        if not pdf_path.exists():
            QMessageBox.warning(self, "Ouvrir", f"Fichier introuvable : {pdf_path.resolve()}")
            return

        try:
            os.startfile(str(pdf_path))
        except Exception as e:
            QMessageBox.warning(self, "Ouvrir", str(e))

    def _delete_selected(self) -> None:
        pdf_id = self._selected_pdf_id()
        if pdf_id is None:
            QMessageBox.information(self, "Supprimer", "Sélectionnez un PDF.")
            return

        item = self.repo.get_by_id(pdf_id)
        if item is None:
            QMessageBox.warning(self, "Supprimer", "PDF introuvable en base.")
            self.refresh()
            return

        filename = item.filename
        pdf_path = exports_dir() / filename

        if QMessageBox.question(
            self,
            "Supprimer",
            f"Supprimer définitivement ce PDF ?\n\nFichier : {filename}\nFacture (ID) : {item.invoice_id}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return

        try:
            if pdf_path.exists():
                pdf_path.unlink()
        except Exception as e:
            QMessageBox.warning(self, "Supprimer", f"Impossible de supprimer le fichier : {e}")
            return

        try:
            self.repo.delete(pdf_id)
        except Exception as e:
            QMessageBox.warning(self, "Supprimer", f"Fichier supprimé, mais erreur BDD : {e}")
            return

        self.refresh()

    def _share_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Partager", "Sélectionnez un PDF.")
            return

        filename_item = self.table.item(row, 2)  # colonne "Fichier"
        invoice_item = self.table.item(row, 1)   # colonne "Facture"
        if not filename_item or not invoice_item:
            QMessageBox.warning(self, "Partager", "Sélection invalide.")
            return

        filename = filename_item.text().strip()
        try:
            invoice_id = int(invoice_item.text())
        except Exception:
            invoice_id = 0

        pdf_path = exports_dir() / filename
        if not pdf_path.exists():
            QMessageBox.warning(self, "Partager", f"Fichier introuvable : {pdf_path.resolve()}")
            return

        # Saisie e-mail
        dlg = ShareEmailDialog(self)
        if dlg.exec() != QDialog.Accepted:
            return

        to_email = dlg.get_email().strip()
        if not to_email or not _EMAIL_RE.match(to_email):
            QMessageBox.warning(self, "Partager", "Adresse e-mail invalide.")
            return

        # Données dynamiques
        client_name = "Client"
        inv_number = Path(filename).stem
        if invoice_id:
            header = self.invoice_repo.get_header(invoice_id)
            client_name = (header.customer_name or "").strip() or "Client"
            inv_number = (header.number or "").strip() or inv_number

        s = self.settings_repo.get()
        g_name = (s.get("garage_name") or "HA AUTOS").strip()
        g_addr = (s.get("garage_address") or "").strip()
        g_cp = (s.get("garage_postal_code") or "").strip()
        g_phone = (s.get("garage_phone") or "").strip()
        g_siret = (s.get("garage_siret") or "").strip()

        subject = f"Facture n°{inv_number} – {client_name}"
        body_lines = [
            "Bonjour,",
            "",
            f"Veuillez trouver ci-joint votre facture n°{inv_number}.",
            "",
            "N’hésitez pas à nous contacter pour toute question ou information complémentaire.",
            "",
            "Cordialement,",
            "",
            g_name,
        ]
        if g_siret:
            body_lines.append(g_siret)
        if g_addr:
            body_lines.append(g_addr)
        if g_cp:
            body_lines.append(g_cp)
        if g_phone:
            body_lines.append(g_phone)
        

        body = "\n".join(body_lines)

        mailto = f"mailto:{quote(to_email)}?subject={quote(subject)}&body={quote(body)}"
        QDesktopServices.openUrl(QUrl(mailto))

        # Ouvre le dossier exports pour joindre vite
        try:
            os.startfile(str(exports_dir().resolve()))
        except Exception:
            pass
    
    def _print_selected(self) -> None:
        filename = self._selected_filename()
        if not filename:
            QMessageBox.information(self, "Imprimer", "Sélectionnez un PDF.")
            return

        pdf_path = exports_dir() / filename
        if not pdf_path.exists():
            QMessageBox.warning(self, "Imprimer", f"Fichier introuvable : {pdf_path.resolve()}")
            return

        try:
            # Ouvre le dialogue d’impression du lecteur PDF par défaut
            os.startfile(str(pdf_path), "print")
        except Exception as e:
            QMessageBox.warning(self, "Imprimer", f"Impossible de lancer l’impression : {e}")

