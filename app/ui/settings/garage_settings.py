from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QLabel,
    QMessageBox,
    QHBoxLayout,
)

from app.db.repos.settings_repo import SettingsRepository
from app.backup.backup_scheduler import BackupScheduler


class GarageSettingsWidget(QWidget):
    def __init__(
        self,
        settings_repo: SettingsRepository,
        backup_scheduler: BackupScheduler,
        parent=None
    ) -> None:
        super().__init__(parent)
        self.repo = settings_repo
        self.backup_scheduler = backup_scheduler

        self._build_ui()
        self._load()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.garage_name = QLineEdit()
        self.garage_address = QTextEdit()
        self.garage_address.setFixedHeight(80)
        self.garage_postal = QLineEdit()
        self.garage_postal.setPlaceholderText("Code postal")
        self.garage_phone = QLineEdit()

        self.onedrive_dir = QLineEdit()
        self.onedrive_dir.setReadOnly(True)

        browse_btn = QPushButton("Choisir dossier OneDrive…")
        browse_btn.clicked.connect(self._choose_onedrive_dir)

        onedrive_layout = QHBoxLayout()
        onedrive_layout.addWidget(self.onedrive_dir)
        onedrive_layout.addWidget(browse_btn)

        self.last_backup_label = QLabel("Dernière sauvegarde : —")
        self.status_label = QLabel("Statut : —")

        form.addRow("Nom du garage", self.garage_name)
        form.addRow("Adresse", self.garage_address)
        form.addRow("Code postal", self.garage_postal)
        form.addRow("Téléphone", self.garage_phone)
        form.addRow("Dossier OneDrive", onedrive_layout)

        layout.addLayout(form)
        layout.addWidget(self.last_backup_label)
        layout.addWidget(self.status_label)

        actions = QHBoxLayout()
        save_btn = QPushButton("Enregistrer les paramètres")
        save_btn.clicked.connect(self._save)

        backup_btn = QPushButton("Sauvegarder maintenant")
        backup_btn.clicked.connect(self._backup_now)

        actions.addWidget(save_btn)
        actions.addWidget(backup_btn)

        layout.addStretch()
        layout.addLayout(actions)

    def _load(self) -> None:
        data = self.repo.get()

        self.garage_name.setText(data.get("garage_name", ""))
        self.garage_address.setPlainText(data.get("garage_address", ""))
        self.garage_postal.setText(data.get("garage_postal_code", ""))
        self.garage_phone.setText(data.get("garage_phone", ""))
        self.onedrive_dir.setText(data.get("onedrive_backup_dir", ""))

        last_backup = data.get("last_backup_at")
        self.last_backup_label.setText(
            f"Dernière sauvegarde : {last_backup or '—'}"
        )

    def set_status(self, msg: str) -> None:
        self.status_label.setText(f"Statut : {msg}")

    def refresh_last_backup(self) -> None:
        data = self.repo.get()
        self.last_backup_label.setText(
            f"Dernière sauvegarde : {data.get('last_backup_at') or '—'}"
        )

    def _save(self) -> None:
        if not self.onedrive_dir.text().strip():
            QMessageBox.warning(
                self,
                "Dossier OneDrive manquant",
                "Veuillez sélectionner un dossier OneDrive pour les sauvegardes.",
            )
            return

        self.repo.update(
            garage_name=self.garage_name.text(),
            garage_address=self.garage_address.toPlainText(),
            garage_postal_code=self.garage_postal.text(),
            garage_phone=self.garage_phone.text(),
            onedrive_backup_dir=self.onedrive_dir.text(),
        )

        self.backup_scheduler.mark_dirty()

        QMessageBox.information(
            self,
            "Paramètres",
            "Paramètres du garage enregistrés.",
        )

    def _backup_now(self) -> None:
        ok = self.backup_scheduler.try_backup_now(force=True)
        self.refresh_last_backup()

        if ok:
            QMessageBox.information(self, "Sauvegarde", "Sauvegarde effectuée.")
        else:
            QMessageBox.warning(self, "Sauvegarde", "Sauvegarde non effectuée.")

    def _choose_onedrive_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self,
            "Sélectionner le dossier OneDrive de sauvegarde",
        )
        if directory:
            self.onedrive_dir.setText(directory)
            self.backup_scheduler.mark_dirty()
