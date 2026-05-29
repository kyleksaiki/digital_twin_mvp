from __future__ import annotations

import json
import math
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Protocol, Tuple

import numpy as np

os.environ.setdefault("NUMBA_CACHE_DIR", os.path.join(tempfile.gettempdir(), "numba_cache"))

try:
    from birdnetlib import Recording
    from birdnetlib.analyzer import Analyzer
except Exception:
    Recording = None
    Analyzer = None

try:
    import soundfile as sf
except Exception:
    sf = None

try:
    import librosa
except Exception:
    librosa = None

try:
    from scipy.signal import resample_poly
except Exception:
    resample_poly = None

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset


# =============================
# Core helpers and types
# =============================

def require_audio_stack() -> None:
    if sf is None or librosa is None:
        raise RuntimeError("This pipeline needs soundfile and librosa installed. Use: pip install soundfile librosa")


def format_hms(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - 3600 * h - 60 * m
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def normalize_label(text: Optional[str]) -> str:
    if text is None:
        return ""
    txt = str(text).strip().lower().replace("-", " ").replace("_", " ")
    return " ".join(txt.split())


@dataclass
class TriggerEvent:
    source_file: str
    trigger_time_s: float
    peak_rms: float
    peak_flux: float
    zcr: float
    bandwidth_hz: float
    snr_db: float


@dataclass
class ConfirmationResult:
    source_file: str
    trigger_time_s: float
    is_gunshot: bool
    confidence: float
    inference_ms: float
    label: str = "gunshot"


@dataclass
class SpeciesResult:
    source_file: str
    trigger_time_s: float
    species: Optional[str]
    confidence: float
    inference_ms: float
    raw: Optional[Dict[str, Any]] = None


@dataclass
class TimelineEvent:
    event_type: str
    source_file: str
    trigger_time_s: float
    trigger_time_formatted: str
    clip_start_s: float
    clip_end_s: float
    shaman_i: Dict[str, Any]
    shaman_ii: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ShamanIPrefilter(Protocol):
    min_gap_s: float

    def detect(self, audio: np.ndarray, sr: int, source_file: str) -> List[TriggerEvent]:
        ...


class GunshotConfirmModel(Protocol):
    def fit(self, positive_clips: List[np.ndarray], negative_clips: List[np.ndarray], sr: int) -> None:
        ...

    def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> ConfirmationResult:
        ...


class BirdConfirmModel(Protocol):
    def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> SpeciesResult:
        ...


# =============================
# Shaman I
# =============================

class BasicGunshotPrefilter:
    def __init__(
        self,
        win_s: float = 0.064,
        hop_s: float = 0.016,
        rms_z_thresh: float = 2.0,
        flux_z_thresh: float = 1.8,
        snr_db_thresh: float = 6.0,
        min_gap_s: float = 0.35,
    ) -> None:
        self.win_s = win_s
        self.hop_s = hop_s
        self.rms_z_thresh = rms_z_thresh
        self.flux_z_thresh = flux_z_thresh
        self.snr_db_thresh = snr_db_thresh
        self.min_gap_s = min_gap_s

    def detect(self, audio: np.ndarray, sr: int, source_file: str) -> List[TriggerEvent]:
        require_audio_stack()
        if audio.size == 0:
            return []
        n_fft = max(256, int(2 ** math.ceil(math.log2(self.win_s * sr))))
        hop_length = max(1, int(self.hop_s * sr))
        frame_length = max(1, int(self.win_s * sr))
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length, center=True)[0]
        zcr = librosa.feature.zero_crossing_rate(y=audio, frame_length=frame_length, hop_length=hop_length, center=True)[0]
        S = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=hop_length, win_length=frame_length))
        bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=sr)[0]
        flux = np.sqrt(np.sum(np.diff(S, axis=1, prepend=S[:, :1]) ** 2, axis=0))[: len(rms)]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        rms_mu, rms_sd = float(np.mean(rms)), float(np.std(rms) + 1e-8)
        flux_mu, flux_sd = float(np.mean(flux)), float(np.std(flux) + 1e-8)
        local_floor = np.array([np.median(rms[max(0, i - 25): min(len(rms), i + 25)]) for i in range(len(rms))])
        snr_db = 20.0 * np.log10((rms + 1e-8) / (local_floor + 1e-8))

        triggers: List[TriggerEvent] = []
        last_t = -1e9
        for i, t in enumerate(times):
            rms_z = (rms[i] - rms_mu) / rms_sd
            flux_z = (flux[i] - flux_mu) / flux_sd
            impulsive = (
                rms_z >= self.rms_z_thresh
                and flux_z >= self.flux_z_thresh
                and snr_db[i] >= self.snr_db_thresh
                and bandwidth[i] >= 1200.0
            )
            if not impulsive or t - last_t < self.min_gap_s:
                continue
            last_t = float(t)
            triggers.append(
                TriggerEvent(
                    source_file=source_file,
                    trigger_time_s=float(t),
                    peak_rms=float(rms[i]),
                    peak_flux=float(flux[i]),
                    zcr=float(zcr[i]),
                    bandwidth_hz=float(bandwidth[i]),
                    snr_db=float(snr_db[i]),
                )
            )
        return triggers


class BasicBirdPrefilter:
    def __init__(
        self,
        win_s: float = 0.25,
        hop_s: float = 0.05,
        rms_z_thresh: float = 1.2,
        centroid_hz_thresh: float = 1400.0,
        bandwidth_hz_thresh: float = 700.0,
        snr_db_thresh: float = 4.0,
        min_gap_s: float = 1.5,
    ) -> None:
        self.win_s = win_s
        self.hop_s = hop_s
        self.rms_z_thresh = rms_z_thresh
        self.centroid_hz_thresh = centroid_hz_thresh
        self.bandwidth_hz_thresh = bandwidth_hz_thresh
        self.snr_db_thresh = snr_db_thresh
        self.min_gap_s = min_gap_s

    def detect(self, audio: np.ndarray, sr: int, source_file: str) -> List[TriggerEvent]:
        require_audio_stack()
        if audio.size == 0:
            return []
        n_fft = max(512, int(2 ** math.ceil(math.log2(self.win_s * sr))))
        hop_length = max(1, int(self.hop_s * sr))
        frame_length = max(1, int(self.win_s * sr))
        rms = librosa.feature.rms(y=audio, frame_length=frame_length, hop_length=hop_length, center=True)[0]
        zcr = librosa.feature.zero_crossing_rate(y=audio, frame_length=frame_length, hop_length=hop_length, center=True)[0]
        S = np.abs(librosa.stft(audio, n_fft=n_fft, hop_length=hop_length, win_length=frame_length))
        centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
        bandwidth = librosa.feature.spectral_bandwidth(S=S, sr=sr)[0]
        flux = np.sqrt(np.sum(np.diff(S, axis=1, prepend=S[:, :1]) ** 2, axis=0))[: len(rms)]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        rms_mu, rms_sd = float(np.mean(rms)), float(np.std(rms) + 1e-8)
        local_floor = np.array([np.median(rms[max(0, i - 20): min(len(rms), i + 20)]) for i in range(len(rms))])
        snr_db = 20.0 * np.log10((rms + 1e-8) / (local_floor + 1e-8))

        triggers: List[TriggerEvent] = []
        last_t = -1e9
        for i, t in enumerate(times):
            rms_z = (rms[i] - rms_mu) / rms_sd
            bird_like = (
                rms_z >= self.rms_z_thresh
                and centroid[i] >= self.centroid_hz_thresh
                and bandwidth[i] >= self.bandwidth_hz_thresh
                and snr_db[i] >= self.snr_db_thresh
                and flux[i] >= np.median(flux)
            )
            if not bird_like or t - last_t < self.min_gap_s:
                continue
            last_t = float(t)
            triggers.append(
                TriggerEvent(
                    source_file=source_file,
                    trigger_time_s=float(t),
                    peak_rms=float(rms[i]),
                    peak_flux=float(flux[i]),
                    zcr=float(zcr[i]),
                    bandwidth_hz=float(bandwidth[i]),
                    snr_db=float(snr_db[i]),
                )
            )
        return triggers


# =============================
# Shaman II
# =============================

class TinyGunshotNet(nn.Module):
    def __init__(self, in_dim: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 128), nn.ReLU(), nn.Dropout(0.2), nn.Linear(128, 32), nn.ReLU(), nn.Linear(32, 1)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


class TorchGunshotConfirm:
    def __init__(self, n_mels: int = 64, epochs: int = 25, batch_size: int = 16, lr: float = 1e-3, device: Optional[str] = None, threshold: float = 0.5) -> None:
        self.n_mels = n_mels
        self.epochs = epochs
        self.batch_size = batch_size
        self.lr = lr
        self.threshold = threshold
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model: Optional[TinyGunshotNet] = None
        self.feature_mean: Optional[np.ndarray] = None
        self.feature_std: Optional[np.ndarray] = None

    def _clip_to_features(self, clip: np.ndarray, sr: int) -> np.ndarray:
        require_audio_stack()
        mel = librosa.feature.melspectrogram(y=clip, sr=sr, n_mels=self.n_mels, fmax=sr // 2)
        logmel = librosa.power_to_db(mel + 1e-8)
        delta = librosa.feature.delta(logmel)
        delta2 = librosa.feature.delta(logmel, order=2)
        feat = np.concatenate([
            np.mean(logmel, axis=1), np.std(logmel, axis=1),
            np.mean(delta, axis=1), np.std(delta, axis=1),
            np.mean(delta2, axis=1), np.std(delta2, axis=1),
        ])
        return feat.astype(np.float32)

    def fit(self, positive_clips: List[np.ndarray], negative_clips: List[np.ndarray], sr: int) -> None:
        if len(positive_clips) < 4 or len(negative_clips) < 4:
            raise ValueError("Need enough positive and negative clips to fit Shaman II.")
        X_pos = np.stack([self._clip_to_features(c, sr) for c in positive_clips], axis=0)
        X_neg = np.stack([self._clip_to_features(c, sr) for c in negative_clips], axis=0)
        n = min(len(X_pos), len(X_neg))
        rng = np.random.default_rng(0)
        pos_idx = rng.choice(len(X_pos), size=n, replace=False)
        neg_idx = rng.choice(len(X_neg), size=n, replace=False)
        X_bal = np.concatenate([X_pos[pos_idx], X_neg[neg_idx]], axis=0)
        y_bal = np.concatenate([np.ones(n, dtype=np.float32), np.zeros(n, dtype=np.float32)], axis=0)
        self.feature_mean = X_bal.mean(axis=0, keepdims=True)
        self.feature_std = X_bal.std(axis=0, keepdims=True) + 1e-6
        Xn = (X_bal - self.feature_mean) / self.feature_std
        ds = TensorDataset(torch.tensor(Xn, dtype=torch.float32), torch.tensor(y_bal, dtype=torch.float32))
        dl = DataLoader(ds, batch_size=min(self.batch_size, len(ds)), shuffle=True)
        self.model = TinyGunshotNet(in_dim=Xn.shape[1]).to(self.device)
        opt = torch.optim.Adam(self.model.parameters(), lr=self.lr)
        loss_fn = nn.BCEWithLogitsLoss()
        self.model.train()
        for _ in range(self.epochs):
            for xb, yb in dl:
                xb = xb.to(self.device)
                yb = yb.to(self.device)
                opt.zero_grad()
                logits = self.model(xb)
                loss = loss_fn(logits, yb)
                loss.backward()
                opt.step()

    def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> ConfirmationResult:
        if self.model is None or self.feature_mean is None or self.feature_std is None:
            raise RuntimeError("Gunshot model is not fit yet.")
        x = self._clip_to_features(clip, sr)[None, :]
        x = (x - self.feature_mean) / self.feature_std
        xt = torch.tensor(x, dtype=torch.float32, device=self.device)
        self.model.eval()
        t0 = time.perf_counter()
        with torch.no_grad():
            prob = torch.sigmoid(self.model(xt)).item()
        dt_ms = (time.perf_counter() - t0) * 1000.0
        return ConfirmationResult(
            source_file=source_file,
            trigger_time_s=float(trigger_time_s),
            is_gunshot=bool(prob >= self.threshold),
            confidence=float(prob),
            inference_ms=float(dt_ms),
        )


class BirdNETConfirm:
    def __init__(self, min_confidence: float = 0.5) -> None:
        if Recording is None or Analyzer is None:
            raise RuntimeError("birdnetlib is required for the bird pipeline. Install with: pip install birdnetlib tensorflow")
        self.min_confidence = min_confidence
        self._analyzer = Analyzer()

    def confirm(self, clip: np.ndarray, sr: int, source_file: str, trigger_time_s: float) -> SpeciesResult:
        require_audio_stack()
        t0 = time.perf_counter()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            sf.write(tmp_path, clip, sr)
            recording = Recording(self._analyzer, tmp_path, min_conf=self.min_confidence)
            recording.analyze()
            best = None
            for det in getattr(recording, "detections", []) or []:
                conf = det.get("confidence", 0.0)
                if best is None or conf > best.get("confidence", 0.0):
                    best = det
            dt_ms = (time.perf_counter() - t0) * 1000.0
            if best is None:
                return SpeciesResult(source_file=source_file, trigger_time_s=trigger_time_s, species=None, confidence=0.0, inference_ms=dt_ms, raw=None)
            species = best.get("common_name") or best.get("scientific_name") or best.get("label")
            return SpeciesResult(source_file=source_file, trigger_time_s=trigger_time_s, species=species, confidence=float(best.get("confidence", 0.0)), inference_ms=dt_ms, raw=best)
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass


# =============================
# Audio + timeline helpers
# =============================

def collect_audio_files(audio_dir: str) -> List[str]:
    p = Path(audio_dir)
    return sorted([str(x) for x in p.rglob("*.wav")] + [str(x) for x in p.rglob("*.mp3")] + [str(x) for x in p.rglob("*.flac")] + [str(x) for x in p.rglob("*.m4a")])


def load_audio(path: str, target_sr: int) -> Tuple[np.ndarray, int]:
    require_audio_stack()
    audio, sr = sf.read(path)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = audio.astype(np.float32)
    if sr != target_sr:
        audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
        sr = target_sr
    peak = np.max(np.abs(audio)) if audio.size else 0.0
    if peak > 0:
        audio = audio / (peak + 1e-8)
    return audio.astype(np.float32), sr


def load_audio_region(path: str, start_s: float, duration_s: float, target_sr: Optional[int] = None) -> Tuple[np.ndarray, int, float, float]:
    require_audio_stack()
    with sf.SoundFile(path) as f:
        native_sr = int(f.samplerate)
        start_frame = max(0, int(start_s * native_sr))
        n_frames = int(duration_s * native_sr)
        f.seek(start_frame)
        audio = f.read(n_frames, dtype="float32", always_2d=False)
    if isinstance(audio, np.ndarray) and audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    end_s = start_s + len(audio) / native_sr
    sr = native_sr
    if target_sr is not None and sr != target_sr:
        if resample_poly is None:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
        else:
            g = math.gcd(sr, target_sr)
            audio = resample_poly(audio, target_sr // g, sr // g).astype(np.float32)
        sr = target_sr
    peak = np.max(np.abs(audio)) if len(audio) else 0.0
    if peak > 0:
        audio = audio / (peak + 1e-8)
    return audio.astype(np.float32), sr, float(start_s), float(end_s)


def extract_centered_clip_from_file(path: str, center_s: float, clip_s: float = 3.0, target_sr: Optional[int] = None) -> Tuple[np.ndarray, int, float, float]:
    half = clip_s / 2.0
    start_s = max(0.0, center_s - half)
    audio, sr, real_start, real_end = load_audio_region(path, start_s, clip_s, target_sr=target_sr)
    target_len = int((target_sr or sr) * clip_s)
    if len(audio) < target_len:
        audio = np.pad(audio, (0, target_len - len(audio)))
    return audio.astype(np.float32), sr, real_start, real_end


def iter_audio_blocks(path: str, block_seconds: float = 60.0, overlap_seconds: float = 2.0) -> Iterator[Tuple[np.ndarray, int, float]]:
    require_audio_stack()
    with sf.SoundFile(path) as f:
        sr = int(f.samplerate)
        block_size = max(1, int(block_seconds * sr))
        overlap = max(0, int(overlap_seconds * sr))
        hop = max(1, block_size - overlap)
        offset = 0
        while offset < len(f):
            f.seek(offset)
            audio = f.read(block_size, dtype="float32", always_2d=False)
            if audio.size == 0:
                break
            if audio.ndim > 1:
                audio = np.mean(audio, axis=1)
            yield audio.astype(np.float32), sr, offset / sr
            offset += hop


def deduplicate_triggers(triggers: List[TriggerEvent], min_gap_s: float) -> List[TriggerEvent]:
    if not triggers:
        return []
    triggers = sorted(triggers, key=lambda t: t.trigger_time_s)
    kept: List[TriggerEvent] = [triggers[0]]
    for trig in triggers[1:]:
        prev = kept[-1]
        if trig.trigger_time_s - prev.trigger_time_s < min_gap_s:
            score_prev = prev.peak_flux + prev.snr_db
            score_cur = trig.peak_flux + trig.snr_db
            if score_cur > score_prev:
                kept[-1] = trig
        else:
            kept.append(trig)
    return kept


def stream_prefilter_file(path: str, shaman_i: ShamanIPrefilter, block_seconds: float = 60.0, overlap_seconds: float = 2.0) -> List[TriggerEvent]:
    all_triggers: List[TriggerEvent] = []
    for block_audio, sr, offset_s in iter_audio_blocks(path, block_seconds=block_seconds, overlap_seconds=overlap_seconds):
        block_peak = np.max(np.abs(block_audio)) if block_audio.size else 0.0
        if block_peak > 0:
            block_audio = block_audio / (block_peak + 1e-8)
        block_triggers = shaman_i.detect(block_audio, sr, source_file=os.path.basename(path))
        for trig in block_triggers:
            trig.trigger_time_s += offset_s
        all_triggers.extend(block_triggers)
    return deduplicate_triggers(all_triggers, min_gap_s=float(getattr(shaman_i, "min_gap_s", 0.35)))


def make_timeline_event(trigger: TriggerEvent, result: Dict[str, Any], clip_start_s: float, clip_end_s: float, event_type: str) -> TimelineEvent:
    return TimelineEvent(
        event_type=event_type,
        source_file=trigger.source_file,
        trigger_time_s=float(trigger.trigger_time_s),
        trigger_time_formatted=format_hms(trigger.trigger_time_s),
        clip_start_s=float(clip_start_s),
        clip_end_s=float(clip_end_s),
        shaman_i=asdict(trigger),
        shaman_ii=result,
    )


def bootstrap_positive_clips(files: List[str], sr: int, top_k: int = 3) -> List[np.ndarray]:
    pre = BasicGunshotPrefilter()
    positives: List[np.ndarray] = []
    for path in files:
        audio, sr_ = load_audio(path, sr)
        triggers = pre.detect(audio, sr_, source_file=os.path.basename(path))
        triggers = sorted(triggers, key=lambda t: t.peak_flux + t.snr_db, reverse=True)[:top_k]
        if not triggers:
            center_s = len(audio) / (2.0 * sr_)
            clip, _, _, _ = extract_centered_clip_from_file(path, center_s, clip_s=3.0, target_sr=sr)
            positives.append(clip)
            continue
        for trig in triggers:
            clip, _, _, _ = extract_centered_clip_from_file(path, trig.trigger_time_s, clip_s=3.0, target_sr=sr)
            positives.append(clip)
            for delta in (-0.20, 0.20):
                t_shift = max(0.0, min(len(audio) / sr_, trig.trigger_time_s + delta))
                clip_shift, _, _, _ = extract_centered_clip_from_file(path, t_shift, clip_s=3.0, target_sr=sr)
                positives.append(clip_shift)
    return positives


def bootstrap_negative_clips(files: List[str], sr: int, max_per_file: int = 3) -> List[np.ndarray]:
    negatives: List[np.ndarray] = []
    clip_s = 3.0
    hop_s = 1.5
    for path in files:
        audio, sr_ = load_audio(path, sr)
        win = int(clip_s * sr_)
        hop = int(hop_s * sr_)
        count = 0
        for start in range(0, max(1, len(audio) - win + 1), hop):
            clip = audio[start: start + win]
            if len(clip) < win:
                clip = np.pad(clip, (0, win - len(clip)))
            negatives.append(clip.astype(np.float32))
            count += 1
            if count >= max_per_file:
                break
        if count == 0:
            center_s = len(audio) / (2.0 * sr_)
            clip, _, _, _ = extract_centered_clip_from_file(path, center_s, clip_s=clip_s, target_sr=sr)
            negatives.append(clip.astype(np.float32))
    return negatives


def build_longform_gunshot_timeline(
    input_audio: str,
    sr: int,
    shaman_i: ShamanIPrefilter,
    shaman_ii: GunshotConfirmModel,
    clip_s: float = 3.0,
    block_seconds: float = 60.0,
) -> List[TimelineEvent]:
    triggers = stream_prefilter_file(input_audio, shaman_i, block_seconds=block_seconds, overlap_seconds=2.0)
    out: List[TimelineEvent] = []
    for trig in triggers:
        clip, clip_sr, clip_start, clip_end = extract_centered_clip_from_file(input_audio, trig.trigger_time_s, clip_s=clip_s, target_sr=sr)
        res = shaman_ii.confirm(clip, clip_sr, os.path.basename(input_audio), trig.trigger_time_s)
        res_dict = asdict(res)
        event_type = "gunshot_confirmed" if res.is_gunshot else "gunshot_candidate"
        out.append(make_timeline_event(trig, res_dict, clip_start, clip_end, event_type))
    return out


def build_longform_bird_timeline(
    input_audio: str,
    sr: int,
    shaman_i: ShamanIPrefilter,
    bird_model: BirdConfirmModel,
    clip_s: float = 3.0,
    block_seconds: float = 60.0,
) -> List[TimelineEvent]:
    triggers = stream_prefilter_file(input_audio, shaman_i, block_seconds=block_seconds, overlap_seconds=2.0)
    out: List[TimelineEvent] = []
    for trig in triggers:
        clip, clip_sr, clip_start, clip_end = extract_centered_clip_from_file(input_audio, trig.trigger_time_s, clip_s=clip_s, target_sr=sr)
        res = bird_model.confirm(clip, clip_sr, os.path.basename(input_audio), trig.trigger_time_s)
        res_dict = asdict(res)
        event_type = "bird_confirmed" if res.species else "bird_candidate"
        out.append(make_timeline_event(trig, res_dict, clip_start, clip_end, event_type))
    return out


def event_center(ev: TimelineEvent) -> float:
    return float(ev.trigger_time_s)


def event_category(ev: TimelineEvent) -> str:
    if ev.event_type.startswith("bird"):
        return normalize_label(ev.shaman_ii.get("species"))
    return normalize_label(ev.shaman_ii.get("label", "gunshot"))


def filter_confirmed_events(events: List[TimelineEvent], kind: str) -> List[TimelineEvent]:
    if kind == "GUNSHOT":
        return [e for e in events if e.event_type == "gunshot_confirmed"]
    if kind == "BIRD":
        return [e for e in events if e.event_type == "bird_confirmed" and e.shaman_ii.get("species")]
    raise ValueError(f"Unsupported kind: {kind}")


def compare_events_to_ground_truth(
    predicted_events: List[TimelineEvent],
    log_json_path: str,
    event_type: str,
    tolerance_s: float = 3.0,
    require_category_match: bool = False,
) -> Dict[str, Any]:
    with open(log_json_path, "r") as f:
        gt = json.load(f)
    expected_events = [e for e in gt.get("events", []) if str(e.get("type", "")).upper() == event_type.upper()]
    preds = filter_confirmed_events(predicted_events, event_type.upper())
    preds = sorted(preds, key=event_center)
    exps = sorted(expected_events, key=lambda x: float(x.get("timestamp_seconds", 0.0)))

    matched_pred = set()
    matched_exp = set()
    matches: List[Dict[str, Any]] = []
    for i, pred in enumerate(preds):
        pred_t = event_center(pred)
        pred_cat = event_category(pred)
        best_j = None
        best_d = None
        for j, exp in enumerate(exps):
            if j in matched_exp:
                continue
            exp_t = float(exp.get("timestamp_seconds", 0.0))
            d = abs(pred_t - exp_t)
            if d > tolerance_s:
                continue
            if require_category_match:
                exp_cat = normalize_label(exp.get("category"))
                if pred_cat and exp_cat and pred_cat != exp_cat:
                    continue
            if best_d is None or d < best_d:
                best_d = d
                best_j = j
        if best_j is not None:
            matched_pred.add(i)
            matched_exp.add(best_j)
            matches.append(
                {
                    "predicted_time_s": pred_t,
                    "predicted_category": pred_cat,
                    "expected_time_s": float(exps[best_j].get("timestamp_seconds", 0.0)),
                    "expected_category": exps[best_j].get("category"),
                    "abs_error_s": float(best_d),
                }
            )

    tp = len(matched_pred)
    fp = len(preds) - tp
    fn = len(exps) - len(matched_exp)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    f1 = 2 * precision * recall / max(1e-12, precision + recall)
    return {
        "event_type": event_type.upper(),
        "tolerance_seconds": tolerance_s,
        "require_category_match": require_category_match,
        "n_predictions": len(preds),
        "n_expected": len(exps),
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": matches,
    }


def merge_timeline_events(*event_lists: List[TimelineEvent]) -> List[TimelineEvent]:
    merged: List[TimelineEvent] = []
    for lst in event_lists:
        merged.extend(lst)
    return sorted(merged, key=event_center)


def write_timeline_json(events: List[TimelineEvent], out_path: str) -> None:
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump([e.to_dict() for e in events], f, indent=2)


def build_node_result_payload(
    node_id: str,
    audio_path: str,
    gunshot_events: List[TimelineEvent],
    bird_events: List[TimelineEvent],
    combined_events: List[TimelineEvent],
    evaluation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "node_id": str(node_id),
        "audio_path": audio_path,
        "gunshot_timeline": [e.to_dict() for e in gunshot_events],
        "bird_timeline": [e.to_dict() for e in bird_events],
        "combined_timeline": [e.to_dict() for e in combined_events],
        "evaluation": evaluation or {},
    }


def ensure_event_timeline_table_sqlite(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS node_event_timelines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                audio_path TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timeline_json TEXT NOT NULL,
                evaluation_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.commit()
    finally:
        con.close()


def save_node_event_timelines_sqlite(
    db_path: str,
    run_id: str,
    node_id: str,
    audio_path: str,
    gunshot_events: List[TimelineEvent],
    bird_events: List[TimelineEvent],
    evaluation: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_event_timeline_table_sqlite(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "DELETE FROM node_event_timelines WHERE run_id=? AND node_id=?",
            (run_id, str(node_id)),
        )
        rows = [
            (run_id, str(node_id), audio_path, "gunshot", json.dumps([e.to_dict() for e in gunshot_events]), json.dumps((evaluation or {}).get("gunshot", {}))),
            (run_id, str(node_id), audio_path, "bird", json.dumps([e.to_dict() for e in bird_events]), json.dumps((evaluation or {}).get("bird", {}))),
            (run_id, str(node_id), audio_path, "combined", json.dumps([e.to_dict() for e in merge_timeline_events(gunshot_events, bird_events)]), json.dumps(evaluation or {})),
        ]
        con.executemany(
            "INSERT INTO node_event_timelines (run_id, node_id, audio_path, event_type, timeline_json, evaluation_json) VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        con.commit()
    finally:
        con.close()



def load_timeline_events_from_json(path: str) -> List[TimelineEvent]:
    with open(path, "r") as f:
        raw = json.load(f)
    return [TimelineEvent(**item) for item in raw]


def evaluate_timeline_jsons(
    bird_timeline_json: Optional[str],
    gunshot_timeline_json: Optional[str],
    ground_truth_log: str,
    bird_tolerance_s: float = 5.0,
    gunshot_tolerance_s: float = 2.0,
) -> Dict[str, Any]:
    evaluation: Dict[str, Any] = {}
    if bird_timeline_json:
        bird_events = load_timeline_events_from_json(bird_timeline_json)
        evaluation["bird"] = compare_events_to_ground_truth(
            bird_events,
            ground_truth_log,
            event_type="BIRD",
            tolerance_s=bird_tolerance_s,
            require_category_match=True,
        )
    if gunshot_timeline_json:
        gun_events = load_timeline_events_from_json(gunshot_timeline_json)
        evaluation["gunshot"] = compare_events_to_ground_truth(
            gun_events,
            ground_truth_log,
            event_type="GUNSHOT",
            tolerance_s=gunshot_tolerance_s,
            require_category_match=False,
        )
    if evaluation:
        tp = sum(v.get("true_positives", 0) for v in evaluation.values())
        fp = sum(v.get("false_positives", 0) for v in evaluation.values())
        fn = sum(v.get("false_negatives", 0) for v in evaluation.values())
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-12, precision + recall)
        evaluation["overall"] = {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }
    return evaluation
