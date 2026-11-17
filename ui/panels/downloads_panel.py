"""Panel de descargas: modo, destino, formato y progreso por canción."""

from __future__ import annotations

import os
from typing import Iterable

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.youtube_service import estimate_audio_size

MODE_PLAYLIST = "playlist"
MODE_INDIVIDUAL = "individual"

FORMAT_MP3 = "mp3"
FORMAT_FLAC = "flac"

SIZE_COLUMN = 0
TITLE_COLUMN = 1
WEIGHT_COLUMN = 2
STATUS_COLUMN = 3
PROGRESS_COLUMN = 4

PROGRESS_STEPS = 1000


def format_size(num_bytes: float) -> str:
    """Formatea bytes de forma legible (B, KB, MB, GB...)."""
    size = float(max(0, num_bytes or 0))
    if size < 1024:
        return f"{int(size)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        size /= 1024.0
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
    return f"{size:.1f} TB"


class DownloadsPanel(QWidget):
    """Configura y sigue las descargas de YouTube.

    El panel no descarga: emite ``start_requested`` con los elementos
    seleccionados y la ventana principal se encarga de lanzar la tarea.
    """

    start_requested = pyqtSignal(list)
    cancel_requested = pyqtSignal()
    open_folder_requested = pyqtSignal()
    destination_changed = pyqtSignal(str)
    format_changed = pyqtSignal(str)
    mode_changed = pyqtSignal(str)
    validation_failed = pyqtSignal(str)

    def __init__(
        self,
        destination: str = "",
        audio_format: str = FORMAT_MP3,
        mode: str = MODE_PLAYLIST,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DownloadsPanel")

        self._items: list[dict] = []
        self._run_rows: list[int] = []
        self._completed: set[int] = set()
        self._failed: set[int] = set()
        self._actual_sizes: dict[int, int] = {}
        self._downloaded_bytes = 0
        self._running = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        settings = QGroupBox("Configuración de descarga", self)
        settings.setObjectName("SettingsCard")
        form = QFormLayout(settings)
        form.setContentsMargins(14, 14, 14, 12)
        form.setSpacing(8)

        self.mode_combo = QComboBox(settings)
        self.mode_combo.addItem("Lista de reproducción completa", MODE_PLAYLIST)
        self.mode_combo.addItem("Selección individual", MODE_INDIVIDUAL)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        form.addRow("Modo", self.mode_combo)

        self.destination_input = QLineEdit(destination, settings)
        self.destination_input.setPlaceholderText("Carpeta donde guardar los archivos…")
        self.destination_input.editingFinished.connect(self._emit_destination)
        browse = QPushButton("…", settings)
        browse.setFixedWidth(34)
        browse.setToolTip("Elegir carpeta de destino")
        browse.clicked.connect(self._browse_destination)
        destination_row = QHBoxLayout()
        destination_row.addWidget(self.destination_input, stretch=1)
        destination_row.addWidget(browse)
        self.browse_button = browse
        form.addRow("Carpeta de destino", destination_row)

        self.format_combo = QComboBox(settings)
        self.format_combo.addItem("MP3 (192 kbps)", FORMAT_MP3)
        self.format_combo.addItem("FLAC (sin pérdida)", FORMAT_FLAC)
        self.format_combo.currentIndexChanged.connect(self._on_format_changed)
        form.addRow("Formato de audio", self.format_combo)

        layout.addWidget(settings)

        summary_card = QFrame(self)
        summary_card.setObjectName("SummaryCard")
        summary = QHBoxLayout(summary_card)
        summary.setContentsMargins(14, 10, 14, 10)
        summary.setSpacing(12)
        self.selected_label = QLabel("Seleccionado: 0 B · 0 pistas")
        self.selected_label.setObjectName("MutedLabel")
        self.selected_label.setToolTip(
            "Peso estimado a partir de la duración. Se sustituye por el tamaño real al completar."
        )
        self.downloaded_label = QLabel("Descargado: 0 B")
        self.downloaded_label.setObjectName("MutedLabel")
        self.downloaded_label.setToolTip("Peso real de los archivos completados en esta sesión.")
        summary.addWidget(self.selected_label)
        summary.addStretch()
        summary.addWidget(self.downloaded_label)
        layout.addWidget(summary_card)

        self.overall_bar = QProgressBar(self)
        self.overall_bar.setRange(0, PROGRESS_STEPS)
        self.overall_bar.setValue(0)
        self.overall_bar.setFormat("%p%")
        self.overall_bar.setAccessibleName("Progreso total de descargas")
        layout.addWidget(self.overall_bar)

        queue_title = QLabel("Cola de descargas")
        queue_title.setObjectName("SectionTitle")
        layout.addWidget(queue_title)

        self.table = QTableWidget(0, 5, self)
        self.table.setObjectName("DownloadsTable")
        self.table.setHorizontalHeaderLabels(["", "Canción", "Peso", "Estado", "Progreso"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setColumnWidth(SIZE_COLUMN, 34)
        self.table.setColumnWidth(WEIGHT_COLUMN, 90)
        self.table.setColumnWidth(STATUS_COLUMN, 210)
        self.table.setColumnWidth(PROGRESS_COLUMN, 150)
        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(TITLE_COLUMN, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(PROGRESS_COLUMN, QHeaderView.ResizeMode.Fixed)
        self.table.itemChanged.connect(self._on_item_changed)
        layout.addWidget(self.table, stretch=1)

        buttons = QHBoxLayout()
        self.open_folder_btn = QPushButton("📂 Abrir carpeta", self)
        self.open_folder_btn.setObjectName("GhostBtn")
        self.open_folder_btn.setToolTip("Abrir la carpeta de destino en el explorador")
        self.open_folder_btn.clicked.connect(self.open_folder_requested.emit)
        buttons.addWidget(self.open_folder_btn)
        buttons.addStretch()
        self.start_btn = QPushButton("⬇️ Descargar", self)
        self.start_btn.setToolTip("Iniciar la descarga de los elementos seleccionados")
        self.start_btn.clicked.connect(self.start)
        buttons.addWidget(self.start_btn)
        self.cancel_btn = QPushButton("■ Cancelar", self)
        self.cancel_btn.setObjectName("DangerBtn")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel)
        buttons.addWidget(self.cancel_btn)
        layout.addLayout(buttons)

        self.set_mode(mode, emit=False)
        self.set_format(audio_format, emit=False)
        self._update_buttons()

    # -- configuración ------------------------------------------------
    def destination(self) -> str:
        return self.destination_input.text().strip()

    def set_destination(self, path: str) -> None:
        self.destination_input.setText(path or "")

    def audio_format(self) -> str:
        return str(self.format_combo.currentData() or FORMAT_MP3)

    def set_format(self, audio_format: str, emit: bool = False) -> None:
        index = self.format_combo.findData((audio_format or FORMAT_MP3).lower())
        self.format_combo.blockSignals(True)
        self.format_combo.setCurrentIndex(max(0, index))
        self.format_combo.blockSignals(False)
        self._refresh_weights()
        if emit:
            self.format_changed.emit(self.audio_format())

    def mode(self) -> str:
        return str(self.mode_combo.currentData() or MODE_PLAYLIST)

    def set_mode(self, mode: str, emit: bool = False) -> None:
        index = self.mode_combo.findData(mode)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentIndex(max(0, index))
        self.mode_combo.blockSignals(False)
        self._apply_mode()
        if emit:
            self.mode_changed.emit(self.mode())

    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, "Carpeta de destino de las descargas", self.destination()
        )
        if folder:
            self.set_destination(folder)
            self.destination_changed.emit(folder)

    def _emit_destination(self) -> None:
        self.destination_changed.emit(self.destination())

    def _on_mode_changed(self) -> None:
        self._apply_mode()
        self.mode_changed.emit(self.mode())

    def _on_format_changed(self) -> None:
        self._refresh_weights()
        self.format_changed.emit(self.audio_format())

    def _apply_mode(self) -> None:
        individual = self.mode() == MODE_INDIVIDUAL
        for row in range(self.table.rowCount()):
            check = self.table.item(row, SIZE_COLUMN)
            if check is None:
                continue
            flags = check.flags()
            if individual:
                check.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                check.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable)
                check.setCheckState(Qt.CheckState.Checked)
        self._recalculate()

    # -- contenido ----------------------------------------------------
    def set_items(
        self,
        results: Iterable[dict],
        mode: str | None = None,
        selected_urls: Iterable[str] | None = None,
    ) -> None:
        """Carga los resultados que se pueden descargar."""
        self._items = [dict(item) for item in results if item.get("url")]
        self._run_rows = []
        self._completed.clear()
        self._failed.clear()
        self._actual_sizes.clear()
        self._downloaded_bytes = 0
        self._running = False
        self.overall_bar.setValue(0)

        if mode is not None:
            self.set_mode(mode, emit=False)

        wanted = set(selected_urls) if selected_urls is not None else None
        self.table.blockSignals(True)
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            check = QTableWidgetItem()
            check.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            checked = wanted is None or item.get("url") in wanted
            check.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.table.setItem(row, SIZE_COLUMN, check)

            title = QTableWidgetItem(item.get("title") or item.get("url", ""))
            artist = item.get("artist", "")
            title.setToolTip(f"{title.text()}\n{artist}".strip())
            self.table.setItem(row, TITLE_COLUMN, title)

            weight = QTableWidgetItem(format_size(self._estimated_size(row)))
            weight.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, WEIGHT_COLUMN, weight)

            self.table.setItem(row, STATUS_COLUMN, QTableWidgetItem("Pendiente"))

            bar = QProgressBar(self.table)
            bar.setRange(0, PROGRESS_STEPS)
            bar.setValue(0)
            bar.setFormat("%p%")
            bar.setAccessibleName(f"Progreso de {title.text()}")
            self.table.setCellWidget(row, PROGRESS_COLUMN, bar)
            self.table.setRowHeight(row, 34)
        self.table.blockSignals(False)

        self._apply_mode()
        self._update_buttons()
        self._recalculate()

    def items(self) -> list[dict]:
        return list(self._items)

    def selected_items(self) -> list[dict]:
        selected = []
        for row in range(self.table.rowCount()):
            check = self.table.item(row, SIZE_COLUMN)
            if check is not None and check.checkState() == Qt.CheckState.Checked:
                selected.append(self._items[row])
        return selected

    def is_running(self) -> bool:
        return self._running

    def start(self) -> bool:
        items = self.selected_items()
        if not items:
            self.validation_failed.emit("Selecciona al menos una canción para descargar.")
            return False
        if not self.destination():
            self.validation_failed.emit("Elige una carpeta de destino antes de descargar.")
            return False
        self.start_requested.emit(items)
        return True

    def _cancel(self) -> None:
        self.cancel_btn.setEnabled(False)
        for row in self._run_rows:
            if row not in self._completed and row not in self._failed:
                self._set_status(row, "Cancelando…")
        self.cancel_requested.emit()

    # -- progreso -----------------------------------------------------
    def mark_started(self, total: int) -> None:
        self._running = True
        self._run_rows = [
            row
            for row in range(self.table.rowCount())
            if self.table.item(row, SIZE_COLUMN) is not None
            and self.table.item(row, SIZE_COLUMN).checkState() == Qt.CheckState.Checked
        ]
        self._completed.clear()
        self._failed.clear()
        self._actual_sizes.clear()
        self._downloaded_bytes = 0
        for row in self._run_rows:
            self._set_status(row, "En cola")
            bar = self._progress_bar(row)
            if bar is not None:
                bar.setValue(0)
        self.overall_bar.setValue(0)
        self._update_buttons()
        self._recalculate()

    def update_item_started(self, index: int, _item: dict) -> None:
        row = self._row_for_run(index)
        if row is not None:
            self._set_status(row, "Descargando…")

    def update_item_progress(self, index: int, data: dict) -> None:
        row = self._row_for_run(index)
        if row is None:
            return
        bar = self._progress_bar(row)
        status = str(data.get("status", ""))
        if status == "downloading":
            downloaded = int(data.get("downloaded_bytes") or 0)
            total = int(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            percent = min(100, int(downloaded * 100 / total)) if total else 0
            if bar is not None:
                bar.setValue(percent * PROGRESS_STEPS // 100)
            if total:
                self._set_weight(row, format_size(total))
            self._set_status(
                row,
                f"Descargando · {format_size(downloaded)} / {format_size(total)}",
            )
        elif status == "finished":
            if bar is not None:
                bar.setValue(PROGRESS_STEPS)
            self._set_status(row, "Procesando formato…")
        elif status == "error":
            self._set_status(row, "Error de descarga")

    def update_item_finished(self, index: int, track) -> None:
        row = self._row_for_run(index)
        if row is None or row in self._completed:
            return
        size = 0
        file_path = getattr(track, "file_path", "") if track is not None else ""
        if file_path:
            try:
                size = os.path.getsize(file_path)
            except OSError:
                size = 0
        self._completed.add(row)
        self._actual_sizes[row] = size
        self._downloaded_bytes += size
        bar = self._progress_bar(row)
        if bar is not None:
            bar.setValue(PROGRESS_STEPS)
        self._set_weight(row, format_size(size) if size else self._estimated_size(row))
        self._set_status(row, "Completado")
        self._recalculate()

    def update_item_failed(self, index: int, message: str) -> None:
        row = self._row_for_run(index)
        if row is None:
            return
        self._failed.add(row)
        bar = self._progress_bar(row)
        if bar is not None:
            bar.setValue(0)
        self._set_status(row, f"Error: {message}" if message else "Error")
        self._recalculate()

    def mark_cancelled(self) -> None:
        for row in self._run_rows:
            if row not in self._completed and row not in self._failed:
                self._set_status(row, "Cancelado")
        self.finish_batch()

    def finish_batch(self) -> None:
        self._running = False
        self._update_buttons()
        self._recalculate()

    # -- helpers ------------------------------------------------------
    def _row_for_run(self, index: int) -> int | None:
        if 0 <= index < len(self._run_rows):
            return self._run_rows[index]
        return None

    def _progress_bar(self, row: int) -> QProgressBar | None:
        widget = self.table.cellWidget(row, PROGRESS_COLUMN)
        return widget if isinstance(widget, QProgressBar) else None

    def _set_status(self, row: int, text: str) -> None:
        item = self.table.item(row, STATUS_COLUMN)
        if item is not None:
            item.setText(text)

    def _set_weight(self, row: int, text: str) -> None:
        item = self.table.item(row, WEIGHT_COLUMN)
        if item is not None:
            item.setText(text)

    def _estimated_size(self, row: int) -> int:
        if 0 <= row < len(self._items):
            return estimate_audio_size(
                self._items[row].get("duration", 0) or 0,
                self.audio_format(),
            )
        return 0

    def _item_size(self, row: int) -> int:
        return self._actual_sizes.get(row, self._estimated_size(row))

    def _refresh_weights(self) -> None:
        if not hasattr(self, "table"):
            return
        for row in range(self.table.rowCount()):
            self._set_weight(row, format_size(self._item_size(row)))
        self._recalculate()

    def _recalculate(self) -> None:
        selected = [
            row
            for row in range(self.table.rowCount())
            if self.table.item(row, SIZE_COLUMN) is not None
            and self.table.item(row, SIZE_COLUMN).checkState() == Qt.CheckState.Checked
        ]
        total_selected = sum(self._item_size(row) for row in selected)
        self.selected_label.setText(
            f"Seleccionado: ≈{format_size(total_selected)} · {len(selected)} pista(s)"
        )
        self.downloaded_label.setText(f"Descargado: {format_size(self._downloaded_bytes)}")

        if total_selected > 0:
            downloaded_selected = sum(
                self._item_size(row) for row in selected if row in self._completed
            )
            percent = min(100, int(downloaded_selected * 100 / total_selected))
        else:
            percent = 0
        self.overall_bar.setValue(percent * PROGRESS_STEPS // 100)

    def _update_buttons(self) -> None:
        editable = not self._running
        self.start_btn.setEnabled(editable)
        self.cancel_btn.setEnabled(self._running)
        self.mode_combo.setEnabled(editable)
        self.format_combo.setEnabled(editable)
        self.destination_input.setEnabled(editable)
        self.browse_button.setEnabled(editable)
        self.table.setEnabled(True)
        for row in range(self.table.rowCount()):
            check = self.table.item(row, SIZE_COLUMN)
            if check is None:
                continue
            flags = check.flags()
            if editable and self.mode() == MODE_INDIVIDUAL:
                check.setFlags(flags | Qt.ItemFlag.ItemIsUserCheckable)
            else:
                check.setFlags(flags & ~Qt.ItemFlag.ItemIsUserCheckable)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() != SIZE_COLUMN or self._running:
            return
        self._recalculate()
