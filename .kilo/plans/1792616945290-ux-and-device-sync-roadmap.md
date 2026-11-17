# Plan de actualización: UX y sincronización entre dispositivos — Music Player Pro

**Proyecto:** `C:\Users\alsan\Documents\reproductor musical pyqt6` (Music Player Pro, Python + PyQt6 + VLC)
**Alcance del plan:** evolución del reproductor propio. La ruta `C:\Users\alsan\AppData\Local\Programs\youtube-music\YouTube Music.exe` se toma como **producto de referencia** (patrón de "Connect" con código de emparejamiento, no se modifica).

---

## 1. Decisiones tomadas (con su motivo)

| # | Decisión | Motivo |
|---|----------|--------|
| D1 | El plan aplica a **Music Player Pro** (este repo), no a YouTube Music.exe | El workspace contiene el código fuente editable; la app de Google es Electron firmado y se sobrescribe en cada auto-update |
| D2 | **Escritorio (PyQt6) + compañero web (PWA)** | Un solo protocolo WebSocket sirve a ambos clientes; sin publicar en stores ni duplicar la UI |
| D3 | Sincroniza **reproducción + biblioteca**; **no** transfiere archivos de audio | Los archivos locales difieren por dispositivo; se separa catálogo lógico vs. disponibilidad local |
| D4 | **Relay auto-hospedado** (FastAPI + WebSocket + SQLite, Docker) | Control total, coste cero, cliente *local-first*; exposición vía Cloudflare Tunnel / Tailscale |
| D5 | **Código de emparejamiento** (6 dígitos + QR, sin cuentas) | Cero fricción, sin PII, sin gestión de passwords; código de recuperación |
| D6 | Rediseño **híbrido**: se conserva el esqueleto, se reconstruyen los componentes | Valor alto sin el riesgo de reescribir la UI y romper la capa VLC |
| D7 | **Dueño único de la sesión + handoff explícito** | Evita escrituras concurrentes sobre el mismo VLC (Spotify Connect) |
| D8 | Distribución: **PyInstaller + Inno Setup + auto-update** | Mantiene el exe ya publicado en `dist/` y mejora el ciclo de actualización |
| D9 | Validación: **pytest + pytest-qt + CI (GitHub Actions)** | La fase de sync es concurrente y dependiente del tiempo: sin tests automáticos es inviable depurar |
| D10 | Extras de Fase 2: Last.fm, teclas multimedia+bandeja+MPRIS, letras, import/export de playlists+duplicados, edición de tags en lote | Selection explícita del usuario. **Fuera de alcance**: ecualizador/DSP |

---

## 2. Restricciones y no-objetivos

**Restricciones**
- Se mantiene la pila PyQt6 Widgets + `python-vlc` + `yt-dlp` + `mutagen`. No se migra a QML.
- El relay es **opcional**: la app debe ser 100 % funcional sin él.
- Sin correo electrónico, sin cuentas, sin datos personales en el relay.
- No se transfieren archivos de audio entre dispositivos.
- Los covers **no** se sincronizan: se re-resuelven por URL en cada dispositivo (caché local por hash de URL).

**No-objetivos**
- Reescribir el reproductor, migrar de VLC, abandonar `yt-dlp`.
- Multi-tenant empresarial, facturación, panel de administración web.
- Soporte nativo iOS/Android (el compañero web cubre ese caso).
- Inspección/modificación de la app oficial de YouTube Music.

---

## 3. Análisis de la arquitectura actual

### 3.1 Estructura

```
main.py                 entrypoint (22 líneas) — QApplication(sys.path)  ← BUG
core/player.py          wrapper de VLC (90 líneas) — sin observadores de eventos
core/playlist.py        modelo de datos de pistas y cola (128 líneas)
ui/main_window.py       1156 líneas: 8 subclases de QThread + toda la UI monolítica
ui/widgets.py          ClickableSlider, CoverArtLabel, MarqueeLabel
ui/themes.py            tokens de diseño en QSS (ya es un mini design system)
ui/tag_editor.py        diálogo de edición de tags
services/youtube_service.py    yt-dlp: búsqueda, descarga, playlists, stream
services/metadata_service.py   mutagen + API de iTunes
services/spotify_service.py    CÓDIGO MUERTO — nunca importado
```

### 3.2 Hallazgos concretos (con anclas)

**Correctitud / bugs**
- `main.py:12` — `QApplication(sys.path)` debe ser `QApplication(sys.argv)`. El `argv` real se descarta; los argumentos de línea de comandos nunca llegan a Qt.
- `core/player.py:63` — `pause()` marca `PAUSED` aunque el reproductor estuviera detenido → estado desincronizado con VLC.
- `core/player.py:54` — `play()` no comprueba que haya medio cargado; retorna en silencio.
- `core/player.py` (completo) — **no hay observadores de eventos de VLC**. `ui/main_window.py:941` detecta el fin de pista comparando `pos >= duration - 1` con un poll de 500 ms: precisión de ±500 ms, saltas de pista en pistas cortas, y no hay evento de error.
- `ui/main_window.py:983` — `closeEvent` llama `t.quit()` sobre hilos que sobrescriben `run()`: `quit()` no detiene un bucle propio de `run()` → "QThread: Destroyed while thread is still running" al cerrar con un escaneo activo.
- `ui/widgets.py:73` — `t.disconnect()` desconecta **todas** las señales del hilo, incluida `finished` → `_cleanup_thread` nunca se ejecuta → fuga de hilos en `active_threads` y crecimiento indefinido de la lista.
- `ui/main_window.py:650` y `:601` — `hasattr(self.yt_service, 'download_dir')` es siempre verdadero; la comparación con `cache_dir` de dos `Path` distintos puede fallar en la comparación de rutas.
- `services/metadata_service.py:295` — `save_cover` usa `output_dir="./cache/covers"` **relativo al CWD**: al ejecutar el `.exe` empaquetado escribe en el directorio de trabajo del usuario, no en la carpeta de la app.
- `services/metadata_service.py:176` — `'ytimg.com'` está en `generic_patterns` → **toda** carátula de YouTube se descarta y se fuerza una búsqueda en iTunes que casi siempre falla. Además el patrón `'vi/'` produce falsos positivos.
- `services/metadata_service.py:24` — `get_metadata` extrae los bytes de la portada en cada llamada → el escaneo de biblioteca decodifica una imagen por archivo, innecesario.
- `core/playlist.py:80` — el shuffle puede elegir el índice actual (repite la misma canción) y `_history` (línea 48) crece sin límite.
- `core/playlist.py:109/119` — `save_to_file` / `load_from_file` **nunca se llaman**: la playlist no se persiste, la app arranca siempre vacía.

**Rendimiento**
- `ui/main_window.py:1067` — `_find_or_create_node` busca hijos linealmente → construcción O(n²) del árbol de biblioteca.
- `ui/main_window.py:1075` — `reorganize_library` reconstruye el árbol entero en cada cambio de modo de vista.
- `ui/main_window.py:132` — `LibraryScanThread` emite **una señal por archivo** → 10 000 pistas = 10 000 eventos en la cola de Qt.
- `ui/main_window.py:935` — timer de 500 ms para la barra de progreso: avance a saltos de medio segundo.
- `ui/widgets.py:122` — `MarqueeLabel` arranca un `QTimer` de 30 ms **siempre activo** (2 etiquetas ≈ 66 wakeups/s en reposo) y repinta aunque no haya desplazamiento.
- `ui/main_window.py:21-211` — 8 clases `QThread` ad-hoc; cada tarea crea un hilo y `_cleanup_threads` (`:975`) no detiene los hilos anteriores → descargas de yt-dlp concurrentes no deseadas.

**UX / accesibilidad**
- `ui/main_window.py:346` — el campo de búsqueda **solo busca en YouTube**: no hay búsqueda local en la biblioteca, que es la función principal de un reproductor local.
- Botones de icono sin texto (`🔀`, `⏮`, `⏭`, `➡️`) sin `setAccessibleName` ni tooltip → ilegibles para lectores de pantalla y ambiguos (el "Ninguno" del repeat se representa con una flecha).
- No hay atajos de teclado, ni teclas multimedia, ni bandeja del sistema, ni minireproductor.
- Un único `status_label` (`:326`) como único canal de feedback: los mensajes se pisan entre sí y los errores son invisibles.
- No hay panel de cola visible (existe el modelo y los modos, no la UI), ni lista de reproducción multiple, ni Favoritos, ni Historial.
- `services/youtube_service.py:130` — `search_songs(max_results=5)`: la UI ofrece "Descargar Todo" sobre 5 resultados.
- `services/metadata_service.py:295` + `ui/tag_editor.py:127` — `search_suggestions` hace una llamada de red **en el hilo de la UI** (comentado en el propio código) → congelación de la ventana.
- `ui/main_window.py:1124` — `open_tag_editor` distingue árbol vs. lista con `hasattr(list_item, "childCount")` (duck typing frágil).
- Sin `QSettings`: tema, volumen, carpeta de descargas y geometría de ventana no se persisten.
- Sin `logging`: 27 `print("[DEBUG] ...")` sin niveles, sin archivo de log, sin contexto.

**Infraestructura**
- `requirements.txt` fija `PyQt6>=6.4.0`, incompatible con el Python 3.13 que usa el proyecto (`__pycache__` = `cpython-313`).
- No hay `pyproject.toml`, ni linter, ni tests, ni CI, ni `.spec` de PyInstaller reproducible (`dist/MusicPlayerPro_v1.1.exe` está committed sin fuente de build).
- `services/spotify_service.py` es código muerto (dependencia `spotipy` incluida sin uso).

---

## 4. Fase 0 — Cimientos (sin cambios de comportamiento visible)

Objetivo: poder construir, testear y evolves sin miedo. Precondición de todas las fases siguientes.

- [ ] **0.1** Corregir `main.py:12` → `QApplication(sys.argv)`.
- [ ] **0.2** `pyproject.toml` con `[project]`, deps reales (`PyQt6>=6.6`, `python-vlc>=3.0.201`, `yt-dlp`, `mutagen`, `requests`), extras `[dev]` (`pytest`, `pytest-qt`, `pytest-asyncio`, `ruff`), y `ruff` configurado (line-length 100, `E,F,I`).
- [ ] **0.3** **Rutas de aplicación** — nuevo `core/paths.py` con `AppPaths` sobre `QStandardPaths.AppDataLocation` (`%LOCALAPPDATA%/MusicPlayerPro/`): `state.db`, `logs/`, `cache/covers/`, `cache/youtube/`, `playlists/`. Elimina los paths relativos a CWD (`metadata_service.py:295`) y los derivados de `__file__` (`youtube_service.py:12`), que no funcionan en un bundle congelado.
- [ ] **0.4** **Logging** — `core/logging_setup.py` con `logging` (DEBUG en archivo rotativo, INFO en consola) y sustituir los 27 `print()`.
- [ ] **0.5** **`core/config.py`** — dataclass `AppConfig` (tema, volumen, carpeta de descargas, tamaño de caché, URL del hub, `lastfm_api_key`…) persistida en `QSettings`; carga/guardado centralizados.
- [ ] **0.6** **Desacoplar hilos** — `core/tasks/` con `Worker(QRunnable)` + `QThreadPool` y un `WorkerSignals`. Migrar las 8 clases `QThread` de `ui/main_window.py:21-211`. Regla dura: **VLC solo se toca desde el hilo de la GUI**; los workers solo hacen I/O.
- [ ] **0.7** **Estructura de UI** — partir `MainWindow` en `ui/panels/` (NowPlaying, Results, Playlist, Library), `ui/models/` (QAbstractItemModel/QAbstractListModel) y `ui/controllers/`. `MainWindow` queda como orquestador < 400 líneas.
- [ ] **0.8** **Tests** — `tests/` con `pytest` + `pytest-qt` + `pytest-asyncio`; primer battery sobre `core/playlist.py` (shuffle/repeat/historial) y `core/player.py` con un **doble de prueba** de VLC (`tests/fakes/fake_vlc.py`) que simule `get_time`, `play`, `pause` y eventos.
- [ ] **0.9** **CI** — `.github/workflows/ci.yml`: ruff + pytest en matriz Windows (principal) y Linux; job de build de PyInstaller en Windows.

---

## 5. Fase 1 — Optimización (UX + rendimiento)

### 5.1 Reproducción fiable (base de todo lo demás)

- [ ] **1.1** **Eventos de VLC** — registrar observadores en `core/player.py` con `vlc.EventType` (`MediaPlayerReachedEnd`, `MediaPlayerPlaying`, `MediaPlayerPaused`, `MediaPlayerStopped`, `MediaPlayerLengthChanged`, `MediaPlayerEncounteredError`, `MediaPlayerTimeChanged`), expuestos como callbacks del `MusicPlayer`; eliminar la detección de fin de pista por comparación (`main_window.py:941`).
  - *Premisa a verificar en el entorno objetivo en los primeros 30 min de la Fase 0:* `python-vlc` expone `vlc.EventType` y `MediaPlayer.event_manager().on(...)` desde la serie 3.0.x (`requirements.txt` ya pide `>=3.0.12118`). Si la versión instalada resultara más antigua, actualizar `python-vlc` a la última 3.0.x y fijar la versión exacta en `pyproject.toml`; si quedara bloqueada la actualización, la alternativa de reserva es un poll de 100 ms sobre `player.get_state()` + `get_time()` (pierde la precisión de fin de pista, que es justo lo que se quiere eliminar).
  - El callback se ejecuta en el hilo que llama a VLC: mantenerlo **siempre** en el hilo de la GUI.
- [ ] **1.2** Corregir la máquina de estados (`play`/`pause`/`stop` reflejando el estado real de VLC) y añadir `MediaPlayerEncounteredError` → toast de error + avance automático con reintento.
- [ ] **1.3** Barra de progreso: timer de la UI a 100 ms alimentado por `MediaPlayerTimeChanged` (no por poll), con arrastre real (`sliderMoved` → `set_position` al soltar) y sin saltos.
- [ ] **1.4** Búsqueda de archivos con `QFileDialog` + arrastre y soltado de archivos desde el explorador (drag & drop sobre la ventana).
- [ ] **1.5** Corregir el modo vídeo: al alternar a vídeo conservar la posición exacta, evitar la doble carga (`main_window.py:876`) y restaurar el HWND de VLC con `int(frame.winId())` verificado en DPI altas (125 %/150 %).

### 5.2 Rendimiento y estabilidad

- [ ] **1.6** **Biblioteca con modelo de datos** — sustituir `QTreeWidget` por `QTreeView` + `QAbstractItemModel` + `QSortFilterProxyModel` (elimina el O(n²) de `_find_or_create_node` y permite ordenar/filtrar de verdad).
- [ ] **1.7** **Listas con carátula real** — `QListView` + `QAbstractListModel` con `QStyledItemDelegate` (portada, título, artista, duración) en vez de texto con emoji embebido en `QListWidgetItem`.
- [ ] **1.8** **Escaneo eficiente** — `get_metadata(with_cover=False)` durante el escaneo; portadas resueltas bajo demanda y cacheadas en disco por hash de URL (`core/cache.py` + `QPixmapCache` en memoria). Señales agrupadas (lote cada 25 archivos o 100 ms).
- [ ] **1.9** **Caché de imágenes** — `ImageLoaderThread` (`ui/widgets.py:8`) reutiliza `QPixmapCache` y un disco de caché; hoy cada cambio de pista vuelve a descargar la misma carátula.
- [ ] **1.10** **Corregir `CoverArtLabel`** — sustituir `t.disconnect()` (`ui/widgets.py:73`) por un token de generación: cada carga nueva invalida la anterior y el hilo se retira siempre en `finished`.
- [ ] **1.11** **Marquee bajo demanda** — arrancar/parar el `QTimer` de 30 ms solo cuando el texto no cabe; parar además cuando la ventana está oculta.
- [ ] **1.12** **Cancelación real de hilos** — flag `threading.Event` compartido en los workers; `closeEvent` cancela y espera con `QThreadPool.waitForDone()` (nunca "QThread destroyed while running").
- [ ] **1.13** **Cerrar `services/spotify_service.py`** y quitar `spotipy` de las dependencias (código muerto confirmado por grep: ninguna importación en todo el repo).

### 5.3 UX (rediseño híbrido)

- [ ] **1.14** **Barra lateral de navegación** (Inicio / Biblioteca / Playlists / Favoritos / Historial) sustituyendo las pestañas; el panel derecho conserva el contenido.
- [ ] **1.15** **Búsqueda global** — un único campo (`Ctrl+F`) que filtra la biblioteca local y, con prefijo `yt:`, busca en YouTube. Sustituye la búsqueda solo-YT (`main_window.py:504`).
- [ ] **1.16** **Capa de feedback** — sustituir `status_label` por toasts no intrusivos (`ui/components/toast.py`) + barra de tareas de descargas con progreso real por archivo y botón de cancelar.
- [ ] **1.17** **Accesibilidad** — `setAccessibleName`/`setToolTip` en todos los botones de icono; navegación por teclado completa (`Tab`/`Espacio`/`Enter`/flechas), `QShortcut` global (Espacio, `Ctrl+F`, `Ctrl+O`, `Ctrl+L`, `Ctrl+Q`, `Ctrl+→/←`, `Ctrl+D`); foco visible; el texto de los botones deja de depender de emoji.
- [ ] **1.18** **Panel de cola y de reproducción** — vista de cola con arrastrar y soltar para reordenar, mover a "me gusta", quitar; indicators de la pista en curso.
- [ ] **1.19** **Panel "Ahora reproduciendo"** — carátula grande, título/artista, formato/bitrate/muestra leídos de VLC, y botón de abrir la carpeta del archivo.
- [ ] **1.20** **Sistema de diseño** — extender `ui/themes.py` (que ya tiene tokens) con una capa de spacing/radios/tipografía y estilos de componentes (foco, hover, disabled); hoy el tema solo cubre controles.
- [ ] **1.21** **Ajustes** — diálogo con carpeta de descargas, tamaño máximo de caché, tema, carpeta de la biblioteca, atajos, URL del hub de sincronización y clave de Last.fm.
- [ ] **1.22** **Persistencia de sesión** — al cerrar: playlist, índice y posición de la pista, volumen, tema, geometría de la ventana, pestañas activas. `QSettings` + `playlists/` en JSON (reutilizando `Playlist.save_to_file`, hoy muerto) + `state.db` para el resto.
- [ ] **1.23** **Arrastrar y soltar** — archivos/auras desde el explorador a la app → añadir a la biblioteca o a la playlist.

---

## 6. Fase 2 — Nuevas funcionalidades

### 6.1 Biblioteca y contenido (2A)
- [ ] **2A.1** Playlists múltiples: crear/renombrar/eliminar/duplicar, reordenar, mover pistas entre playlists.
- [ ] **2A.2** Import/export **M3U** y **JSON**; detección de duplicados (hash de contenido + fingerprint título/artista/duración) con vista de "duplicados encontrados" y purga en lote.
- [ ] **2A.3** **Edición de tags en lote** con vista previa de cambios antes de escribir; mover la búsqueda de sugerencias de `ui/tag_editor.py:127` a un worker (hoy congela la UI).

### 6.2 Integración con el sistema (2B)
- [ ] **2B.1** **Teclas multimedia** — Windows: `RegisterHotKey` vía `ctypes` (sin dependencias) para Play/Pause/Next/Prev/Stop; macOS: `NSEvent`; Linux: **MPRIS** sobre D-Bus (`dbus-next`) expuesta a escritorios KDE/GNOME.
- [ ] **2B.2** **Bandeja del sistema** (`QSystemTrayIcon`) con menú (reproducir/pausa/siguiente/anterior/salir) y **minireproductor**.
- [ ] **2B.3** Opcional: **SMTC de Windows** para la superposición multimedia del SO (solo si el resto de la fase 2 es estable).

### 6.3 Letras y scrobbling (2C / 2D)
- [ ] **2C.1** **Letras** — API **LRCLIB** (`lrclib.net/api/get`, sin clave) con fallback a `lyrics.ovh`; caché en disco por `track_key`; normalización de la duración para el match.
- [ ] **2C.2** **Panel de letras** con línea activa resaltada según la posición; disponible también en el compañero web.
- [ ] **2D.1** **Last.fm** — `pylast` (o implementación propia con `hashlib`); flujo "now playing" + scrobble al 50 % o a los 4 min (reglas oficiales); cola offline si falla la red; clave API en Ajustes.

### 6.4 Sincronización (2E) — ver sección 7 para el diseño completo
- [ ] **2E.1** Relay (`sync_server/`) + esquema SQLite + endpoints + WebSocket.
- [ ] **2E.2** Cliente de escritorio (`sync/`): protocolo, store local, outbox, mapeo de pistas, comandos.
- [ ] **2E.3** Integración con `MainWindow`: badges de "sincronizado", indicador de dueño de sesión, handoff, diálogo de emparejamiento.
- [ ] **2E.4** Compañero web (`web/`): PWA con estado, controles remotos, cola, biblioteca, emparejamiento, lista de dispositivos, "Tomar el control".

---

## 7. Diseño técnico de la sincronización

### 7.1 Topología

```
  ┌──────────────────┐            WebSocket (JSON, v1)           ┌───────────────┐
  │  Escritorio      │◄───────────────────────────────────────►│               │
  │  PyQt6 + VLC     │            HTTPS (snapshot, pairing)    │  Relay        │
  └──────────────────┘                                          │  FastAPI +    │
  ┌──────────────────┐                                          │  SQLite       │
  │  Compañero web   │◄───────────────────────────────────────►│  (opcional)   │
  │  PWA (móvil)     │                                          └───────────────┘
  └──────────────────┘                                                   │
                                                          Docker Compose / exe
                                                              + Cloudflare
                                                                Tunnel / Tailscale
```

El relay es un **coordinador stateless-ish**: guarda el estado de la biblioteca y la sesión de reproducción, reenvía mensajes y registra un log de eventos ordenado. **No** almacena audio ni PII.

### 7.2 Modelo de datos (SQLite del relay)

| Tabla | Campos clave | Nota |
|---|---|---|
| `household` | `id` (uuid), `name`, `created_at` | Un "hogar" = biblioteca compartida |
| `device` | `id`, `household_id`, `name`, `platform`, `app_version`, `token_hash`, `last_seen_at`, `revoked_at` | `token_hash` = argon2; nunca se guarda el token en claro |
| `pairing_code` | `id`, `household_id`, `code_hash`, `expires_at`, `max_uses`, `uses` | Caduca en 5 min, un solo uso |
| `playback_session` | `household_id`, `owner_device_id`, `track_key`, `state`, `position_ms`, `volume`, `queue_json`, `queue_index`, `rev`, `updated_at` | **Una sola fila por hogar** → el dueño es único por construcción |
| `library_item` | `id` (uuid del cliente), `household_id`, `kind`, `payload_json`, `order_key`, `version`, `updated_at`, `deleted_at` | `kind` ∈ `playlist`/`favorite`/`history`/`rating` |
| `event_log` | `seq` (monotónico por hogar), `household_id`, `type`, `payload_json`, `created_at` | Fuente de deltas; poda > 30 días |

`order_key` es un **índice fraccionario** (estilo LexoRank) para que dos dispositivos inserten en distintas posiciones de la misma playlist sin reordenar toda la lista.

### 7.3 Identidad de pistas (el punto crítico)

Las rutas locales **difieren por dispositivo**, así que la clave de sincronización **no puede ser la ruta**:

- Remotas (YouTube): `yt:<video_id>` — estable y ya disponible en `Track.id`.
- Locales: `local:<sha1(normalize(title)|normalize(artist)|round(duration))>` — independiente del sistema de archivos.
  - `normalize()` = minúsculas, sin diacríticos, sin puntuación, espacios colapsados.
  - Complemento opcional `file_hash` (sha1 del archivo) para coincidencia estricta cuando ambos dispositivos lo tienen.

**Limitación conocida:** un mismo tema presente como MP3 local en un dispositivo y como `yt:` en otro **no** coincide (requiere fingerprinting acústico tipo Chromaprint — marcado como fuera de alcance en §12).

**Binding local (no sincronizado):** tabla `track_binding` en el cliente (`track_key → {file_path, size, mtime}`) + resolución en la UI:
- `track_key` conocida y con binding local → reproducible.
- `track_key` conocida sin binding → se muestra como **"no disponible en este dispositivo"** y la app ofrece resolverla: buscar en la biblioteca local, o (si es `yt:`) descargarla.

### 7.4 Protocolo (WebSocket, JSON versionado)

Envelope: `{"v": 1, "t": "<tipo>", "id": "<uuid>", ...}`.

| Dirección | Tipo | Contenido |
|---|---|---|
| C→S | `hello` | `device_id`, `token`, `since` (último `seq` conocido) |
| S→C | `hello_ok` | `cursor`, `owner_device_id`, `server_time` |
| S→C | `playback_state` | `owner`, `track_key`, `state`, `position_ms`, `volume`, `queue`, `queue_index`, `rev`, `ts` |
| C→S | `command` | `cmd` ∈ `play/pause/next/prev/seek/volume/queue_set/queue_add/takeover`, `args`, `cmd_id` |
| S→C | `command` | Reenviado **solo al dueño de la sesión** |
| C→O | `command_result` | `cmd_id`, `ok`, `error` |
| C→S | `mutation` | `kind`, `op` (`upsert`/`delete`), `item_id`, `payload`, `base_version` |
| S→C | `mutation_applied` | `item_id`, `new_version`, `seq` |
| C→S | `ping` / S→C `pong` | Heartbeat 20 s; corte tras 60 s sin `pong` |

**Endpoints REST (complementan al WS):**
- `POST /v1/pairing/request` → crea hogar + dispositivo y devuelve credenciales (y opcionalmente un código).
- `POST /v1/pairing/claim {code}` → canjea el código, devuelve `device_id` + token de larga duración.
- `POST /v1/pairing/rotate` / `POST /v1/devices/{id}/revoke`.
- `GET /v1/sync/snapshot?since=<seq>` → snapshot + cursor.
- `GET /v1/session` → estado actual (fallback si el WS cae).

### 7.5 Modelo de control (dueño único + handoff)

1. El dispositivo que inicia una sesión de reproducción se convierte en **dueño**; el relay lo registra en `playback_session.owner_device_id`.
2. Los demás son **controladores**: envían `command`; el relay lo reenvía al dueño; el dueño lo aplica sobre VLC y responde `command_result`; el nuevo estado se difunde como `playback_state`.
3. **Handoff**: `command cmd=takeover` transfiere la propiedad; el dueño anterior libera el control y su UI pasa a "control remoto" (icono deindicador claro).
4. **El relay rechaza** cualquier `playback_state` que no venga del dueño → imposible la escritura concurrente.
5. Anti-rebote: cada comando lleva `cmd_id`; el relay deduplica por `cmd_id` (2 min de TTL) y el cliente lo ignora si su `rev` es antiguo.

### 7.6 Resolución de conflictos de biblioteca

- **LWW por ítem** con `version` del servidor. El cliente envía `base_version`; si no coincide, el relay responde 409 con la versión actual y el cliente reintenta fusionando (para `playlist`/`favorite` el merge es "unión por `item_id`"; para el orden, `order_key`).
- **Tombstones** (`deleted_at`) durante 30 días → un dispositivo fuera de línea que borra no resucita el ítem al reconectar.
- **Idempotencia**: `item_id` UUID generado por el cliente + outbox local → reintentar es seguro.
- **Reloj**: el orden lo decide el `seq` del relay, **nunca** el reloj del cliente (evita el sesgo de skew).

### 7.7 Cliente de escritorio (`sync/`)

| Módulo | Responsabilidad |
|---|---|
| `sync/protocol.py` | Dataclasses + codec JSON + negociación de versión (`v`) |
| `sync/client.py` | `SyncClient`: hilo dedicado con `asyncio` + `websockets` + `httpx`; emite señales Qt (`pyqtSignal`) — **nunca** toca widgets desde el hilo |
| `sync/store.py` | SQLite local: caché del estado, `outbox` de mutaciones pendientes, `track_binding` |
| `sync/mapper.py` | `track_key` ↔ archivo local; fingerprints; resolución de "no disponible" |
| `sync/commands.py` | Puente entre la intención de la GUI (play/pause/seek) y el rol local: dueño → aplica local + difunde; controlador → envía `command` |
| `sync/manager.py` | Fachada `SyncManager` usada por `MainWindow` (estado, señal de cambios, errores) |

**Modelo local-first:** la app aplica los cambios al instante en local y los encola; el relay es un acelerador, no un requisito. Sin hub → la app funciona igual, sin sincronización.

### 7.8 Compañero web (`web/`)

- PWA estática (sin build step obligatorio: ES modules + Web Components), servida por el relay en `/` o por GitHub Pages apuntando al hub configurado.
- Vistas: **Ahora reproduciendo** (carátula, título, posición, estado), **Controles remotos**, **Cola**, **Biblioteca** (playlists/favoritos/historial), **Ajustes** (URL del hub, emparejamiento, lista de dispositivos, "Tomar el control").
- El navegador es un **dispositivo más** (`platform: web`) con su propio token.
- Reconexión con backoff exponencial + jitter; al reconectar, `hello` con `since` → el relay reenvía los deltas perdidos.
- Comandos optimistas: la UI se mueve al instante y se corrige con la confirmación del dueño.

---

## 8. Migración y rollout

1. **Migración local:** primera ejecución de la versión nueva → crea `%LOCALAPPDATA%/MusicPlayerPro/state.db` (esquema v1), importa `playlist.json` si existe (de `Playlist.save_to_file`) y calcula los `track_key` de forma perezosa al cargar cada pista.
2. **Sin migración del relay:** es nuevo. El esquema de `state.db` lleva `user_version`; cada cambio lleva un script de migración numerado en `core/migrations/`. Existe "Restablecer sincronización" (borra la caché local y re-sincroniza desde el snapshot).
3. **Rollout por flags:** `AppConfig` incluye `sync.enabled`, `sync.hub_url`, `features.lyrics`, `features.lastfm`, `features.tray`. Cada fase entra detrás de un flag; se activa por defecto solo tras validar en el CI.
4. **Compatibilidad de protocolo:** `protocol.v` con ventana de 2 versiones (`v: 1` acepta `v: 1`); el relay rechaza conexiones con versión mayor con un mensaje legible. Los clientes antiguos siguen funcionando en modo local.
5. **Despliegue del relay:** `docker compose up -d` (Postgres no requerido; SQLite con WAL) + `docker compose` reverse-proxy opcional. Exposición recomendada: Cloudflare Tunnel (URL estable, TLS, sin abrir puertos) o Tailscale. El cliente web apunta a la URL pública del hub.
6. **Actualización del cliente:** el actualizador comprueba GitHub Releases, verifica hash/firma, **no actualiza mientras se reproduce** y conserva la versión anterior para hacer rollback.

---

## 9. Modos de fallo y comportamiento esperado

| Fallo | Comportamiento exigido |
|---|---|
| Relay caído / sin internet | La app sigue funcionando 100 % en local. Las mutaciones se encolan en el `outbox` y se envían al reconectar. Indicador "Sin conexión — N cambios pendientes" |
| WebSocket se cae | Reconexión con backoff (1 s → 60 s) + jitter; `hello` con `since` recupera los deltas. El estado de reproducción se congela visualmente tras 5 s sin更新 y se marca "desincronizado" |
| Reloj del dispositivo desviado | Irrelevante: el orden lo da el `seq` del relay |
| Dos dispositivos editan la misma playlist | Merge por `item_id` + `order_key` fraccionario; el usuario ve ambas versiones fusionadas, sin pisarse |
| Pista no disponible en el dispositivo | Se muestra en la lista con estado "no disponible" y acción de resolver (buscar local / descargar) |
| Token de dispositivo revocado | El siguiente `hello` recibe 401 → la app pasa a modo local y avisa de que debe re-emparejarse |
| yt-dlp deja de funcionar (cambio en YouTube) | Error claro en la UI ("YouTube cambió su formato; actualiza yt-dlp") en vez de un fallo genérico; la biblioteca local no se ve afectada |
| VLC no instalado | Detección al arrancar con diálogo de instalación y enlace, en vez de `Exception` en `MusicPlayer.__init__` |
| Falla la escritura de tags | Resultado por archivo y resumen ("12 escritos, 2 fallaron") en vez de un bool opaco (`metadata_service.py:290`) |
| Descarga interrumpida | Archivo parcial limpiado y la pista descartada; la cola de descargas es cancelable y reintentable |

---

## 10. Validación

**Unitarias (`pytest`)**
- `core/playlist.py`: next/previous con shuffle, repeat NONE/ALL/ONE, historial, fin de lista.
- `core/player.py` con el doble `tests/fakes/fake_vlc.py`: transiciones de estado, `set_position`, callbacks de evento.
- `core/mapper.py`: fingerprint estable (títulos con acentos/MAYÚSCULAS/puntuación colapsan al mismo `track_key`).
- `sync/protocol.py`: round-trip encode/decode, versionado, mensajes inválidos.
- `sync/store.py`: outbox, reintento idempotente, migraciones de esquema.

**UI (`pytest-qt`)**
- Smoke de `MainWindow` (arranque, tema aplicado, estado inicial).
- Interacción: añadir pista, buscar en biblioteca, cambiar de tema, editar tags, cola reordenada.
- Regresión de los bugs corregidos: no se emite `state_changed` espurio al pausar estando parado; el hilo de la carátula se retira siempre; la app cierra con un escaneo en curso sin `QThread destroyed`.

**Contrato de sincronización (`pytest-asyncio` + relay real en Docker)**
1. Emparejamiento: crear hogar → claim del código → credenciales válidas; claim repetido falla; código expirado falla.
2. Propagación: cliente A reproduce → cliente B recibe `playback_state` con la misma pista y posición (±300 ms).
3. Control remoto: B envía `pause` → A aplica y responde `command_result` → B ve `paused`.
4. Handoff: B toma el control → A deja de ser dueño → A ya no puede escribir estado; B sí.
5. Deltas: cliente B offline → A muta la playlist → B reconecta con `since` y recibe solo lo perdido.
6. Conflicto: A y B editan el mismo ítem con `base_version` obsoleto → 409 → merge correcto.
7. Borrado offline: B borra offline, A edita → al reconectar el ítem queda borrado (tombstone).
8. Revocación: revocar el token de B → B recibe 401 y cae a modo local.
9. Durante 2 y 3, el relay se reinicia → los clientes reconectan y recuperan el estado.

**Rendimiento (script de banco, no bloqueante en CI)**
- Biblioteca de 20 000 pistas: tiempo de escaneo, tiempo de construcción del árbol, pico de memoria, tiempo de cambio de vista.
- Criterio de aceptación: cambio de vista de biblioteca < 200 ms con 20 000 ítems (hoy es O(n²)).

**Manuales (checklist por fase, en `docs/checklists/`)**
- Verificar que el audio no se corta al final de la pista; que la posición se conserva al alternar vídeo/audio; que el zoom de Windows 150 % no rompe el vídeo incrustado.

---

## 11. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| R1 | Conflicto de estado de reproducción entre dispositivos | Saltos/fighting de reproducción | Dueño único impuesto por el relay (D7) + handoff explícito |
| R2 | Latencia percibida en el control remoto | UX de "app colgada" | Aplicación optimista local + interpolación de la posición + indicador de "desincronizado" |
| R3 | Identidad de pistas entre dispositivos | Pistas duplicadas o "no disponibles" | `track_key` por fingerprint + binding local + flujo de resolución; matching acústico fuera de alcance |
| R4 | Relay expuesto a internet | Abuso de la cuenta de la biblioteca | Tokens hasheados (argon2), TLS por túnel, códigos de un solo uso con caducidad, rate limit, revocación por dispositivo, sin PII |
| R5 | Ruptura de `yt-dlp` con los cambios de YouTube | Descargas fallan | Fijar versiones, aviso explícito en la UI, cliente alterno, caché local, biblioteca local no afectada |
| R6 | Empaquetado de VLC en el `.exe` (DLLs, HWND, DPI) | El vídeo incrustado no funciona tras empaquetar | Build reproducible con `.spec` versionado + prueba de humo en CI + matriz de DPI |
| R7 | Hilos mal gestionados (VLC desde hilo no principal, cierres) | Crashes aleatorios | Regla dura "VLC solo en el hilo GUI" + `QThreadPool` + `waitForDone` en el cierre + tests de regresión |
| R8 | Tokens de dispositivo en el navegador (PWA) | Robo de sesión | Tokens por dispositivo revocables, sin cookies globales, logout explícito desde el escritorio |
| R9 | Crecimiento de `event_log` y de la caché local | Degradación y disco lleno | Poda por edad (30 días), `VACUUM` periódico, límite de caché configurable, purga automática de covers |
| R10 | Actualización automática en mitad de una reproducción | Interrupción del audio | No actualizar durante la reproducción; différer; conservar la versión anterior para rollback; hash y firma verificados |
| R11 | Refactor grande de `MainWindow` (1156 líneas) | Regresionesfuncionales | Fase 0 isolates el refactor *antes* de tocar funcionalidad; tests de humo y de regresión como red |
| R12 | Doble emission de señales desde hilos | "QObject: Cannot create children for a parent that is in a different thread" | Señales Qt como único canal desde los workers; aserciones en el test de humo |
| R13 | SQLite del relay bajo concurrencia | "database is locked" | WAL + `busy_timeout` + un solo escritor (el relay) + reintentos con backoff |
| R14 | Coste de la infraestructura (VPS) | Coste mensual recurrente | El hub local funciona gratis en LAN; el túnel gratuito (Cloudflare/Tailscale) cubre el caso remoto; el hub es opcional |

---

## 12. Preguntas abiertas (requieren decisión del usuario)

1. **Exposición del relay**: ¿Cloudflare Tunnel (URL estable gratuita) o un VPS propio con dominio? Afecta a la config por defecto del cliente y a la documentación.
2. **Segundo escritorio**: ¿el plan debe soportar también Linux/macOS como clientes de escritorio, o Windows queda como plataforma únicasupported en el primer lanzamiento?
3. **Seguridad del código de emparejamiento**: ¿código de 6 dígitos simple (como el de Chromecast) o con pin de 4 dígitos adicional para redes Wi-Fi públicas?
4. **Matching acústico**: ¿se acepta la limitación de que un MP3 local y su equivalente en YouTube no se emparejen, o se-ejecuta Chromaprint (fase posterior)?
5. **Portada de las pistas de YouTube**: la corrección de `is_generic_cover` recuperará las miniaturas de YouTube; ¿se prefiere la miniatura de YouTube o la de iTunes como portada por defecto cuando ambas existen?
6. **Alcance del scrobbling**: ¿se scrobblea también lo que se reproduce desde la caché de YouTube, o solo desde archivos locales con tags válidos?

---

## 13. Definición de "hecho" por fase

- **Fase 0**: `pytest` verde en CI, `ruff` sin errores, la app arranca y reproduce un archivo local, el exe se compila desde el `.spec` versionado.
- **Fase 1**: fin de pista sin cortes ni saltos; cambio de vista de biblioteca < 200 ms con 20 000 ítems; sin "QThread destroyed" al cerrar; búsqueda local funcionando; tema/volume/sesión persistentes; todas las acciones accesibles por teclado.
- **Fase 2**: los 9 tests de contrato de sincronización en verde; el compañero web controla la reproducción desde el móvil; letras, Last.fm, bandeja/teclas y playlists múltiples operativos.
- **Fase 3**: instalador firmado funcionando en una máquina limpia; actualización automática verificada de principio a fin con rollback; `docker compose up` levanta el relay y un dispositivo se empareja en < 2 minutos siguiendo la guía.
