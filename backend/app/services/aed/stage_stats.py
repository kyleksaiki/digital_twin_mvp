"""Pipeline stage statistics — derived from real workflow output, never assumed.

Maps the backend's stage timelines onto the five UI stages of the Model
Performance dashboard and persists one PipelineStageStatRow per run per stage,
plus one AudioProcessingStatRow per run with model provenance and run-level
processing measurements.

UI-stage <-> backend mapping (documented in AED_INTEGRATION_NOTES.md):
  stage1 Audio Filtering      — prefilter over the whole file: entered = 3 s
	  windows in the audio, passed = deduplicated triggers, failed = windows
	  discarded as background.
  stage2 AED Event Detection  — the AED TinyCNN: entered = triggers scored,
	  passed = meaningful, failed = not meaningful.
  stage3 Feature Extraction   — audio feature rows built for confirmed clips
	  (timed inside HumanPresenceAdapter.confirm).
  stage4 Context Enrichment   — node/time/context features merged per event.
  stage5 Human Presence Classification — proxy classifier decision: passed =
	  human presence confirmed, failed = classified wildlife-only.

Every count below is computed from actual TimelineEvent dicts in the payload.
A stage that did not run reports zeros.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.db_models import AudioProcessingStatRow, PipelineStageStatRow, RunMetricsRow

logger = logging.getLogger(__name__)

STAGE_LABELS = {
	"stage1": "Stage 1: Audio Filtering",
	"stage2": "Stage 2: AED Event Detection",
	"stage3": "Stage 3: Feature Extraction",
	"stage4": "Stage 4: Context Enrichment",
	"stage5": "Stage 5: Human Presence Classification",
}

CONFIDENCE_BINS = [(i / 10.0, (i + 1) / 10.0) for i in range(10)]


def _blank_stage() -> Dict[str, Any]:
	return {"entered": 0, "passed": 0, "failed": 0, "total_ms": 0.0, "details": {}}


def _bump(details: Dict[str, int], label: str, count: int = 1) -> None:
	details[label] = details.get(label, 0) + count


def compute_stage_stats(
	payload: Dict[str, Any],
	audio_seconds: Optional[float],
	prefilter_ms: float = 0.0,
) -> Dict[str, Dict[str, Any]]:
	"""Derive the five UI stages' stats from one node's workflow payload.

	prefilter_ms is the measured wall time of the stage-1 scan over the whole
	file. It is passed in rather than derived because the prefilter emits
	triggers, not per-window timings.
	"""
	timelines = payload.get("stage_timelines") or {}
	candidates: List[Dict[str, Any]] = timelines.get("stage_1_event_candidates") or []
	gate_events: List[Dict[str, Any]] = timelines.get("stage_2_tinycnn_birdcall") or []
	hp_events: List[Dict[str, Any]] = timelines.get("stage_4_human_presence") or []

	stats = {stage_id: _blank_stage() for stage_id in STAGE_LABELS}

	# --- stage1: Audio Filtering -------------------------------------------
	s1 = stats["stage1"]
	windows = int(audio_seconds // 3.0) if audio_seconds and audio_seconds > 0 else len(candidates)
	windows = max(windows, len(candidates))
	s1["entered"] = windows
	s1["passed"] = len(candidates)
	s1["failed"] = max(0, windows - len(candidates))
	s1["total_ms"] = float(prefilter_ms or 0.0)
	_bump(s1["details"], "Trigger candidates", len(candidates))
	_bump(s1["details"], "Filtered as background", s1["failed"])

	# --- stage2: AED Event Detection ---------------------------------------
	s2 = stats["stage2"]
	for event in gate_events:
		gate = event.get("shaman_ii") or {}
		s2["entered"] += 1
		s2["total_ms"] += float(gate.get("inference_ms") or 0.0)
		status = str(gate.get("model_status") or "")
		if str(event.get("event_type")) == "birdcall_stage2_confirmed":
			s2["passed"] += 1
			label = "Meaningful audio" if status == "aed_tinycnn" else "Unscored (model unavailable)"
			_bump(s2["details"], label)
		else:
			s2["failed"] += 1
			_bump(s2["details"], "Not meaningful")

	# --- stages 3-5 from the human-presence events -------------------------
	s3, s4, s5 = stats["stage3"], stats["stage4"], stats["stage5"]
	for event in hp_events:
		hp = event.get("shaman_ii") or {}
		raw = hp.get("raw") or {}
		features = raw.get("features") or {}
		timing = raw.get("timing_ms") or {}

		s3["entered"] += 1
		s3["total_ms"] += float(timing.get("features") or 0.0)
		if features.get("feature_extraction_error"):
			s3["failed"] += 1
			s3["passed"] -= 0  # keep explicit: an errored row did not pass
			_bump(s3["details"], "Feature extraction error")
		else:
			s3["passed"] += 1
			extracted = sum(
				1 for key, value in features.items()
				if not str(key).startswith("MFCC_") and isinstance(value, (int, float)) and value not in (0.0,)
			)
			_bump(s3["details"], "Audio features extracted" if extracted else "Empty feature row")

		s4["entered"] += 1
		s4["passed"] += 1
		s4["total_ms"] += float(timing.get("context") or 0.0)
		_bump(
			s4["details"],
			"With node metadata" if raw.get("had_node_metadata") else "Time/audio context only",
		)

		s5["entered"] += 1
		s5["total_ms"] += float(timing.get("score") or hp.get("inference_ms") or 0.0)
		if str(event.get("event_type")) == "human_presence_confirmed":
			s5["passed"] += 1
			_bump(s5["details"], "Human Presence")
		else:
			s5["failed"] += 1
			_bump(s5["details"], "Wildlife")

	return stats


def confidence_histogram(payload: Dict[str, Any]) -> Dict[str, Any]:
	"""10-bin histogram of AED meaningful-confidence over all scored clips."""
	gate_events = (payload.get("stage_timelines") or {}).get("stage_2_tinycnn_birdcall") or []
	bins = [0] * len(CONFIDENCE_BINS)
	values: List[float] = []
	for event in gate_events:
		gate = event.get("shaman_ii") or {}
		if str(gate.get("model_status") or "") != "aed_tinycnn":
			continue
		confidence = float(gate.get("confidence") or 0.0)
		values.append(confidence)
		index = min(int(confidence * 10), 9)
		bins[index] += 1
	return {
		"bins": [
			{"label": f"{int(low * 100)}-{int(high * 100)}%", "count": count}
			for (low, high), count in zip(CONFIDENCE_BINS, bins)
		],
		"scored": len(values),
		"mean_confidence": (sum(values) / len(values)) if values else 0.0,
	}


def merge_stage_stats(aggregate: Dict[str, Dict[str, Any]], node_stats: Dict[str, Dict[str, Any]]) -> None:
	"""Accumulate one node's stats into the per-run aggregate (multi-file runs)."""
	for stage_id, stage in node_stats.items():
		target = aggregate.setdefault(stage_id, _blank_stage())
		target["entered"] += stage["entered"]
		target["passed"] += stage["passed"]
		target["failed"] += stage["failed"]
		target["total_ms"] += stage["total_ms"]
		for label, count in stage["details"].items():
			_bump(target["details"], label, count)


def persist_pipeline_stats(
	db: Session,
	run_id: int,
	stage_stats: Dict[str, Dict[str, Any]],
	model_info: Dict[str, Any],
	threshold: float,
	audio_seconds: float,
	wall_ms: float,
	histogram: Dict[str, Any],
	clips_skipped: int = 0,
) -> None:
	"""Replace this run's stage rows and processing row with fresh real values."""
	# SessionLocal runs with autoflush=False: flush first so the RunMetricsRow
	# created moments ago by _persist_workflow_result is visible to our query.
	db.flush()
	db.query(PipelineStageStatRow).filter(PipelineStageStatRow.run_id == run_id).delete()
	db.query(AudioProcessingStatRow).filter(AudioProcessingStatRow.run_id == run_id).delete()

	for stage_id, label in STAGE_LABELS.items():
		stage = stage_stats.get(stage_id) or _blank_stage()
		entered = int(stage["entered"])
		mean_ms = (stage["total_ms"] / entered) if entered else 0.0
		db.add(
			PipelineStageStatRow(
				run_id=run_id,
				stage_id=stage_id,
				stage_label=label,
				entered=entered,
				passed=int(stage["passed"]),
				failed=int(stage["failed"]),
				mean_ms=float(mean_ms),
				total_ms=float(stage["total_ms"]),
				details_json=json.dumps(
					[{"label": k, "count": v} for k, v in sorted(stage["details"].items(), key=lambda kv: -kv[1])]
				),
			)
		)

	clips_scored = int(histogram.get("scored") or 0)
	wall_s = wall_ms / 1000.0 if wall_ms else 0.0
	db.add(
		AudioProcessingStatRow(
			run_id=run_id,
			model_status=str(model_info.get("model_status") or "unknown"),
			checkpoint_file=model_info.get("checkpoint_file"),
			model_version=model_info.get("model_version"),
			threshold=float(threshold),
			device=model_info.get("device"),
			clips_scored=clips_scored,
			clips_skipped=int(clips_skipped),
			mean_confidence=float(histogram.get("mean_confidence") or 0.0),
			confidence_histogram_json=json.dumps(histogram.get("bins") or []),
			audio_seconds=float(audio_seconds or 0.0),
			wall_ms=float(wall_ms or 0.0),
			throughput_cps=(clips_scored / wall_s) if wall_s > 0 else 0.0,
			val_acc=model_info.get("val_acc"),
			val_precision=model_info.get("not_meaningful_precision"),
			val_recall=model_info.get("not_meaningful_recall"),
			val_f1=model_info.get("not_meaningful_f1"),
		)
	)

	# conf_threshold in RunMetricsRow is the confidence threshold actually used
	# for this run — a real value, previously always 0.
	metrics = db.query(RunMetricsRow).filter(RunMetricsRow.run_id == run_id).first()
	if metrics:
		metrics.conf_threshold = float(threshold)

	db.flush()
	logger.info(
		"Pipeline stats stored for run %s: %s clips scored, %.1fs audio, %.0fms wall",
		run_id,
		clips_scored,
		audio_seconds or 0.0,
		wall_ms or 0.0,
	)