"""Audio processing services for the staged workflow."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.db_models import AIEventRow, DetectionByTypeRow, NetworkNodeRow, NodeEventRow, RunMetricsRow, RunRow
from app.utils.paths import get_base_path, get_user_data_path, is_frozen


logger = logging.getLogger(__name__)
# DATA_ROOT mirrors the upload route: where saved audio + generated
# output actually live on disk. Under a frozen build this is the
# per-user app-data folder so paths round-trip across launches.
PROJECT_ROOT = get_user_data_path() if is_frozen() else get_base_path()

try:
	from app.audio_workflow.node_audio_workflow import run_node_audio_workflow
except Exception as exc:
	logger.exception("Failed to import node audio workflow: %s", exc)
	run_node_audio_workflow = None

try:
	from app.services.aed import stage_stats as aed_stage_stats
	from app.services.aed.gate import get_model_info as aed_get_model_info
except Exception as exc:
	logger.exception("Failed to import AED stage stats: %s", exc)
	aed_stage_stats = None
	aed_get_model_info = None


def _resolve_path(path: str) -> Path:
	path_obj = Path(path)
	if not path_obj.is_absolute():
		path_obj = PROJECT_ROOT / path_obj
	return path_obj


def _validate_local_path(path: Optional[str], label: str) -> None:
	if not path:
		return
	resolved = _resolve_path(path)
	if not resolved.exists():
		raise HTTPException(status_code=400, detail=f"{label} does not exist: {path}")


def _confidence_from_event(event: Dict[str, Any]) -> float:
	shaman_ii = event.get("shaman_ii") or {}
	shaman_i = event.get("shaman_i") or {}
	try:
		value = shaman_ii.get("confidence")
		if value is None:
			value = shaman_i.get("confidence", 0.0)
		return float(value or 0.0)
	except (TypeError, ValueError):
		return 0.0


def _latency_from_event(event: Dict[str, Any]) -> int:
	shaman_ii = event.get("shaman_ii") or {}
	shaman_i = event.get("shaman_i") or {}
	try:
		value = shaman_ii.get("inference_ms")
		if value is None:
			value = shaman_i.get("inference_ms", 0.0)
		return int(round(float(value or 0.0)))
	except (TypeError, ValueError):
		return 0


def _event_label(event: Dict[str, Any]) -> str:
	event_type = str(event.get("event_type", "ai_event"))
	shaman_ii = event.get("shaman_ii") or {}
	species = shaman_ii.get("species")
	label = shaman_ii.get("label")

	if event_type == "bird_confirmed":
		return str(species or "Bird")
	if event_type == "human_presence_confirmed":
		return "Human Presence"
	if event_type == "birdnet_skipped":
		# With the AED gate, a stage-2-confirmed event that is not human presence
		# is "meaningful audio" (bird, insect, other animal) — not provably a bird.
		return "Wildlife"
	return str(label or event_type).replace("_", " ").title()


def _is_dashboard_event(event: Dict[str, Any]) -> bool:
	return str(event.get("event_type")) in {
		"bird_confirmed",
		"birdnet_skipped",
		"human_presence_confirmed",
	}


def _persist_workflow_result(db: Session, db_run_id: int, node_id: str, payload: Dict[str, Any]) -> None:
	run = db.query(RunRow).filter(RunRow.id == db_run_id).first()
	if not run:
		raise HTTPException(status_code=404, detail=f"Run not found: {db_run_id}")

	combined = payload.get("combined_timeline") or []
	dashboard_events = [event for event in combined if _is_dashboard_event(event)]

	db.query(AIEventRow).filter(
		AIEventRow.run_id == db_run_id,
		AIEventRow.node_id == node_id,
	).delete()
	db.query(NodeEventRow).filter(
		NodeEventRow.run_id == db_run_id,
		NodeEventRow.node_id == node_id,
	).delete()

	counts: Dict[str, int] = {}
	total_latency = 0
	for event in dashboard_events:
		label = _event_label(event)
		confidence = _confidence_from_event(event)
		latency_ms = _latency_from_event(event)
		total_latency += latency_ms
		counts[label] = counts.get(label, 0) + 1
		timestamp_ms = int(round(float(event.get("trigger_time_s", 0.0)) * 1000.0))

		db.add(
			AIEventRow(
				run_id=db_run_id,
				node_id=node_id,
				timestamp_ms=timestamp_ms,
				event_type=label,
				confidence=confidence,
				latency_ms=latency_ms,
				energy_mj=0.0,
			)
		)

	for label, count in counts.items():
		db.add(NodeEventRow(run_id=db_run_id, node_id=node_id, event_text=f"{count} {label}"))

	node = db.query(NetworkNodeRow).filter(
		NetworkNodeRow.run_id == db_run_id,
		NetworkNodeRow.node_id == node_id,
	).first()
	if node:
		node.ai_det = len(dashboard_events)

	db.flush()
	db.query(DetectionByTypeRow).filter(DetectionByTypeRow.run_id == db_run_id).delete()
	all_ai_events = db.query(AIEventRow).filter(AIEventRow.run_id == db_run_id).all()
	aggregate_counts: Dict[str, int] = {}
	for event in all_ai_events:
		aggregate_counts[event.event_type] = aggregate_counts.get(event.event_type, 0) + 1
	for label, count in aggregate_counts.items():
		db.add(DetectionByTypeRow(run_id=db_run_id, event_type=label, count=count))

	metrics = db.query(RunMetricsRow).filter(RunMetricsRow.run_id == db_run_id).first()
	if metrics:
		metrics.detection_count = len(all_ai_events)
		if all_ai_events:
			metrics.latency_ms = int(round(sum(e.latency_ms for e in all_ai_events) / len(all_ai_events)))
	elif all_ai_events:
		db.add(
			RunMetricsRow(
				run_id=db_run_id,
				accuracy=0.0,
				fpr=0.0,
				latency_ms=int(round(total_latency / max(1, len(dashboard_events)))),
				detection_count=len(all_ai_events),
				battery_health=0.0,
				congestion=0,
				throughput=0.0,
				conf_threshold=0.0,
			)
		)


def _normalize_audio_inputs(
	audio_path: Optional[str],
	audio_files: Optional[List[str]],
	node_audio_map: Optional[Dict[str, str]],
) -> List[tuple[Optional[str], str]]:
	inputs: List[tuple[Optional[str], str]] = []
	if node_audio_map:
		for node_id, path in node_audio_map.items():
			if path:
				inputs.append((str(node_id), str(path)))
	if not inputs:
		if audio_path:
			inputs.append((None, audio_path))
		if audio_files:
			inputs.extend([(None, item) for item in audio_files if item])
	return inputs


def _audio_node_id(audio_path: str, index: int) -> str:
	stem = Path(audio_path).stem.strip().lower()
	cleaned = "".join(char if char.isalnum() or char == "_" else "_" for char in stem).strip("_")
	return cleaned or f"audio_{index + 1}"


def process_run_audio(
	db: Session,
	run_id: int,
	*,
	audio_path: Optional[str] = None,
	audio_files: Optional[List[str]] = None,
	node_audio_map: Optional[Dict[str, str]] = None,
	out_root: str = "audio_workflow_outputs",
	tinycnn_weights: Optional[str] = None,
	tinycnn_threshold: float = 0.3,
	birdnet_threshold: float = 0.5,
	human_presence_threshold: float = 0.5,
	sr: int = 48000,
	clip_s: float = 3.0,
	block_seconds: float = 60.0,
	skip_birdnet: bool = True,
) -> List[Dict[str, Any]]:
	if not run_node_audio_workflow:
		raise HTTPException(status_code=501, detail="Audio workflow not available. Install node_audio_workflow.")

	run = db.query(RunRow).filter(RunRow.id == run_id).first()
	if not run:
		raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")

	inputs = _normalize_audio_inputs(audio_path, audio_files, node_audio_map)
	if not inputs:
		return []

	_validate_local_path(tinycnn_weights, "TinyCNN weights")
	resolved_weights = _resolve_path(tinycnn_weights) if tinycnn_weights else None

	out_root_path = Path(out_root)
	out_root_path.mkdir(parents=True, exist_ok=True)

	results: List[Dict[str, Any]] = []
	aggregate_stats: Dict[str, Dict[str, Any]] = {}
	aggregate_histogram: Dict[str, Any] = {"bins": [], "scored": 0, "mean_confidence": 0.0}
	total_audio_seconds = 0.0
	total_wall_ms = 0.0
	for index, (explicit_node_id, input_audio) in enumerate(inputs):
		_validate_local_path(input_audio, "Audio path")
		resolved_audio = _resolve_path(input_audio)
		node_id = explicit_node_id or _audio_node_id(str(resolved_audio), index)
		node_out_dir = out_root_path / f"run_{run_id}" / node_id

		wall_start = time.perf_counter()
		try:
			result = run_node_audio_workflow(
				input_audio=str(resolved_audio),
				out_dir=str(node_out_dir),
				node_id=node_id,
				run_id=str(run_id),
				tinycnn_weights=str(resolved_weights) if resolved_weights else None,
				tinycnn_threshold=tinycnn_threshold,
				birdnet_threshold=birdnet_threshold,
				human_presence_threshold=human_presence_threshold,
				sr=sr,
				clip_s=clip_s,
				block_seconds=block_seconds,
				skip_birdnet=skip_birdnet,
			)
		except RuntimeError as exc:
			raise HTTPException(status_code=500, detail=str(exc)) from exc
		wall_ms = (time.perf_counter() - wall_start) * 1000.0
		total_wall_ms += wall_ms

		_persist_workflow_result(db, run_id, node_id, result["backend_payload"])

		# Pipeline stage statistics — derived from the real timelines, never assumed.
		if aed_stage_stats is not None:
			try:
				audio_seconds = _audio_duration_seconds(resolved_audio)
				total_audio_seconds += audio_seconds or 0.0
				downstream_ms = _downstream_ms(result["backend_payload"])
				prefilter_ms = max(0.0, wall_ms - downstream_ms)
				node_stats = aed_stage_stats.compute_stage_stats(
					result["backend_payload"], audio_seconds, prefilter_ms=prefilter_ms
				)
				aed_stage_stats.merge_stage_stats(aggregate_stats, node_stats)
				histogram = aed_stage_stats.confidence_histogram(result["backend_payload"])
				_merge_histograms(aggregate_histogram, histogram)
			except Exception:
				logger.exception("Failed to compute pipeline stage stats for run %s node %s", run_id, node_id)
		results.append(
			{
				"node_id": node_id,
				"audio_path": str(resolved_audio),
				"out_dir": str(node_out_dir),
				"summary": result["summary"],
			}
		)

	if aed_stage_stats is not None and aggregate_stats:
		try:
			model_info = aed_get_model_info() if aed_get_model_info else {}
			aed_stage_stats.persist_pipeline_stats(
				db,
				run_id,
				aggregate_stats,
				model_info,
				threshold=tinycnn_threshold,
				audio_seconds=total_audio_seconds,
				wall_ms=total_wall_ms,
				histogram=aggregate_histogram,
			)
		except Exception:
			logger.exception("Failed to persist pipeline stage stats for run %s", run_id)

	return results


def _downstream_ms(payload: Dict[str, Any]) -> float:
	"""Total measured time spent in stages 2-5, used to isolate the stage-1 scan."""
	timelines = payload.get("stage_timelines") or {}
	total = 0.0
	for event in timelines.get("stage_2_tinycnn_birdcall") or []:
		total += float((event.get("shaman_ii") or {}).get("inference_ms") or 0.0)
	for event in timelines.get("stage_4_human_presence") or []:
		total += float((event.get("shaman_ii") or {}).get("inference_ms") or 0.0)
	return total


def _audio_duration_seconds(path: Path) -> Optional[float]:
	"""Read audio duration from the file header without decoding the clip."""
	try:
		import soundfile

		info = soundfile.info(str(path))
		if info.samplerate and info.frames:
			return float(info.frames) / float(info.samplerate)
	except Exception:
		logger.debug("soundfile could not read duration for %s", path, exc_info=True)
	try:
		import librosa

		duration = float(librosa.get_duration(path=str(path)))
		return duration if duration > 0 else None
	except Exception:
		logger.debug("librosa could not read duration for %s", path, exc_info=True)
	return None


def _merge_histograms(aggregate: Dict[str, Any], histogram: Dict[str, Any]) -> None:
	"""Accumulate one node file's confidence histogram into the run aggregate."""
	prev_scored = int(aggregate.get("scored") or 0)
	new_scored = int(histogram.get("scored") or 0)
	if not aggregate.get("bins"):
		aggregate["bins"] = [dict(b) for b in histogram.get("bins") or []]
	else:
		for target, source in zip(aggregate["bins"], histogram.get("bins") or []):
			target["count"] = int(target.get("count") or 0) + int(source.get("count") or 0)
	total = prev_scored + new_scored
	if total > 0:
		aggregate["mean_confidence"] = (
			aggregate.get("mean_confidence", 0.0) * prev_scored
			+ histogram.get("mean_confidence", 0.0) * new_scored
		) / total
	aggregate["scored"] = total


__all__ = ["process_run_audio", "run_node_audio_workflow"]