# Integration Notes — Battery Simulator + YOLO Human Detection

Both features were built together (originally planned as two commits; delivered
as one combined change set at Kyle's request). They are still independent:
everything under `battery_sim`/`battery.py` is Part A, everything under
`vision.py`/`HumanVisualDetection` is Part B, and either can be reverted by
deleting its files and the few marked call sites.

## Files added vs. modified

**Added (backend)**
- `backend/app/services/battery_sim/__init__.py`
- `backend/app/services/battery_sim/single_node_simulator.py` — vendored from the battery-simulator repo (see "Re-syncing" below)
- `backend/app/services/battery_sim/adapter.py` — all Digital Twin ↔ simulator translation
- `backend/app/routes/battery.py` — `GET /api/runs/{run_id}/battery`
- `backend/app/routes/vision.py` — `POST /api/vision/detect-humans`

**Added (frontend)**
- `frontend/src/components/HumanVisualDetection.jsx`
- `frontend/src/styles/HumanVisualDetection.css`

**Modified (backend)**
- `backend/app/db_models.py` — new `BatterySimResultRow` table; `Boolean, Text` added to the sqlalchemy import; one relationship line on `RunRow` (needed for ORM-level cascade delete, matching every other child table). No existing column changed. The table is picked up automatically by `init_db()`'s `Base.metadata.create_all` — no `database.py` change was needed, because "registration" in this codebase is simply living on `Base`.
- `backend/app/routes/runs.py` — defensive import of the battery service; new `_run_battery_sim_safe()` helper; `_process_audio_background` gained a `shaman_config` parameter and now commits audio results **before** running the sim (so a rolled-back sim failure can never discard the detection timeline), then runs the sim, then flips status; `create_run` passes `req.shamanConfig` to the background task and runs the sim inline for no-audio runs (idle-drain baseline).
- `backend/app/main.py` — two imports + two `include_router` lines.
- `backend/requirements.txt` — added `ultralytics`, `pillow`.
- `.gitignore` — `*.pt` (YOLO weights).
- `README.md` — YOLO first-run weight download note.

**Modified (frontend)**
- `frontend/src/api.js` — `fetchBatteryStats(runId)` (existing `getJson` pattern) and `detectHumans(file)` (multipart).
- `frontend/src/components/CreateRun.jsx` — `t_proc`/`t_tx` inputs + state + reset; power-step validation via the existing `validateStep` pattern; "Resolved" wattage column and ⚡ markers on the four modeled components with an explanatory note; `shamanConfig.timing` in the payload; confirmation message gains a one-line battery result; Review step shows the timing values.
- `frontend/src/components/BatteryStatistics.jsx` — rewritten (see below).
- `frontend/src/components/Sidebar.jsx` — one nav item, **not** gated on `isRunLoaded`.
- `frontend/src/App.jsx` — import, title map entry, page div, CSS import.

## New table

`battery_sim_results` — one row per run (re-processing replaces the row):
`run_id` (FK, CASCADE), `node_id`, `battery_wh`, `energy_consumed_wh`,
`energy_remaining_wh`, `final_battery_percent`, `average_power_w`,
`avg_drain_percent_per_hour`, `projected_total_life_hours` (nullable),
`duration_hours`, `duration_source` ("audio" | "dropdown"),
`total_detections`, `alive`, `series_json`, `breakdown_json`, `created_at`.

Rounded mirrors are still written to `NetworkNodeRow.battery` / `drain` so
legacy consumers (netmap, dashboards) keep working; the new table is the
source of truth for Battery Statistics.

## New endpoints

- `GET /api/runs/{run_id}/battery` → stored simulator output, or
  `{"available": false}` with HTTP 200 when none exists (old runs must not
  break the page).
- `POST /api/vision/detect-humans` (multipart `file`) → normalized person
  boxes: `{detections: [{x1,y1,x2,y2,confidence}], image_width, image_height,
  model, inference_ms}`. Server confidence floor 0.1; the UI slider filters
  client-side. Stateless: nothing persisted. 15 MB cap, non-images and corrupt
  files → 400, missing/unloadable model → 503 with an actionable message.

## Configure Run → simulator parameter mapping

| Simulator field | Source | Resolution |
|---|---|---|
| `battery_wh` | `shamanConfig.batteryLife` (Battery Capacity, Wh) | must be > 0 (validated) |
| `P_mic` | `components.micListen` | power rule below |
| `P_proc_lp` | `components.sleep` | power rule below |
| `P_proc_hp` | `components.working` | power rule below |
| `P_tx` | `components.transmit` | power rule below |
| `t_proc` | `shamanConfig.timing.t_proc` (new field, default 0.030 s) | ≥ 0 (validated) |
| `t_tx` | `shamanConfig.timing.t_tx` (new field, default 0.005 s) | ≥ 0 (validated) |

Power rule (in `adapter._resolve_component_watts`, mirrored in CreateRun's
"Resolved" column): `power` wins when > 0; else `W = voltage × current / 1000`
(mA); else the simulator's `NodeConfig` default. A `None` never reaches the
simulator. `receive`, `cameraImage`, `cameraSleep`, `micSleep` are recorded
with the run but not modeled — the Power Configuration step says so.

Duration comes from the uploaded audio's header (`soundfile.info`, falling
back to `librosa.get_duration`), not the dropdown; the dropdown is only the
fallback, and the UI labels that case as an estimate. Time step is
`max(60, duration_seconds / 200)` — chart resolution only; total energy is
step-size independent.

Events: every `AIEventRow` for the run, `time = timestamp_ms / 1000`.

## Re-syncing the vendored simulator

`single_node_simulator.py` is upstream's file plus exactly two local
modifications, both marked with `LOCAL MODIFICATION` comments and listed in
the module docstring:

1. `_step_energy()` takes an extra `unconfirmed_in_step` (default 0):
   unconfirmed events cost `t_proc` only; confirmed cost `t_proc + t_tx`.
2. `run()` counts unconfirmed events per step and passes them through.

With the defaults, output is identical to upstream — verified against
`single_node_scenario.json` (98.49% final, same breakdown). To re-sync: copy
the upstream file over this one and re-apply the two marked hunks. All other
translation lives in `adapter.py` and never needs re-applying.

## Assumptions a reviewer should double-check

1. **The prompt's event-type mapping doesn't match the DB.** The spec said to
   map raw workflow event types (`birdnet_skipped` → unconfirmed, etc.), but
   `_persist_workflow_result()` stores *display labels* in
   `AIEventRow.event_type`: `birdnet_skipped` → `"Bird"`,
   `human_presence_confirmed` → `"Human Presence"`, `bird_confirmed` → the
   species name (it only fires when a species exists — see
   `node_audio_workflow.py` line ~542). So the adapter treats label `"Bird"`
   as unconfirmed and everything else as confirmed, which is exactly
   equivalent under the current pipeline. If `_event_label()` ever changes,
   update `UNCONFIRMED_LABELS` in `adapter.py`.
2. **Per-event `energy_mj`** is back-filled by the adapter as the analytic
   burst energy `(P_proc_hp·t_proc [+ P_tx·t_tx]) × 1000`, independent of the
   step-level burst capping the simulator applies when detections cluster.
3. **Multiple audio files:** duration uses the *longest* uploaded clip (the
   new-run flow only ever uploads one, for the single Shaman node).
4. **Battery Statistics empty state (deliberate deviation from the spec):**
   per Kyle's request, the "No battery data available for this run" message is
   gone. Priority: real sim data → legacy netmap node values (old runs, which
   keep the old back-extrapolated line and their stored `powerBreakdown`,
   with the fabricated 45/25/15/10/5 percentage split removed) → a fully
   rendered zeroed layout (flat 0% line, 0-valued component bars). The
   "Select a run" state is unchanged.
5. **Sim trigger ordering:** with audio, the detection timeline is committed
   before the sim runs, so a sim failure (logged, rolled back) can never
   discard audio results or fail the run. Without audio, the sim runs inline
   during `create_run` with an empty event list.
6. `frontend/dist/` was rebuilt with the new pages (`npx vite build`); run
   `npm run dev` for development as usual.

## Verification performed

- Vendored simulator reproduces upstream results exactly on
  `single_node_scenario.json`; all-unconfirmed variant zeroes transmitter
  energy while HP processor energy is unchanged.
- Full adapter flow against SQLite: audio-header duration (30 s clip →
  0.00833 h, source `audio`), series starts at `{0, 100.0}`, correct
  per-event `energy_mj` (19.47 mJ confirmed / 15.84 mJ unconfirmed at the
  ESP32-ish defaults), node mirrors written, idempotent re-run, ORM cascade
  delete removes the result row.
- Request-level (FastAPI TestClient): `POST /api/runs/create` without audio →
  inline sim → `GET /battery` returns 201 points, `duration_source:
  "dropdown"`, 99.63% final at defaults; unknown run → `{"available": false}`;
  `detect-humans` without `ultralytics` installed → clean 503 while the rest
  of the app (including startup) is unaffected.
- `npx vite build` passes with all frontend changes.
