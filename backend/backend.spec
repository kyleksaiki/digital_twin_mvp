
"""PyInstaller spec for the Shaman Digital Twin backend (FastAPI sidecar).

Builds a single-file ``shaman-backend.exe`` that the Tauri shell launches
as a sidecar. Bundles the AED model checkpoint so the backend can find
it under ``sys._MEIPASS`` without a hard-coded path, and pulls in
hidden imports / data files for every library used by the app.

Run from inside the venv (PowerShell):
    cd backend
    pyinstaller shaman-backend.spec --noconfirm

Notes:
- The entry script is ``app/main.py`` which boots uvicorn in __main__.
- ``app/services/aed/models/tinycnn_v3.pth`` ships inside the bundle
  under ``app/services/aed/models/``; ``app.services.aed.inference``
  locates it via ``get_base_path()`` (see app/utils/paths.py).
- ultralytics, librosa, scipy, and torch all ship non-code assets
  (yaml configs, version files, .npy data) that PyInstaller's default
  hooks miss — we add them via ``collect_data_files``.
- birdnetlib + tensorflow + tflite-runtime are heavy and optional; the
  backend imports them defensively, so we only pull them into the
  archive if the host venv actually has them installed. That keeps the
  sidecar's size manageable for builds that don't use the optional
  BirdNET stage.
"""
from pathlib import Path

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_submodules,
    copy_metadata,
)


def _try_collect(package: str) -> list:
    """collect_submodules raises if the package isn't importable. Wrap it
    so the spec builds cleanly whether or not the optional deps are in
    the venv that ran pyinstaller."""
    try:
        return list(collect_submodules(package))
    except Exception:
        return []


def _has_package(package: str) -> bool:
    """True iff `import package` would succeed in this Python."""
    try:
        __import__(package)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hidden imports — every module that the app or one of its deps does via
# dynamic import, getattr, or plugin discovery. Static analysis misses
# these, so we enumerate them here.
# ---------------------------------------------------------------------------
hiddenimports = []
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('torch')
hiddenimports += collect_submodules('torchaudio')
hiddenimports += collect_submodules('soundfile')
hiddenimports += collect_submodules('librosa')
hiddenimports += collect_submodules('scipy')
hiddenimports += collect_submodules('fastapi')
hiddenimports += collect_submodules('sqlalchemy')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pydantic_core')
# ultralytics uses dynamic plugin discovery — without these the YOLO
# predictor crashes on first use. We deliberately pull in only the
# detection subset (and nn + engine plumbing) and NOT the sam /
# fastsam / semantic / classify / pose / obb subpackages. Those pull
# in matplotlib, which we don't ship, and the app never calls them.
hiddenimports += [
    'ultralytics',
    'ultralytics.engine',
    'ultralytics.engine.model',
    'ultralytics.engine.predictor',
    'ultralytics.engine.results',
    'ultralytics.models',
    'ultralytics.models.yolo',
    'ultralytics.models.yolo.detect',
    'ultralytics.models.yolo.model',
    'ultralytics.nn',
    'ultralytics.nn.tasks',
    'ultralytics.utils',
    'ultralytics.utils.downloads',
    'ultralytics.utils.torch_utils',
    'ultralytics.utils.ops',
    'ultralytics.utils.nms',
    'ultralytics.utils.plotting',
]
# numba/llvmlite for librosa's JIT paths
hiddenimports += collect_submodules('numba')

# Optional — only added when the host venv actually has these packages.
# The app imports them inside try/except so a build without them still
# works for every flow except the BirdNET classifier stage.
for optional_pkg in ('birdnetlib', 'birdnetlib.analyzer', 'tflite_runtime', 'tensorflow'):
    hiddenimports += _try_collect(optional_pkg)

# ---------------------------------------------------------------------------
# Data files bundled inside the executable.
# ---------------------------------------------------------------------------
datas = [
    # AED model checkpoint — resolution paths in app.services.aed.inference
    # are anchored to sys._MEIPASS, so this relative path is the location
    # the running app will look for it.
    ('app/services/aed/models/tinycnn_v3.pth', 'app/services/aed/models'),
]

# ultralytics ships its config yaml + coco dataset yaml inside the wheel.
datas += collect_data_files('ultralytics', include_py_files=False)
datas += collect_data_files('ultralytics/assets', include_py_files=False)
# librosa ships version files and a couple of small json configs.
datas += collect_data_files('librosa')
# scipy ships tests data and .npy/.npz fixtures — keep only the runtime
# bits that PyInstaller's hooks miss.
datas += collect_data_files('scipy')
# numpy runtime metadata
datas += copy_metadata('numpy')
datas += copy_metadata('librosa')
datas += copy_metadata('scipy')
datas += copy_metadata('torch')
datas += copy_metadata('ultralytics')
# Optional metadata for bird-related packages.
for optional_pkg in ('birdnetlib', 'tflite_runtime', 'tensorflow'):
    if _has_package(optional_pkg):
        try:
            datas += copy_metadata(optional_pkg)
        except Exception:
            pass

a = Analysis(
    ['app/main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
    # Catch a few well-known false positives that PyInstaller's analysis
    # flags as missing but the runtime never needs. NOTE: do NOT exclude
    # matplotlib — ultralytics does an unconditional `import matplotlib`
    # through its training/sam modules, so the module has to be bundled
    # even though the app never plots anything.
    excludes=[
        'tkinter',
        'PyQt5',
        'PyQt6',
        'IPython',
        'jupyter',
        'pytest',
        'test',
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    name='shaman-backend',
    debug=False,
    console=True,  # Set to True to see stdout logs in dev; the Tauri
                   # shell plugin streams stdout to its own log.
)