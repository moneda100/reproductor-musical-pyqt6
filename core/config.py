"""Configuración central de la aplicación.

Se persiste con ``QSettings`` (Windows: registro) y expone valores por
defecto seguros. Todas las claves están namespaced bajo ``MusicPlayerPro/``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

from PyQt6.QtCore import QSettings

from core.paths import APP_NAME, APP_ORG, get_paths

SETTINGS_ORG = APP_ORG
SETTINGS_APP = APP_NAME


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class AppConfig:
    """Preferencias de la aplicación."""

    # --- apariencia ---
    theme: str = "auto"  # "auto", "dark", "light", o nombre de tema específico
    native_style: str = ""

    # --- reproducción ---
    volume: int = 70
    shuffle: bool = False
    repeat_mode: str = "none"

    # --- rutas ---
    download_dir: str = ""
    library_dirs: list[str] = field(default_factory=list)

    # --- descargas ---
    download_format: str = "mp3"
    download_mode: str = "playlist"

    # --- caché ---
    max_cache_mb: int = 512

    # --- integraciones ---
    lastfm_api_key: str = ""
    lastfm_username: str = ""
    lastfm_session_key: str = ""
    features_lyrics: bool = True
    features_lastfm: bool = False
    features_tray: bool = True
    features_smtc: bool = True
    features_audio_detection: bool = True
    # --- mini reproductor ---
    mini_stay_on_top: bool = True

    # --- ventana ---
    window_geometry: str = ""
    window_state: str = ""
    last_view: str = "home"

    # --- tamaño de vídeo (incrustado) ---
    video_size_mode: str = "standard"  # standard | cinema | fullscreen | resizable
    video_width: int = 960
    video_height: int = 540

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered)


class ConfigStore:
    """Lectura/escritura de :class:`AppConfig` sobre ``QSettings``.

    Se usa el formato INI dentro de la carpeta de datos de la app (en vez del
    registro de Windows) para que la configuración sea portable, no contamine
    el registro del usuario y pueda aislarse en las pruebas.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        if settings is not None:
            self._settings = settings
            return
        paths = get_paths()
        QSettings.setPath(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            str(paths.root),
        )
        self._settings = QSettings(
            QSettings.Format.IniFormat,
            QSettings.Scope.UserScope,
            SETTINGS_ORG,
            SETTINGS_APP,
        )

    # -- lectura ---------------------------------------------------
    def load(self) -> AppConfig:
        s = self._settings
        paths = get_paths()
        cfg = AppConfig(
            theme=s.value("appearance/theme", "dark", str),
            native_style=s.value("appearance/native_style", "", str),
            volume=int(s.value("playback/volume", 70)),
            shuffle=_bool(s.value("playback/shuffle", False), False),
            repeat_mode=s.value("playback/repeat_mode", "none", str),
            download_dir=s.value("paths/download_dir", "", str),
            library_dirs=list(s.value("paths/library_dirs", [], list) or []),
            download_format=str(s.value("downloads/format", "mp3")).lower(),
            download_mode=str(s.value("downloads/mode", "playlist")).lower(),
            max_cache_mb=int(s.value("cache/max_mb", 512)),
            lastfm_api_key=s.value("lastfm/api_key", "", str),
            lastfm_username=s.value("lastfm/username", "", str),
            lastfm_session_key=s.value("lastfm/session_key", "", str),
            features_lyrics=_bool(s.value("features/lyrics", True), True),
            features_lastfm=_bool(s.value("features/lastfm", False), False),
            features_tray=_bool(s.value("features/tray", True), True),
            features_smtc=_bool(s.value("features/smtc", True), True),
            features_audio_detection=_bool(s.value("features/audio_detection", True), True),
            mini_stay_on_top=_bool(s.value("mini/stay_on_top", True), True),
            window_geometry=s.value("window/geometry", "", str),
            window_state=s.value("window/state", "", str),
            last_view=s.value("window/last_view", "home", str),
            video_size_mode=s.value("video/size_mode", "standard", str),
            video_width=int(s.value("video/width", 960)),
            video_height=int(s.value("video/height", 540)),
        )
        if not cfg.download_dir:
            cfg.download_dir = str(paths.youtube_cache_dir)
        return cfg

    # -- escritura -------------------------------------------------
    def save(self, cfg: AppConfig) -> None:
        s = self._settings
        s.setValue("appearance/theme", cfg.theme)
        s.setValue("appearance/native_style", cfg.native_style)
        s.setValue("playback/volume", int(cfg.volume))
        s.setValue("playback/shuffle", bool(cfg.shuffle))
        s.setValue("playback/repeat_mode", cfg.repeat_mode)
        s.setValue("paths/download_dir", cfg.download_dir)
        s.setValue("paths/library_dirs", list(cfg.library_dirs))
        s.setValue("downloads/format", cfg.download_format)
        s.setValue("downloads/mode", cfg.download_mode)
        s.setValue("cache/max_mb", int(cfg.max_cache_mb))
        s.setValue("lastfm/api_key", cfg.lastfm_api_key)
        s.setValue("lastfm/username", cfg.lastfm_username)
        s.setValue("lastfm/session_key", cfg.lastfm_session_key)
        s.setValue("features/lyrics", bool(cfg.features_lyrics))
        s.setValue("features/lastfm", bool(cfg.features_lastfm))
        s.setValue("features/tray", bool(cfg.features_tray))
        s.setValue("features/smtc", bool(cfg.features_smtc))
        s.setValue("features/audio_detection", bool(cfg.features_audio_detection))
        s.setValue("mini/stay_on_top", bool(cfg.mini_stay_on_top))
        s.setValue("window/geometry", cfg.window_geometry)
        s.setValue("window/state", cfg.window_state)
        s.setValue("window/last_view", cfg.last_view)
        s.setValue("video/size_mode", cfg.video_size_mode)
        s.setValue("video/width", int(cfg.video_width))
        s.setValue("video/height", int(cfg.video_height))
        s.sync()


def load_config() -> AppConfig:
    return ConfigStore().load()


def save_config(cfg: AppConfig) -> None:
    ConfigStore().save(cfg)
