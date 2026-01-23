from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QTableWidget,
    QTableWidgetItem, QMessageBox, QHeaderView
)

from app.db.repos.invoice_repo import InvoiceRepository
from app.domain.money import cents_to_euros


class InvoiceListWidget(QWidget):
    open_invoice = Signal(int)  # invoice_id (0 = nouvelle facture non persistée)

    def __init__(self, repo: InvoiceRepository, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher (001, nom, date)…")
        self.search.returnPressed.connect(self.refresh)

        btn_new = QPushButton("Nouvelle facture")
        btn_new.clicked.connect(self._new_invoice)

        btn_refresh = QPushButton("Rafraîchir")
        btn_refresh.clicked.connect(self.refresh)

        top.addWidget(self.search)
        top.addWidget(btn_new)
        top.addWidget(btn_refresh)
        layout.addLayout(top)

        # 5 colonnes : ID (caché), N°, Date, Destinataire, Total TTC
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ID", "N°", "Date", "Destinataire", "Total TTC"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setColumnHidden(0, True)
        self.table.doubleClicked.connect(self._open_selected)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Fixed)    # N°
        header.setSectionResizeMode(2, QHeaderView.Fixed)    # Date
        header.setSectionResizeMode(4, QHeaderView.Fixed)    # Total
        header.setSectionResizeMode(3, QHeaderView.Stretch)  # Destinataire

        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(4, 170)

        self.table.setStyleSheet("""
            QTableWidget::item { padding-right: 8px; padding-left: 6px; }
        """)

        layout.addWidget(self.table, stretch=1)

        actions = QHBoxLayout()

        btn_open = QPushButton("Ouvrir")
        btn_open.clicked.connect(self._open_selected)

        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self._cancel_selected)

        btn_delete = QPushButton("Supprimer")
        btn_delete.clicked.connect(self._delete_selected)

        actions.addWidget(btn_open)
        actions.addWidget(btn_cancel)
        actions.addWidget(btn_delete)
        actions.addStretch()
        layout.addLayout(actions)

    def refresh(self) -> None:
        items = self.repo.list_invoices(self.search.text())
        self.table.setRowCount(0)

        for it in items:
            r = self.table.rowCount()
            self.table.insertRow(r)

            # ID (caché)
            self.table.setItem(r, 0, QTableWidgetItem(str(it.id)))

            # N° + statut
            number = (it.number or "(Brouillon)")

            self.table.setItem(r, 1, QTableWidgetItem(number))

            # Date
            self.table.setItem(r, 2, QTableWidgetItem(it.date))

            # Destinataire
            self.table.setItem(r, 3, QTableWidgetItem(it.customer_name))

            # Total TTC
            total_item = QTableWidgetItem(cents_to_euros(it.total_cents))
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 4, total_item)

    def _selected_invoice_id(self) -> int | None:
        sel = self.table.selectionModel().selectedRows()
        if not sel:
            return None
        row = sel[0].row()
        return int(self.table.item(row, 0).text())

    def _new_invoice(self) -> None:
        self.open_invoice.emit(0)

    def _open_selected(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            QMessageBox.information(self, "Ouvrir", "Sélectionnez une facture.")
            return
        self.open_invoice.emit(invoice_id)

    def _cancel_selected(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            QMessageBox.information(self, "Annuler", "Sélectionnez une facture.")
            return
        try:
            self.repo.cancel(invoice_id)
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Annuler", str(e))

    def _delete_selected(self) -> None:
        invoice_id = self._selected_invoice_id()
        if invoice_id is None:
            QMessageBox.information(self, "Supprimer", "Sélectionnez une facture.")
            return

        if QMessageBox.question(self, "Supprimer", "Supprimer ce brouillon ?") != QMessageBox.Yes:
            return

        try:
            self.repo.delete(invoice_id)
            self.refresh()
        except Exception as e:
            QMessageBox.warning(self, "Supprimer", str(e))
