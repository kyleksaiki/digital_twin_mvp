"""AEDMeaningfulGate — stage-2 gate backed by the new AED TinyCNN.

Drop-in replacement for audio_workflow.tiny_cnn_birdcall.TinyCNNBirdcallGate:
same constructor shape and the same confirm(clip, sr, source_file,
trigger_time) -> result-with-to_dict() contract, so node_audio_workflow.py
needs only a one-line swap.

Semantics differ from the old gate and that difference is the point:
- The model scores "meaningful audio" (bird, other animal incl. insects,
  human activity) vs "not meaningful" (background/weather). It is NOT a
  bird-only detector.
- The model returns not_meaningful_prob (LOWER = more interesting). To stay
  continuous with the old gate's convention — confidence means "interesting",
  clip passes when confidence >= threshold — we expose
  confidence = 1 - not_meaningful_prob and gate on that. The raw
  not_meaningful_prob is preserved in the result for transparency.

The model is loaded once per process and cached; a missing checkpoint or
import failure degrades to pass-through (model_status explains why), matching
the old gate's fallback convention so the workflow always completes.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)

try:
	import torch

	from app.services.aed import inference as aed_inference
	_IMPORT_ERROR: Optional[str] = None
except Exception as exc:  # pragma: no cover - depends on install
	logger.exception("AED inference unavailable: %s", exc)
	torch = None
	aed_inference = None
	_IMPORT_ERROR = str(exc)

_model = None
_checkpoint_meta: Dict[str, Any] = {}
_device = None
_model_status = "not_loaded"
_model_lock = threading.Lock()


def _ensure_model() -> str:
	"""Load and cache the model once per process. Returns the model status string."""
	global _model, _checkpoint_meta, _device, _model_status
	if _model is not None:
		return _model_status
	with _model_lock:
		if _model is not None:
			return _model_status
		if aed_inference is None:
			_model_status = f"aed_import_failed: {_IMPORT_ERROR}"
			return _model_status
		checkpoint_path = aed_inference.resolve_checkpoint_path()
		if not checkpoint_path:
			_model_status = "aed_checkpoint_missing"
			logger.warning(
				"No AED checkpoint found (looked in %s and AED_MODEL_PATH). "
				"Stage 2 will pass clips through unscored.",
				aed_inference.DEFAULT_MODEL_DIR,
			)
			return _model_status
		try:
			model, checkpoint = aed_inference.load_model(checkpoint_path)
			_model = model
			_device = next(model.parameters()).device
			_checkpoint_meta = {
				"checkpoint_file": os.path.basename(checkpoint_path),
				"model_version": str(checkpoint.get("notes", os.path.basename(checkpoint_path))),
				"val_acc": checkpoint.get("val_acc"),
				"not_meaningful_precision": checkpoint.get("not_meaningful_precision"),
				"not_meaningful_recall": checkpoint.get("not_meaningful_recall"),
				"not_meaningful_f1": checkpoint.get("not_meaningful_f1"),
				"device": str(_device),
			}
			_model_status = "aed_tinycnn"
			logger.info(
				"AED model loaded: %s (%s) on %s",
				_checkpoint_meta["checkpoint_file"],
				_checkpoint_meta["model_version"],
				_device,
			)
		except Exception as exc:
			logger.exception("Failed to load AED checkpoint %s", checkpoint_path)
			_model_status = f"aed_load_failed: {exc}"
	return _model_status


def get_model_info() -> Dict[str, Any]:
	"""Checkpoint provenance for the model card. Loads the model if needed."""
	status = _ensure_model()
	return {"model_status": status, **_checkpoint_meta}


@dataclass
class AEDGateResult:
	"""Same field names the old BirdcallGateResult exposed, plus AED specifics.

	`is_birdcall` is kept as the decision field the workflow branches on, but
	with the new model it means "is meaningful audio" — see `label`.
	"""
	source_file: str
	trigger_time_s: float
	is_birdcall: bool
	confidence: float
	inference_ms: float
	label: str = "meaningful_audio"
	model_status: str = "aed_tinycnn"
	raw: Optional[Dict[str, Any]] = field(default=None)

	def to_dict(self) -> Dict[str, Any]:
		return asdict(self)


class AEDMeaningfulGate:
	"""Stage-2 gate: meaningful vs not-meaningful audio via the AED TinyCNN."""

	def __init__(self, weights_path: Optional[str] = None, threshold: float = 0.5) -> None:
		# weights_path is accepted for signature compatibility with the old
		# gate; the AED checkpoint is resolved by inference.resolve_checkpoint_path
		# (AED_MODEL_PATH env var / bundled models dir). An explicit legacy
		# weights_path is ignored deliberately — old checkpoints do not fit
		# this architecture.
		self.threshold = float(threshold)
		self.model_status = _ensure_model()

	def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> AEDGateResult:
		self.model_status = _ensure_model()

		if _model is None:
			# Degrade to pass-through so the pipeline still completes; the
			# status string tells the stats layer nothing was actually scored.
			return AEDGateResult(
				source_file=source_file,
				trigger_time_s=float(trigger_time_s),
				is_birdcall=True,
				confidence=0.0,
				inference_ms=0.0,
				label="unscored_candidate",
				model_status=self.model_status,
				raw={"reason": "aed_model_unavailable"},
			)

		t0 = time.perf_counter()
		try:
			mel = aed_inference.clip_to_mel(clip, sr)
			mel_tensor = torch.from_numpy(mel).unsqueeze(0).unsqueeze(0)  # (1, 1, N_MELS, frames)
			not_meaningful_prob = float(aed_inference.predict(_model, mel_tensor, _device)[0])
		except Exception as exc:
			logger.exception("AED inference failed on clip at %.2fs of %s", trigger_time_s, source_file)
			return AEDGateResult(
				source_file=source_file,
				trigger_time_s=float(trigger_time_s),
				is_birdcall=False,
				confidence=0.0,
				inference_ms=float((time.perf_counter() - t0) * 1000.0),
				label="inference_error",
				model_status=f"aed_inference_error: {exc}",
				raw={"error": str(exc)},
			)
		inference_ms = (time.perf_counter() - t0) * 1000.0

		# Meaningful confidence: higher = more interesting (continuous with the
		# old gate's convention). Decision: confidence >= threshold.
		confidence = 1.0 - not_meaningful_prob
		is_meaningful = confidence >= self.threshold

		return AEDGateResult(
			source_file=source_file,
			trigger_time_s=float(trigger_time_s),
			is_birdcall=bool(is_meaningful),
			confidence=float(confidence),
			inference_ms=float(inference_ms),
			label="meaningful_audio" if is_meaningful else "not_meaningful",
			model_status="aed_tinycnn",
			raw={
				"not_meaningful_prob": float(not_meaningful_prob),
				"threshold": self.threshold,
				"model_version": _checkpoint_meta.get("model_version"),
				"checkpoint_file": _checkpoint_meta.get("checkpoint_file"),
			},
		)
