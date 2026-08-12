"""Filesystem path resolution that works in dev and in a PyInstaller bundle.

Why this module exists
----------------------
Most of the backend resolves paths relative to ``__file__`` (e.g.
``Path(__file__).resolve().parents[3]`` for the backend root). That works
fine in dev but breaks under PyInstaller: in a frozen build, ``__file__``
points into the ``sys._MEIPASS`` temp dir, the source tree is not on disk,
and the process cwd is whatever folder the user launched the .exe from.

The helpers below give every module a single, consistent way to ask
"where is the bundle root?" and "where do I write user files?":

* ``get_base_path()`` — read-only assets shipped with the app (model
  checkpoints, bundled JSON, the source tree if you want it). In dev
  this is the backend/ root; in a frozen build it's ``sys._MEIPASS``.
* ``get_user_data_path()`` — writable per-user state (the SQLite DB,
  uploaded audio, generated reports). In dev this is also the backend/
  root for parity; in a frozen build it is a per-user app-data folder
  (e.g. ``%APPDATA%/ShamanDigitalTwin`` on Windows) so the .exe is not
  required to live in a writable location.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR_NAME = "ShamanDigitalTwin"


def get_base_path() -> Path:
    """Return the read-only base directory for bundled assets.

    * In dev: the backend/ root (three parents up from this file, which
      lives at ``backend/app/utils/paths.py``).
    * In a PyInstaller bundle: ``sys._MEIPASS``, the temp dir PyInstaller
      unpacks the archive into at startup.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """True when running inside a PyInstaller (or other) frozen bundle."""
    return getattr(sys, "frozen", False)


def get_user_data_path() -> Path:
    """Return a writable directory for user state (DB, uploads, exports).

    * In dev: the backend/ root — same as :func:`get_base_path`. Keeping
      dev and frozen paths consistent makes local debugging match what
      the bundled app does on disk.
    * Frozen on Windows: ``%APPDATA%\\ShamanDigitalTwin`` (created on
      first call). On macOS: ``~/Library/Application Support/ShamanDigitalTwin``.
      On Linux: ``$XDG_DATA_HOME/ShamanDigitalTwin`` or the
      ``~/.local/share`` fallback. This matches the Tauri identifier's
      app-data convention so the desktop app's frontend and the
      sidecar's backend can agree on where state lives.
    """
    if not is_frozen():
        return get_base_path()

    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / _APP_DIR_NAME
        # Fallback if APPDATA is unset (very unusual).
        return Path.home() / _APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _APP_DIR_NAME
    # Linux / other Unix
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / _APP_DIR_NAME


def ensure_user_data_path() -> Path:
    """Same as :func:`get_user_data_path` but creates the directory first.

    Safe to call from module import time; a missing parent is not an
    error here, only on the actual write.
    """
    path = get_user_data_path()
    path.mkdir(parents=True, exist_ok=True)
    return path
