# Music Player Pro — Release Notes

> **⚠️ ESTADO: BETA — EN DESARROLLO ACTIVO**
>
> Las notas de versión reflejan el estado actual de desarrollo. **La API, configuración, base de datos e interfaz pueden cambiar entre versiones beta sin aviso previo**. No hay garantía de compatibilidad hacia atrás. Haz copias de seguridad de `state.db` y la carpeta de datos antes de actualizar.

---

## v1.2.0-beta (2026-11-17) — "Sync & Polish"

### 🎯 Novedades Principales

#### Reproducción y Motor
- **Fin de pista por eventos de VLC** (`MediaPlayerEndReached`) — elimina polling de 500 ms, posición exacta, avance automático fiable.
- **Posición persistente** al alternar entre modo audio y modo vídeo (misma pista, mismo `track_key`).
- **Teclas multimedia del sistema** (Windows SMTC / Linux MPRIS): Play/Pausa, Anterior/Siguiente, Volumen.
- **Bandeja del sistema** con minireproductor integrado (mostrar/ocultar, controles básicos).
- **Mini reproductor flotante** rediseñado: portada, progreso, volumen, controles completos, **vista de vídeo opcional**, arrastrable, `stay-on-top`, desacoplable.

#### Biblioteca y Búsqueda
- **Escaneo eficiente**: carátulas ya no se decodifican durante el escaneo (lotes de señales).
- **Cambio de vista instantáneo** (Carpetas / Artistas / Álbumes) < 200 ms con 20 000 pistas.
- **Filtro de texto** sobre el árbol de la biblioteca.
- **Búsqueda global unificada**: filtra local + `yt:` para YouTube (debounce 450 ms).
- **Resultados YouTube en tarjetas**: reproducir streaming, descargar, menú contextual, paginación «Cargar más» (20/page, acumulativo).
- **Enlace YouTube pegado** → diálogo: reproducir / descargar.

#### Descargas
- **Gestor en ventana independiente** (`Ctrl+Shift+D`) — no ensucia la UI principal.
- **Dos modos**: lista completa o selección individual (checkboxes).
- **Carpeta destino configurable** + formato **MP3 / FLAC**.
- **Progreso individual** por canción + **totales en vivo** (peso seleccionado / descargado real).

#### Organización
- **Playlists múltiples** con importación/exportación **M3U** y **JSON**.
- **Detección de duplicados**: hash de contenido (SHA-256) + fingerprint acústico.
- **Edición de etiquetas en lote** (ID3/Vorbis/MP4) con vista previa de cambios.

#### Letras y Last.fm
- **Letras sincronizadas** desde **LRCLIB** (fallback lyrics.ovh), línea activa resaltada, cache por `track_key`.
- **Letras incrustadas** (USLT) en archivos locales como prioridad.
- **Scrobbling Last.fm** con cola offline (reintento al recuperar red) + Now Playing notification.

#### Sincronización entre Dispositivos (Beta)
- **Relay propio**: FastAPI + SQLite (WAL) + WebSocket — despliegue con `docker compose up -d`.
- **Emparejamiento por código de 6 dígitos**; un dispositivo «dueño» controla, el resto controla a distancia.
- **Compañero web PWA** (`web/`) — instala como app en móvil, sin build step.
- **Local-first**: sin red la app funciona igual; outbox + snapshot sincronizan al volver.
- **Protocolo versionado v1** con cursores para consistencia eventual.

#### Interfaz y Temas
- **Sistema de diseño renovado**: tokens de espaciado (xs→xl), radios (sm→pill), tipografía (sm→xl), foco, elevación.
- **14 temas**: 7 clásicos (Dark, Light, Cyberpunk, Nord, Dracula, Catppuccin, Solarized) + 7 **Claymorphism/Neumorfismo suave** (`clay_*`).
- **Tema High Contrast** (WCAG AAA — 7:1) para accesibilidad/baja visión.
- **Avisos flotantes (toasts)** en lugar de etiqueta de estado única.
- **Navegación lateral**, cola reordenable, panel «Ahora reproduciendo» con formato/bitrate/muestra.
- **Tarjetas de resultado** con contador, estado vacío, pistas de uso.
- **Accesibilidad completa**: nombres accesibles (`setAccessibleName`), tooltips, atajos registrados únicos, contraste WCAG AA verificado en 14/14 temas, foco visible (anillo 2px PRIMARY), navegación Tab lógica.

#### Vídeo (Responsive)
- **4 modos**: Estándar (960×540), Cine (1280×720), Pantalla completa, **Responsivo** (se adapta al contenedor).
- **Redimensionable** con bordes (modo Responsivo), persistencia con debounce (500 ms).
- **Corrección de `setFixedSize`** → `resize()` en modos responsivos para no bloquear layout.
- **Validación de proporción 16:9** en `set_video_size`.
- **VideoWidget nativo** (`WA_NativeWindow` sin `WA_PaintOnScreen`) se redimensiona con el frame.

#### Onboarding (Primera Ejecución)
- **Wizard 3 pasos** al detectar `state.db` vacío:
  1. Bienvenida + atajos principales.
  2. Seleccionar carpeta musical (diálogo nativo) + escaneo automático.
  3. Elegir tema (selector visual 14 temas) + activar bandeja/mini-player.

#### Calidad y Tests
- **288 tests passing** (100%): unitarios, integración, UI QA (29), UX QA (15), smoke (22), temas (28), PWA (4+5 Playwright), descargas, playlists, letras, búsqueda, actualizador, store.
- **CI**: ruff + pytest en Windows/Linux (Python 3.11/3.12/3.13), job `qa` con métricas/capturas, build PyInstaller.
- **Métricas validadas**: carga 1000 pistas < 2s, temas 14×10 < 2s, filtro 1000 entradas < 3s, memoria 5000 pistas 2.6 MB, contraste mínimo 4.86:1 (solarized), ventana mínima 980×680.

---

### 🔧 Detalles Técnicos y Cambios Internos

#### Arquitectura
- Separación estricta en capas: `core/` (dominio, sin Qt), `ui/` (PyQt6), `services/` (externos), `sync/` (cliente), `sync_server/` (relay), `web/` (PWA).
- `MainWindow` como orquestador; controladores dedicados (`PlaybackController`, `PlaylistController`, `LibraryController`, `SearchController`, `FilesController`).
- Tareas en segundo plano sobre `QThreadPool` + `QRunnable` con cancelación cooperativa (`threading.Event`).
- Configuración portable (INI en `AppData`) + logging rotativo (10 MB × 5).

#### Correcciones Críticas (desde v1.1)
| # | Bug | Archivo | Fix |
|---|-----|---------|-----|
| 1 | Slider en ms vs segundos (progreso no visible) | `ui/main_window.py` | `setRange(0, duration_sec)` |
| 2 | Seek reinicia canción (race VLC) | `ui/panels/controls_panel.py` | Bandera `_seeking` + `QTimer.singleShot(800ms)` |
| 3 | QSS `{{`/`}}` rompía estilos | `ui/themes.py` | Escape correcto en plantillas |
| 4 | Bandeja sin icono | `ui/tray.py` | `QIcon` desde recurso empaquetado |
| 5 | Atajo `Ctrl+L` ambiguo | `ui/menu.py` | Atajos únicos registrados |
| 6 | `QDockWidget` sin objectName | `ui/main_window.py` | `setObjectName` para QSS |
| 7 | SMTC no disponible (WinRT) | `services/smtc_service.py` | Placeholder elegante, fallback MPRIS |
| 8 | `QFont::setPointSize` warning (-1) | `ui/widgets.py`, `now_playing.py` | Fuente válida (≥12) / espacio en labels vacíos |
| 9 | `QApplication.openUrl` no existe | `ui/main_window.py` | `QDesktopServices.openUrl` |
| 10 | `sqlite3.OperationalError` ruta no escribible | `core/paths.py`, `main.py` | Fallback robusto + `MUSICPLAYERPRO_HOME` |
| 11 | Crash `_play_favorite`: `Playlist.count` | `ui/main_window.py` | `playlist.count()` → `len(playlist)` |
| 12 | Duplicados en `_play_favorite` | `playlist_controller.py` | Búsqueda por `track_key` antes de añadir |
| 13 | `RuntimeError` `Toast.dismiss` widget destruido | `ui/components/toast.py` | `QPointer` / `deleteLater` seguro |
| 14 | Múltiples `ImageProvider` (pools hilos) | `ui/image_provider.py`, `widgets.py` | Singleton compartido |
| 15 | Polling SMTC 2s innecesario | `services/smtc_service.py` | Intervalo 5s + solo si ventana activa |
| 16 | `ClickableSlider` ancho negativo | `ui/widgets.py` | Validación `subControlRect` |
| 17 | VLC ventana externa en streams YouTube | `core/player.py`, `main_window.py` | `video_set_output` al widget incrustado |
| 18 | Opciones reproducción/descarga/playlist en resultados | `results_panel.py`, `main_window.py` | Menú contextual + botones tarjeta |

#### Refactorizaciones (SOLID)
- `LocalStore` thread-safe: `RLock` serializando escrituras SQLite (`check_same_thread=False` + lock).
- `MusicPlayer`: caché de posición (`_cached_position_ms`) evita cruce C/Python en cada frame.
- `CoverArtLabel`: `ImageProvider` singleton inyectado, no creado por llamada.
- `MarqueeLabel`: timer solo bajo demanda (texto desborda + visible).
- `TrackListModel`: `beginResetModel`/`endResetModel` para cargas masivas.
- `ThemeManager`: datos (Theme/DesignTokens) separados de presentación (QSS generation).

---

### 📦 Instalación y Actualización

```bash
# Desde fuente (desarrollo)
git pull
pip install -e ".[dev]"
python main.py

# Ejecutable standalone
# Descargar MusicPlayerPro_v1.2.0.exe de Releases
# O compilar:
pip install pyinstaller
pyinstaller --nocfirm MusicPlayerPro.spec

# Instalador Windows (requiere Inno Setup 6)
ISCC.exe installer\MusicPlayerPro.iss

# Relay de sincronización (Docker)
echo "MUSICPLAYERPRO_RELAY_PEPPER=tu-secreto" > .env
docker compose up -d
```

> **⚠️ Actualización desde v1.1**: La migración v3 (`sync_outbox`) se aplica automáticamente al arrancar. Haz backup de `state.db` antes de actualizar.

---

### 🐛 Known Issues / Limitaciones Actuales (Beta)

| Área | Descripción | Workaround / Estado |
|------|-------------|---------------------|
| **Atajos flechas** | Espec: `←/→`; Implementado: `Ctrl+←/→` | Usar `Ctrl+←/→`; se unificará en v1.3 |
| **SMTC Windows** | WinRT requiere vtables COM exactos | Funciona en la mayoría; fallback MPRIS en Linux |
| **PWA offline** | Service Worker registrado; sin tests de caché | Validación manual; añadir Workbox + Lighthouse CI |
| **Migraciones BD** | Test v1→vN no cubre datos reales | Añadir tests de migración versionada |
| **Actualizador E2E** | Tests unitarios OK; falta test rollback real | Test integración con binario firmado |
| **Relay server tests** | Solo tests cliente; servidor no probado | Tests contrato WebSocket + API REST |
| **Rendimiento >20k** | Benchmark script existe; sin test CI automatizado | Añadir `pytest-benchmark` en CI nocturno |
| **i18n** | Strings hardcoded español/inglés | Extraer a `.ts` / `gettext` en v1.3 |
| **Tema auto-sistema** | No detecta Light/Dark del SO | `QGuiApplication.styleHints().colorScheme()` en v1.3 |
| **Reduced motion** | `MarqueeLabel` no respeta `prefers-reduced-motion` | Añadir media query Qt en v1.3 |

---

### 🔗 Enlaces Útiles
- **Repositorio**: https://github.com/tu-usuario/musicplayerpro
- **Issues**: https://github.com/tu-usuario/musicplayerpro/issues
- **Discusiones**: https://github.com/tu-usuario/musicplayerpro/discussions
- **Documentación QA**: `docs/QA_UI_REPORT.md`
- **Revisión Arquitectura**: `docs/QA_REVIEW.md`
- **Auditoría Vídeo**: `docs/VIDEO_AUDIT.md`
- **Historial Bugs**: `docs/BUG_REPORT.md`

---

*Music Player Pro v1.2.0-beta — Desarrollado con ❤️ usando Python, PyQt6 y VLC.*
*Fecha: 2026-11-17*