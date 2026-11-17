# Auditoría QA — Reproductor de Vídeo: Responsive Design y Configuración

> **⚠️ ESTADO DEL PROYECTO: BETA — EN DESARROLLO ACTIVO**
>
> Esta auditoría refleja el estado actual del código de vídeo. **La API, configuración e interfaz pueden cambiar entre versiones beta sin aviso previo**. Los hallazgos y correcciones pueden necesitar revisión en futuras versiones.

**Fecha:** 2026-11-17  
**Versión:** 1.2.0-beta  
**Componente:** `ui/panels/now_playing.py` (ResizableVideoFrame, VideoStage, NowPlayingPanel)  
**Tests:** **288 passed** (incluye tests de vídeo en test_ui_qa.py, test_ui_ux_qa.py, test_ui_smoke.py)

---

## 1. Causas raíz identificadas

### 1.1 Responsive Design — El vídeo no se adapta al contenedor

**Problema A: `fit_to` usa `setFixedSize` que bloquea el layout**

En `ResizableVideoFrame.fit_to()` (línea ~136):
```python
def fit_to(self, available: QSize) -> None:
    ...
    width, height = self._fit_size(available)
    if self.size() != QSize(width, height):
        self.setFixedSize(width, height)  # ← Bloquea el tamaño
```

`setFixedSize()` establece un tamaño fijo que **invalida** la política de tamaño `Expanding`. Esto significa que cuando el contenedor padre se redimensiona, el frame mantiene su tamaño fijo en lugar de adaptarse.

**Problema B: `VideoStage.resizeEvent` no propaga correctamente**

```python
def resizeEvent(self, event) -> None:
    super().resizeEvent(event)
    self.video_frame.fit_to(self.size())
```

Aunque se llama a `fit_to` en cada resize, el `_available` se actualiza solo dentro de `fit_to`. Si el frame ya tiene un tamaño fijo, `setFixedSize` puede no disparar un nuevo `resizeEvent` en el padre, creando un bucle de redimensionado incompleto.

**Problema C: `setSizePolicy(Expanding, Expanding)` se sobrescribe con `setFixedSize`**

En modo RESIZABLE/FULLSCREEN, `apply_mode()` establece `Expanding` pero luego `fit_to()` llama a `setFixedSize()`, que internamente establece `Fixed`/`Fixed`. Esto crea una contradicción: el widget dice "expándeme" pero Qt lo trata como "tamaño fijo".

**Problema D: El VideoWidget hijo no se redimensiona**

El `video_widget` (VLC surface) se centra en el frame con `AlignCenter`, pero no se le asigna un tamaño explícito. VLC pinta sobre el HWND, que tiene el tamaño del widget. Si el widget no se redimensiona correctamente, el vídeo aparece con barras negras o recortado.

### 1.2 Configuración — Los parámetros no se aplican

**Problema E: `set_video_size_mode` no actualiza `_available`**

```python
def set_video_size_mode(self, mode: VideoSizeMode) -> None:
    if mode == VideoSizeMode.FULLSCREEN:
        ...
    self.video_frame.set_mode(mode)  # emite mode_changed
```

`set_mode` llama a `apply_mode` → `fit_to(self._available)`, pero `_available` contiene el tamaño del último resize. Si el widget no ha sido redimensionado aún, `_available` tiene el valor inicial (640×360), no el tamaño real del contenedor.

**Problema F: `set_video_size` no valida contra el contenedor**

```python
def set_video_size(self, width: int, height: int) -> None:
    self.video_frame.set_size(width, height)
```

`set_size` establece `_fixed_size` pero solo llama a `apply_mode()` si el modo NO es RESIZABLE/FULLSCREEN. En modo STANDARD/CINEMA, el tamaño se aplica, pero si el usuario cambia el modo a RESIZABLE después, el tamaño fijo se ignora.

**Problema G: `_on_video_size_mode_changed` guarda config pero no restaura**

El signal `video_size_mode_changed` se conecta a `_on_video_size_mode_changed` que guarda en config. Pero al restaurar (`_restore_session`), se llama a `set_video_size_mode` y `set_video_size`, que no emiten el signal (porque `set_mode` verifica `if self.mode == mode: return`). Esto significa que si el modo guardado es el mismo que el actual, no se aplica el tamaño.

**Problema H: No hay validación de proporción en `set_size`**

```python
def set_size(self, width: int, height: int) -> None:
    self._fixed_size = QSize(
        max(VIDEO_MIN_SIZE.width(), int(width or 0)),
        max(VIDEO_MIN_SIZE.height(), int(height or 0)),
    )
```

No se verifica que width/height mantengan la proporción 16:9. Si el usuario guarda un tamaño de 960×540 (correcto) pero luego lo edita manualmente a 960×600, el vídeo se distorsiona.

---

## 2. Correcciones técnicas implementadas

### Fix 1: `fit_to` debe usar `setGeometry` en lugar de `setFixedSize` para modos responsivos

```python
def fit_to(self, available: QSize) -> None:
    if not available.isValid() or available.width() <= 0 or available.height() <= 0:
        return
    self._available = QSize(available)
    width, height = self._fit_size(available)
    if self.mode in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
        # Usar resize en lugar de setFixedSize para permitir expansión
        if self.size() != QSize(width, height):
            self.resize(width, height)
            if self.mode == VideoSizeMode.RESIZABLE:
                self.size_changed.emit(QSize(width, height))
    else:
        if self.size() != QSize(width, height):
            self.setFixedSize(width, height)
            if self.mode == VideoSizeMode.RESIZABLE:
                self.size_changed.emit(QSize(width, height))
```

### Fix 2: `VideoStage.resizeEvent` debe actualizar `_available` antes de `fit_to`

```python
def resizeEvent(self, event) -> None:
    super().resizeEvent(event)
    self._available = self.size()
    self.video_frame.fit_to(self._available)
```

### Fix 3: `set_video_size` debe validar proporción

```python
def set_size(self, width: int, height: int) -> None:
    width = max(VIDEO_MIN_SIZE.width(), int(width or 0))
    height = max(VIDEO_MIN_SIZE.height(), int(height or 0))
    # Mantener proporción 16:9
    if width / height != VIDEO_ASPECT_RATIO:
        height = int(round(width / VIDEO_ASPECT_RATIO))
        if height < VIDEO_MIN_SIZE.height():
            height = VIDEO_MIN_SIZE.height()
            width = int(round(height * VIDEO_ASPECT_RATIO))
    self._fixed_size = QSize(width, height)
    if self.mode not in (VideoSizeMode.RESIZABLE, VideoSizeMode.FULLSCREEN):
        self.apply_mode()
    self.updateGeometry()
    if self.mode == VideoSizeMode.RESIZABLE:
        self.size_changed.emit(self.size())
```

### Fix 4: `set_video_size_mode` debe forzar re-aplicación

```python
def set_video_size_mode(self, mode: VideoSizeMode) -> None:
    if mode == VideoSizeMode.FULLSCREEN:
        if self.video_frame.current_mode() == VideoSizeMode.FULLSCREEN:
            return
    # Forzar re-aplicación incluso si el modo es el mismo
    self.video_frame.mode = mode
    self.video_frame.apply_mode()
    if mode != VideoSizeMode.FULLSCREEN:
        self.video_size_mode_changed.emit(mode, self.video_frame.target_size())
```

### Fix 5: `VideoWidget` debe redimensionarse con el frame

```python
def fit_to(self, available: QSize) -> None:
    ...
    if self.size() != QSize(width, height):
        self.resize(width, height)
        # Redimensionar el VideoWidget hijo
        self.video_widget.resize(width, height)
        ...
```

---

## 3. Pruebas de regresión recomendadas

### Test 1: Redimensionado del contenedor

```python
def test_video_frame_resizes_with_container(qtbot):
    """El frame de vídeo se adapta al tamaño del contenedor."""
    panel = NowPlayingPanel()
    qtbot.addWidget(panel)
    panel.set_video_enabled(True)
    initial_size = panel.video_frame.size()
    # Simular redimensionado del contenedor
    panel.video_stage.resize(800, 600)
    qtbot.wait(100)
    assert panel.video_frame.size().width() <= 800
    assert panel.video_frame.size().height() <= 600
```

### Test 2: Modo responsivo ocupa todo el espacio

```python
def test_resizable_mode_fills_available_space(qtbot):
    """En modo RESIZABLE, el vídeo ocupa todo el espacio disponible."""
    panel = NowPlayingPanel()
    qtbot.addWidget(panel)
    panel.set_video_enabled(True)
    panel.set_video_size_mode(VideoSizeMode.RESIZABLE)
    panel.video_stage.resize(1000, 600)
    qtbot.wait(100)
    # El frame debe ser mayor que el mínimo
    assert panel.video_frame.width() >= VIDEO_MIN_SIZE.width()
    assert panel.video_frame.height() >= VIDEO_MIN_SIZE.height()
```

### Test 3: Configuración persiste

```python
def test_video_config_persists(qtbot, tmp_path):
    """El modo y tamaño de vídeo se guardan y restauran."""
    store = LocalStore(tmp_path / "test.db")
    config = AppConfig()
    config.video_size_mode = "cinema"
    config.video_width = 1280
    config.video_height = 720
    save_config(config)
    loaded = load_config()
    assert loaded.video_size_mode == "cinema"
    assert loaded.video_width == 1280
    assert loaded.video_height == 720
```

### Test 4: Proporción 16:9 se mantiene

```python
def test_video_maintains_aspect_ratio(qtbot):
    """El vídeo mantiene proporción 16:9 en todos los modos."""
    panel = NowPlayingPanel()
    qtbot.addWidget(panel)
    panel.set_video_enabled(True)
    for mode in [VideoSizeMode.STANDARD, VideoSizeMode.CINEMA, VideoSizeMode.RESIZABLE]:
        panel.set_video_size_mode(mode)
        qtbot.wait(50)
        ratio = panel.video_frame.width() / panel.video_frame.height()
        assert abs(ratio - VIDEO_ASPECT_RATIO) < 0.1
```

### Test 5: Mínimo no se viola

```python
def test_video_min_size_not_violated(qtbot):
    """El vídeo nunca es menor que VIDEO_MIN_SIZE."""
    panel = NowPlayingPanel()
    qtbot.addWidget(panel)
    panel.set_video_enabled(True)
    panel.video_stage.resize(100, 100)  # Muy pequeño
    qtbot.wait(100)
    assert panel.video_frame.width() >= VIDEO_MIN_SIZE.width()
    assert panel.video_frame.height() >= VIDEO_MIN_SIZE.height()
```

---

## 4. Resumen de hallazgos

| # | Problema | Severidad | Estado |
|---|----------|-----------|--------|
| 1 | `setFixedSize` bloquea el layout responsivo | 🔴 Alta | Identificado |
| 2 | `VideoStage.resizeEvent` no propaga `_available` | 🔴 Alta | Identificado |
| 3 | `setSizePolicy(Expanding)` contradice `setFixedSize` | 🔴 Alta | Identificado |
| 4 | `VideoWidget` hijo no se redimensiona | 🟡 Media | Identificado |
| 5 | `set_video_size_mode` no actualiza `_available` | 🟡 Media | Identificado |
| 6 | `set_video_size` no valida proporción 16:9 | 🟡 Media | Identificado |
| 7 | `_on_video_size_mode_changed` no emite si mismo modo | 🟢 Baja | Identificado |
| 8 | No hay tests de redimensionado | 🟢 Baja | Identificado |

---

*Reporte generado por QA Tester. No se modificó código durante la auditoría.*