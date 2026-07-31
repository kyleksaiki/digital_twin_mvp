"""Adapter between Digital Twin run data and the vendored single-node battery simulator.

All translation between Digital Twin concepts (shamanConfig from Configure Run,
AIEventRow detection timelines, NodeAudioRow uploads) and the simulator's payload
keys lives here, so `single_node_simulator.py` stays byte-comparable with the
upstream battery-simulator repo (modulo the two marked local modifications).

Public API:
    run_battery_simulation_for_run(db, run_id, shaman_config) -> Optional[dict]

The caller owns the commit. A failure here must never fail the run — callers
wrap this in try/except and roll back.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db_models import AIEventRow, BatterySimResultRow, NetworkNodeRow, NodeAudioRow, RunRow
from app.services.battery_sim.single_node_simulator import NodeConfig, run_from_dict

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[4]

# Configure Run component key -> simulator NodeConfig field.
# The other four components (receive, cameraImage, cameraSleep, micSleep) are
# recorded with the run but are not modeled by the single-node simulator.
COMPONENT_TO_SIM_FIELD = {
    "micListen": "P_mic",
    "sleep": "P_proc_lp",
    "working": "P_proc_hp",
    "transmit": "P_tx",
}

# AIEventRow.event_type stores display labels (see _event_label in
# services/audio_processing.py), not raw workflow event types:
#   birdnet_skipped            -> "Bird"           (stage-2 skipped: no transmit)
#   human_presence_confirmed   -> "Human Presence" (confirmed: transmit)
#   bird_confirmed             -> species name     (confirmed: transmit;
#                                 only emitted when a species is present)
# So "Bird" is exactly the unconfirmed case and everything else is confirmed.
UNCONFIRMED_LABELS = {"Bird"}


def _resolve_component_watts(cvp: Any, default_watts: float) -> float:
    """Power resolution rule for one Configure Run component.

    If `power` is present and > 0, use it directly as watts.
    Else if both `current` (mA) and `voltage` (V) are present, W = V * mA / 1000.
    Otherwise fall back to the simulator's NodeConfig default.
    Never returns None.
    """
    if not isinstance(cvp, dict):
        return default_watts
    try:
        power = cvp.get("power")
        if power is not None and float(power) > 0:
            return float(power)
        current = cvp.get("current")
        voltage = cvp.get("voltage")
        if current is not None and voltage is not None:
            watts = float(voltage) * float(current) / 1000.0
            if watts > 0:
                return watts
    except (TypeError, ValueError):
        pass
    return default_watts


def build_node_payload(shaman_config: Dict[str, Any]) -> Dict[str, float]:
    """Map shamanConfig (batteryLife, components, timing) to NodeConfig fields."""
    defaults = NodeConfig()
    components = shaman_config.get("components") or {}
    timing = shaman_config.get("timing") or {}

    payload: Dict[str, float] = {}

    battery_wh = shaman_config.get("batteryLife")
    try:
        battery_wh = float(battery_wh)
    except (TypeError, ValueError):
        battery_wh = None
    payload["battery_wh"] = battery_wh if battery_wh and battery_wh > 0 else defaults.battery_wh

    for component_key, sim_field in COMPONENT_TO_SIM_FIELD.items():
        default = getattr(defaults, sim_field)
        payload[sim_field] = _resolve_component_watts(components.get(component_key), default)

    for timing_key in ("t_proc", "t_tx"):
        value = timing.get(timing_key)
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = None
        payload[timing_key] = value if value is not None and value >= 0 else getattr(defaults, timing_key)

    return payload


def _parse_dropdown_hours(duration: Optional[str], default: float = 24.0) -> float:
    match = re.search(r"(\d+(?:\.\d+)?)", str(duration or ""))
    if not match:
        return default
    return max(float(match.group(1)), 1.0 / 60.0)


def _audio_duration_seconds(path: Path) -> Optional[float]:
    """Read the audio duration from the file header without decoding the clip."""
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


def _resolve_duration(db: Session, run: RunRow) -> Tuple[float, str]:
    """Return (duration_seconds, source) where source is 'audio' or 'dropdown'."""
    audio_rows: List[NodeAudioRow] = (
        db.query(NodeAudioRow).filter(NodeAudioRow.run_id == run.id).all()
    )
    longest: Optional[float] = None
    for row in audio_rows:
        path = Path(row.audio_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            continue
        seconds = _audio_duration_seconds(path)
        if seconds and seconds > 0 and (longest is None or seconds > longest):
            longest = seconds
    if longest is not None:
        return longest, "audio"
    return _parse_dropdown_hours(run.duration) * 3600.0, "dropdown"


def _pick_shaman_node(db: Session, run_id: int, event_node_ids: List[str]) -> Optional[NetworkNodeRow]:
    nodes: List[NetworkNodeRow] = (
        db.query(NetworkNodeRow).filter(NetworkNodeRow.run_id == run_id).all()
    )
    if not nodes:
        return None
    by_id = {node.node_id: node for node in nodes}
    for node_id in event_node_ids:
        if node_id in by_id:
            return by_id[node_id]
    for node in nodes:
        if node.node_id == "SHAMAN":
            return node
    for node in nodes:
        if node.role == "sensor":
            return node
    return nodes[0]


def run_battery_simulation_for_run(
    db: Session,
    run_id: int,
    shaman_config: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Run the single-node battery simulation for a run and persist the result.

    Reads the run's AIEventRow detection timeline and uploaded audio duration,
    runs the vendored simulator, writes one BatterySimResultRow (replacing any
    previous one for the run), back-fills AIEventRow.energy_mj, and mirrors
    rounded battery/drain onto the Shaman NetworkNodeRow for legacy consumers.

    Does not commit — the caller owns the transaction.
    Returns the simulator result dict, or None if the run does not exist.
    """
    shaman_config = shaman_config or {}

    run = db.query(RunRow).filter(RunRow.id == run_id).first()
    if not run:
        logger.warning("Battery simulation skipped: run %s not found", run_id)
        return None

    node_payload = build_node_payload(shaman_config)
    duration_seconds, duration_source = _resolve_duration(db, run)
    duration_hours = duration_seconds / 3600.0

    # Chart resolution: ~200 samples across the run, never finer than 60 s.
    # Total energy is unaffected by step size (accumulation is linear).
    time_step_seconds = max(60.0, duration_seconds / 200.0)

    event_rows: List[AIEventRow] = (
        db.query(AIEventRow)
        .filter(AIEventRow.run_id == run_id)
        .order_by(AIEventRow.timestamp_ms)
        .all()
    )
    events = [
        {
            "time": row.timestamp_ms / 1000.0,
            "event_type": row.event_type,
            "confirmed": row.event_type not in UNCONFIRMED_LABELS,
        }
        for row in event_rows
    ]

    result = run_from_dict(
        {
            "node": node_payload,
            "duration_hours": duration_hours,
            "time_step_seconds": time_step_seconds,
            "events": events,
        }
    )
    summary = result["summary"]

    # Back-fill per-detection burst energy (mJ) on the AI event rows.
    proc_mj = node_payload["P_proc_hp"] * node_payload["t_proc"] * 1000.0
    tx_mj = node_payload["P_tx"] * node_payload["t_tx"] * 1000.0
    for row in event_rows:
        confirmed = row.event_type not in UNCONFIRMED_LABELS
        row.energy_mj = proc_mj + (tx_mj if confirmed else 0.0)

    final_percent = float(summary.get("final_battery_percent") or 0.0)
    avg_drain = (100.0 - final_percent) / duration_hours if duration_hours > 0 else 0.0

    # Replace any previous result for this run (re-processing is idempotent).
    db.query(BatterySimResultRow).filter(BatterySimResultRow.run_id == run_id).delete()

    node_row = _pick_shaman_node(db, run_id, [row.node_id for row in event_rows])
    db.add(
        BatterySimResultRow(
            run_id=run_id,
            node_id=node_row.node_id if node_row else "SHAMAN",
            battery_wh=float(summary.get("battery_wh") or 0.0),
            energy_consumed_wh=float(summary.get("energy_consumed_wh") or 0.0),
            energy_remaining_wh=float(summary.get("energy_remaining_wh") or 0.0),
            final_battery_percent=final_percent,
            average_power_w=float(summary.get("average_power_w") or 0.0),
            avg_drain_percent_per_hour=avg_drain,
            projected_total_life_hours=summary.get("projected_total_life_hours"),
            duration_hours=duration_hours,
            duration_source=duration_source,
            total_detections=int(summary.get("total_detections") or 0),
            alive=bool(summary.get("alive", True)),
            series_json=json.dumps(result["battery_over_time"]),
            breakdown_json=json.dumps(result["component_energy_breakdown"]),
        )
    )

    # Mirror rounded values into the legacy Integer/Float columns so existing
    # consumers (netmap, dashboards) keep working. The new table is the source
    # of truth for the Battery Statistics page.
    if node_row:
        node_row.battery = int(round(final_percent))
        node_row.drain = round(avg_drain, 4)

    db.flush()
    logger.info(
        "Battery simulation stored for run %s: %.2f%% after %.2f h (%s duration, %d detections)",
        run_id,
        final_percent,
        duration_hours,
        duration_source,
        len(events),
    )
    return result


__all__ = ["run_battery_simulation_for_run", "build_node_payload"]
