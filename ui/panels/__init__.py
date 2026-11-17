"""Paneles de la interfaz."""

from ui.panels.controls_panel import ControlsPanel
from ui.panels.library_panel import LibraryPanel
from ui.panels.lyrics_panel import LyricsPanel
from ui.panels.now_playing import NowPlayingPanel
from ui.panels.playlist_panel import PlaylistPanel
from ui.panels.queue_panel import QueuePanel
from ui.panels.results_panel import ResultsPanel
from ui.panels.settings_dialog import SettingsDialog
from ui.panels.sidebar import NavItem, Sidebar

__all__ = [
    "ControlsPanel",
    "LibraryPanel",
    "LyricsPanel",
    "NavItem",
    "NowPlayingPanel",
    "PlaylistPanel",
    "QueuePanel",
    "ResultsPanel",
    "SettingsDialog",
    "Sidebar",
]
