"""Pruebas de la actualización automática, la versión y el gestor de playlists."""

from __future__ import annotations

import hashlib

from core.updater import (
    ReleaseInfo,
    UpdateApplier,
    parse_checksum_file,
    sha256_file,
    verify_checksum,
    write_startup_witness,
)
from core.version import APP_VERSION, is_newer, parse_version


# ======================================================================
# Versión
# ======================================================================
def test_parse_version():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("2.0") == (2, 0, 0)
    assert parse_version("1.2.3-beta.1") == (1, 2, 3)


def test_is_newer():
    assert is_newer("999.0.0", "1.2.0")
    assert not is_newer("1.2.0", "1.2.0")
    assert not is_newer("1.1.0", "1.2.0")
    assert APP_VERSION


# ======================================================================
# Actualizador
# ======================================================================
def test_sha256_and_verify(tmp_path):
    target = tmp_path / "bin.exe"
    target.write_bytes(b"contenido")
    digest = hashlib.sha256(b"contenido").hexdigest()
    assert sha256_file(target) == digest
    assert verify_checksum(target, digest)
    assert not verify_checksum(target, "0" * 64)
    assert not verify_checksum(target, "")


def test_parse_checksum_file():
    content = "abc123  MusicPlayerPro.exe\ndef456  otro.exe\n"
    assert parse_checksum_file(content) == "abc123"
    assert parse_checksum_file("") == ""


def test_release_is_newer():
    release = ReleaseInfo(version="999.0.0")
    assert release.is_newer
    assert not ReleaseInfo(version="0.0.1").is_newer


def test_install_rolls_back_on_failure(tmp_path):
    """Si la nueva versión no arranca, se restaura la anterior."""
    exe = tmp_path / "MusicPlayerPro.exe"
    exe.write_bytes(b"vieja")
    applier = UpdateApplier(app_dir=tmp_path)
    applier._current_executable = lambda: exe  # type: ignore[method-assign]

    download = tmp_path / "nueva.exe"
    download.write_bytes(b"nueva")

    release = ReleaseInfo(version="999.0.0", asset_name="nueva.exe")
    ok = applier.install(release, download)

    assert ok is False
    assert exe.read_bytes() == b"vieja"
    assert not exe.with_suffix(".exe.bak").exists()


def test_install_succeeds_and_removes_backup(tmp_path, monkeypatch):
    exe = tmp_path / "MusicPlayerPro.exe"
    exe.write_bytes(b"vieja")
    applier = UpdateApplier(app_dir=tmp_path)
    applier._current_executable = lambda: exe  # type: ignore[method-assign]
    monkeypatch.setattr(applier, "_verify_startup", lambda _exe: True)

    download = tmp_path / "nueva.exe"
    download.write_bytes(b"nueva")
    ok = applier.install(ReleaseInfo(version="999.0.0"), download)

    assert ok is True
    assert exe.read_bytes() == b"nueva"
    assert not exe.with_suffix(".exe.bak").exists()


def test_startup_witness_is_written(tmp_path):
    from core.updater import STARTUP_WITNESS

    write_startup_witness(tmp_path)
    assert (tmp_path / STARTUP_WITNESS).exists()


def test_download_rejects_bad_checksum(tmp_path, monkeypatch):
    applier = UpdateApplier(app_dir=tmp_path)
    release = ReleaseInfo(
        version="999.0.0",
        url="https://example.invalid/app.exe",
        sha256="0" * 64,
        asset_name="app.exe",
    )
    # Sin red la descarga falla y no debe devolver ninguna ruta.
    assert applier.download(release) is None
