"""Human visual detection endpoints (YOLO person detection on uploaded images).

Stateless by design: images are processed in memory and discarded — nothing is
persisted to disk or the database. Mirrors the defensive-import pattern in
services/audio_processing.py so a missing `ultralytics` install never crashes
FastAPI startup; only this endpoint degrades.
"""
from __future__ import annotations

import io
import logging
import threading
import time

from fastapi import APIRouter, File, HTTPException, UploadFile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/vision", tags=["vision"])

MODEL_NAME = "yolo11n.pt"       # nano COCO checkpoint — few MB, CPU-friendly
PERSON_CLASS_ID = 0             # COCO class 0 = person
SERVER_CONFIDENCE_FLOOR = 0.1   # low floor; the frontend slider filters upward
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024

try:
    from ultralytics import YOLO
except Exception as exc:  # pragma: no cover - depends on install
    logger.exception("Failed to import ultralytics: %s", exc)
    YOLO = None

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - depends on install
    logger.exception("Failed to import Pillow: %s", exc)
    Image = None

_model = None
_model_lock = threading.Lock()


def _get_model():
    """Load the YOLO model once and cache it for the process lifetime."""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is None:
            logger.info("Loading YOLO model %s (first use downloads weights)", MODEL_NAME)
            _model = YOLO(MODEL_NAME)
    return _model


def _read_upload_capped(upload: UploadFile) -> bytes:
    """Read the upload into memory, rejecting anything over MAX_UPLOAD_BYTES."""
    buffer = io.BytesIO()
    total = 0
    while True:
        chunk = upload.file.read(CHUNK_SIZE)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large (max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB).",
            )
        buffer.write(chunk)
    return buffer.getvalue()


@router.post("/detect-humans")
def detect_humans(file: UploadFile = File(...)) -> dict:
    """Detect people in an uploaded image and return normalized bounding boxes."""
    if YOLO is None or Image is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Human detection is not available on this server. "
                "Install the missing dependencies with: pip install ultralytics pillow"
            ),
        )

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image file (jpg, png, webp).")

    data = _read_upload_capped(file)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Could not read the image — the file may be corrupt.")

    try:
        model = _get_model()
    except Exception as exc:
        logger.exception("Failed to load YOLO model %s", MODEL_NAME)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not load the detection model ({MODEL_NAME}). "
                "First use downloads weights and requires network access; "
                f"check server connectivity and logs. ({exc})"
            ),
        )

    started = time.perf_counter()
    try:
        results = model.predict(
            source=image,
            conf=SERVER_CONFIDENCE_FLOOR,
            classes=[PERSON_CLASS_ID],
            verbose=False,
        )
    except Exception as exc:
        logger.exception("YOLO inference failed")
        raise HTTPException(status_code=500, detail=f"Detection failed: {exc}")
    inference_ms = int(round((time.perf_counter() - started) * 1000.0))

    detections = []
    if results:
        boxes = results[0].boxes
        if boxes is not None:
            for cls_id, conf, xyxyn in zip(
                boxes.cls.tolist(), boxes.conf.tolist(), boxes.xyxyn.tolist()
            ):
                if int(cls_id) != PERSON_CLASS_ID:
                    continue  # belt-and-braces; predict() already filters
                x1, y1, x2, y2 = (max(0.0, min(1.0, float(v))) for v in xyxyn)
                detections.append(
                    {
                        "x1": round(x1, 4),
                        "y1": round(y1, 4),
                        "x2": round(x2, 4),
                        "y2": round(y2, 4),
                        "confidence": round(float(conf), 4),
                    }
                )

    detections.sort(key=lambda d: -d["confidence"])
    return {
        "detections": detections,
        "image_width": image.width,
        "image_height": image.height,
        "model": MODEL_NAME.replace(".pt", ""),
        "inference_ms": inference_ms,
    }
