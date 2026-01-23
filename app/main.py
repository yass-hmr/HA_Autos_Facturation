from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget, QStyle, QTabBar

from app.db.db import connect, init_schema
from app.utils.paths import app_data_dir

from app.db.repos.invoice_repo import InvoiceRepository
from app.db.repos.settings_repo import SettingsRepository
from app.db.repos.pdf_repo import PdfExportRepository

from app.backup.backup_scheduler import BackupScheduler
from app.backup.backup_manager import BackupManager

from app.ui.invoices.invoice_list import InvoiceListWidget
from app.ui.invoices.invoice_editor import InvoiceEditorWidget
from app.ui.pdfs.pdf_list import PdfListWidget

from app.ui.settings.main_window import SettingsWidget


class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None) -> None:
        super().__init__(parent)

        self.conn = conn
        self.setWindowTitle("HA Facturation")

        # =========================
        # Icône de l'application
        # =========================
        icon_png = Path(__file__).resolve().parent / "assets" / "ha_facturation_icone.png"
        if icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

        # =========================
        # Repositories
        # =========================
        self.settings_repo = SettingsRepository(conn)
        self.invoice_repo = InvoiceRepository(conn)
        self.pdf_repo = PdfExportRepository(conn)

        # =========================
        # Backup (OneDrive)
        # =========================
        from app.backup.backup_manager import BackupManager
        from app.backup.backup_scheduler import BackupScheduler

        backup_manager = BackupManager()
        self.backup = BackupScheduler(
            conn=conn,
            settings_repo=self.settings_repo,
            backup_manager=backup_manager,
            interval_minutes=30,
        )
        self.backup.start()

        # =========================
        # Tabs
        # =========================
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self.setCentralWidget(self.tabs)

        # ---- Paramètres (premier, icône, pas fermable)
        self.settings_tab = SettingsWidget(self.settings_repo, self.backup)
        self.idx_settings = self.tabs.addTab(self.settings_tab, "")
        self.tabs.setTabToolTip(self.idx_settings, "Paramètres")
        self.tabs.setTabIcon(
            self.idx_settings,
            self.style().standardIcon(QStyle.SP_FileDialogDetailedView),
        )
        self._hide_close_button(self.idx_settings)

        # ---- Factures (liste)
        self.invoice_list_tab = InvoiceListWidget(self.invoice_repo)
        self.invoice_list_tab.open_invoice.connect(self._open_invoice_from_list)
        self.idx_invoices = self.tabs.addTab(self.invoice_list_tab, "Factures")
        self._hide_close_button(self.idx_invoices)

        # ---- PDF
        self.pdf_list_tab = PdfListWidget(self.pdf_repo, conn=conn)
        self.idx_pdfs = self.tabs.addTab(self.pdf_list_tab, "PDF")
        self._hide_close_button(self.idx_pdfs)

        # Ouvrir directement l'onglet Factures
        self.tabs.setCurrentIndex(self.idx_invoices)

    def _apply_icons(self) -> None:
        icon_png = Path(__file__).resolve().parent / "assets" / "ha_facturation_icone.png"
        if icon_png.exists():
            self.setWindowIcon(QIcon(str(icon_png)))

    def update_last_backup(self, created_at_iso: str) -> None:
        self.conn.execute(
            "UPDATE settings SET last_backup_at = ? WHERE id = 1",
            (created_at_iso,),
        )
        self.conn.commit()
    
    def _hide_close_button(self, tab_index: int) -> None:
        bar = self.tabs.tabBar()
        bar.setTabButton(tab_index, QTabBar.ButtonPosition.LeftSide, None)
        bar.setTabButton(tab_index, QTabBar.ButtonPosition.RightSide, None)

    def _open_invoice_from_list(self, invoice_id: int) -> None:
        # 0 => nouvelle facture
        self._open_invoice_editor(None if invoice_id == 0 else invoice_id)

    def _open_invoice_editor(self, invoice_id: int | None) -> None:
        editor = InvoiceEditorWidget(
            repo=self.invoice_repo,
            backup_scheduler=self.backup,
            pdf_repo=self.pdf_repo,
            invoice_id=invoice_id,
        )
        idx = self.tabs.addTab(editor, "Facture")
        self.tabs.setCurrentIndex(idx)

        editor.tab_title_changed.connect(lambda title, i=idx: self._set_tab_title_safe(i, title))
        editor.invoice_persisted.connect(lambda _id, i=idx: self._refresh_editor_title(i, editor))
        editor.closed.connect(lambda i=idx: self._close_editor_tab(i))

        self._refresh_editor_title(idx, editor)

    def _refresh_editor_title(self, idx: int, editor: InvoiceEditorWidget) -> None:
        try:
            self.tabs.setTabText(idx, editor.current_tab_title())
        except Exception:
            self.tabs.setTabText(idx, "Facture")

    def _set_tab_title_safe(self, idx: int, title: str) -> None:
        if 0 <= idx < self.tabs.count():
            self.tabs.setTabText(idx, title)

    def _close_editor_tab(self, idx: int) -> None:
        if 0 <= idx < self.tabs.count():
            w = self.tabs.widget(idx)
            self.tabs.removeTab(idx)
            if w is not None:
                w.deleteLater()

        self.invoice_list_tab.refresh()
        self.pdf_list_tab.refresh()

    def _on_tab_close_requested(self, index: int) -> None:
        if index in (self.idx_settings, self.idx_invoices, self.idx_pdfs):
            return
        self._close_editor_tab(index)


def main() -> int:
    app = QApplication(sys.argv)

    # Icône globale (taskbar)
    icon_png = Path(__file__).resolve().parent / "assets" / "ha_facturation_icone.png"
    if icon_png.exists():
        app.setWindowIcon(QIcon(str(icon_png)))

    db_path = app_data_dir() / "app.db"
    conn = connect(db_path)
    init_schema(conn)

    win = MainWindow(conn)
    win.resize(1100, 720)
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
