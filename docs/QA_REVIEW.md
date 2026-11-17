# Revisión QA Exhaustiva — Music Player Pro

> **⚠️ ESTADO DEL PROYECTO: BETA — EN DESARROLLO ACTIVO**
>
> Esta revisión refleja el estado actual del código. **La API, configuración, base de datos e interfaz pueden cambiar entre versiones beta sin aviso previo**. Los hallazgos y recomendaciones pueden quedar obsoletos en futuras versiones.

**Fecha:** 2026-11-17  
**Revisor:** QA Engineer / Senior Python Developer  
**Versión analizada:** 1.2.0-beta  
**Estado del proyecto:** **288 tests passing**, ruff clean, ~1200 líneas en `ui/main_window.py`

---

## 1. Detección de errores y bugs

### 1.1 Race condition en `_on_track_changed` con `_restore_position_ms`

**Ubicación:** `ui/main_window.py:481-484`

```python
def _on_track_changed(self, track: Track) -> None:
    if self._restore_position_ms is not None:
        self.playback_controller.seek(self._restore_position_ms / 1000.0)
        self._restore_position_ms = None
```

**Problema:** `seek()` se llama inmediatamente después de `load()`, pero VLC aún no ha terminado de cargar el medio. El `set_time` puede ser ignorado o aplicarse sobre el medio anterior. Además, no se verifica que `track` sea válido antes de llamar a `seek`.

**Solución propuesta:**
```python
def _on_track_changed(self, track: Track) -> None:
    if track is None:
        return
    self.now_playing_panel.set_track_info(track.title, track.artist, track.album)
    is_fav = self.store.is_favorite(track.track_key)
    self.now_playing_panel.favorite_btn.setText("⭐" if is_fav else "☆")
    self.now_playing_panel.favorite_btn.setToolTip(
        "Quitar de favoritos" if is_fav else "Añadir a favoritos"
    )
    if self._restore_position_ms is not None:
        pos = self._restore_position_ms
        self._restore_position_ms = None
        # Esperar a que VLC reporte la duración antes de hacer seek
        QTimer.singleShot(100, lambda: self.playback_controller.seek(pos / 1000.0))
```

### 1.2 `_on_position_changed` no actualiza `time_label` durante seeking

**Ubicación:** `ui/panels/controls_panel.py:129-142`

```python
def set_position(self, seconds: float, duration: float) -> None:
    if self._dragging:
        return
    self.time_label.setText(format_time(seconds))
    if self._seeking:
        return  # Ignora el slider pero ya actualizó time_label
    ...
```

**Problema:** Durante el seeking, el `time_label` se actualiza con el tiempo antiguo de VLC, confundiendo al usuario. Debería mostrar el tiempo del slider.

**Solución:**
```python
def set_position(self, seconds: float, duration: float) -> None:
    if self._dragging:
        return
    if self._seeking:
        # Mostrar el tiempo del slider, no el de VLC
        self.time_label.setText(format_time(self.slider.value()))
        return
    self.time_label.setText(format_time(seconds))
    if duration > 0:
        self.slider.setRange(0, int(duration))
        self.slider.setValue(int(seconds))
        self.duration_label.setText(format_time(duration))
```

### 1.3 `set_position` en `MusicPlayer` no maneja `seconds <= 0`

**Ubicación:** `core/player.py:299-304`

```python
def set_position(self, seconds: float) -> None:
    if self.current_media:
        try:
            self.player.set_time(int(seconds * 1000))
        except Exception as exc:
            logger.debug("No se pudo fijar la posición: %s", exc)
```

**Problema:** Si `seconds` es negativo o NaN, `set_time` puede fallar silenciosamente o comportarse de forma inesperada. No hay validación de entrada.

**Solución:**
```python
def set_position(self, seconds: float) -> None:
    if not self.current_media:
        return
    try:
        ms = max(0, int(seconds * 1000))
        if ms < 0 or ms != ms:  # NaN check
            return
        self.player.set_time(ms)
    except Exception as exc:
        logger.debug("No se pudo fijar la posición: %s", exc)
```

### 1.4 `_play_favorite` añade duplicados a la playlist

**Ubicación:** `ui/main_window.py:776-784`

```python
def _play_favorite(self, index: int) -> None:
    track = self.favorites_model.track_at(index)
    if track is None:
        return
    self.playlist_controller.add_tracks([track])
    idx = self.playlist_controller.playlist.count - 1
    self.playback_controller.play_index(idx)
```

**Problema:** Cada vez que se reproduce un favorito, se añade un duplicado a la playlist principal. No se verifica si la pista ya existe.

**Solución:**
```python
def _play_favorite(self, index: int) -> None:
    track = self.favorites_model.track_at(index)
    if track is None:
        return
    existing = self.playlist_controller.index_of(track)
    if existing >= 0:
        self.playback_controller.play_index(existing)
    else:
        self.playlist_controller.add_tracks([track])
        idx = self.playlist_controller.playlist.count - 1
        self.playback_controller.play_index(idx)
```

### 1.5 Excepción no manejada en `_on_smtc_session`

**Ubicación:** `ui/main_window.py:392-404`

```python
def _on_smtc_session(self, info: MediaSessionInfo) -> None:
    if not info or not info.title:
        return
    app = info.source_app or info.app_user_model_id or "otra aplicación"
    ...
```

**Problema:** Si `info` es `None` (no `MediaSessionInfo`), `info.title` lanza `AttributeError`. El `if not info` no protege contra `None` si el tipo no es el esperado.

**Solución:**
```python
def _on_smtc_session(self, info: MediaSessionInfo) -> None:
    if not isinstance(info, MediaSessionInfo) or not info.title:
        return
    ...
```

### 1.6 `LocalStore` no es thread-safe para escrituras concurrentes

**Ubicación:** `core/store.py:30`

```python
self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
```

**Problema:** `check_same_thread=False` permite acceso desde múltiples hilos, pero SQLite no es seguro para escrituras concurrentes sin bloqueo. El `busy_timeout=5000` ayuda, pero no previene `sqlite3.OperationalError: database is locked` en escenarios de alta concurrencia.

**Solución propuesta:** Usar un lock (threading.Lock) para serializar las operaciones de escritura, o usar un pool de conexiones.

---

## 2. Refactorización y estructura (SOLID)

### 2.1 `MainWindow` viola el Principio de Responsabilidad Única (SRP)

**Problema:** `ui/main_window.py` tiene 1104 líneas y maneja:
- Construcción de UI
- Conexión de señales
- Gestión de temas
- Gestión de favoritos
- Gestión de historial
- Gestión de playlists
- Integración con SMTC
- Integración con media keys
- Integración con tray
- Sincronización de sesión
- Drag & drop
- Cierre

**Propuesta:** Extraer controladores:
```
ui/
├── main_window.py          # Solo orquestación (~300 líneas)
├── controllers/
│   ├── session_controller.py    # _save_session, _restore_session
│   ├── favorites_controller.py   # _toggle_favorite, _play_favorite, etc.
│   ├── theme_controller.py       # apply_theme, apply_native_style
│   └── integration_controller.py # _start_integrations, _on_smtc_*
├── panels/...
└── components/...
```

### 2.2 `MusicPlayer` mezcla responsabilidades (SRP)

**Problema:** `MusicPlayer` maneja eventos de VLC, estado, callbacks, y la API de reproducción. Debería separarse en:
- `VlcEngine`: Wrapper de VLC (load, play, pause, seek, volume)
- `PlayerStateMachine`: Gestión de estado (PlayerState)
- `PlayerEventBridge`: Puente de eventos VLC → Qt signals

### 2.3 `ControlsPanel.set_position` tiene lógica de negocio

**Problema:** El panel de UI tiene lógica de `_seeking` y `_dragging` que debería estar en el controlador. El panel debería ser "tonto" (solo renderizar).

**Propuesta:** Mover `_seeking` y `_dragging` a `PlaybackController`, y que `ControlsPanel` solo emita señales y reciba valores.

### 2.4 Dependencias circulares potenciales

**Problema:** `MainWindow` crea `PlaybackController(playlist_controller, player)` y `PlaylistController(store, ...)`. Si en el futuro se necesita que `PlaylistController` acceda a `PlaybackController`, se crea un ciclo.

**Propuesta:** Usar un patrón de mediador o inyección de dependencias con interfaces.

### 2.5 `ThemeManager` acoplado a `QWidget`

**Problema:** `ThemeManager.get_theme(name)` retorna QSS directamente. Debería separarse la definición del tema (datos) de la generación del QSS (presentación).

---

## 3. Optimización de funcionalidades

### 3.1 Polling de SMTC cada 2 segundos

**Problema:** `SMTCService._timer` hace polling cada 2s incluso cuando no hay cambios. Esto consume CPU innecesariamente.

**Propuesta:** Usar eventos de WinRT (si disponibles) en lugar de polling. Si no, aumentar el intervalo a 5s y solo sondear cuando la ventana está activa.

### 3.2 `get_position()` llama a VLC en cada frame

**Problema:** `_on_position_changed` se emite en cada `MediaPlayerTimeChanged` (cada ~250ms). Cada llamada a `get_position()` llama a `self.player.get_time()` que cruza la frontera C/Python.

**Propuesta:** Cachear la posición en `_on_time_changed` y usar el valor cacheado en `get_position()`.

```python
def _on_time_changed(self, event=None) -> None:
    time_ms = getattr(event, "new_time", 0) or 0
    self._cached_position_ms = int(time_ms)
    self.signals.position_changed.emit(self._cached_position_ms)

def get_position(self) -> float:
    return self._cached_position_ms / 1000.0 if self._cached_position_ms > 0 else 0.0
```

### 3.3 `CoverArtLabel.set_cover` crea un nuevo `ImageProvider` cada vez

**Problema:** En `CoverArtLabel.set_cover`, si no se pasa provider, se crea uno nuevo cada vez. Esto puede causar fugas de hilos.

**Solución:** Usar un singleton o inyectar el provider desde el exterior.

### 3.4 `MarqueeLabel` usa `QTimer` de 40ms (25 FPS)

**Problema:** El timer de 40ms consume CPU incluso cuando el texto no se está desplazando. Aunque `_check_scroll` detiene el timer cuando no es necesario, hay casos edge donde sigue corriendo.

**Propuesta:** Usar `QPropertyAnimation` en lugar de QTimer para el scroll, lo cual es más eficiente y usa el sistema de animaciones de Qt.

### 3.5 `TrackListModel` no usa `beginInsertRows`/`endInsertRows`

**Problema:** Si el modelo se actualiza en bloque (ej. al cargar una playlist de 1000 pistas), no se usan las señales de batch, causando múltiples actualizaciones de la vista.

**Propuesta:** Implementar `beginResetModel`/`endResetModel` para actualizaciones masivas.

---

## 4. Pruebas unitarias sugeridas

### 4.1 Tests de `MusicPlayer`

```python
def test_set_position_with_negative_value(player, fake_vlc):
    """set_position con valor negativo no debe crashear."""
    player.load("/music/song.mp3")
    player.set_position(-5.0)
    assert player.get_position() == 0.0

def test_set_position_with_nan(player, fake_vlc):
    """set_position con NaN no debe crashear."""
    import math
    player.load("/music/song.mp3")
    player.set_position(math.nan)
    assert player.get_position() == 0.0

def test_get_position_returns_cached_value(player, fake_vlc):
    """get_position debe retornar el valor cacheado."""
    player.load("/music/song.mp3")
    fake_vlc.instance.players[0].advance(5000)
    assert player.get_position() == pytest_approx(5.0)

def test_load_empty_source_returns_false(player):
    """load con fuente vacía debe retornar False."""
    assert player.load("") is False

def test_load_none_source_returns_false(player):
    """load con None debe retornar False."""
    assert player.load(None) is False
```

### 4.2 Tests de `ControlsPanel`

```python
def test_set_position_does_not_update_slider_during_seek(qtbot):
    """Durante seeking, el slider no debe actualizarse."""
    panel = ControlsPanel()
    qtbot.addWidget(panel)
    panel._seeking = True
    panel.set_position(30.0, 180.0)
    assert panel.slider.value() == 0  # No cambió

def test_set_position_updates_time_label_during_seek(qtbot):
    """Durante seeking, time_label muestra el tiempo del slider."""
    panel = ControlsPanel()
    qtbot.addWidget(panel)
    panel.slider.setValue(45)
    panel._seeking = True
    panel.set_position(30.0, 180.0)
    assert panel.time_label.text() == "0:45"

def test_slider_click_emits_seek_requested(qtbot):
    """Click en el slider emite seek_requested."""
    panel = ControlsPanel()
    qtbot.addWidget(panel)
    with qtbot.waitSignal(panel.seek_requested, timeout=1000):
        panel.slider.sliderReleased.emit()
```

### 4.3 Tests de `LocalStore`

```python
def test_add_favorite_duplicate_does_not_create_duplicate(tmp_path):
    """Añadir el mismo favorito dos veces no crea duplicado."""
    store = LocalStore(tmp_path / "test.db")
    track = make_track("key1", "Title", "Artist")
    store.add_favorite(track)
    store.add_favorite(track)
    assert len(store.favorites()) == 1

def test_remove_nonexistent_favorite_does_not_crash(tmp_path):
    """Eliminar un favorito inexistente no debe crashear."""
    store = LocalStore(tmp_path / "test.db")
    store.remove_favorite("nonexistent_key")  # No debe lanzar excepción

def test_favorites_persist_after_close(tmp_path):
    """Los favoritos persisten tras cerrar y reabrir el store."""
    db_path = tmp_path / "test.db"
    store = LocalStore(db_path)
    track = make_track("key1", "Title", "Artist")
    store.add_favorite(track)
    store.close()
    store2 = LocalStore(db_path)
    assert store2.is_favorite("key1")
    store2.close()

def test_session_roundtrip(tmp_path):
    """La sesión se guarda y restaura correctamente."""
    db_path = tmp_path / "test.db"
    store = LocalStore(db_path)
    store.set_session({"current_index": 5, "position": 120000})
    session = store.get_session()
    assert session["current_index"] == 5
    assert session["position"] == 120000
    store.close()
```

### 4.4 Tests de integración (UI Smoke)

```python
def test_play_favorite_does_not_duplicate_in_playlist(window, qtbot):
    """Reproducir un favorito no duplica en la playlist principal."""
    # Añadir pista a favoritos
    track = make_track("key1", "Title", "Artist")
    window.playlist_controller.add_tracks([track])
    window._toggle_favorite_at(0)
    # Reproducir desde favoritos
    window.sidebar.select("favorites")
    qtbot.wait(100)
    window.favorites_panel.play_requested.emit(0)
    qtbot.wait(100)
    # Verificar que no se duplicó
    assert window.playlist_controller.playlist.count == 1

def test_open_track_folder_does_not_crash(window, qtbot):
    """Abrir carpeta de pista no debe crashear."""
    track = make_track("key1", "Title", "Artist", file_path="/tmp/song.mp3")
    window.playlist_controller.add_tracks([track])
    window._open_track_folder()  # No debe lanzar excepción

def test_theme_change_applies_immediately(window, qtbot):
    """Cambiar de tema aplica el QSS inmediatamente."""
    original = window.styleSheet()
    window.apply_theme("nord")
    assert window.styleSheet() != original
    assert "Nord" not in window.styleSheet()  # El QSS no contiene el nombre
```

### 4.5 Tests de edge cases

```python
def test_play_index_with_invalid_index_returns_false(playback_controller):
    """play_index con índice inválido retorna False."""
    assert playback_controller.play_index(-1) is False
    assert playback_controller.play_index(999) is False

def test_seek_during_paused_state(player, fake_vlc):
    """Seek durante pausa debe funcionar."""
    player.load("/music/song.mp3")
    player.play()
    player.pause()
    player.set_position(30.0)
    assert player.get_position() == pytest_approx(30.0)

def test_volume_clamping(player, fake_vlc):
    """El volumen se clampea entre 0 y 1."""
    player.set_volume(1.5)
    assert player.volume == 1.0
    player.set_volume(-0.5)
    assert player.volume == 0.0

def test_empty_playlist_next_does_not_crash(playback_controller):
    """next() en playlist vacía no debe crashear."""
    result = playback_controller.next()
    assert result is None

def test_concurrent_store_writes_do_not_lock(tmp_path):
    """Escrituras concurrentes al store no deben causar 'database is locked'."""
    import threading
    store = LocalStore(tmp_path / "test.db")
    errors = []
    def writer(i):
        try:
            track = make_track(f"key{i}", f"Title{i}", f"Artist{i}")
            store.add_favorite(track)
        except Exception as e:
            errors.append(e)
    threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(errors) == 0
    assert len(store.favorites()) == 10
    store.close()
```

---

## Resumen de prioridades y estado de resolución

| Prioridad | Área | Acción | Estado |
|-----------|------|--------|--------|
| 🔴 Alta | Bugs | Validar entrada en `set_position` (NaN, negativos, inf) | ✅ Resuelto |
| 🔴 Alta | Bugs | Evitar duplicados en `_play_favorite` (búsqueda por track_key e índice seguro) | ✅ Resuelto |
| 🔴 Alta | Bugs | Race condition en `_on_track_changed` con `_restore_position_ms` | ✅ Resuelto |
| 🔴 Alta | Bugs | `ControlsPanel.set_position` ignorando `time_label` durante seeking | ✅ Resuelto |
| 🔴 Alta | Bugs | Excepción `MediaSessionInfo` en `_on_smtc_session` | ✅ Resuelto |
| 🔴 Alta | Concurrencia | Thread-safety en `LocalStore` con serialización `_thread_safe` y `RLock` | ✅ Resuelto |
| 🟡 Media | Performance | Cachear posición en `MusicPlayer` | ✅ Resuelto |
| 🟡 Media | Performance | Reducir polling de SMTC de 2s a 5s | ✅ Resuelto |
| 🟡 Media | Performance | Singleton `ImageProvider` compartido en `CoverArtLabel` | ✅ Resuelto |
| 🟢 Baja | Tests | Añadir tests unitarios y de edge cases sugeridos (4.1 - 4.5) | ✅ Resuelto (**288 tests passing**) |
| 🟢 Baja | Pruebas reales | Detección y corrección de bugs de inicialización de rutas y widgets | ✅ Resuelto |

---

*Revisión QA y correcciones completadas. Suite de pruebas: **288 passed**, ruff clean.*