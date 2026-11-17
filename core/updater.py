"""Auto-actualización con verificación y rollback.

Flujo:

1. Se consulta la API de releases de GitHub y se busca untag más nuevo.
2. Se descarga el asset a una carpeta temporal.
3. Se verifica el **SHA-256** contra el checksum publicado en el release.
4. Se hace una copia del ejecutable actual (``app.exe.bak``).
5. Se sustituye el ejecutable y se lanza con ``--verify-startup``: la nueva
   versión escribe un testigo y termina.
6. Si la nueva versión **no** arranca, se restaura la copia (rollback).

El proceso principal no se reemplaza a sí mismo: el arranque de la app nueva
es quien completa la sustitución.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.version import APP_VERSION, is_newer

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
VERIFY_FLAG = "--verify-startup"
STARTUP_WITNESS = "update-ok.txt"
CHECKSUM_SUFFIX = ".sha256"


@dataclass
class ReleaseInfo:
    """Información de una versión publicada."""

    version: str
    name: str = ""
    notes: str = ""
    url: str = ""
    sha256: str = ""
    size: int = 0
    asset_name: str = ""

    @property
    def is_newer(self) -> bool:
        return is_newer(self.version, APP_VERSION)


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    """Hash SHA-256 de un fichero."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksum(path: Path, expected: str) -> bool:
    """Comprueba el SHA-256 de un fichero."""
    if not expected:
        return False
    return sha256_file(path).lower() == expected.strip().lower()


class UpdateChecker:
    """Consulta los releases publicados en GitHub."""

    def __init__(self, repo: str = "musicplayerpro/musicplayerpro", timeout: int = 15) -> None:
        self.repo = repo
        self.timeout = timeout

    def fetch_latest(self) -> Optional[ReleaseInfo]:
        """Devuelve el último release, o ``None`` si no hay nada nuevo."""
        import httpx

        url = GITHUB_API.format(repo=self.repo)
        try:
            response = httpx.get(
                url,
                timeout=self.timeout,
                headers={"Accept": "application/vnd.github+json"},
            )
            if response.status_code != 200:
                logger.warning("GitHub respondió %s", response.status_code)
                return None
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo consultar GitHub: %s", exc)
            return None

        release = ReleaseInfo(
            version=str(data.get("tag_name", "")).lstrip("vV"),
            name=str(data.get("name", "")),
            notes=str(data.get("body", "")),
        )
        for asset in data.get("assets", []):
            name = asset.get("name", "")
            if name.endswith(".exe") and not release.url:
                release.url = asset.get("browser_download_url", "")
                release.asset_name = name
                release.size = int(asset.get("size", 0) or 0)
            if name.endswith(CHECKSUM_SUFFIX):
                release.sha256 = self._read_checksum(asset.get("browser_download_url", ""))

        if not release.url:
            logger.info("El último release no incluye un ejecutable para Windows")
            return None
        if not release.is_newer:
            logger.info("Ya se está en la última versión (%s)", APP_VERSION)
            return None
        return release

    @staticmethod
    def _read_checksum(url: str) -> str:
        import httpx

        if not url:
            return ""
        try:
            response = httpx.get(url, timeout=10)
            if response.status_code != 200:
                return ""
            content = response.text.strip()
            # Formato habitual: "<hash>  <fichero>"
            return content.split()[0] if content else ""
        except Exception as exc:  # noqa: BLE001
            logger.debug("No se pudo leer el checksum: %s", exc)
            return ""


class UpdateApplier:
    """Descarga, verifica e instala una actualización."""

    def __init__(self, app_dir: Optional[Path] = None) -> None:
        self.app_dir = Path(app_dir) if app_dir else Path(sys.executable).parent
        self.work_dir = Path(tempfile.gettempdir()) / "musicplayerpro-update"

    # -- descarga ------------------------------------------------------
    def download(
        self,
        release: ReleaseInfo,
        progress: Callable[[int, int], None] | None = None,
    ) -> Optional[Path]:
        """Descarga el asset y verifica su SHA-256."""
        import httpx

        if not release.url:
            return None
        self.work_dir.mkdir(parents=True, exist_ok=True)
        target = self.work_dir / (release.asset_name or f"MusicPlayerPro-{release.version}.exe")

        try:
            with httpx.stream("GET", release.url, timeout=60, follow_redirects=True) as response:
                if response.status_code != 200:
                    logger.warning("La descarga falló: %s", response.status_code)
                    return None
                total = int(response.headers.get("content-length", 0) or 0)
                downloaded = 0
                with open(target, "wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1 << 16):
                        handle.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo descargar la actualización: %s", exc)
            return None

        if release.sha256 and not verify_checksum(target, release.sha256):
            logger.error("El checksum de la actualización no coincide: se descarta")
            target.unlink(missing_ok=True)
            return None
        return target

    # -- instalación ------------------------------------------------------
    def install(self, release: ReleaseInfo, downloaded: Path) -> bool:
        """Sustituye el ejecutable actual dejando una copia para el rollback."""
        target_exe = self._current_executable()
        if target_exe is None:
            logger.error("No se encuentra el ejecutable de la aplicación")
            return False

        backup = target_exe.with_suffix(target_exe.suffix + ".bak")
        try:
            if backup.exists():
                backup.unlink()
            shutil.copy2(target_exe, backup)
        except OSError as exc:
            logger.error("No se pudo hacer la copia de seguridad: %s", exc)
            return False

        try:
            shutil.copy2(downloaded, target_exe)
        except OSError as exc:
            logger.error("No se pudo instalar la actualización: %s", exc)
            self.rollback()
            return False

        logger.info("Actualización instalada; verificando el arranque…")
        if self._verify_startup(target_exe):
            backup.unlink(missing_ok=True)
            logger.info("Actualización verificada (%s)", release.version)
            return True

        logger.warning("La nueva versión no arrancó: se revierte el cambio")
        self.rollback()
        return False

    def _current_executable(self) -> Optional[Path]:
        if getattr(sys, "frozen", False):
            return Path(sys.executable)
        return None

    def _verify_startup(self, executable: Path) -> bool:
        """Arranca la nueva versión en modo verificación y comprueba el testigo."""
        witness = self.work_dir / STARTUP_WITNESS
        witness.unlink(missing_ok=True)
        try:
            process = subprocess.Popen(  # noqa: S603
                [str(executable), VERIFY_FLAG],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            process.wait(timeout=45)
        except Exception as exc:  # noqa: BLE001
            logger.warning("No se pudo verificar el arranque: %s", exc)
            return False
        return witness.exists()

    def rollback(self) -> bool:
        """Restaura la copia de seguridad del ejecutable."""
        target_exe = self._current_executable()
        if target_exe is None:
            return False
        backup = target_exe.with_suffix(target_exe.suffix + ".bak")
        if not backup.exists():
            return False
        try:
            shutil.copy2(backup, target_exe)
            backup.unlink(missing_ok=True)
            logger.info("Se restauró la versión anterior")
            return True
        except OSError as exc:
            logger.error("No se pudo restaurar la versión anterior: %s", exc)
            return False


def write_startup_witness(directory: Optional[Path] = None) -> None:
    """Escribe el testigo que confirma que la app arranca correctamente."""
    target = Path(directory) if directory else Path(tempfile.gettempdir()) / "musicplayerpro-update"
    try:
        target.mkdir(parents=True, exist_ok=True)
        (target / STARTUP_WITNESS).write_text(str(time.time()), encoding="utf-8")
    except OSError as exc:
        logger.debug("No se pudo escribir el testigo: %s", exc)


def parse_checksum_file(content: str) -> str:
    """Extrae el hash de un fichero ``SHA256SUMS.txt``."""
    for line in (content or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if parts:
            return parts[0]
    return ""


def load_release_from_file(path: Path) -> Optional[ReleaseInfo]:
    """Lee un release desde un JSON local (para pruebas o mirror interno)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return ReleaseInfo(
        version=str(data.get("version", "")),
        name=str(data.get("name", "")),
        notes=str(data.get("notes", "")),
        url=str(data.get("url", "")),
        sha256=str(data.get("sha256", "")),
        size=int(data.get("size", 0) or 0),
        asset_name=str(data.get("asset_name", "")),
    )


def is_update_supported() -> bool:
    """La auto-actualización solo tiene sentido en el ejecutable empaquetado."""
    return bool(getattr(sys, "frozen", False)) and os.name == "nt"
