# Reporte de Pruebas Funcionales — Reproductor de Audio (Music Player Pro)

> **⚠️ ESTADO DEL PROYECTO: BETA — EN DESARROLLO ACTIVO**
>
> Este reporte documenta bugs históricos ya corregidos. **La API, configuración, base de datos e interfaz pueden cambiar entre versiones beta sin aviso previo**. Algunos workarounds documentados pueden ya no ser necesarios en versiones actuales.

**Fecha:** 2026-11-17 (actualizado)  
**Versión:** 1.2.0-beta  
**Entorno:** Windows 11 / Python 3.13.2 / PyQt6 / python-vlc  
**Suite de tests:** `pytest -q` → **288 passed** (0 failed)  
**Lint:** `ruff check .` → clean

---

## 1. Visualización de progreso (indicador de tiempo actual)

### Caso de prueba 1.1 — Avance del tiempo en tiempo real
**Pasos para reproducir:**
1. Cargar una pista de ≥ 3 minutos.
2. Iniciar la reproducción.
3. Observar las etiquetas `time_label` y `duration_label` y el slider.

**Comportamiento esperado:**  
El tiempo actual (minutos:segundos) se actualiza cada ~1 s y el slider avanza suavemente.

**Comportamiento actual (antes del fix):**  
El slider permanecía pegado al inicio porque su rango estaba en **milisegundos** (0–180000) mientras `set_position` recibía **segundos** (0–180). El tiempo mostrado sí avanzaba (etiqueta), pero la barra no reflejaba el progreso.

**Estado:** ✅ CORREGIDO — `ui/main_window.py::_on_duration_changed` ahora configura `setRange(0, int(duration_ms / 1000))`, alineando las unidades con `set_position(seconds)`.

---

### Caso de prueba 1.2 — Etiqueta de tiempo formateada
**Pasos:** Reproducir pista de 3:45 y observar la etiqueta a los 90 s.  
**Esperado:** `1:30`  
**Actual:** `1:30` ✅ (format_time en `controls_panel.py` formatea correctamente)  
**Estado:** ✅ Sin fallos.

---

## 2. Error de reinicio al adelantar (seek)

### Caso de prueba 2.1 — Click en la barra de progreso
**Pasos para reproducir:**
1. Reproducir una pista de ≥ 2 minutos.
2. Hacer clic en el centro de la barra de progreso.
3. Observar la posición resultante.

**Comportamiento esperado:**  
La reproducción salta al tiempo correspondiente al punto clickeado.

**Comportamiento actual (antes del fix):**  
El slider volvía al principio (0:00) y la canción se reiniciaba. Causa: `MediaPlayerTimeChanged` de VLC llegaba con el tiempo anterior antes de que `set_time` se aplicara, sobrescribiendo el valor del slider.

**Estado:** ✅ CORREGIDO — `ClickableSlider.mousePressEvent` emite `sliderReleased` tras fijar el valor; `ControlsPanel._on_slider_released` activa la bandera `_seeking` que ignora actualizaciones del slider durante 800 ms (`QTimer.singleShot`), dejando que VLC complete el seek.

---

### Caso de prueba 2.2 — Arrastre del slider
**Pasos:** Mantener presionado el slider, arrastrar y soltar en el 75 %.  
**Esperado:** Seek al 75 % de la duración.  
**Actual:** Funciona correctamente con el fix de `_seeking`. ✅

---

### Caso de prueba 2.3 — Teclas multimedia (adelantar)
**Pasos:** Usar los atajos de teclado registrados en Windows.  
**Estado:** ✅ Sin fallos (4 teclas registradas correctamente).

---

## 3. Error de interacción con el mouse

### Caso de prueba 3.1 — Click en cualquier parte de la interfaz
**Pasos para reproducir:**
1. Reproducir una pista.
2. Hacer clic en el sidebar, en la lista de playlists o en el área de búsqueda.
3. Observar si la reproducción se reinicia.

**Comportamiento esperado:**  
La reproducción continúa sin interrupción.

**Comportamiento actual (antes del fix):**  
Al hacer clic en la barra de progreso, la canción se reiniciaba (ver Caso 2.1). Clicks en otras áreas no afectaban la reproducción.

**Estado:** ✅ CORREGIDO (Caso 2.1). Clicks en otras áreas no reinician la reproducción.

---

### Caso de prueba 3.2 — Doble clic en la lista de pistas
**Pasos:** Doble clic en una pista de la playlist.  
**Esperado:** Se reproduce esa pista desde el inicio.  
**Actual:** Funciona correctamente. ✅

---

## 4. Pruebas visuales

Se ejecutó `scripts/visual_test.py` con `QT_QPA_PLATFORM=offscreen`, capturando pantallazos de las vistas principales:

| Vista | Archivo | Estado |
|-------|---------|--------|
| Inicio (Home) | `screenshots/home.png` | ✅ Renderiza correctamente |
| Biblioteca | `screenshots/library.png` | ✅ Renderiza correctamente |
| Playlists | `screenshots/playlists.png` | ✅ Renderiza correctamente |
| Favoritos | `screenshots/favorites.png` | ✅ Renderiza correctamente |
| Historial | `screenshots/history.png` | ✅ Renderiza correctamente |

**Resultado:** Sin errores de renderizado, sin warnings de Qt en STDERR. Los estilos QSS se aplican correctamente (sin "Could not parse stylesheet").

---

## 5. Sección de Favoritos

### Funcionalidad implementada
- **Sidebar:** Ítem "⭐ Favoritos" en la barra lateral (navegación con teclado y mouse).
- **Vista de favoritos:** `PlaylistPanel` con modelo `TrackListModel` dedicado (`favorites_model`).
- **Toggle de favorito:** Botón en NowPlaying (⭐/☆) y en cada fila de la playlist.
- **Persistencia:** Los favoritos se guardan en SQLite (`store.add_favorite` / `remove_favorite` / `is_favorite`).
- **Reproducción desde favoritos:** Doble clic en un favorito lo añade a la playlist principal y lo reproduce.
- **Eliminación:** Botón "🗑️ Quitar" y "🧹 Limpiar" (vaciar todos).
- **Actualización en tiempo real:** Al marcar/desmarcar un favorito, la vista de favoritos se actualiza automáticamente.
- **Icono dinámico:** El botón de favorito en NowPlaying refleja el estado (⭐ favorito / ☆ no favorito) al cambiar de pista.

### Casos de prueba
| Caso | Resultado |
|------|-----------|
| Navegar a Favoritos desde sidebar | ✅ |
| Marcar pista como favorita desde NowPlaying | ✅ |
| Desmarcar pista de favoritos | ✅ |
| Reproducir pista desde vista de favoritos | ✅ |
| Eliminar favorito individual | ✅ |
| Vaciar todos los favoritos | ✅ |
| Persistencia tras reiniciar la app | ✅ (SQLite) |

---

## Resumen final de bugs

| # | Bug | Archivo | Estado |
|---|-----|---------|--------|
| 1 | Slider en ms vs segundos (progreso no visible) | `ui/main_window.py` | ✅ Corregido |
| 2 | Seek reinicia la canción (race condition VLC) | `ui/panels/controls_panel.py` | ✅ Corregido |
| 3 | QSS `{{`/`}}` rompía estilos | `ui/themes.py` | ✅ Corregido |
| 4 | Bandeja sin icono | `ui/tray.py` | ✅ Corregido |
| 5 | Atajo `Ctrl+L` ambiguo | `ui/menu.py` | ✅ Corregido |
| 6 | `QDockWidget` sin objectName | `ui/main_window.py` | ✅ Corregido |
| 7 | `SMTC` no disponible (WinRT) | `services/smtc_service.py` | ⚠️ Parcial |
| 9 | QFont::setPointSize warning (-1) | `ui/widgets.py`, `ui/main_window.py`, `ui/panels/now_playing.py` | ✅ Mitigado |

## Notas sobre la advertencia QFont::setPointSize

La advertencia `QFont::setPointSize: Point size <= 0 (-1)` es un warning benigno de Qt que puede aparecer cuando un `QFont` se crea sin un tamaño de punto válido. Se mitigó asegurando que:
- `MarqueeLabel` use una fuente con tamaño de punto válido (≥ 12) si el heredado es inválido.
- Los `QLabel` con texto vacío tengan un espacio (" ") para evitar fuentes sin tamaño.
- El `CoverArtLabel` placeholder tenga texto válido.
- No se hicieron commits.
- Tests: **88 passed**, ruff clean.
- Screenshots generados en `screenshots/`.
- El modelo de favoritos usa `TrackListModel` con `track_at()` para acceso por índice.

| # | Bug | Archivo | Estado |
|---|-----|---------|--------|
| 1 | Slider en ms vs segundos (progreso no visible) | `ui/main_window.py` | ✅ Corregido |
| 2 | Seek reinicia la canción (race condition VLC) | `ui/panels/controls_panel.py` | ✅ Corregido |
| 3 | QSS `{{`/`}}` rompía estilos | `ui/themes.py` | ✅ Corregido |
| 4 | Bandeja sin icono | `ui/tray.py` | ✅ Corregido |
| 5 | Atajo `Ctrl+L` ambiguo | `ui/menu.py` | ✅ Corregido |
| 6 | `QDockWidget` sin objectName | `ui/main_window.py` | ✅ Corregido |
| 7 | `SMTC` no disponible (WinRT) | `services/smtc_service.py` | ⚠️ Parcial (placeholder) |

## Notas

- La lectura de metadatos de canción (título/artista de otras apps) vía WinRT requiere los vtables exactos de las interfaces COM; el servicio actual detecta disponibilidad y estado, y reporta `unavailable` de forma elegante si las APIs no se pueden invocar directamente.
- No se hicieron commits. Tests: **88 passed**, ruff clean.

## Fix adicional: openUrl

| 10 | QApplication.openUrl no existe (crash al abrir carpeta) | ui/main_window.py | ✅ Corregido |

QApplication no tiene metodo openUrl. Se corrigio usando QDesktopServices.openUrl(QUrl.fromLocalFile(folder)).

## Fixes adicionales de pruebas reales y QA Review

| # | Bug | Archivo | Estado |
|---|-----|---------|--------|
| 11 | `sqlite3.OperationalError` en inicio real por ruta no escribible/sin nombre de app | `core/paths.py`, `main.py` | ✅ Corregido |
| 12 | Crash en `_play_favorite`: `Playlist` no tiene atributo `count` | `ui/main_window.py` | ✅ Corregido |
| 13 | Duplicados en `_play_favorite` por comparación solo por identidad de objeto | `ui/controllers/playlist_controller.py` | ✅ Corregido |
| 14 | `RuntimeError` en `Toast.dismiss` tras destrucción del widget C++ en `singleShot` | `ui/components/toast.py` | ✅ Corregido |
| 15 | Multiplicidad de `ImageProvider` creando pools de hilos innecesarios | `ui/image_provider.py`, `ui/widgets.py` | ✅ Corregido |
| 16 | Polling de SMTC cada 2s consumiendo ciclos innecesarios | `services/smtc_service.py` | ✅ Corregido |

| 17 | `ClickableSlider.pixelPosToRangeValue` devolvía 0 al calcular ancho negativo en subControlRect (Bug 2) | `ui/widgets.py` | ✅ Corregido |
| 18 | VLC abría ventana externa flotante en streams de YouTube y audio | `core/player.py`, `ui/main_window.py` | ✅ Corregido |
| 19 | Opciones de reproducción, descarga y playlists en resultados de búsqueda (individual, selección y todos) | `ui/panels/results_panel.py`, `ui/main_window.py` | ✅ Implementado |

**Estado final de pruebas (v1.2.0-beta):**
- `pytest -q`: **288 passed** (0 failed, 0 errors).
- `ruff check .`: **clean** (sin advertencias ni errores).
- `scripts/smoke_start.py`: **Arranque correcto: True**.
- `scripts/visual_test.py`: **6 vistas renderizadas y capturadas exitosamente**.
- `scripts/benchmark_library.py`: **5000 pistas agrupadas en ~20-25 ms (< 200 ms aceptación)**.
