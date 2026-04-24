# Battery Simulation — Math, Assumptions, and Data Flow

This document explains exactly what the battery simulator does, what numbers
it uses, where those numbers come from, and what is still configurable vs.
hard-coded. It is the reference to review before accepting any plot the
simulator produces.

---

## 1. What the simulator is for

Given:

- a **network topology** (sensors → relays → command) from the Configure
  Run modal,
- per-node-type **power configurations** (sleep / working / transmit /
  receive / mic, etc.) also from the Configure Run modal,
- a **timeline of AI detection events** (from the AI pipeline's JSON, or
  the DB, or mocked),

produce:

- per-node **battery % over time** (a line for each node),
- per-node **energy budget breakdown** (baseline idle vs. event-driven),
- a **worst-node** marker so we know which sensor dies first.

The primary deliverable is the per-node `(time, battery_percent)` series —
exportable as CSV or returned as JSON.

---

## 2. Physical model

### 2.1 Hardware roles

| Role      | Hardware (project parlance) | Does what                        |
| --------- | --------------------------- | -------------------------------- |
| `sensor`  | **Shaman I**                | Mic + ESP32. Runs BOTH stages of AI locally. Transmits only confirmed events over LoRa. |
| `relay`   | **Shaman II**               | LoRa router. Receives packets from children, forwards up the tree. Does no classification. |
| `command` | **Gateway / Command Node**  | Terminal. Receives packets from the tree. |

Note: the `shaman_i` / `shaman_ii` keys in the AI pipeline's event JSON
refer to the two **processing stages** of inference, not the two node
types. Both stages run on the Shaman I microcontroller.

### 2.2 Event-processing pipeline on Shaman I

```
 mic → [Stage 1: acoustic prefilter, always-on, low power]
                  │
                  │  (peak RMS / spectral flux crosses threshold)
                  ▼
        [Stage 2: confirmation model, bursty]
                  │
                  ▼
       ┌──────────┴──────────┐
       │                     │
   candidate             confirmed
   (stop)       (LoRa TX up the mesh)
```

Only `*_confirmed` events trigger a transmission. `*_candidate` events
consume processing power on the sensor but no radio energy.

---

## 3. Energy bookkeeping

All accounting is in Watt-hours (Wh). Every term below is either:
- a continuous power (W) multiplied by a time interval (h), or
- a pulse: power (W) × duration (s) / 3600.

### 3.1 Baseline (continuous)

Applied every time step `dt`:

```
Sensor  (Shaman I):   ΔE = (P_sleep + P_micListen) * dt
Relay   (Shaman II):  ΔE = P_sleep * dt
Command (Shaman II):  ΔE = P_sleep * dt          # mains-powered? set P_sleep=0.
```

Stage 1 prefilter is folded into the sensor baseline. If you want it
broken out, set `stage1_duration_s > 0` on each event and the engine
adds a `(P_working - P_sleep)` delta for that duration.

### 3.2 Per-event, on the originating sensor

For each event `e`:

```
Stage-2 burst:  ΔE_s2 = (P_working - P_sleep) * e.stage2_duration_s / 3600
```

where `e.stage2_duration_s` comes from the AI pipeline's
`shaman_ii.inference_ms` field (converted to seconds). The
`stage2_default_working_s` config (30 ms) is used only if `inference_ms`
is missing.

If `e.confirmed`:

```
TX burst:       ΔE_tx = P_transmit * T_airtime * frames_per_hop / 3600
```

### 3.3 Per-confirmed-event, up the tree

For each ancestor `a` of the sensor on the path to the gateway:

```
RX burst:       ΔE_rx = P_receive  * T_airtime * frames_per_hop / 3600
if a is not the gateway and has a parent:
    TX burst:   ΔE_tx = P_transmit * T_airtime * frames_per_hop / 3600
```

The gateway receives but does not forward.

### 3.4 LoRa time-on-air (`T_airtime`)

Using the Semtech formula (SX1276 datasheet §4.1.1.6) with the project's
defaults (SF10, BW 125 kHz, CR 4/5, 128-byte payload, 8-symbol preamble,
explicit header, CRC on, no low-data-rate optimization):

```
t_sym       = 2^SF / BW                              # 1.024 ms at SF10/125
t_preamble  = (n_preamble + 4.25) * t_sym            # 12.55 ms
n_payload   = 8 + max(ceil((8*PL − 4*SF + 28 + 16) / (4*SF)) * CR, 0)
            = 8 + max(ceil((1024 − 40 + 44)/40) * 5, 0)
            = 8 + 26*5 = 138 symbols  (for PL=128)
t_payload   = n_payload * t_sym                      # 141.3 ms
T_airtime   ≈ 1.231 s per frame for 128-byte SF10 packets
```

Sanity: three frames per hop × 1.231 s ≈ 3.7 s of radio on-time per
confirmed event per hop. At `P_transmit = 0.39 W`, that's ≈ 0.0004 Wh per
hop per confirmed event. 50 confirmed events over 12 h from a child ⇒
~0.02 Wh of radio drain on the relay — consistent with the CLI output on
the mock 3S–1R–1C topology.

---

## 4. Data sources — what flows in, what is assumed

| Quantity                     | Source                                  | Fallback                      |
| ---------------------------- | --------------------------------------- | ----------------------------- |
| `battery_wh` per node type   | Configure Run → `batteryLife`           | 22 Wh                          |
| `P_sleep/working/transmit/receive/micListen/...` | Configure Run → `components[k].current/voltage/power` | Per-state defaults in `config.py` |
| Topology (nodes + edges)     | Configure Run → `nodes` / `edges`       | None — required                |
| Event timestamps             | AI event timeline JSON → `trigger_time_s` | DB `ai_events` row, else mock |
| Stage-2 inference duration   | AI event timeline → `shaman_ii.inference_ms` | 30 ms                          |
| Confirmed vs. candidate      | AI event timeline → `event_type` suffix | All-confirmed (conservative)   |
| LoRa packet bytes            | `radio.packet_bytes`                    | 128 B *(see §6)*              |
| LoRa SF / BW / CR            | `radio.spreading_factor / bandwidth_hz / coding_rate` | SF10, 125 kHz, 4/5 |
| Frames per hop               | `radio.frames_per_hop`                  | 3                              |
| Time step                    | `time_step_seconds`                     | 60 s                           |

Filename → node_id mapping for AI events is inferred from the GUI's
`mediaFiles` dict by pulling the `node_NNN` token out of each filename.

---

## 5. What the Configure Run modal is missing today

The current modal (see `frontend/src/components/CreateRun.jsx`) collects
everything per-component as current/voltage/power, but does not collect
radio or timing parameters. Recommended additions so operators can change
these without editing `config.py`:

- **LoRa radio panel** (per run):
  - Packet bytes (default 128)
  - Spreading factor (default 10)
  - Bandwidth kHz (default 125)
  - Frames per hop (default 3)
- **Event-timing panel** (per Shaman I):
  - Stage-1 extra working duration per candidate (default 0 s)
  - Stage-2 default inference duration when the AI timeline is missing
    `inference_ms` (default 30 ms)
- **Optional persistence of `shaman_i_config` / `shaman_ii_config` into
  the `runs` row.** Today `POST /api/runs/create` accepts them in the
  request body but does not persist them to the DB — the battery API
  takes them as parameters on each simulate call instead. This is fine
  for live simulation but means configs are lost if the page reloads.
  Follow-up: add `shaman_i_config` / `shaman_ii_config` JSON columns to
  `RunRow`, or stash them under namespaced keys in `calibration_data`.

---

## 6. Known data inconsistencies and how the sim handles them

### 6.1 LoRa packet size: 128 B vs. 4128 B

The Mesh Network Planning §6.2 doc says each node transmits a
**~128-byte** summary packet ("semantic transmission"). The "Example
Output" slide instead shows a **4128-byte** payload. These two numbers
imply a ~32× difference in radio airtime and energy.

**Decision:** default to 128 B because the 128-byte value is tied to a
clear rationale (class ID + timestamp + geo + confidence). The 4128-byte
number appears to be an artifact of an earlier prototype that streamed the
full feature vector. We expose `radio.packet_bytes` on the API/CLI so
either value can be selected per run.

### 6.2 Stage-1 duration

The AI event timeline doesn't emit a Stage-1 duration — only `inference_ms`
for the Stage-2 model. Because Stage 1 is a streaming DSP filter that is
*always on*, we fold its steady-state power into the `sleep + micListen`
baseline rather than modeling a per-event burst. If that approximation
turns out to be wrong (e.g. hardware measurements show a spike on every
candidate), set `timings.stage1_extra_working_s` > 0 and the engine will
add a per-candidate burst.

### 6.3 Receiver listening window

We bill `T_airtime × frames_per_hop` of RX time per confirmed packet per
hop. In reality an idle listening relay has some continuous receive-mode
current draw. For an always-on LoRa gateway this matters a lot; for a
duty-cycled receiver it matters less. **We currently lump idle RX into
`P_sleep`** because the GUI gives us only one baseline. If you need to
split them, bump `P_sleep` of the Shaman II config to the
duty-cycle-adjusted RX current + MCU sleep.

---

## 7. Data flow (end to end)

```
Configure Run modal
   │  (Shaman I config, Shaman II config, nodes, edges, mediaFiles)
   ▼
POST /api/runs/create                       →  runs table (+network_nodes, network_edges)
                                               (shamanIConfig/shamanIIConfig forwarded but not yet persisted)

AI pipeline                                 →  combined_ai_event_timeline.json
                                               (stored on disk, can be uploaded)

POST /api/battery/simulate  (run_id, configs, ai_events_path, media_files)
   │
   ├─ SimulationConfig.from_run_config(...)   ← maps Configure Run payload → internal config
   ├─ SimNetwork.from_db_nodes(...)           ← reads network_nodes / network_edges
   ├─ load_ai_events_with_stats(...)          ← reads AI event JSON + mediaFiles map
   └─ BatterySimulator(...).run()             ← §3 math
          │
          ▼
     time-series JSON per node  +  summary  +  CSV via scripts/run_battery_sim.py
```

---

## 8. How to run it

### 8.1 Via API (from the frontend or curl)

```bash
curl -X POST http://localhost:8000/api/battery/simulate \
  -H 'Content-Type: application/json' \
  -d '{
        "run_id": 1,
        "duration_hours": 12,
        "time_step_seconds": 60,
        "shaman_i_config":  { ...Configure Run shaman_i payload... },
        "shaman_ii_config": { ...Configure Run shaman_ii payload... },
        "radio_config": { "packet_bytes": 128, "spreading_factor": 10 },
        "ai_events_path": "/abs/path/combined_ai_event_timeline.json",
        "media_files": {"S1": "node_001_..wav", "S2": "node_002_..wav"}
      }'
```

### 8.2 Via CLI (no DB or frontend needed)

```bash
cd backend
python scripts/run_battery_sim.py \
  --topology topology.json \
  --config configs.json \
  --ai-events /path/to/combined_ai_event_timeline.json \
  --media-files media_files.json \
  --duration-hours 12 \
  --out-csv battery.csv --out-json battery.json
```

Or purely synthetic:

```bash
python scripts/run_battery_sim.py \
  --mock-topology 3S-1R-1C \
  --duration-hours 12 --events-per-node 25 \
  --out-csv /tmp/battery.csv
```

---

## 9. Sensitivity knobs (for quick what-ifs)

| Knob                               | Expected behavior                                   |
| ---------------------------------- | --------------------------------------------------- |
| Increase `shaman_i.micListen` current by 2× | Sensor slope ~doubles (baseline dominated) |
| Switch `radio.packet_bytes` 128 → 4128 | Relay & gateway RX/TX energy rises ~30× per confirmed event |
| Drop `radio.spreading_factor` 10 → 7 | Airtime drops ~8×; event-driven energy falls accordingly |
| Raise `duration_hours` 12 → 24      | All baselines scale linearly; event-driven scales with event count |

If any of these show *surprising* results (non-linear, flipped sign, large
discontinuities) in your sweeps, that's a bug — file an issue.
