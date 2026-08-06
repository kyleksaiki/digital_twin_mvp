from __future__ import annotations

import argparse
import math
import json
import os
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

try:
    from .audio_event_common import (
        BasicBirdPrefilter,
        BirdNETConfirm,
        TimelineEvent,
        extract_centered_clip_from_file,
        format_hms,
        merge_timeline_events,
        stream_prefilter_file,
        write_timeline_json,
    )
    from .tiny_cnn_birdcall import TinyCNNBirdcallGate
    try:
        from app.services.aed.gate import AEDMeaningfulGate
    except Exception:
        AEDMeaningfulGate = None
except ImportError:  # pragma: no cover - supports running as a script
    from audio_event_common import (
        BasicBirdPrefilter,
        BirdNETConfirm,
        TimelineEvent,
        extract_centered_clip_from_file,
        format_hms,
        merge_timeline_events,
        stream_prefilter_file,
        write_timeline_json,
    )
    from tiny_cnn_birdcall import TinyCNNBirdcallGate
    AEDMeaningfulGate = None  # standalone-script mode: app package not importable


@dataclass
class HumanPresenceResult:
    source_file: str
    trigger_time_s: float
    is_human_presence: bool
    confidence: float
    inference_ms: float
    label: str = "human_presence"
    model_status: str = "proxy_feature_scorer"
    raw: Optional[Dict[str, Any]] = None


class HumanPresenceAdapter:
    """Adapter boundary for Griffen's final human-presence model.

    Until the trained artifact is available, this proxy scorer computes a
    model-shaped feature row from audio, BirdNET/TinyCNN output, time, weather,
    and optional human-activity metadata. It is not the final model; it exists
    to exercise the real inference contract and backend output shape.
    """

    sentinel_species_cols = [
        "Myiothlypis fulvicauda_Buff-rumped Warbler",
        "Habia atrimaxillaris_Black-cheeked Ant-Tanager",
        "Thamnophilus bridgesi_Black-hooded Antshrike",
        "Tinamus major_Great Tinamou",
        "Patagioenas nigrirostris_Short-billed Pigeon",
        "Ramphastos ambiguus_Yellow-throated Toucan",
        "Cyanoloxia cyanoides_Blue-black Grosbeak",
        "Lipaugus unirufus_Rufous Piha",
        "Threnetes ruckeri_Band-tailed Barbthroat",
        "Ara macao_Scarlet Macaw",
    ]

    def __init__(self, threshold: float = 0.5) -> None:
        self.threshold = float(threshold)
        self.model_status = "proxy_feature_scorer"
        self._recent_rms: List[float] = []
        self._recent_sentinel_counts: List[int] = []

    def confirm(
        self,
        event: TimelineEvent,
        clip: Optional[np.ndarray] = None,
        sr: Optional[int] = None,
        node_metadata: Optional[Dict[str, Any]] = None,
    ) -> HumanPresenceResult:
        t0 = time.perf_counter()
        metadata = node_metadata or {}
        audio_features = self._extract_audio_features(clip, sr)
        t1 = time.perf_counter()
        context_features = self._build_context_features(event, metadata, audio_features)
        t2 = time.perf_counter()
        feature_row = {**audio_features, **context_features}
        confidence = self._score_proxy(feature_row)
        t3 = time.perf_counter()
        inference_ms = (t3 - t0) * 1000.0

        return HumanPresenceResult(
            source_file=event.source_file,
            trigger_time_s=event.trigger_time_s,
            is_human_presence=bool(confidence >= self.threshold),
            confidence=float(max(0.0, min(1.0, confidence))),
            inference_ms=float(inference_ms),
            raw={
                "reason": "proxy_until_trained_human_presence_model_is_available",
                "threshold": self.threshold,
                "features": feature_row,
                "had_node_metadata": bool(metadata),
                "timing_ms": {
                    "features": (t1 - t0) * 1000.0,
                    "context": (t2 - t1) * 1000.0,
                    "score": (t3 - t2) * 1000.0,
                },
            },
        )

    def _extract_audio_features(self, clip: Optional[np.ndarray], sr: Optional[int]) -> Dict[str, float]:
        if clip is None or sr is None or len(clip) == 0:
            return self._empty_audio_features()

        y = np.asarray(clip, dtype=np.float32)
        if y.ndim > 1:
            y = np.mean(y, axis=1)
        rms_energy = float(np.sqrt(np.mean(np.square(y))) if y.size else 0.0)

        try:
            import librosa

            n_fft = min(2048, max(256, int(2 ** math.ceil(math.log2(max(256, min(len(y), sr // 10)))))))
            hop_length = max(1, n_fft // 4)
            spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length)
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, n_fft=n_fft, hop_length=hop_length)
            features = {
                "Spectral RMS Energy": rms_energy,
                "Zero Crossing Rate": float(np.mean(librosa.feature.zero_crossing_rate(y=y, hop_length=hop_length))),
                "Spectral Bandwidth": float(np.mean(librosa.feature.spectral_bandwidth(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length))),
                "Spectral Rolloff (85%)": float(np.mean(librosa.feature.spectral_rolloff(y=y, sr=sr, n_fft=n_fft, hop_length=hop_length, roll_percent=0.85))),
                "Spectral Flatness": float(np.mean(librosa.feature.spectral_flatness(y=y, n_fft=n_fft, hop_length=hop_length))),
                "Onset Strength": float(np.mean(librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length))),
                "Spectral Contrast": float(np.mean(spectral_contrast)),
            }
            for idx in range(13):
                features[f"MFCC_{idx + 1}"] = float(np.mean(mfcc[idx])) if mfcc.shape[0] > idx else 0.0
            return {k: self._finite_float(v) for k, v in features.items()}
        except Exception as exc:
            features = self._empty_audio_features()
            features["Spectral RMS Energy"] = rms_energy
            features["feature_extraction_error"] = str(exc)
            return features

    def _empty_audio_features(self) -> Dict[str, float]:
        features = {
            "Spectral RMS Energy": 0.0,
            "Zero Crossing Rate": 0.0,
            "Spectral Bandwidth": 0.0,
            "Spectral Rolloff (85%)": 0.0,
            "Spectral Flatness": 0.0,
            "Onset Strength": 0.0,
            "Spectral Contrast": 0.0,
        }
        for idx in range(13):
            features[f"MFCC_{idx + 1}"] = 0.0
        return features

    def _build_context_features(
        self,
        event: TimelineEvent,
        metadata: Dict[str, Any],
        audio_features: Dict[str, float],
    ) -> Dict[str, Any]:
        bird = event.shaman_ii or {}
        species = self._bird_species(bird)
        bird_confidence = self._coerce_float(bird.get("confidence"), 0.0)
        if bird_confidence == 0.0:
            bird_confidence = self._coerce_float((event.shaman_i or {}).get("confidence"), 0.0)

        sentinel_features = {col: int(self._species_matches_sentinel(species, col)) for col in self.sentinel_species_cols}
        sentinel_count = int(sum(sentinel_features.values()))

        hour = self._event_hour(event, metadata)
        rms = self._coerce_float(audio_features.get("Spectral RMS Energy"), 0.0)
        recent_rms_mean = float(np.mean(self._recent_rms[-5:])) if self._recent_rms else rms
        volume_spike = rms - recent_rms_mean
        self._recent_rms.append(rms)

        recent_sentinel_mean = float(np.mean(self._recent_sentinel_counts[-100:])) if self._recent_sentinel_counts else float(sentinel_count)
        eerie_silence = int(sentinel_count == 0 and (recent_sentinel_mean > 0.05 or rms < max(0.005, recent_rms_mean * 0.65)))
        self._recent_sentinel_counts.append(sentinel_count)

        windspeed = self._metadata_float(metadata, ["Windspeed", "windspeed", "wind_speed"], 0.0)
        human_activity_score = self._metadata_float(metadata, ["Human Activity Score", "human_activity_score"], 0.0)
        if human_activity_score > 1.0:
            human_activity_score = human_activity_score / 100.0

        context = {
            "species": species,
            "confidence": bird_confidence,
            "Temperature": self._metadata_float(metadata, ["Temperature", "temperature"], 0.0),
            "Humidity": self._metadata_float(metadata, ["Humidity", "humidity"], 0.0),
            "Windspeed": windspeed,
            "Precipitation": self._metadata_float(metadata, ["Precipitation", "precipitation"], 0.0),
            "Human Activity Score": float(max(0.0, min(1.0, human_activity_score))),
            "hour_sin": math.sin(hour * (2 * math.pi / 24.0)),
            "hour_cos": math.cos(hour * (2 * math.pi / 24.0)),
            "Eerie_Silence": eerie_silence,
            "Volume_Wind_Ratio": rms / (windspeed + 1e-5),
            "Volume_Spike_15s": volume_spike,
            "Sentinel_Count": sentinel_count,
        }
        return {**context, **sentinel_features}

    def _score_proxy(self, features: Dict[str, Any]) -> float:
        human_activity = self._coerce_float(features.get("Human Activity Score"), 0.0)
        rms = self._coerce_float(features.get("Spectral RMS Energy"), 0.0)
        spike = self._coerce_float(features.get("Volume_Spike_15s"), 0.0)
        onset = self._coerce_float(features.get("Onset Strength"), 0.0)
        flatness = self._coerce_float(features.get("Spectral Flatness"), 0.0)
        wind = self._coerce_float(features.get("Windspeed"), 0.0)
        bird_confidence = self._coerce_float(features.get("confidence"), 0.0)
        sentinel_count = self._coerce_float(features.get("Sentinel_Count"), 0.0)
        eerie_silence = self._coerce_float(features.get("Eerie_Silence"), 0.0)

        rms_signal = min(1.0, math.log1p(max(0.0, rms) * 120.0) / math.log1p(120.0))
        spike_signal = min(1.0, max(0.0, spike) * 80.0)
        onset_signal = min(1.0, max(0.0, onset) / 8.0)
        flatness_signal = min(1.0, max(0.0, flatness) * 4.0)
        wind_penalty = min(0.5, max(0.0, wind - 4.0) / 18.0)

        linear = -2.2
        linear += 3.2 * human_activity
        linear += 0.75 * rms_signal
        linear += 0.95 * spike_signal
        linear += 0.45 * onset_signal
        linear += 0.35 * flatness_signal
        linear += 0.25 * bird_confidence
        linear += 0.35 * min(1.0, sentinel_count)
        linear += 0.65 * eerie_silence
        linear -= wind_penalty
        return 1.0 / (1.0 + math.exp(-linear))

    def _event_hour(self, event: TimelineEvent, metadata: Dict[str, Any]) -> float:
        explicit_hour = self._metadata_float(metadata, ["Datetime_hour", "hour", "local_hour"], None)
        if explicit_hour is not None:
            return float(explicit_hour) % 24.0

        timestamp = self._metadata_value(metadata, ["audio_start_timestamp", "Timestamp Local", "Datetime", "Timestamp UTC"])
        if timestamp:
            try:
                dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                dt = dt + timedelta(seconds=float(event.trigger_time_s))
                return float(dt.hour) + float(dt.minute) / 60.0
            except ValueError:
                pass
        return (float(event.trigger_time_s) / 3600.0) % 24.0

    def _bird_species(self, bird_payload: Dict[str, Any]) -> str:
        raw = bird_payload.get("raw") if isinstance(bird_payload.get("raw"), dict) else {}
        for key in ("species", "scientific_name", "common_name", "label"):
            value = bird_payload.get(key) or raw.get(key)
            if value:
                return str(value)
        return ""

    def _species_matches_sentinel(self, species: str, sentinel_col: str) -> bool:
        if not species:
            return False
        species_norm = species.lower()
        scientific, _, common = sentinel_col.partition("_")
        return scientific.lower() in species_norm or common.lower() in species_norm

    def _metadata_value(self, metadata: Dict[str, Any], keys: List[str]) -> Any:
        lower_map = {str(k).lower(): v for k, v in metadata.items()}
        for key in keys:
            if key in metadata:
                return metadata[key]
            value = lower_map.get(key.lower())
            if value is not None:
                return value
        return None

    def _metadata_float(self, metadata: Dict[str, Any], keys: List[str], default: Optional[float]) -> Optional[float]:
        return self._coerce_float(self._metadata_value(metadata, keys), default)

    def _coerce_float(self, value: Any, default: Optional[float]) -> Optional[float]:
        try:
            if value is None or value == "":
                return default
            return self._finite_float(float(value))
        except (TypeError, ValueError):
            return default

    def _finite_float(self, value: float) -> float:
        if not math.isfinite(float(value)):
            return 0.0
        return float(value)


def _event_from_stage(
    event_type: str,
    source_file: str,
    trigger_time_s: float,
    clip_start_s: float,
    clip_end_s: float,
    shaman_i: Dict[str, Any],
    shaman_ii: Dict[str, Any],
) -> TimelineEvent:
    return TimelineEvent(
        event_type=event_type,
        source_file=source_file,
        trigger_time_s=float(trigger_time_s),
        trigger_time_formatted=format_hms(trigger_time_s),
        clip_start_s=float(clip_start_s),
        clip_end_s=float(clip_end_s),
        shaman_i=shaman_i,
        shaman_ii=shaman_ii,
    )


def _read_node_metadata(path: Optional[str]) -> Dict[str, Any]:
    if not path:
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    raise ValueError("Node metadata JSON must be an object keyed by field name.")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _presence_confidence(event: TimelineEvent) -> float:
    try:
        return float(event.shaman_ii.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _presence_detected(event: TimelineEvent) -> bool:
    if event.event_type == "human_presence_confirmed":
        return True
    value = event.shaman_ii.get("is_human_presence")
    return bool(value)


def _simplified_statement(event: TimelineEvent) -> str:
    time_text = event.trigger_time_formatted or format_hms(event.trigger_time_s)
    if _presence_detected(event):
        return f"Human presence detected at time {time_text}."
    return f"No human presence detected at time {time_text}."


def build_simplified_human_presence_payload(
    node_id: str,
    audio_path: str,
    human_presence_events: List[TimelineEvent],
) -> Dict[str, Any]:
    results = []
    for event in sorted(human_presence_events, key=lambda item: item.trigger_time_s):
        results.append(
            {
                "node_id": str(node_id),
                "time_s": float(event.trigger_time_s),
                "time_formatted": event.trigger_time_formatted or format_hms(event.trigger_time_s),
                "human_presence_detected": _presence_detected(event),
                "confidence": _presence_confidence(event),
                "statement": _simplified_statement(event),
            }
        )

    if results:
        statements = [item["statement"] for item in results]
    else:
        statements = ["No reported cases available for human-presence evaluation."]

    return {
        "node_id": str(node_id),
        "audio_path": audio_path,
        "result_type": "human_presence_final_results",
        "results": results,
        "statements": statements,
    }


def write_simplified_human_presence_results(
    out_dir: Path,
    node_id: str,
    audio_path: str,
    human_presence_events: List[TimelineEvent],
) -> Dict[str, Any]:
    simplified_dir = out_dir / "simplified_results"
    payload = build_simplified_human_presence_payload(node_id, audio_path, human_presence_events)
    _write_json(simplified_dir / "final_human_presence_results.json", payload)
    (simplified_dir / "final_human_presence_results.txt").write_text(
        "\n".join(payload["statements"]) + "\n",
        encoding="utf-8",
    )
    return payload


def _save_sqlite(
    db_path: str,
    run_id: str,
    node_id: str,
    audio_path: str,
    stage_timelines: Dict[str, List[TimelineEvent]],
    summary: Dict[str, Any],
) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS node_audio_workflow_timelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                stage_name TEXT NOT NULL,
                timeline_json TEXT NOT NULL,
                summary_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "DELETE FROM node_audio_workflow_timelines WHERE run_id=? AND node_id=?",
            (run_id, node_id),
        )
        rows = [
            (
                run_id,
                node_id,
                audio_path,
                stage_name,
                json.dumps([e.to_dict() for e in events]),
                json.dumps(summary),
            )
            for stage_name, events in stage_timelines.items()
        ]
        con.executemany(
            """
            INSERT INTO node_audio_workflow_timelines
            (run_id, node_id, audio_path, stage_name, timeline_json, summary_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        con.commit()
    finally:
        con.close()


def build_backend_payload(
    node_id: str,
    audio_path: str,
    event_candidates: List[TimelineEvent],
    tinycnn_events: List[TimelineEvent],
    birdnet_events: List[TimelineEvent],
    human_presence_events: List[TimelineEvent],
    combined_events: List[TimelineEvent],
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "node_id": str(node_id),
        "audio_path": audio_path,
        "stage_timelines": {
            "stage_1_event_candidates": [e.to_dict() for e in event_candidates],
            "stage_2_tinycnn_birdcall": [e.to_dict() for e in tinycnn_events],
            "stage_3_birdnet": [e.to_dict() for e in birdnet_events],
            "stage_4_human_presence": [e.to_dict() for e in human_presence_events],
        },
        "combined_timeline": [e.to_dict() for e in combined_events],
        "summary": summary,
    }


def run_node_audio_workflow(
    input_audio: str,
    out_dir: str,
    node_id: Optional[str] = None,
    run_id: Optional[str] = None,
    tinycnn_weights: Optional[str] = None,
    tinycnn_threshold: float = 0.3,
    birdnet_threshold: float = 0.5,
    human_presence_threshold: float = 0.5,
    sr: int = 48000,
    clip_s: float = 3.0,
    block_seconds: float = 60.0,
    metadata_json: Optional[str] = None,
    db_path: Optional[str] = None,
    skip_birdnet: bool = False,
) -> Dict[str, Any]:
    out_dir_p = Path(out_dir)
    out_dir_p.mkdir(parents=True, exist_ok=True)
    node = str(node_id or Path(input_audio).stem)
    metadata = _read_node_metadata(metadata_json)

    stage1 = BasicBirdPrefilter()
    # Stage 2 gate: the new AED meaningful-audio model. Falls back to the
    # legacy birdcall gate only if the AED service failed to import entirely.
    if AEDMeaningfulGate is not None:
        stage2 = AEDMeaningfulGate(weights_path=tinycnn_weights, threshold=tinycnn_threshold)
    else:
        stage2 = TinyCNNBirdcallGate(weights_path=tinycnn_weights, threshold=tinycnn_threshold)
    human_presence = HumanPresenceAdapter(threshold=human_presence_threshold)
    birdnet = None if skip_birdnet else BirdNETConfirm(min_confidence=birdnet_threshold)

    triggers = stream_prefilter_file(input_audio, stage1, block_seconds=block_seconds, overlap_seconds=clip_s)
    event_candidates: List[TimelineEvent] = []
    tinycnn_events: List[TimelineEvent] = []
    birdnet_events: List[TimelineEvent] = []
    human_presence_events: List[TimelineEvent] = []

    for trigger in triggers:
        clip, clip_sr, clip_start, clip_end = extract_centered_clip_from_file(
            input_audio,
            trigger.trigger_time_s,
            clip_s=clip_s,
            target_sr=sr,
        )
        trigger_dict = asdict(trigger)
        event_candidates.append(
            _event_from_stage(
                "event_candidate",
                os.path.basename(input_audio),
                trigger.trigger_time_s,
                clip_start,
                clip_end,
                trigger_dict,
                {"label": "birdcall_or_mixed_audio_candidate"},
            )
        )

        gate_result = stage2.confirm(clip, clip_sr, os.path.basename(input_audio), trigger.trigger_time_s)
        gate_event = _event_from_stage(
            "birdcall_stage2_confirmed" if gate_result.is_birdcall else "birdcall_stage2_rejected",
            os.path.basename(input_audio),
            trigger.trigger_time_s,
            clip_start,
            clip_end,
            trigger_dict,
            gate_result.to_dict(),
        )
        tinycnn_events.append(gate_event)
        if not gate_result.is_birdcall:
            continue

        if birdnet is not None:
            bird_result = birdnet.confirm(clip, clip_sr, os.path.basename(input_audio), trigger.trigger_time_s)
            bird_event = _event_from_stage(
                "bird_confirmed" if bird_result.species else "bird_candidate",
                os.path.basename(input_audio),
                trigger.trigger_time_s,
                clip_start,
                clip_end,
                gate_result.to_dict(),
                asdict(bird_result),
            )
            birdnet_events.append(bird_event)
        else:
            bird_event = _event_from_stage(
                "birdnet_skipped",
                os.path.basename(input_audio),
                trigger.trigger_time_s,
                clip_start,
                clip_end,
                gate_result.to_dict(),
                {"model_status": "skipped_by_flag"},
            )
            birdnet_events.append(bird_event)

        hp_result = human_presence.confirm(bird_event, clip=clip, sr=clip_sr, node_metadata=metadata)
        human_presence_events.append(
            _event_from_stage(
                "human_presence_confirmed" if hp_result.is_human_presence else "human_presence_candidate",
                os.path.basename(input_audio),
                bird_event.trigger_time_s,
                bird_event.clip_start_s,
                bird_event.clip_end_s,
                bird_event.shaman_ii,
                asdict(hp_result),
            )
        )

    combined = merge_timeline_events(birdnet_events, human_presence_events)
    stage_timelines = {
        "stage_1_event_candidates": event_candidates,
        "stage_2_tinycnn_birdcall": tinycnn_events,
        "stage_3_birdnet": birdnet_events,
        "stage_4_human_presence": human_presence_events,
        "combined": combined,
    }
    summary = {
        "node_id": node,
        "run_id": run_id,
        "input_audio": input_audio,
        "n_stage_1_candidates": len(event_candidates),
        "n_stage_2_birdcall_confirmed": sum(e.event_type == "birdcall_stage2_confirmed" for e in tinycnn_events),
        "n_birdnet_events": len(birdnet_events),
        "n_human_presence_events": len(human_presence_events),
        "tinycnn_model_status": stage2.model_status,
        "birdnet_status": "skipped" if skip_birdnet else "enabled",
        "human_presence_status": human_presence.model_status,
    }
    payload = build_backend_payload(
        node,
        input_audio,
        event_candidates,
        tinycnn_events,
        birdnet_events,
        human_presence_events,
        combined,
        summary,
    )

    write_timeline_json(event_candidates, str(out_dir_p / "stage_1_event_candidates.json"))
    write_timeline_json(tinycnn_events, str(out_dir_p / "stage_2_tinycnn_birdcall_timeline.json"))
    write_timeline_json(birdnet_events, str(out_dir_p / "stage_3_birdnet_timeline.json"))
    write_timeline_json(human_presence_events, str(out_dir_p / "stage_4_human_presence_timeline.json"))
    write_timeline_json(combined, str(out_dir_p / "node_combined_timeline.json"))
    simplified_results = write_simplified_human_presence_results(out_dir_p, node, input_audio, human_presence_events)
    _write_json(out_dir_p / "backend_payload.json", payload)
    _write_json(out_dir_p / "node_run_summary.json", summary)

    if db_path and run_id:
        _save_sqlite(db_path, str(run_id), node, input_audio, stage_timelines, summary)

    return {
        "summary": summary,
        "backend_payload": payload,
        "stage_timelines": stage_timelines,
        "simplified_results": simplified_results,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="One-node audio workflow: event detection -> TinyCNN bird-call gate -> BirdNET -> human presence.")
    ap.add_argument("--input_audio", required=True)
    ap.add_argument("--out_dir", default="node_audio_workflow_outputs")
    ap.add_argument("--node_id")
    ap.add_argument("--run_id")
    ap.add_argument("--tinycnn_weights")
    ap.add_argument("--tinycnn_threshold", type=float, default=0.3)
    ap.add_argument("--birdnet_threshold", type=float, default=0.5)
    ap.add_argument("--human_presence_threshold", type=float, default=0.5)
    ap.add_argument("--sr", type=int, default=48000)
    ap.add_argument("--clip_s", type=float, default=3.0)
    ap.add_argument("--block_seconds", type=float, default=60.0)
    ap.add_argument("--metadata_json")
    ap.add_argument("--db_path")
    ap.add_argument("--skip_birdnet", action="store_true", help="Use while birdnetlib/tensorflow is unavailable locally.")
    args = ap.parse_args()

    result = run_node_audio_workflow(
        input_audio=args.input_audio,
        out_dir=args.out_dir,
        node_id=args.node_id,
        run_id=args.run_id,
        tinycnn_weights=args.tinycnn_weights,
        tinycnn_threshold=args.tinycnn_threshold,
        birdnet_threshold=args.birdnet_threshold,
        human_presence_threshold=args.human_presence_threshold,
        sr=args.sr,
        clip_s=args.clip_s,
        block_seconds=args.block_seconds,
        metadata_json=args.metadata_json,
        db_path=args.db_path,
        skip_birdnet=args.skip_birdnet,
    )
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
