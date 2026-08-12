from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import numpy as np
import os
import tempfile
import torch
import torch.nn as nn

from app.utils.paths import get_base_path

os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "numba_cache"))

try:
    import librosa
except Exception:
    librosa = None


class TinyCNN(nn.Module):
    """TinyCNN architecture copied from cnn_tiny.ipynb for bird-call gating."""

    def __init__(self) -> None:
        super().__init__()
        self.conv_block1 = nn.Sequential(
            nn.Conv2d(1, 16, kernel_size=3, padding=1),
            nn.BatchNorm2d(16),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.conv_block2 = nn.Sequential(
            nn.Conv2d(16, 32, kernel_size=3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.conv_block3 = nn.Sequential(
            nn.Conv2d(32, 64, kernel_size=3, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(),
            nn.MaxPool2d(2),
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Linear(64 * 8 * 16, 64),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.conv_block1(x)
        x = self.conv_block2(x)
        x = self.conv_block3(x)
        return self.classifier(x)


@dataclass
class BirdcallGateResult:
    source_file: str
    trigger_time_s: float
    is_birdcall: bool
    confidence: float
    inference_ms: float
    label: str = "birdcall"
    model_status: str = "tinycnn"
    raw: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _require_librosa() -> None:
    if librosa is None:
        raise RuntimeError("TinyCNN bird-call gating needs librosa installed.")


def clip_to_tinycnn_mel(
    clip: np.ndarray,
    sr: int,
    model_sr: int = 22050,
    duration_s: float = 3.0,
    n_mels: int = 64,
    n_fft: int = 1024,
    hop_length: int = 512,
    target_frames: int = 128,
) -> np.ndarray:
    """Return the 64x128 log-mel tensor shape expected by the notebook model."""
    _require_librosa()
    audio = np.asarray(clip, dtype=np.float32)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    if sr != model_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=model_sr)

    target_len = int(model_sr * duration_s)
    if len(audio) < target_len:
        audio = np.pad(audio, (0, target_len - len(audio)))
    else:
        audio = audio[:target_len]

    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=model_sr,
        n_mels=n_mels,
        n_fft=n_fft,
        hop_length=hop_length,
    )
    mel_db = librosa.power_to_db(mel, ref=np.max).astype(np.float32)
    if mel_db.shape[1] < target_frames:
        mel_db = np.pad(mel_db, ((0, 0), (0, target_frames - mel_db.shape[1])), mode="edge")
    else:
        mel_db = mel_db[:, :target_frames]
    return mel_db


class TinyCNNBirdcallGate:
    """Stage-two bird-call filter.

    If weights are supplied, this uses the notebook TinyCNN. If they are not
    supplied yet, it runs an explicit deterministic fallback so the workflow can
    be exercised end-to-end without random model output.
    """

    def __init__(
        self,
        weights_path: Optional[str] = None,
        threshold: float = 0.3,
        device: Optional[str] = None,
        normalize_min: Optional[float] = None,
        normalize_max: Optional[float] = None,
    ) -> None:
        self.threshold = float(threshold)
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.normalize_min = normalize_min
        self.normalize_max = normalize_max
        self.model: Optional[TinyCNN] = None
        self.model_status = "fallback_no_weights"

        if weights_path:
            # Resolve relative weights paths against the bundle base so
            # PyInstaller builds can find a checkpoint shipped under
            # `app/audio_workflow/models/` (see backend.spec). Absolute
            # paths (e.g. from the user's filesystem) are used as-is.
            candidate = Path(weights_path)
            if not candidate.is_absolute():
                candidate = get_base_path() / candidate
            if not candidate.exists():
                raise FileNotFoundError(f"TinyCNN weights not found: {weights_path}")
            path = candidate
            self.model = TinyCNN().to(self.device)
            state = torch.load(path, map_location=self.device)
            if isinstance(state, dict) and "model_state_dict" in state:
                self.normalize_min = state.get("normalize_min", self.normalize_min)
                self.normalize_max = state.get("normalize_max", self.normalize_max)
                state = state["model_state_dict"]
            self.model.load_state_dict(state)
            self.model.eval()
            self.model_status = "tinycnn_weights_loaded"

    def _normalize(self, mel: np.ndarray) -> np.ndarray:
        mn = float(np.min(mel) if self.normalize_min is None else self.normalize_min)
        mx = float(np.max(mel) if self.normalize_max is None else self.normalize_max)
        if mx <= mn:
            return np.zeros_like(mel, dtype=np.float32)
        return ((mel - mn) / (mx - mn)).astype(np.float32)

    def _fallback_probability(self, mel: np.ndarray) -> Tuple[float, Dict[str, Any]]:
        high_band = mel[18:, :]
        low_band = mel[:18, :]
        high_energy = float(np.mean(high_band))
        low_energy = float(np.mean(low_band))
        contrast = high_energy - low_energy
        temporal_var = float(np.std(np.diff(mel, axis=1)))
        score = 1.0 / (1.0 + np.exp(-(0.10 * contrast + 0.035 * temporal_var + 1.0)))
        return float(score), {"high_low_contrast_db": contrast, "temporal_variation": temporal_var}

    def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> BirdcallGateResult:
        t0 = time.perf_counter()
        mel = clip_to_tinycnn_mel(clip, sr)
        raw: Dict[str, Any] = {"mel_shape": list(mel.shape)}

        if self.model is None:
            probability, fallback_raw = self._fallback_probability(mel)
            raw.update(fallback_raw)
        else:
            x = self._normalize(mel)
            xt = torch.tensor(x[None, None, :, :], dtype=torch.float32, device=self.device)
            with torch.no_grad():
                probability = float(self.model(xt).squeeze().item())

        return BirdcallGateResult(
            source_file=source_file,
            trigger_time_s=float(trigger_time_s),
            is_birdcall=bool(probability >= self.threshold),
            confidence=float(probability),
            inference_ms=float((time.perf_counter() - t0) * 1000.0),
            model_status=self.model_status,
            raw=raw,
        )
