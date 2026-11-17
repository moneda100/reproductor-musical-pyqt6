"""Doble de prueba para ``python-vlc``.

Simula lo mínimo que necesita :class:`core.player.MusicPlayer`:
``Instance``, ``media_player_new``, los estados, el reloj y los eventos.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any, Callable, Optional


class State(IntEnum):
    NothingSpecial = 0
    Opening = 1
    Buffering = 2
    Playing = 3
    Paused = 4
    Stopped = 5
    Ended = 6
    Error = 7


class EventType(IntEnum):
    MediaPlayerNothingSpecial = 0
    MediaPlayerOpening = 1
    MediaPlayerBuffering = 2
    MediaPlayerPlaying = 3
    MediaPlayerPaused = 4
    MediaPlayerStopped = 5
    MediaPlayerEndReached = 6
    MediaPlayerEncounteredError = 7
    MediaPlayerLengthChanged = 8
    MediaPlayerTimeChanged = 9
    MediaPlayerMediaChanged = 10


class FakeEvent:
    """Evento con los atributos que consulta el reproductor."""

    def __init__(self, **kwargs: Any) -> None:
        self.new_time = kwargs.get("new_time", 0)
        self.new_length = kwargs.get("new_length", 0)
        self.new_buffer = kwargs.get("new_buffer", 100)


class FakeEventManager:
    def __init__(self, player: "FakeMediaPlayer") -> None:
        self._player = player
        self._handlers: dict[int, list[Callable]] = {}

    def on(self, event: int, handler: Callable) -> "FakeEventHandle":
        self._handlers.setdefault(int(event), []).append(handler)
        return FakeEventHandle(self, int(event), handler)

    def event_attach(self, event: int, handler: Callable) -> int:
        self.on(event, handler)
        return 0

    def event_detach(self, event: int, handler: Callable) -> int:
        self.remove(event, handler)
        return 0

    def emit(self, event: int, **kwargs: Any) -> None:
        payload = FakeEvent(**kwargs)
        for handler in list(self._handlers.get(int(event), [])):
            handler(payload)

    def remove(self, event: int, handler: Callable) -> None:
        handlers = self._handlers.get(int(event), [])
        if handler in handlers:
            handlers.remove(handler)


class FakeEventHandle:
    def __init__(self, manager: FakeEventManager, event: int, handler: Callable) -> None:
        self._manager = manager
        self._event = event
        self._handler = handler

    def detach(self) -> None:
        self._manager.remove(self._event, self._handler)


class FakeMedia:
    def __init__(self, source: str) -> None:
        self.source = source
        self._tracks: list[dict] = []
        self._stats = None

    def get_tracks_info(self) -> list[dict]:
        return list(self._tracks)

    def get_stats(self):
        return self._stats

    def set_tracks(self, tracks: list[dict]) -> None:
        self._tracks = tracks


class FakeMediaPlayer:
    def __init__(self) -> None:
        self.media: Optional[FakeMedia] = None
        self.state = State.Stopped
        self._time = 0
        self._length = 0
        self._volume = 0
        self._manager = FakeEventManager(self)
        self.play_calls = 0
        self.pause_calls = 0
        self.stop_calls = 0
        self.hwnd: Optional[int] = None
        self.xwindow: Optional[int] = None
        self.nsobject: Optional[int] = None

    # -- reproducción ------------------------------------------------
    def play(self) -> int:
        self.play_calls += 1
        if self.media is None:
            return -1
        self.state = State.Playing
        return 0

    def pause(self) -> None:
        self.pause_calls += 1
        if self.state == State.Playing:
            self.state = State.Paused
        elif self.state == State.Paused:
            self.state = State.Playing

    def set_pause(self, paused: bool) -> None:
        self.pause_calls += 1
        self.state = State.Paused if paused else State.Playing

    def stop(self) -> None:
        self.stop_calls += 1
        self.state = State.Stopped
        self._time = 0

    # -- medio ---------------------------------------------------------
    def set_media(self, media: FakeMedia) -> None:
        self.media = media
        self.state = State.Stopped
        self._time = 0

    def get_time(self) -> int:
        return self._time

    def set_time(self, time_ms: int) -> None:
        self._time = time_ms

    def get_length(self) -> int:
        return self._length

    def get_state(self) -> int:
        return self.state

    def audio_set_volume(self, volume: int) -> int:
        self._volume = volume
        return 0

    def audio_get_volume(self) -> int:
        return self._volume

    # -- vídeo ----------------------------------------------------------
    def set_hwnd(self, hwnd: int) -> None:
        self.hwnd = hwnd

    def set_xwindow(self, xid: int) -> None:
        self.xwindow = xid

    def set_nsobject(self, ns_object: int) -> None:
        self.nsobject = ns_object

    # -- eventos ----------------------------------------------------------
    def event_manager(self) -> FakeEventManager:
        return self._manager

    # -- utilidades de test -----------------------------------------------
    def set_length(self, length_ms: int) -> None:
        self._length = length_ms
        self._manager.emit(EventType.MediaPlayerLengthChanged, new_length=length_ms)

    def advance(self, delta_ms: int) -> None:
        self._time += delta_ms
        self._manager.emit(EventType.MediaPlayerTimeChanged, new_time=self._time)

    def end_reached(self) -> None:
        self.state = State.Ended
        self._manager.emit(EventType.MediaPlayerEndReached)

    def encountered_error(self) -> None:
        self.state = State.Error
        self._manager.emit(EventType.MediaPlayerEncounteredError)


class FakeInstance:
    def __init__(self) -> None:
        self.players: list[FakeMediaPlayer] = []
        self.media_sources: list[str] = []

    def media_player_new(self) -> FakeMediaPlayer:
        player = FakeMediaPlayer()
        self.players.append(player)
        return player

    def media_new(self, source: str) -> FakeMedia:
        self.media_sources.append(source)
        return FakeMedia(source)

    def media_new_path(self, path: str) -> FakeMedia:
        self.media_sources.append(path)
        return FakeMedia(path)


class FakeVlcModule:
    """Módulo falso compatible con la parte de la API de ``vlc`` que usamos."""

    State = State
    EventType = EventType

    def __init__(self) -> None:
        self.instance = FakeInstance()

    def Instance(self, *args: Any, **kwargs: Any) -> FakeInstance:  # noqa: N802
        return self.instance
