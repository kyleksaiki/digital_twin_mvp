"""Audio upload endpoints for long-running workflows."""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.utils.paths import ensure_user_data_path, get_user_data_path, get_base_path, is_frozen


# Uploads go in a writable location: in dev that's the backend/ root
# (where they have always lived), and in a frozen build that's the
# per-user app-data folder (uploads must NEVER live inside _MEIPASS,
# which is a read-only temp dir).
if is_frozen():
    DATA_ROOT = get_user_data_path()
else:
    DATA_ROOT = get_base_path()
UPLOAD_ROOT = DATA_ROOT / "uploads"
PENDING_ROOT = UPLOAD_ROOT / "pending"
CHUNK_SIZE = 8 * 1024 * 1024

router = APIRouter(prefix="/api/audio", tags=["audio"])


def _ensure_data_dirs() -> None:
    """Create upload + pending dirs lazily. Idempotent and safe to call per request."""
    ensure_user_data_path()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    PENDING_ROOT.mkdir(parents=True, exist_ok=True)


def _sanitize_node_id(node_id: str) -> str:
    return "".join(ch for ch in str(node_id) if ch.isalnum() or ch in {"_", "-"}).strip("_-")


def _build_filename(node_id: str, filename: str) -> str:
    suffix = Path(filename).suffix or ".wav"
    safe_node = _sanitize_node_id(node_id) or "node"
    if safe_node.lower().startswith("node_"):
        return f"{safe_node}{suffix}"
    return f"node_{safe_node}{suffix}"


def _relative_path(path: Path) -> str:
    # Path is always under DATA_ROOT in both dev and frozen modes,
    # so relative_to is well-defined.
    return path.relative_to(DATA_ROOT).as_posix()


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    node_id: str = Form(...),
    run_id: Optional[int] = Form(None),
) -> dict:
    """Stream a large audio file to disk without loading into RAM."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")

    _ensure_data_dirs()
    upload_id = uuid.uuid4().hex
    target_dir = (
        UPLOAD_ROOT / f"run_{run_id}"
        if run_id is not None
        else PENDING_ROOT / upload_id
    )
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / _build_filename(node_id, file.filename)

    try:
        with target_path.open("wb") as handle:
            while True:
                chunk = await file.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
    finally:
        await file.close()

    response = {"saved_path": _relative_path(target_path), "node_id": node_id}
    if run_id is not None:
        response["run_id"] = run_id
    else:
        response["upload_id"] = upload_id
    return response
