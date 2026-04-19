# Music Player Pro 🎵

Un reproductor de música moderno y versátil desarrollado con **Python** y **PyQt6**. Esta aplicación permite gestionar tu biblioteca musical local y disfrutar de contenido directamente desde **YouTube** con capacidades de streaming y descarga.

## ✨ Características Principales

*   **Reproducción Dual:** Soporte para archivos locales (MP3, FLAC, WAV, M4A, OGG) y URLs de YouTube.
*   **Integración con YouTube:**
    *   Búsqueda integrada de canciones.
    *   Descarga masiva de resultados.
    *   Modo de visualización de video en tiempo real (vía VLC).
    *   Descarga permanente en formato MP3 con metadatos incrustados.
*   **Gestión de Biblioteca:**
    *   Escaneo asíncrono de carpetas locales.
    *   Organización automática por Carpetas, Artistas o Álbumes.
*   **Editor de Metadatos Pro:**
    *   Edición de etiquetas ID3/Vorbis/MP4.
    *   Búsqueda de sugerencias de metadatos y portadas a través de la API de iTunes.
*   **Interfaz Moderna:**
    *   Temas personalizados: Dark (estilo Spotify), Light y Cyberpunk.
    *   Widgets personalizados: Sliders clickeables, etiquetas con desplazamiento (Marquee) y carga asíncrona de carátulas.
*   **Controles Avanzados:** Shuffle, modos de repetición y gestión de cola de reproducción.

## 🛠️ Tecnologías Utilizadas

*   **PyQt6:** Para la interfaz de usuario robusta y reactiva.
*   **VLC (python-vlc):** Motor de reproducción de alto rendimiento para audio y video.
*   **yt-dlp:** Para la extracción y descarga de contenido desde YouTube.
*   **Mutagen:** Manipulación de metadatos de archivos de audio.
*   **Requests:** Comunicación con APIs externas (iTunes/Spotify).

## 📂 Estructura del Proyecto

*   `main.py`: Punto de entrada de la aplicación.
*   `core/`: Lógica central del reproductor y gestión de la lista de reproducción.
    *   `player.py`: Wrapper de la instancia de VLC.
    *   `playlist.py`: Lógica de navegación entre pistas y persistencia.
*   `ui/`: Todos los componentes de la interfaz de usuario.
    *   `main_window.py`: Ventana principal y orquestación de hilos.
    *   `widgets.py`: Componentes visuales personalizados.
    *   `tag_editor.py`: Diálogo para la edición de etiquetas.
    *   `themes.py`: Gestión de estilos QSS.
*   `services/`: Servicios externos y utilidades.
    *   `youtube_service.py`: Lógica de búsqueda y descarga.
    *   `metadata_service.py`: Extracción y búsqueda de información de pistas.

## 🚀 Instalación y Requisitos

1.  **VLC Media Player:** Es indispensable tener instalado VLC en el sistema, ya que el motor de reproducción depende de sus librerías.
2.  **Dependencias de Python:**
    ```bash
    pip install PyQt6 python-vlc yt-dlp mutagen requests spotipy
    ```
3.  **FFmpeg:** Para las descargas permanentes de YouTube y conversión a MP3, se recomienda tener `ffmpeg` instalado y accesible en el PATH del sistema.

## 📝 Notas de Uso

*   **Modo Video:** Al activar el icono de TV, el reproductor intentará extraer el stream de video de YouTube para mostrarlo en el panel principal.
*   **Caché:** Las canciones reproducidas de YouTube se almacenan temporalmente en una carpeta de caché para evitar descargas repetidas durante la misma sesión.
*   **Búsqueda Online:** El editor de etiquetas permite buscar la información oficial de una canción simplemente ingresando el título o artista.

---
Desarrollado con ❤️ usando Python y PyQt6.
