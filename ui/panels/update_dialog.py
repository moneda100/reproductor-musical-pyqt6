"""Diálogo de actualización: comprueba, descarga e instala una versión nueva."""

from __future__ import annotations

import logging

from PyQt6.QtCore import QThreadPool, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.tasks.worker import Worker
from core.updater import ReleaseInfo, UpdateApplier, UpdateChecker
from core.version import APP_VERSION

logger = logging.getLogger(__name__)


class UpdateDialog(QDialog):
    """Flujo de actualización con progreso y resultado."""

    finished_ok = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Actualizaciones")
        self.resize(520, 420)
        self.pool = pool or QThreadPool(self)
        self.checker = UpdateChecker()
        self.applier = UpdateApplier()
        self.release: ReleaseInfo | None = None

        layout = QVBoxLayout(self)

        self.current_label = QLabel(f"Versión actual: {APP_VERSION}")
        self.current_label.setObjectName("TitleLabel")
        layout.addWidget(self.current_label)

        self.status_label = QLabel("Buscando actualizaciones…")
        layout.addWidget(self.status_label)

        self.notes = QTextEdit()
        self.notes.setReadOnly(True)
        self.notes.setVisible(False)
        layout.addWidget(self.notes, stretch=1)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.install_btn = QPushButton("Instalar")
        self.install_btn.setObjectName("SecondaryBtn")
        self.install_btn.setEnabled(False)
        self.install_btn.clicked.connect(self._install)
        buttons.addWidget(self.install_btn)
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.close)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        self._check()

    # -- comprobación ---------------------------------------------------
    def _check(self) -> None:
        worker = Worker(self.checker.fetch_latest)
        worker.signals.result.connect(self._on_release)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_release(self, release) -> None:
        if release is None:
            self.status_label.setText("Ya estás en la última versión.")
            return
        self.release = release
        self.status_label.setText(f"Versión disponible: {release.version}")
        if release.notes:
            self.notes.setPlainText(release.notes)
            self.notes.setVisible(True)
        self.install_btn.setEnabled(True)

    def _on_error(self, error: str) -> None:
        self.status_label.setText(f"No se pudo comprobar: {error}")

    # -- instalación ------------------------------------------------------
    def _install(self) -> None:
        if self.release is None:
            return
        self.install_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status_label.setText("Descargando…")

        worker = Worker(self.applier.download, self.release, self._on_progress)
        worker.signals.result.connect(self._on_downloaded)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_progress(self, downloaded: int, total: int) -> None:
        if total:
            self.progress.setRange(0, total)
            self.progress.setValue(downloaded)
        else:
            self.progress.setRange(0, 0)

    def _on_downloaded(self, path) -> None:
        if path is None:
            self.status_label.setText("No se pudo descargar la actualización.")
            self.progress.setVisible(False)
            return
        self.progress.setRange(0, 0)
        self.status_label.setText("Instalando…")
        ok = self.applier.install(self.release, path)
        if ok:
            self.status_label.setText(f"Actualizado a la versión {self.release.version}.")
            QMessageBox.information(
                self,
                "Actualización completada",
                f"Music Player Pro se ha actualizado a la versión {self.release.version}.",
            )
        else:
            self.status_label.setText(
                "La actualización no se pudo completar: se ha restaurado la versión anterior."
            )
            QMessageBox.warning(
                self,
                "Actualización fallida",
                "No se pudo actualizar la aplicación.\n"
                "Se ha restaurado la versión anterior automáticamente.",
            )
        self.progress.setVisible(False)
        self.finished_ok.emit(ok)
