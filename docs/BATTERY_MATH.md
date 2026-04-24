# Battery Simulation — Math, Assumptions, and Data Flow

This document explains what the battery simulator does, what numbers it uses,
where those numbers come from, and what is still configurable vs. hard-coded.
Every equation and variable name matches the project's
**Energy State / Variables / Equations** spec.

---

## 1. What the simulator is for

Given:

- a **network topology** (sensors → relays → command) from the Configure Run modal,
- per-node-type **power configurations** (current/voltage per state) from
  Configure Run — mapped onto the spec's power variables,
- an **AI event timeline** (from the AI pipeline's JSON, or the DB, or mocked),

produce:

- per-node **battery % over time** (a line for each node),
- per-node **energy budget** (E_consumed, E_remaining, percent_used, P_average),
- per-node **projected battery life** (T_battery_life = E_battery / P_average),
- a **worst-node** marker.

Primary deliverable: per-node `(time, battery_percent)` time-series exportable
as CSV or JSON.

---

## 2. Physical model

### 2.1 Hardware roles

| Role      | Hardware     | Does what                                                                |
| --------- | ------------ | ------------------------------------------------------------------------ |
| `sensor`  | Shaman I     | Mic + ESP32. Runs AI filter continuously. Transmits via WiFi to parent Shaman II. |
| `relay`   | Shaman II    | Main processor + ESP32 controller + LoRa radio. Receives (WiFi from Shaman I, LoRa from Shaman II), forwards upstream via LoRa. |
| `command` | Gateway      | Same hardware class as Shaman II. Terminal of the mesh — receives, does not forward. |

### 2.2 Communication paths (spec §2)

```
Shaman I  --- WiFi -->  Shaman II (relay)  --- LoRa -->  Shaman II (relay/gateway)
```

- Sensor → Relay hop: **WiFi** (`t_tx_wifi`, `P_wifi_tx`, `P_wifi_rx`)
- Relay → Relay / Relay → Gateway: **LoRa** (`t_tx_lora`, `P_lora_tx`, `P_lora_rx`)

Every Shaman II has LoRa receiving **always on** (listening for mesh packets).
The main processor sleeps between events; the ESP32 controller also sleeps.

---

## 3. Spec equations — implemented verbatim

All accounting is in Watt-hours (Wh). Power×time is divided by 3600 to convert
from seconds-based durations to hours. `T` is the simulation duration in hours.

### 3.1 Shaman I energy (§3.1 of spec)

```
E_ShaI      = E_baseline + E_tx
E_baseline  = (P_proc_shaI_active + P_mic) · T
E_tx        = n_local · P_wifi_tx · t_tx_wifi · frames_per_hop
```

- `n_local` = number of events the sensor detected.
- The AI filter runs continuously ⇒ processor is in the **active** state as a
  baseline (not sleep). Same for mic.
- Every detected event is transmitted — there is no confirmed/candidate filter
  at this layer.

### 3.2 Shaman II energy (§3.2 of spec)

```
E_ShaII     = E_baseline + E_rx_wifi + E_rx_lora + E_tx + E_process + E_retry

E_baseline  = (P_controller_sleep + P_lora_rx + P_proc_shaII_sleep) · T
E_rx_wifi   = n_received_wifi · P_wifi_rx · t_rx_wifi
E_rx_lora   = n_received_lora · P_lora_rx · t_rx_lora
E_tx        = n_forward · P_lora_tx · t_tx_lora · frames_per_hop
E_process   = n_received · (P_proc_shaII_active − P_proc_shaII_sleep) · t_proc_shaII
E_retry     = n_retries · (P_lora_tx · t_tx_lora · frames_per_hop
                         + P_backoff · t_backoff)
```

- `n_received_wifi` counts packets from Shaman I children (via WiFi).
- `n_received_lora` counts packets from Shaman II children (via LoRa).
- `n_received = n_received_wifi + n_received_lora`.
- `n_forward = n_local + n_received`. Shaman II has no mic, so `n_local = 0`
  for relays; gateways don't forward so their `E_tx` term contributes 0
  in the engine.
- `n_retries` is driven by `radio.avg_retries_per_tx` (0 by default = best-case).

### 3.3 Per-event communication chain

When a Shaman I detects an event, the engine applies:

1. **Sensor side (§3.3):**
   `E_comm_shaI = P_wifi_tx · t_tx_wifi · frames_per_hop`

2. **Parent Shaman II (§3.3):**
   `E_comm_shaII = P_wifi_rx · t_rx_wifi + (P_proc_shaII_active − P_proc_shaII_sleep) · t_proc_shaII`

3. **Walk up the tree**: for every ancestor Shaman II, add its `E_rx_lora`,
   `E_process`, and (unless it's the gateway) its `E_tx` + any CSMA retries.

### 3.4 Battery-life outputs (§3.4)

Every node reports:
```
E_remaining       = E_battery − E_consumed
percent_used      = (E_consumed / E_battery) · 100
percent_remaining = 100 − percent_used
P_average         = E_consumed / T                   (W, averaged over the run)
T_battery_life    = E_battery / P_average            (hours, projected)
```

### 3.5 LoRa `t_tx_lora` / `t_rx_lora`

Computed via the Semtech SX1276 datasheet (§4.1.1.6) time-on-air formula:

```
t_sym       = 2^SF / BW
t_preamble  = (n_preamble + 4.25) · t_sym
n_payload   = 8 + max(ceil((8·PL − 4·SF + 28 + 16) / (4·SF)) · CR, 0)
t_payload   = n_payload · t_sym
t_tx_lora   = t_preamble + t_payload
t_rx_lora   = t_tx_lora                   # receiver airtime equals transmit airtime
t_hop_lora  = t_tx_lora · frames_per_hop
```

With defaults (SF10, 125 kHz BW, CR 4/5, PL=128 B, preamble=8):
`t_tx_lora ≈ 1.231 s per frame` → `t_hop_lora ≈ 3.69 s per hop`.

---

## 4. Variable map — spec ↔ code

| Spec variable         | Code location                                 | Default |
| --------------------- | --------------------------------------------- | ------- |
| **Shaman I**          |                                               |         |
| `P_mic`               | `ShamanIConfig.P_mic`                         | 1.98 mW (0.6 mA @ 3.3V) |
| `P_mic_off`           | `ShamanIConfig.P_mic_off`                     | 0.33 mW |
| `P_proc_shaI_active`  | `ShamanIConfig.P_proc_shaI_active`            | 528 mW (160 mA @ 3.3V) |
| `P_proc_shaI_sleep`   | `ShamanIConfig.P_proc_shaI_sleep`             | 2.64 mW |
| `P_wifi_tx`           | `ShamanIConfig.P_wifi_tx`                     | 726 mW (220 mA @ 3.3V) |
| `t_proc_shaI`         | `ShamanIConfig.t_proc_shaI`                   | 30 ms (per event) |
| `t_tx_wifi`           | `ShamanIConfig.t_tx_wifi`                     | 5 ms (per frame) |
| **Shaman II**         |                                               |         |
| `P_proc_shaII_active` | `ShamanIIConfig.P_proc_shaII_active`          | 3.5 W (Radxa-class SBC) |
| `P_proc_shaII_sleep`  | `ShamanIIConfig.P_proc_shaII_sleep`           | 500 mW |
| `P_controller_active` | `ShamanIIConfig.P_controller_active`          | 528 mW |
| `P_controller_sleep`  | `ShamanIIConfig.P_controller_sleep`           | 2.64 mW |
| `P_lora_tx`           | `ShamanIIConfig.P_lora_tx`                    | 389 mW (118 mA @ 3.3V, +14 dBm) |
| `P_lora_rx`           | `ShamanIIConfig.P_lora_rx`                    | 19.8 mW (6 mA @ 3.3V) |
| `P_wifi_rx`           | `ShamanIIConfig.P_wifi_rx`                    | 330 mW (100 mA @ 3.3V) |
| `P_backoff`           | `ShamanIIConfig.P_backoff`                    | 19.8 mW (≈ `P_lora_rx`) |
| `t_proc_shaII`        | `ShamanIIConfig.t_proc_shaII`                 | 10 ms |
| `t_rx_wifi`           | `ShamanIIConfig.t_rx_wifi`                    | 5 ms |
| `t_backoff`           | `ShamanIIConfig.t_backoff`                    | 100 ms |
| `t_tx_lora`           | `RadioConfig.t_tx_lora` (derived, Semtech)    | 1.231 s |
| `t_rx_lora`           | `RadioConfig.t_rx_lora` (derived, = TX time)  | 1.231 s |
| **Battery**           |                                               |         |
| `V`, `Q`, `E_battery` | `ShamanIConfig.battery_wh` / `ShamanIIConfig.battery_wh` (Wh) | 22 Wh each |
| `T`                   | `duration_hours` request param                | 3 h |
| **Protocol**          |                                               |         |
| `frames_per_hop`      | `RadioConfig.frames_per_hop`                  | 3 (data + ACK + handshake) |
| `SF`                  | `RadioConfig.spreading_factor`                | 10 |
| `n_retries`           | runtime counter + `RadioConfig.avg_retries_per_tx` | 0 (best-case) |

### Where every default comes from
- ESP32 datasheet figures for sleep / active / WiFi TX/RX.
- Semtech SX1276 datasheet for LoRa TX/RX currents and airtime formula.
- MEMS mic datasheets for `P_mic` / `P_mic_off`.
- Radxa-class SBC for Shaman II main-processor draw (3.5 W active / 0.5 W sleep).
- `frames_per_hop = 3` directly from Kyle's email.
- Every default is overridden the moment the user fills in Configure Run.

---

## 5. Configure Run → spec mapping

The existing GUI (`frontend/src/components/CreateRun.jsx`) uses older component
names. We map them as follows — no frontend changes required:

| GUI `components` key (per node type)     | Shaman I spec variable        | Shaman II spec variable           |
| ---------------------------------------- | ----------------------------- | --------------------------------- |
| `sleep`                                  | `P_proc_shaI_sleep`           | `P_proc_shaII_sleep`              |
| `working`                                | `P_proc_shaI_active`          | `P_proc_shaII_active`             |
| `transmit`                               | `P_wifi_tx`                   | `P_lora_tx`                       |
| `receive`                                | — (sensors don't RX)          | `P_lora_rx`                       |
| `micListen`                              | `P_mic`                       | —                                 |
| `micSleep`                               | `P_mic_off`                   | —                                 |

Spec variables **not yet exposed in the GUI** (fall back to defaults until added):

- `P_controller_active` / `P_controller_sleep` (Shaman II sub-controller)
- `P_wifi_rx` (Shaman II WiFi receiver current)
- `P_backoff` (CSMA backoff-wait current)
- `t_proc_shaII`, `t_rx_wifi`, `t_backoff`
- `avg_retries_per_tx` (CSMA retry rate)

These can be added to Configure Run as a follow-up.

---

## 6. What the engine does each time step

```
for every dt (default 60 s):
    for every node:
        ΔE_baseline = P_baseline(node) · (dt / 3600)      # §3.1 or §3.2
        node.E_consumed += ΔE_baseline

    for every AI event with timestamp in [t, t+dt):
        sensor.n_local += 1
        sensor.E_consumed += P_wifi_tx · t_tx_wifi · frames / 3600   (§3.1)
        walk up the tree:
            relay.n_received_{wifi|lora} += 1   (depending on child type)
            relay.E_consumed += RX term                               (§3.2)
            relay.E_consumed += E_process term                        (§3.2)
            if not gateway:
                relay.E_consumed += E_tx term + E_retry term          (§3.2)

    record (time, battery_percent) for every node
```

`P_baseline(node)`:
- Sensor: `P_proc_shaI_active + P_mic`
- Relay / Gateway: `P_controller_sleep + P_lora_rx + P_proc_shaII_sleep`

---

## 7. End-to-end data flow

```
Configure Run modal
   │  (Shaman I config, Shaman II config, nodes, edges, mediaFiles)
   ▼
POST /api/runs/create          →  runs + network_nodes + network_edges rows

AI pipeline                    →  combined_ai_event_timeline.json
                                  (stored on disk, can be uploaded)

POST /api/battery/simulate  (run_id, configs, ai_events_path, media_files)
   │
   ├─ SimulationConfig.from_run_config(...)   ← GUI payload → spec variables
   ├─ SimNetwork.from_db_nodes(...)           ← topology graph from DB
   ├─ load_ai_events_with_stats(...)          ← events JSON → SimEvent list
   └─ BatterySimulator(...).run()             ← spec equations §3
         │
         ▼
   time-series JSON per node  +  summary  +  CSV via scripts/run_battery_sim.py
```

---

## 8. How to run it

### 8.1 Via API

```bash
curl -X POST http://localhost:8000/api/battery/simulate \
  -H 'Content-Type: application/json' \
  -d '{
        "run_id": 1,
        "duration_hours": 12,
        "time_step_seconds": 60,
        "shaman_i_config":  { ...Configure Run shaman_i payload... },
        "shaman_ii_config": { ...Configure Run shaman_ii payload... },
        "radio_config": {
            "packet_bytes": 128,
            "spreading_factor": 10,
            "frames_per_hop": 3,
            "avg_retries_per_tx": 0
        },
        "ai_events_path": "/abs/path/combined_ai_event_timeline.json",
        "media_files": {"S1": "node_001_..wav", "S2": "node_002_..wav"}
      }'
```

### 8.2 Via CLI

```bash
cd backend
source .venv/bin/activate
python scripts/run_battery_sim.py \
  --topology topology.json \
  --config configs.json \
  --ai-events /path/to/combined_ai_event_timeline.json \
  --media-files media_files.json \
  --duration-hours 12 \
  --out-csv battery.csv --out-json battery.json
```

### 8.3 Purely synthetic

```bash
python scripts/run_battery_sim.py \
  --mock-topology 3S-1R-1C \
  --duration-hours 12 --events-per-node 25 \
  --out-csv /tmp/battery.csv
```

---

## 9. Approximations explicitly called out

| Approximation                               | Why                                                               |
| ------------------------------------------- | ----------------------------------------------------------------- |
| `avg_retries_per_tx = 0` default             | No collision / channel-utilisation model yet. Raise this knob to explore contention energy. |
| WiFi airtime = 5 ms per frame (default)      | Real 802.11 airtime depends on rate + packet size. A 5 ms figure is a reasonable small-packet approximation; override via future GUI field or payload. |
| `t_proc_shaII = 10 ms` default               | Typical ESP32 / SBC packet-handling spike. Override via GUI if benched. |
| Gateway treated as Shaman II with no forward | Spec doesn't define a separate gateway equation; gateway uses Shaman II baseline + RX but `E_tx=0`. |
| Shaman I TX uses no retries                  | Spec puts the CSMA/retry model on the LoRa side; WiFi uplink assumed reliable at short range. |

---

## 10. Sensitivity knobs

| Knob                                       | Expected effect                                              |
| ------------------------------------------ | ------------------------------------------------------------ |
| 2× `P_proc_shaI_active` on Shaman I         | Sensor baseline ~doubles (dominates the budget).             |
| 2× `P_proc_shaII_sleep` on Shaman II        | Relay/gateway baseline ~doubles.                             |
| Raise `avg_retries_per_tx` 0 → 2            | Relay/gateway `E_tx` roughly triples; `n_retries` rises.     |
| Drop `spreading_factor` 10 → 7              | LoRa airtime falls ~8× → `E_tx_lora` falls proportionally.   |
| Raise `packet_bytes` 128 → 4128             | LoRa airtime rises ~30× → radio energy on relays climbs.     |
| Double `duration_hours`                     | All baselines scale linearly; event-driven scales with event count. |

Any result that is non-linear, flipped sign, or has large discontinuities in a
sweep is a bug — file an issue.
