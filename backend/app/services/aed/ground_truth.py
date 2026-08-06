"""Ground-truth evaluation — real accuracy measured on the run's own audio.

The audio generator writes a `_log.json` next to each file listing every
inserted event with its timestamp and duration. When the user supplies that
log, we can compute genuinely measured detection performance for this run
instead of falling back to the model's held-out validation figures.

Matching rule
-------------
A ground-truth event occupies [start, start + duration]. A detection is
recorded at the trigger time (the centre of a 3 s clip), so a detection is
counted as hitting an event when it lands inside that window widened by
HALF_CLIP_S on both sides.

  event recall     = ground-truth events with >= 1 detection / all events
  detection precision = detections landing inside some event / all detections

Both are reported because they answer different questions: recall is "did we
miss poaching activity", precision is "how much of what we flagged was real".
Duplicate detections on one long event are counted once for recall and are
reported separately as detections_per_event — a 45 s macaw call legitimately
produces several 3 s detections, which is why the raw detection count exceeds
the event count and is not an error.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

HALF_CLIP_S = 1.5

# Generator event types -> how the pipeline can label them today. The AED gate
# detects "meaningful audio" and does not separate species from gunshots, so
# both ground-truth types map onto the same detection class; we report recall
# per type so the split is still visible.
TYPE_LABELS = {"BIRD": "Bird calls", "GUNSHOT": "Gunshots"}


def parse_ground_truth(payload: Any) -> Optional[Dict[str, Any]]:
	"""Normalize a generator log into {events, duration_seconds, source}.

	Accepts the full log dict, or a bare list of events. Returns None when the
	payload has no usable events, so callers can simply skip evaluation.
	"""
	if not payload:
		return None

	events_raw: Any = None
	metadata: Dict[str, Any] = {}
	if isinstance(payload, dict):
		events_raw = payload.get("events")
		metadata = payload.get("metadata") or {}
	elif isinstance(payload, list):
		events_raw = payload
	if not isinstance(events_raw, list) or not events_raw:
		return None

	events: List[Dict[str, Any]] = []
	for item in events_raw:
		if not isinstance(item, dict):
			continue
		try:
			start = float(item.get("timestamp_seconds"))
		except (TypeError, ValueError):
			continue
		try:
			duration = float(item.get("duration_seconds") or 0.0)
		except (TypeError, ValueError):
			duration = 0.0
		events.append(
			{
				"start": start,
				"end": start + max(0.0, duration),
				"type": str(item.get("type") or "EVENT").upper(),
				"category": str(item.get("category") or "Unknown"),
			}
		)

	if not events:
		return None

	events.sort(key=lambda e: e["start"])
	duration_seconds = 0.0
	try:
		duration_seconds = float(metadata.get("duration_seconds") or 0.0)
	except (TypeError, ValueError):
		duration_seconds = 0.0
	if duration_seconds <= 0:
		duration_seconds = max(e["end"] for e in events)

	return {
		"events": events,
		"duration_seconds": duration_seconds,
		"node_id": str(metadata.get("node_id") or ""),
		"mode": str(metadata.get("mode") or ""),
	}


def _hits(detection_s: float, event: Dict[str, Any]) -> bool:
	return (event["start"] - HALF_CLIP_S) <= detection_s <= (event["end"] + HALF_CLIP_S)


def evaluate(ground_truth: Dict[str, Any], detection_times_s: List[float]) -> Dict[str, Any]:
	"""Compare detection times against ground-truth events. All values measured."""
	events = ground_truth["events"]
	detections = sorted(float(t) for t in detection_times_s)

	matched_events = 0
	matched_detection_idx = set()
	per_type: Dict[str, Dict[str, int]] = {}
	per_event_counts: List[int] = []

	for event in events:
		bucket = per_type.setdefault(event["type"], {"total": 0, "matched": 0})
		bucket["total"] += 1

		hit_count = 0
		for index, detection in enumerate(detections):
			if detection < event["start"] - HALF_CLIP_S:
				continue
			if detection > event["end"] + HALF_CLIP_S:
				break
			hit_count += 1
			matched_detection_idx.add(index)

		per_event_counts.append(hit_count)
		if hit_count:
			matched_events += 1
			bucket["matched"] += 1

	total_events = len(events)
	total_detections = len(detections)
	true_positives = len(matched_detection_idx)

	recall = (matched_events / total_events) if total_events else 0.0
	precision = (true_positives / total_detections) if total_detections else 0.0
	f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

	matched_counts = [c for c in per_event_counts if c > 0]
	detections_per_event = (sum(matched_counts) / len(matched_counts)) if matched_counts else 0.0

	return {
		"available": True,
		"total_events": total_events,
		"total_detections": total_detections,
		"matched_events": matched_events,
		"missed_events": total_events - matched_events,
		"true_positive_detections": true_positives,
		"false_positive_detections": total_detections - true_positives,
		"recall": recall,
		"precision": precision,
		"f1": f1,
		"detections_per_event": detections_per_event,
		"by_type": [
			{
				"label": TYPE_LABELS.get(key, key.title()),
				"total": value["total"],
				"matched": value["matched"],
				"recall": (value["matched"] / value["total"]) if value["total"] else 0.0,
			}
			for key, value in sorted(per_type.items(), key=lambda kv: -kv[1]["total"])
		],
	}


def evaluate_run(ground_truth_payload: Any, detection_times_s: List[float]) -> Optional[Dict[str, Any]]:
	"""Parse + evaluate in one step. Returns None when no usable ground truth."""
	parsed = parse_ground_truth(ground_truth_payload)
	if not parsed:
		return None
	try:
		return evaluate(parsed, detection_times_s)
	except Exception:
		logger.exception("Ground-truth evaluation failed")
		return None