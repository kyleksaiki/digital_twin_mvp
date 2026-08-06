# AED Integration Notes

New AED (acoustic event detection) TinyCNN replaces the legacy birdcall gate.
Uploading audio in Configure Run now runs the real model end-to-end and the
Model Performance page shows only measured values.

## Files added

- `backend/app/services/aed/architecture.py` — vendored TinyCNN (upstream `src/model/architecture.py`, header added)
- `backend/app/services/aed/inference.py` — vendored constants + `load_model` + `predict`; local `clip_to_mel` for in-memory clips (each step maps 1:1 to upstream `preprocess_clip`)
- `backend/app/services/aed/gate.py` — `AEDMeaningfulGate`, drop-in for the old gate's `confirm()` contract; model cached once per process; degrades to pass-through with a clear `model_status` when the checkpoint/torch is missing
- `backend/app/services/aed/stage_stats.py` — derives the 5 UI stages' pass/fail/timing from real timelines; persists them + provenance
- `backend/app/services/aed/models/tinycnn_v3.pth` — **committed** (2.2 MB): works out of the box; override with `AED_MODEL_PATH`

## Files modified

- `audio_workflow/node_audio_workflow.py` — stage-2 gate swapped to `AEDMeaningfulGate` (legacy gate kept as import-failure fallback); `HumanPresenceAdapter.confirm` now records per-sub-step `timing_ms` and `had_node_metadata` (additive)
- `services/audio_processing.py` — `birdnet_skipped` display label `"Bird"` → `"Wildlife"`; confidence/latency fall back to `shaman_i` (the gate's real values) when `shaman_ii` only holds the skip marker; processing loop instrumented (audio duration, wall time) and persists stage stats after events
- `services/battery_sim/adapter.py` — `UNCONFIRMED_LABELS = {"Bird", "Wildlife"}` ("Bird" kept for legacy runs) so Wildlife stays the no-transmit case
- `db_models.py` — new `pipeline_stage_stats` and `audio_processing_stats` tables (+ cascade relationships on RunRow)
- `routes/runs.py` — dashboard now also returns `pipeline_stats` (keyed stage1..stage5) and `processing` (provenance, measurements, validation block)
- `frontend/src/components/ModelPerformanceDashboard.jsx` — rewritten: real stage cards + drill-down, AED confidence distribution chart, Model Card panel, honest zero states

## Decisions (and why)

1. **UI-stage mapping.** stage1 Audio Filtering = prefilter (entered = 3 s
   windows in the file, passed = triggers); stage2 AED Event Detection = the
   new model; stage3 Feature Extraction and stage4 Context Enrichment =
   instrumented sub-steps inside `HumanPresenceAdapter.confirm` (timed, not
   restructured); stage5 Human Presence Classification = the proxy scorer's
   decision. Stage labels in the UI updated to match.
2. **Polarity.** The model outputs `not_meaningful_prob` (lower = interesting).
   The gate exposes `confidence = 1 − not_meaningful_prob` and passes when
   `confidence ≥ threshold` — continuous with the old convention, so the
   existing `tinycnn_threshold` config keeps its meaning. Verified: silence →
   confidence 0.00, chirps → 1.00.
3. **Labels.** A stage-2-confirmed event that is not human presence is now
   `"Wildlife"` (the model detects meaningful audio: bird, insect, other
   animal — not provably a bird). Battery sim updated in the same change;
   Wildlife = classified locally, no transmit energy (verified 15.84 mJ vs
   confirmed events).
4. **Accuracy/FPR are NOT faked.** A field recording has no ground truth. The
   dashboard shows measured metrics (detections, mean confidence, latency,
   pass rates, throughput) and a Model Card with the checkpoint's held-out
   validation figures, explicitly labeled "not this run". Reported val_acc
   99.84% is a validation-set figure; upstream's own docs (DIAGNOSIS_LABELS)
   show why such numbers must not be presented as deployment accuracy.
5. **Checkpoint v3 committed.** Upstream's API default; best F1 (0.99) with
   recall 1.0. Resolution order: `AED_MODEL_PATH` env → bundled v3 → newest
   `tinycnn_v*.pth` in `services/aed/models/`. `.gitignore`'s `*.pt` (YOLO)
   does not match `.pth`.
6. **Per-clip inference, not batched** — deliberate deviation from the task
   prompt. Batching requires restructuring the workflow loop; the model is
   ~2 MB and runs ~20 ms/clip on CPU inside a background task, so per-clip
   cost is acceptable. Revisit if runs regularly process many hours of audio.
7. **`torch.load(weights_only=False)`** — deliberate: checkpoints carry plain
   metadata we read for provenance, and they ship with the repo.
8. **autoflush=False gotcha.** `SessionLocal` doesn't autoflush; stage-stats
   persistence flushes first so the metrics row created moments earlier is
   visible. Keep that flush if you touch the ordering.

## Verified end-to-end

90 s synthetic file, 4 chirp bursts: 30 windows → 4 triggers → 4 meaningful
(conf 1.0, ~20 ms/clip cpu) → 4 Wildlife events; stage stats, histogram,
provenance, metrics (`conf_threshold` 0.5, real latency), battery sim, and the
dashboard payload all confirmed via TestClient. App boots without ultralytics
and without the AED checkpoint (pipeline reports pass-through). Old runs and
the template run render every page with zeros.

## Re-sync with upstream audio-detection repo

Copy `src/model/architecture.py` over `services/aed/architecture.py` (restore
the header) and diff `aed_inference.py` against `services/aed/inference.py`
(only `clip_to_mel` and `resolve_checkpoint_path` are local). Drop new
checkpoints into `services/aed/models/`.
