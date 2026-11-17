"""Panel de resultados de búsqueda con tarjetas y acciones rápidas.

Cada resultado se dibuja como una tarjeta con:
- índice, título, artista/fuente y duración;
- botón de reproducción (streaming para YouTube);
- botón de descarga (solo YouTube);
- menú contextual con Reproducir / Descargar / Añadir a playlist / Copiar.

La lista admite «Cargar más» para paginar búsquedas de YouTube sin perder
los resultados ya mostrados.
"""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QPolygon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QPushButton,
    QStyle,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from ui.models.results_model import ResultRoles, ResultsModel

CARD_MARGIN_X = 4
CARD_MARGIN_Y = 3
ACTION_SIZE = 34
ACTION_GAP = 8
ACTION_RIGHT = 10


class ResultCardDelegate(QStyledItemDelegate):
    """Dibuja resultados como tarjetas con acciones integradas."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), 70)

    @staticmethod
    def card_rect(item_rect: QRect) -> QRect:
        return item_rect.adjusted(CARD_MARGIN_X, CARD_MARGIN_Y, -CARD_MARGIN_X, -CARD_MARGIN_Y)

    @staticmethod
    def action_rects(card: QRect, has_download: bool) -> tuple[QRect, QRect | None]:
        """Devuelve los rectángulos de los botones Reproducir y Descargar."""
        right = card.right() - ACTION_RIGHT
        download = None
        if has_download:
            download = QRect(
                right - ACTION_SIZE,
                card.top() + (card.height() - ACTION_SIZE) // 2,
                ACTION_SIZE,
                ACTION_SIZE,
            )
            right = download.left() - ACTION_GAP
        play = QRect(
            right - ACTION_SIZE,
            card.top() + (card.height() - ACTION_SIZE) // 2,
            ACTION_SIZE,
            ACTION_SIZE,
        )
        return play, download

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        palette = option.palette
        card = self.card_rect(option.rect)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        if selected:
            background = QColor(palette.highlight().color())
            background.setAlpha(80)
        elif hovered:
            background = QColor(palette.text().color())
            background.setAlpha(16)
        else:
            background = QColor(palette.base().color())
            background.setAlpha(90)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(card, 10, 10)

        accent = QColor(palette.highlight().color())
        text_color = QColor(palette.text().color())
        muted = QColor(text_color)
        muted.setAlpha(170)

        # -- insignia con el índice --
        badge_size = 30
        badge = QRect(
            card.left() + 12,
            card.top() + (card.height() - badge_size) // 2,
            badge_size,
            badge_size,
        )
        painter.setBrush(accent)
        painter.drawEllipse(badge)
        badge_font = QFont(option.font)
        badge_font.setBold(True)
        badge_font.setPointSize(max(8, badge_font.pointSize() - 1))
        painter.setFont(badge_font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), str(index.row() + 1))

        # -- textos --
        title = str(index.data(ResultRoles.Title) or "")
        artist = str(index.data(ResultRoles.Artist) or "")
        source = str(index.data(ResultRoles.Source) or "youtube")
        duration = index.data(ResultRoles.Duration) or 0
        is_local = source == "local"

        play_rect, download_rect = self.action_rects(card, not is_local)
        text_left = badge.right() + 12
        text_right = play_rect.left() - 58
        text_width = max(40, text_right - text_left)

        title_font = QFont(option.font)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(text_color)
        painter.drawText(
            QRect(text_left, card.top() + 12, text_width, 20),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._elide(painter, title, text_width),
        )

        small_font = QFont(option.font)
        small_font.setPointSize(max(7, small_font.pointSize() - 1))
        painter.setFont(small_font)
        painter.setPen(muted)
        origin = "Biblioteca" if is_local else "YouTube"
        subtitle = f"{artist or 'Desconocido'}  ·  {origin}"
        painter.drawText(
            QRect(text_left, card.top() + 34, text_width, 18),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            self._elide(painter, subtitle, text_width),
        )

        if duration:
            painter.setPen(muted)
            painter.drawText(
                QRect(play_rect.left() - 54, card.top(), 48, card.height()),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                _format_duration(duration),
            )

        # -- acciones --
        self._paint_play(painter, play_rect, accent)
        if download_rect is not None:
            self._paint_download(painter, download_rect, muted)
        painter.restore()

    @staticmethod
    def _paint_play(painter: QPainter, rect: QRect, accent: QColor) -> None:
        fill = QColor(accent)
        fill.setAlpha(40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        painter.setBrush(accent)
        size = 10
        triangle_x = rect.center().x() - size // 3
        triangle_y = rect.center().y() - size // 2
        painter.drawPolygon(
            QPolygon(
                [
                    QPoint(triangle_x, triangle_y),
                    QPoint(triangle_x, triangle_y + size),
                    QPoint(triangle_x + size, triangle_y + size // 2),
                ]
            )
        )

    @staticmethod
    def _paint_download(painter: QPainter, rect: QRect, color: QColor) -> None:
        fill = QColor(color)
        fill.setAlpha(28)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawEllipse(rect)
        pen = QPen(color, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        center_x = rect.center().x()
        top = rect.center().y() - 5
        bottom = rect.center().y() + 3
        painter.drawLine(center_x, top, center_x, bottom)
        painter.drawLine(center_x - 4, bottom - 4, center_x, bottom)
        painter.drawLine(center_x + 4, bottom - 4, center_x, bottom)
        painter.drawLine(center_x - 5, bottom + 4, center_x + 5, bottom + 4)

    @staticmethod
    def _elide(painter: QPainter, text: str, width: int) -> str:
        return painter.fontMetrics().elidedText(
            text or "", Qt.TextElideMode.ElideRight, max(10, width)
        )


class ResultsListView(QListView):
    """Vista con clics directos sobre los botones de cada tarjeta."""

    play_clicked = pyqtSignal(int)
    download_clicked = pyqtSignal(int)
    menu_requested = pyqtSignal(int, QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ResultsList")
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.ExtendedSelection)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

    def _result_at(self, index) -> dict | None:
        model = self.model()
        if model is None or not index.isValid():
            return None
        getter = getattr(model, "result_at", None)
        return getter(index.row()) if callable(getter) else None

    def _button_at(self, pos: QPoint, index) -> str | None:
        result = self._result_at(index)
        if result is None:
            return None
        item_rect = self.visualRect(index)
        card = ResultCardDelegate.card_rect(item_rect)
        play_rect, download_rect = ResultCardDelegate.action_rects(
            card, result.get("source") != "local"
        )
        if play_rect.contains(pos):
            return "play"
        if download_rect is not None and download_rect.contains(pos):
            return "download"
        return None

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.indexAt(pos)
            button = self._button_at(pos, index)
            if button == "play":
                self.play_clicked.emit(index.row())
                event.accept()
                return
            if button == "download":
                self.download_clicked.emit(index.row())
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):  # noqa: N802
        index = self.indexAt(event.pos())
        if index.isValid():
            self.menu_requested.emit(index.row(), event.globalPos())
            event.accept()
            return
        super().contextMenuEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            parent_panel = self.parent()
            selected = (
                parent_panel.selected_results()
                if hasattr(parent_panel, "selected_results")
                else []
            )
            if len(selected) > 1 and hasattr(parent_panel, "play_selected_requested"):
                parent_panel.play_selected_requested.emit(selected)
                event.accept()
                return
            index = self.currentIndex()
            if index.isValid():
                self.play_clicked.emit(index.row())
                event.accept()
                return
        super().keyPressEvent(event)


def _format_duration(seconds) -> str:
    try:
        total = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    if total < 0:
        return ""
    return f"{total // 60}:{total % 60:02d}"


class ResultsPanel(QWidget):
    """Lista de resultados (YouTube o biblioteca local) con acciones."""

    download_requested = pyqtSignal(dict)
    download_selected_requested = pyqtSignal(list)
    download_all_requested = pyqtSignal()
    play_requested = pyqtSignal(dict)
    play_selected_requested = pyqtSignal(list)
    play_all_requested = pyqtSignal(list)
    play_video_requested = pyqtSignal(dict)
    open_folder_requested = pyqtSignal(dict)
    add_to_queue_requested = pyqtSignal(list)
    add_to_playlist_requested = pyqtSignal(object, str)
    create_playlist_requested = pyqtSignal(object)
    add_to_favorites_requested = pyqtSignal(list)
    clear_requested = pyqtSignal()
    load_more_requested = pyqtSignal()
    status_message = pyqtSignal(str)

    def __init__(self, model: ResultsModel, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = model
        self._title = "Resultados"
        self._playlists: list[dict] = []
        self._loading_more = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(8)
        self.header_label = QLabel("Resultados")
        self.header_label.setObjectName("TitleLabel")
        header.addWidget(self.header_label)

        self.count_label = QLabel("0")
        self.count_label.setObjectName("CountChip")
        self.count_label.setToolTip("Resultados encontrados")
        header.addWidget(self.count_label)
        header.addStretch()

        self.play_all_btn = QPushButton("▶ Reproducir todo")
        self.play_all_btn.setObjectName("PrimaryBtn")
        self.play_all_btn.setToolTip("Reproducir todos los resultados de búsqueda")
        self.play_all_btn.setEnabled(False)
        self.play_all_btn.clicked.connect(self._on_play_all_clicked)
        header.addWidget(self.play_all_btn)

        self.add_all_btn = QPushButton("➕ Añadir todo…")
        self.add_all_btn.setObjectName("SecondaryBtn")
        self.add_all_btn.setToolTip("Añadir todos los resultados a la cola o a una playlist")
        self.add_all_btn.setEnabled(False)
        self.add_all_btn.clicked.connect(self._on_add_all_btn_clicked)
        header.addWidget(self.add_all_btn)

        self.load_more_btn = QPushButton("⬇️ Cargar más")
        self.load_more_btn.setObjectName("SecondaryBtn")
        self.load_more_btn.setToolTip("Traer 20 resultados adicionales")
        self.load_more_btn.clicked.connect(self.load_more_requested.emit)
        self.load_more_btn.hide()
        header.addWidget(self.load_more_btn)

        self.download_all_btn = QPushButton("⬇️ Descargar todo")
        self.download_all_btn.setObjectName("SecondaryBtn")
        self.download_all_btn.setToolTip("Abrir el gestor con todas las canciones de YouTube")
        self.download_all_btn.setEnabled(False)
        self.download_all_btn.clicked.connect(self.download_all_requested.emit)
        header.addWidget(self.download_all_btn)

        self.clear_btn = QPushButton("Limpiar")
        self.clear_btn.setObjectName("GhostBtn")
        self.clear_btn.setToolTip("Vaciar los resultados")
        self.clear_btn.clicked.connect(self.clear_requested.emit)
        header.addWidget(self.clear_btn)

        layout.addLayout(header)

        self.hint_label = QLabel(
            "Selecciona o haz doble clic para reproducir · Clic derecho para opciones de descarga, playlist y favoritos"
        )
        self.hint_label.setObjectName("HintLabel")
        layout.addWidget(self.hint_label)

        self.list_view = ResultsListView(self)
        self.list_view.setModel(self.model)
        self.list_view.setItemDelegate(ResultCardDelegate(self.list_view))
        self.list_view.doubleClicked.connect(self._on_double_clicked)
        self.list_view.play_clicked.connect(self._on_play_clicked)
        self.list_view.download_clicked.connect(self._on_download_clicked)
        self.list_view.menu_requested.connect(self._on_menu_requested)
        layout.addWidget(self.list_view, stretch=1)

        self.empty_label = QLabel(
            "Escribe en el buscador para filtrar tu biblioteca\n"
            "o usa el prefijo «yt:» para buscar en YouTube."
        )
        self.empty_label.setObjectName("EmptyState")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, stretch=1)
        self.empty_label.hide()

        self.model.count_changed.connect(self._on_count_changed)
        self._on_count_changed(self.model.rowCount())

    # -- contenido ----------------------------------------------------
    def set_results(self, results: list[dict], title: str = "Resultados") -> None:
        self._title = title or "Resultados"
        self.model.set_results(results)
        self._on_count_changed(len(results))

    def append_results(self, results: list[dict]) -> None:
        added = self.model.append_results(results)
        if added == 0:
            self.show_load_more(False)

    def current_results(self) -> list[dict]:
        return self.model.results()

    def set_playlists(self, playlists: list[dict]) -> None:
        self._playlists = list(playlists)

    def show_load_more(self, visible: bool) -> None:
        self.load_more_btn.setVisible(bool(visible))
        if not visible:
            self.set_loading_more(False)

    def set_loading_more(self, loading: bool) -> None:
        self._loading_more = bool(loading)
        if self._loading_more:
            self.load_more_btn.setText("Cargando…")
            self.load_more_btn.setEnabled(False)
        else:
            self.load_more_btn.setText("⬇️ Cargar más")
            self.load_more_btn.setEnabled(True)

    def is_loading_more(self) -> bool:
        return self._loading_more

    def selected_results(self) -> list[dict]:
        """Devuelve los resultados actualmente seleccionados en la lista."""
        indexes = self.list_view.selectedIndexes()
        rows = sorted({idx.row() for idx in indexes if idx.isValid()})
        results = []
        for r in rows:
            res = self.model.result_at(r)
            if res:
                results.append(res)
        return results

    # -- acciones de la lista -----------------------------------------
    def _on_count_changed(self, count: int) -> None:
        self.header_label.setText(f"{self._title} ({count})")
        self.count_label.setText(str(count))
        has_results = count > 0
        self.list_view.setVisible(has_results)
        self.empty_label.setVisible(not has_results)
        self.play_all_btn.setEnabled(has_results)
        self.add_all_btn.setEnabled(has_results)
        has_youtube = any(
            result.get("source") != "local" for result in self.model.results()
        )
        self.download_all_btn.setEnabled(has_youtube)

    def _on_double_clicked(self, index) -> None:
        result = self.model.result_at(index.row())
        if result:
            self.play_requested.emit(result)

    def _on_play_clicked(self, row: int) -> None:
        result = self.model.result_at(row)
        if result:
            self.play_requested.emit(result)

    def _on_play_all_clicked(self) -> None:
        results = self.model.results()
        if results:
            self.play_all_requested.emit(results)

    def _on_add_all_btn_clicked(self) -> None:
        results = self.model.results()
        if not results:
            return
        menu = QMenu(self)
        queue_action = menu.addAction("➕  Añadir todo a la cola actual")
        menu.addSeparator()
        self._build_playlist_menu(menu, target_results=results, label="📑  Añadir todo a playlist")
        fav_action = menu.addAction("⭐  Añadir todo a favoritos")
        pos = self.add_all_btn.mapToGlobal(QPoint(0, self.add_all_btn.height()))
        chosen = menu.exec(pos)
        if chosen is None:
            return
        if chosen is queue_action:
            self.add_to_queue_requested.emit(results)
        elif chosen is fav_action:
            self.add_to_favorites_requested.emit(results)
        elif chosen.property("playlist_id"):
            self.add_to_playlist_requested.emit(results, chosen.property("playlist_id"))
        elif chosen.property("create_playlist"):
            self.create_playlist_requested.emit(results)

    def _on_download_clicked(self, row: int) -> None:
        result = self.model.result_at(row)
        if result and result.get("source") != "local":
            self.download_requested.emit(result)

    def _on_menu_requested(self, row: int, global_pos: QPoint) -> None:
        clicked_result = self.model.result_at(row)
        if clicked_result is None:
            return

        selected = self.selected_results()
        if not selected or clicked_result not in selected:
            self.list_view.setCurrentIndex(self.model.index(row, 0))
            selected = [clicked_result]

        menu = QMenu(self)
        is_multiple = len(selected) > 1

        if is_multiple:
            play_action = menu.addAction(f"▶  Reproducir seleccionadas ({len(selected)})")
            add_queue_action = menu.addAction("➕  Añadir selección a la cola")
            menu.addSeparator()
            self._build_playlist_menu(menu, target_results=selected, label="📑  Añadir selección a playlist")
            fav_action = menu.addAction("⭐  Añadir selección a favoritos")
            yt_count = sum(1 for r in selected if r.get("source") != "local")
            download_action = (
                menu.addAction(f"⬇️  Descargar seleccionadas ({yt_count})…")
                if yt_count > 0
                else None
            )
            video_action = None
            folder_action = None
            copy_action = None
        else:
            item = selected[0]
            is_local = item.get("source") == "local"
            play_action = menu.addAction("▶  Reproducir")
            video_action = menu.addAction("🎬  Reproducir vídeo") if not is_local else None
            add_queue_action = menu.addAction("➕  Añadir a la cola")
            menu.addSeparator()
            self._build_playlist_menu(menu, target_results=selected, label="📑  Añadir a playlist")
            fav_action = menu.addAction("⭐  Añadir a favoritos")
            download_action = menu.addAction("⬇️  Descargar…") if not is_local else None
            folder_action = menu.addAction("📂  Abrir carpeta") if is_local else None
            copy_action = menu.addAction("🔗  Copiar enlace") if not is_local else None

        all_results = self.model.results()
        if len(all_results) > 1:
            menu.addSeparator()
            all_menu = menu.addMenu(f"📋  Todos los resultados ({len(all_results)})")
            play_all_act = all_menu.addAction("▶  Reproducir todos")
            add_all_queue_act = all_menu.addAction("➕  Añadir todos a la cola")
            all_menu.addSeparator()
            self._build_playlist_menu(all_menu, target_results=all_results, label="📑  Añadir todos a playlist")
            fav_all_act = all_menu.addAction("⭐  Añadir todos a favoritos")
            total_yt = sum(1 for r in all_results if r.get("source") != "local")
            download_all_act = (
                all_menu.addAction(f"⬇️  Descargar todos ({total_yt})…")
                if total_yt > 0
                else None
            )
        else:
            play_all_act = None
            add_all_queue_act = None
            fav_all_act = None
            download_all_act = None

        chosen = menu.exec(global_pos)
        if chosen is None:
            return

        if chosen is play_action:
            if is_multiple:
                self.play_selected_requested.emit(selected)
            else:
                self.play_requested.emit(selected[0])
        elif video_action is not None and chosen is video_action:
            self.play_video_requested.emit(selected[0])
        elif chosen is add_queue_action:
            self.add_to_queue_requested.emit(selected)
        elif fav_action is not None and chosen is fav_action:
            self.add_to_favorites_requested.emit(selected)
        elif download_action is not None and chosen is download_action:
            if is_multiple:
                self.download_selected_requested.emit(selected)
            else:
                self.download_requested.emit(selected[0])
        elif folder_action is not None and chosen is folder_action:
            self.open_folder_requested.emit(selected[0])
        elif copy_action is not None and chosen is copy_action:
            QApplication.clipboard().setText(str(selected[0].get("url", "")))
            self.status_message.emit("Enlace copiado al portapapeles")
        elif play_all_act is not None and chosen is play_all_act:
            self.play_all_requested.emit(all_results)
        elif add_all_queue_act is not None and chosen is add_all_queue_act:
            self.add_to_queue_requested.emit(all_results)
        elif fav_all_act is not None and chosen is fav_all_act:
            self.add_to_favorites_requested.emit(all_results)
        elif download_all_act is not None and chosen is download_all_act:
            self.download_all_requested.emit()
        elif chosen.property("playlist_id"):
            target_items = chosen.property("target_items") or selected
            self.add_to_playlist_requested.emit(target_items, chosen.property("playlist_id"))
        elif chosen.property("create_playlist"):
            target_items = chosen.property("target_items") or selected
            self.create_playlist_requested.emit(target_items)

    def _build_playlist_menu(
        self,
        menu: QMenu,
        target_results: list[dict],
        label: str = "📑  Añadir a playlist",
    ) -> QMenu:
        submenu = menu.addMenu(label)
        for playlist in self._playlists:
            action = submenu.addAction(playlist.get("name", "Playlist"))
            action.setProperty("playlist_id", playlist.get("id", ""))
            action.setProperty("target_items", target_results)
        if self._playlists:
            submenu.addSeparator()
        create = submenu.addAction("Nueva playlist…")
        create.setProperty("create_playlist", True)
        create.setProperty("target_items", target_results)
        return submenu
