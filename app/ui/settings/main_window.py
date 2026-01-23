from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QLineEdit, QTextEdit,
    QHBoxLayout, QPushButton, QMessageBox
)

from app.db.repos.settings_repo import SettingsRepository
from app.backup.backup_scheduler import BackupScheduler


class SettingsWidget(QWidget):
    def __init__(self, repo: SettingsRepository, backup: BackupScheduler, parent=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.backup = backup
        self._build_ui()
        self.load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.in_name = QLineEdit()
        self.in_address = QTextEdit()
        self.in_address.setFixedHeight(70)
        self.in_postal = QLineEdit()
        self.in_phone = QLineEdit()
        self.in_siret = QLineEdit()
        self.in_siret.setPlaceholderText("Ex: 123 456 789 00012")
        self.in_onedrive = QLineEdit()
        self.in_onedrive.setPlaceholderText("Dossier OneDrive de sauvegarde (optionnel)")

        form.addRow("Nom du garage", self.in_name)
        form.addRow("Adresse", self.in_address)
        form.addRow("Code postal", self.in_postal)
        form.addRow("Téléphone", self.in_phone)
        form.addRow("SIRET", self.in_siret)
        form.addRow("Dossier OneDrive", self.in_onedrive)
        layout.addLayout(form)

        actions = QHBoxLayout()
        btn_save = QPushButton("Enregistrer")
        btn_save.clicked.connect(self.save)
        btn_reload = QPushButton("Recharger")
        btn_reload.clicked.connect(self.load)
        actions.addWidget(btn_save)
        actions.addWidget(btn_reload)
        actions.addStretch()
        layout.addLayout(actions)

        layout.addStretch()

    def load(self) -> None:
        s = self.repo.get()
        self.in_name.setText((s.get("garage_name") or "").strip())
        self.in_address.setPlainText((s.get("garage_address") or "").strip())
        self.in_postal.setText((s.get("garage_postal_code") or "").strip())
        self.in_phone.setText((s.get("garage_phone") or "").strip())
        self.in_siret.setText((s.get("garage_siret") or "").strip())
        self.in_onedrive.setText((s.get("onedrive_backup_dir") or "").strip())

    def save(self) -> None:
        try:
            self.repo.update(
                garage_name=self.in_name.text(),
                garage_address=self.in_address.toPlainText(),
                garage_postal_code=self.in_postal.text(),
                garage_phone=self.in_phone.text(),
                garage_siret=self.in_siret.text(),
                onedrive_backup_dir=self.in_onedrive.text(),
            )

            # Indique au scheduler qu'il y a des changements à sauvegarder
            self.backup.mark_dirty()

            QMessageBox.information(self, "Paramètres", "Paramètres enregistrés.")
        except Exception as e:
            QMessageBox.warning(self, "Paramètres", str(e))

