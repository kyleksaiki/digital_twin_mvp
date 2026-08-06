"""Core AED inference — vendored from the audio-detection repo's aed_inference.py.

`load_model` and `predict` are upstream's functions, minimally adapted
(no sys.path mutation, guarded MPS check, explicit weights_only). The mel
parameters are upstream's constants and MUST match training — do not change.

`clip_to_mel` is the one local addition: upstream preprocesses from a file
path via librosa.load; the Digital Twin workflow hands us an in-memory clip
that has already been resampled/mono'd by extract_centered_clip_from_file.
Each step below maps 1:1 to the documented upstream pipeline
(aed_inference.preprocess_clip / api.main.compute_mel):
  resample+mono+truncate (done by caller) -> right zero-pad to SR*DURATION
  -> melspectrogram(N_MELS, N_FFT, HOP_LENGTH, FMIN, FMAX)
  -> power_to_db(ref=np.max)  (per-clip max-referenced, no other norm)
  -> [:, :N_FRAMES] -> float32.

To re-sync with upstream: diff against aed_inference.py; only the marked
sections differ.
"""
from __future__ import annotations

import os
from typing import Optional, Tuple

import numpy as np

try:
	import librosa
except Exception:  # pragma: no cover - depends on install
	librosa = None

import torch

from app.services.aed.architecture import TinyCNN

# ---------------------------------------------------------------------------
# Mel spectrogram parameters (must match training — do not change)
# ---------------------------------------------------------------------------
SR = 48000
DURATION = 3.0
N_MELS = 128
N_FFT = 1024
HOP_LENGTH = 512
FMIN = 50
FMAX = 16000
N_FRAMES = 256  # time-axis length the model expects, after truncation

DEFAULT_THRESHOLD = 0.5


def pick_device() -> torch.device:
	"""cuda -> mps -> cpu, with the MPS check guarded (absent on some builds)."""
	if torch.cuda.is_available():
		return torch.device("cuda")
	try:
		if torch.backends.mps.is_available():
			return torch.device("mps")
	except AttributeError:
		pass
	return torch.device("cpu")


def load_model(model_path: str, device: Optional[torch.device] = None) -> Tuple[TinyCNN, dict]:
	"""Load a TinyCNN checkpoint. Returns (model in eval mode on device, checkpoint dict).

	weights_only=False is deliberate: these checkpoints carry plain metadata
	(notes, val_acc, precision/recall/f1) alongside model_state_dict, and we
	read it for provenance. The files ship with the repo, not from users.
	"""
	if device is None:
		device = pick_device()

	checkpoint = torch.load(model_path, map_location="cpu", weights_only=False)

	model = TinyCNN()
	model.load_state_dict(checkpoint["model_state_dict"])
	model.eval()
	model.to(device)
	return model, checkpoint


def predict(model: TinyCNN, mel_batch: torch.Tensor, device: torch.device) -> np.ndarray:
	"""Run TinyCNN on a batch of preprocessed mels -> not_meaningful probabilities.

	Model output is the raw "meaningful" logit; upstream convention is to report
	the complement of its sigmoid. LOWER not_meaningful_prob = more interesting.
	"""
	with torch.no_grad():
		mel_batch = mel_batch.to(device)
		raw_probs = torch.sigmoid(model(mel_batch).squeeze(1)).cpu().numpy()
	return 1.0 - raw_probs


def clip_to_mel(clip: np.ndarray, sr: int) -> np.ndarray:
	"""In-memory equivalent of upstream preprocess_clip for an already-loaded clip.

	Returns np.ndarray of shape (N_MELS, <=N_FRAMES), dtype float32.
	Raises if librosa is unavailable or the clip is empty.
	"""
	if librosa is None:
		raise RuntimeError("AED inference needs librosa installed.")
	if clip is None or clip.size == 0:
		raise ValueError("Empty audio clip.")

	y = np.asarray(clip, dtype=np.float32)
	if y.ndim > 1:
		y = np.mean(y, axis=-1)
	if sr != SR:
		y = librosa.resample(y, orig_sr=sr, target_sr=SR)

	expected_len = int(SR * DURATION)
	if len(y) < expected_len:
		y = np.pad(y, (0, expected_len - len(y)))
	else:
		y = y[:expected_len]

	mel = librosa.feature.melspectrogram(
		y=y,
		sr=SR,
		n_mels=N_MELS,
		n_fft=N_FFT,
		hop_length=HOP_LENGTH,
		fmin=FMIN,
		fmax=FMAX,
	)
	mel_db = librosa.power_to_db(mel, ref=np.max)
	return mel_db[:, :N_FRAMES].astype(np.float32)


DEFAULT_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")


def resolve_checkpoint_path() -> Optional[str]:
	"""AED_MODEL_PATH env var wins; else tinycnn_v3.pth; else newest tinycnn_v*.pth present."""
	env_path = os.getenv("AED_MODEL_PATH", "").strip()
	if env_path:
		return env_path if os.path.exists(env_path) else None
	preferred = os.path.join(DEFAULT_MODEL_DIR, "tinycnn_v3.pth")
	if os.path.exists(preferred):
		return preferred
	if os.path.isdir(DEFAULT_MODEL_DIR):
		candidates = sorted(
			f for f in os.listdir(DEFAULT_MODEL_DIR)
			if f.startswith("tinycnn_v") and f.endswith(".pth")
		)
		if candidates:
			return os.path.join(DEFAULT_MODEL_DIR, candidates[-1])
	return None
