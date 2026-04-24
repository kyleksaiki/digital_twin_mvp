"""
AI event log loader.

Reads the AI pipeline's event-timeline JSON and converts each entry into a
`SimEvent` that the battery simulator can consume.

Expected input shape (one JSON file, a list of entries):

    [
      {
        "event_type":      "bird_confirmed",       # or e.g. "gunshot_candidate"
        "source_file":     "node_001_....wav",     # which audio clip it came from
        "trigger_time_s":  198.3,                  # seconds into the clip
        "clip_start_s":    196.8,
        "clip_end_s":      199.8,
        "shaman_ii": {
            "inference_ms": 135.99,                # Stage-2 model duration
            "confidence":   0.997
        }
      },
      ...
    ]

To turn a `source_file` into a topology node_id (e.g. "S1"), the caller
passes a `node_id_map` like `{"node_001": "S1", "node_002": "S2", ...}`.
The helper `infer_node_map_from_media_files` builds that map from the
Create-Run UI's mediaFiles payload.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from .events import SimEvent, EventTimeline


# Extract "node_001" (or similar) from a filename like
# "node_001_12hr_20260407_152944.wav". Falls back to the whole stem.
_NODE_RE = re.compile(r"(node[_\-]?\d+)", re.IGNORECASE)


def _extract_filename_key(source_file: str) -> str:
    """Return a stable key we can map to a node_id.

    Priority: "node_XXX" substring → full filename stem → raw string.
    """
    if not source_file:
        return ""
    m = _NODE_RE.search(source_file)
    if m:
        return m.group(1).lower().replace("-", "_")
    return Path(source_file).stem


def _is_confirmed(event_type: str) -> bool:
    return event_type.lower().endswith("_confirmed")


def load_ai_events(
    path: Union[str, Path],
    node_id_map: Dict[str, str],
    duration_hours: Optional[float] = None,
) -> EventTimeline:
    """Load an AI event timeline JSON → `EventTimeline`.

    Args:
      path: path to the event timeline JSON (a list of event entries).
      node_id_map: maps a filename key → topology node_id.
                   Keys can be either:
                     - "node_001"  (extracted token — preferred)
                     - full filename stem or basename
                     - or a raw substring that will be matched loosely.
                   Example: {"node_001": "S1", "node_002": "S2"}
      duration_hours: override the simulated duration; if None, we derive
                      it from the latest event timestamp (+10% buffer).

    Returns: EventTimeline with all events mapped to topology node_ids.
             Events whose source_file doesn't match any known node are
             silently dropped. For diagnostics on dropped events, call
             `load_ai_events_with_stats` instead.
    """
    return load_ai_events_with_stats(path, node_id_map, duration_hours)[0]


def load_ai_events_with_stats(
    path: Union[str, Path],
    node_id_map: Dict[str, str],
    duration_hours: Optional[float] = None,
):
    """Same as `load_ai_events` but also returns a diagnostic dict
    reporting how many entries were parsed, how many mapped to nodes,
    how many were confirmed vs. candidate, and which source_files failed
    to match any node in the provided map.
    """
    with open(path, "r") as f:
        raw = json.load(f)

    if not isinstance(raw, list):
        raise ValueError(
            f"Expected AI event timeline to be a JSON list; got {type(raw).__name__}")

    normalized_map = {k.lower().strip(): v for k, v in node_id_map.items()}

    events: List[SimEvent] = []
    unmatched_files: Dict[str, int] = {}
    max_ts = 0.0

    for entry in raw:
        source = entry.get("source_file", "")
        key = _extract_filename_key(source)

        node_id = normalized_map.get(key)
        if node_id is None:
            for mk, mv in normalized_map.items():
                if mk and mk in source.lower():
                    node_id = mv
                    break

        if node_id is None:
            unmatched_files[source] = unmatched_files.get(source, 0) + 1
            continue

        ts = float(entry.get("trigger_time_s", 0.0))
        max_ts = max(max_ts, ts)

        clip_start = float(entry.get("clip_start_s", ts))
        clip_end   = float(entry.get("clip_end_s",   ts))
        clip_dur   = max(0.0, clip_end - clip_start)

        sh2 = entry.get("shaman_ii") or {}
        inference_ms = float(sh2.get("inference_ms", 30.0))
        confidence = float(sh2.get("confidence") or 0.0)

        events.append(SimEvent(
            node_id           = node_id,
            timestamp_s       = ts,
            event_type        = entry.get("event_type", "unknown"),
            confirmed         = _is_confirmed(entry.get("event_type", "")),
            confidence        = confidence,
            stage1_duration_s = 0.0,
            stage2_duration_s = inference_ms / 1000.0,
            clip_duration_s   = clip_dur or 3.0,
        ))

    if duration_hours is None:
        duration_seconds = max(max_ts * 1.1, 60.0)
    else:
        duration_seconds = duration_hours * 3600.0

    timeline = EventTimeline(events=events, duration_seconds=duration_seconds)

    stats = {
        "total_entries":       len(raw),
        "mapped_events":       len(events),
        "confirmed_events":    timeline.confirmed_count(),
        "candidate_events":    timeline.candidate_count(),
        "unmatched_files":     unmatched_files,
        "derived_duration_s":  duration_seconds,
    }
    return timeline, stats


def infer_node_map_from_media_files(media_files: Dict[str, str]) -> Dict[str, str]:
    """Derive a filename→node_id map from the GUI's `mediaFiles` payload.

    The UI stores `{node_id: filename}`; we invert it and extract the
    `node_XXX` token for robust matching.

    Example:
      mediaFiles = {"S1": "node_001_12hr_...wav", "S2": "node_002_..wav"}
      returns     {"node_001": "S1", "node_002": "S2"}
    """
    result: Dict[str, str] = {}
    for node_id, filename in (media_files or {}).items():
        if not filename:
            continue
        key = _extract_filename_key(filename)
        if key:
            result[key] = node_id
        stem = Path(filename).stem.lower()
        result.setdefault(stem, node_id)
    return result
