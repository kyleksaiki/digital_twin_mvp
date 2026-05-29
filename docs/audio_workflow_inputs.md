# Required Inputs for the Node Audio Workflow

This is the current UI/backend field list for the 5-stage audio workflow. It is based on `Folder Guide.docx`, `cnn_tiny.ipynb`, `CNN_experiments.ipynb`, `modeling_human_presence_analysis_Final.ipynb`, and the runnable Python pipeline files in `backend/app/audio_workflow`.

## Per Run

- `run_id`: Unique ID for the processing run.
- `out_root`: Output folder for manifests, timelines, summaries, and backend payloads.
- `db_path`: Optional SQLite path for storing per-node timelines.
- `skip_birdnet`: Boolean for local runs where BirdNET dependencies are not installed yet.

## Per Node

- `node_id`: Digital Twin node identifier.
- `audio_path`: Local path to the single long audio file for this node.
- `metadata_json`: Optional node/window metadata JSON for contextual features (weather, human activity, etc.).
- `audio_start_timestamp`: Needed to convert timeline seconds into wall-clock time.
- `timezone`: Needed for time-of-day, sunrise/sunset, and local display.
- `latitude`: Needed by BirdNET and weather/sun calculations.
- `longitude`: Needed by BirdNET and weather/sun calculations.

## Stage 1: Event Detection / Candidate Generation

- Long node audio clip.
- Target sample rate for analysis, currently default `48000`.
- `block_seconds`: Streaming block size for multi-hour files.
- `clip_s`: Centered candidate clip duration, currently default `3.0`.
- Candidate detector thresholds:
  - `rms_z_thresh`
  - `centroid_hz_thresh`
  - `bandwidth_hz_thresh`
  - `snr_db_thresh`
  - `min_gap_s`

## Stage 2: TinyCNN Bird-Call Gate

- Candidate audio clip from Stage 1.
- TinyCNN weights path, once Griffen provides the trained artifact.
- TinyCNN threshold, currently default `0.3` from the notebook recall-prioritizing setup.
- Mel preprocessing constants:
  - `model_sr`: `22050`
  - `duration_s`: `3.0`
  - `n_mels`: `64`
  - `n_fft`: `1024`
  - `hop_length`: `512`
  - `target_frames`: `128`
- Optional normalization values from training:
  - `normalize_min`
  - `normalize_max`

## Stage 3: BirdNET

- TinyCNN-confirmed candidate clip.
- BirdNET confidence threshold, currently default `0.5`.
- Latitude and longitude.
- Date/time or week of recording if BirdNET location/time filtering is enabled.
- Output fields expected by the downstream workflow:
  - common name
  - scientific name or label
  - confidence
  - raw BirdNET detection payload

## Stage 4: Human Presence Detection

The notebook currently uses a tabular model approach. The UI should be ready to provide these fields per clip/window when available:

- `clip_name` or stable clip/window ID.
- `Recorder` or device/node ID.
- `Timestamp`
- `Timestamp Local`
- `Timestamp UTC`
- `Datetime`
- `Time Of Day`
- `Sunrise`
- `Sunset`
- `Temperature`
- `Windspeed`
- `Precipitation`
- `Humidity`
- `Weathercode`
- `Weather Desc`
- `Human Activity`
- `Human Activity Score`
- `species`
- `confidence`
- `Sim Type`
- `Sim Relative Time`

Audio feature columns used by the human-presence notebook:

- `Spectral RMS Energy`
- `Zero Crossing Rate`
- `Spectral Bandwidth`
- `Spectral Rolloff (85%)`
- `Spectral Flatness`
- `Onset Strength`
- `Spectral Contrast`
- `Spectral_Contrast_Band_1` through `Spectral_Contrast_Band_7`
- `MFCC_1` through `MFCC_13`
- `Mel_1` through `Mel_40`

Engineered features referenced by the notebook:

- `hour_sin`
- `hour_cos`
- `Eerie_Silence`
- `Volume_Wind_Ratio`
- `Volume_Spike_15s`

Sentinel species indicator columns referenced by the notebook:

- `Myiothlypis fulvicauda_Buff-rumped Warbler`
- `Habia atrimaxillaris_Black-cheeked Ant-Tanager`
- `Thamnophilus bridgesi_Black-hooded Antshrike`
- `Tinamus major_Great Tinamou`
- `Patagioenas nigrirostris_Short-billed Pigeon`
- `Ramphastos ambiguus_Yellow-throated Toucan`
- `Cyanoloxia cyanoides_Blue-black Grosbeak`
- `Lipaugus unirufus_Rufous Piha`
- `Threnetes ruckeri_Band-tailed Barbthroat`
- `Ara macao_Scarlet Macaw`

## Stage 5: Backend / Timeline Output

- `node_id`
- `run_id`
- `audio_path`
- Stage timelines:
  - `stage_1_event_candidates`
  - `stage_2_tinycnn_birdcall`
  - `stage_3_birdnet`
  - `stage_4_human_presence`
  - `combined`
- For each event:
  - `event_type`
  - `source_file`
  - `trigger_time_s`
  - `trigger_time_formatted`
  - `clip_start_s`
  - `clip_end_s`
  - stage-specific model inputs/outputs
  - `confidence`
  - `inference_ms`

