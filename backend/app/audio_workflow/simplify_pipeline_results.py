from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _format_hms(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - 3600 * h - 60 * m
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _read_json(path: Path) -> Optional[Any]:
    if not path.exists():
        return None
    with open(path, "r") as f:
        return json.load(f)


def _presence_detected(event: Dict[str, Any]) -> bool:
    if event.get("event_type") == "human_presence_confirmed":
        return True
    shaman_ii = event.get("shaman_ii") or {}
    return bool(shaman_ii.get("is_human_presence"))


def _presence_confidence(event: Dict[str, Any]) -> float:
    shaman_ii = event.get("shaman_ii") or {}
    try:
        return float(shaman_ii.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _event_time_s(event: Dict[str, Any]) -> float:
    try:
        return float(event.get("trigger_time_s", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _event_time_formatted(event: Dict[str, Any]) -> str:
    return str(event.get("trigger_time_formatted") or _format_hms(_event_time_s(event)))


def _statement(event: Dict[str, Any]) -> str:
    time_text = _event_time_formatted(event)
    if _presence_detected(event):
        return f"Human presence detected at time {time_text}."
    return f"No human presence detected at time {time_text}."


def load_human_presence_events(source_dir: Path) -> List[Dict[str, Any]]:
    stage_file = source_dir / "stage_4_human_presence_timeline.json"
    stage_events = _read_json(stage_file)
    if isinstance(stage_events, list):
        return [item for item in stage_events if isinstance(item, dict)]

    payload = _read_json(source_dir / "backend_payload.json")
    if isinstance(payload, dict):
        stage_timelines = payload.get("stage_timelines") or {}
        events = stage_timelines.get("stage_4_human_presence")
        if isinstance(events, list):
            return [item for item in events if isinstance(item, dict)]
    return []


def load_node_context(source_dir: Path) -> Dict[str, str]:
    payload = _read_json(source_dir / "backend_payload.json")
    if isinstance(payload, dict):
        return {
            "node_id": str(payload.get("node_id") or source_dir.name),
            "audio_path": str(payload.get("audio_path") or ""),
        }
    return {"node_id": source_dir.name, "audio_path": ""}


def build_simplified_payload(source_dir: Path) -> Dict[str, Any]:
    context = load_node_context(source_dir)
    events = sorted(load_human_presence_events(source_dir), key=_event_time_s)
    results = [
        {
            "node_id": context["node_id"],
            "time_s": _event_time_s(event),
            "time_formatted": _event_time_formatted(event),
            "human_presence_detected": _presence_detected(event),
            "confidence": _presence_confidence(event),
            "statement": _statement(event),
        }
        for event in events
    ]

    if results:
        statements = [item["statement"] for item in results]
        status = "ok"
    else:
        statements = ["Human presence was not evaluated in this output folder."]
        status = "human_presence_not_evaluated"

    return {
        "node_id": context["node_id"],
        "audio_path": context["audio_path"],
        "source_dir": str(source_dir),
        "result_type": "human_presence_final_results",
        "status": status,
        "results": results,
        "statements": statements,
    }


def write_simplified_results(source_dir: Path, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    target_dir = out_dir or (source_dir / "simplified_results")
    target_dir.mkdir(parents=True, exist_ok=True)
    payload = build_simplified_payload(source_dir)

    with open(target_dir / "final_human_presence_results.json", "w") as f:
        json.dump(payload, f, indent=2)
    (target_dir / "final_human_presence_results.txt").write_text(
        "\n".join(payload["statements"]) + "\n",
        encoding="utf-8",
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Write simplified final human-presence results for a pipeline output folder.")
    parser.add_argument("source_dir", help="Pipeline output directory containing backend_payload.json or stage_4_human_presence_timeline.json.")
    parser.add_argument("--out_dir", help="Optional output directory. Defaults to SOURCE_DIR/simplified_results.")
    args = parser.parse_args()

    payload = write_simplified_results(
        source_dir=Path(args.source_dir),
        out_dir=Path(args.out_dir) if args.out_dir else None,
    )
    print(json.dumps({"status": payload["status"], "statements": payload["statements"]}, indent=2))


if __name__ == "__main__":
    main()
