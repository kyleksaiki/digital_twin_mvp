import React, { useState } from "react";
import { createRun, fetchRunStatus, uploadAudio } from "../api";
import ModalStepper from "./common/ModalStepper";
import useStepNavigator from "../hooks/useStepNavigator";

/**
 * CreateRun - Simplified run configuration page.
 *
 * Replaces the previous interactive topology design canvas with a form-based
 * configuration interface. The map and node placement logic have been removed
 * because the simulation now focuses on a single Shaman node.
 */

const PROCESSOR_OPTIONS = ["ESP32", "Radxa Zero", "Raspberry Pi", "Custom"];

const STAGE1_FIELDS = [
  {
    key: "target_sample_rate",
    label: "Target Sample Rate (Hz)",
    type: "number",
    step: "1",
    defaultValue: 48000,
  },
  {
    key: "block_seconds",
    label: "Block Seconds",
    type: "number",
    step: "1",
    defaultValue: 60,
  },
  {
    key: "clip_s",
    label: "Clip Duration (s)",
    type: "number",
    step: "0.1",
    defaultValue: 3.0,
  },
  {
    key: "rms_z_thresh",
    label: "RMS Z Threshold",
    type: "number",
    step: "0.1",
    defaultValue: 1.2,
  },
  {
    key: "centroid_hz_thresh",
    label: "Centroid Threshold (Hz)",
    type: "number",
    step: "1",
    defaultValue: 1400,
  },
  {
    key: "bandwidth_hz_thresh",
    label: "Bandwidth Threshold (Hz)",
    type: "number",
    step: "1",
    defaultValue: 700,
  },
  {
    key: "snr_db_thresh",
    label: "SNR Threshold (dB)",
    type: "number",
    step: "0.1",
    defaultValue: 4.0,
  },
  {
    key: "min_gap_s",
    label: "Min Gap (s)",
    type: "number",
    step: "0.1",
    defaultValue: 1.5,
  },
];

const STAGE1_DEFAULTS = STAGE1_FIELDS.reduce((acc, field) => {
  acc[field.key] = field.defaultValue ?? "";
  return acc;
}, {});

const DURATION_OPTIONS = ["1h", "6h", "12h", "24h", "48h", "72h"];

const ENVIRONMENT_OPTIONS = [
  "Tropical Forest",
  "Cloud Forest",
  "Lowland Rainforest",
  "Riparian",
  "Edge / Clearing",
  "Custom",
];

const TARGET_SPECIES_PRESETS = [
  "Tinamus major (Great Tinamou)",
  "Ara macao (Scarlet Macaw)",
  "Ramphastos ambiguus (Yellow-throated Toucan)",
  "Patagioenas nigrirostris (Short-billed Pigeon)",
  "Myiothlypis fulvicauda (Buff-rumped Warbler)",
];

const COMPONENT_FIELDS = [
  { key: "sleep", label: "Processor Sleep" },
  { key: "working", label: "Processor Working" },
  { key: "transmit", label: "Radio Transmit" },
  { key: "receive", label: "Radio Receive" },
  { key: "cameraImage", label: "Camera Image" },
  { key: "cameraSleep", label: "Camera Sleep" },
  { key: "micListen", label: "Mic Listen" },
  { key: "micSleep", label: "Mic Sleep" },
];

function Cvp(current, voltage, power) {
  return {
    current: current ?? null,
    voltage: voltage ?? null,
    power: power ?? null,
  };
}

function buildDefaultComponents() {
  return COMPONENT_FIELDS.reduce((acc, field) => {
    acc[field.key] = Cvp();
    return acc;
  }, {});
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") return "";
  return value;
}

export default function CreateRun({ onRunCreated }) {
  const [runName, setRunName] = useState("");
  const [description, setDescription] = useState("");
  const [environment, setEnvironment] = useState("Tropical Forest");
  const [targetSpecies, setTargetSpecies] = useState([]);
  const [sensitivity, setSensitivity] = useState(0.5);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.75);
  const [sampleRate, setSampleRate] = useState(48000);
  const [duration, setDuration] = useState("24h");
  const [scenario, setScenario] = useState("MVP Simulation");
  const [shamanProcessor, setShamanProcessor] = useState("ESP32");
  const [batteryCapacity, setBatteryCapacity] = useState(30);
  const [components, setComponents] = useState(buildDefaultComponents);
  const [stage1Config, setStage1Config] = useState({ ...STAGE1_DEFAULTS });
  const [audioFile, setAudioFile] = useState(null);
  const [workflow, setWorkflow] = useState("configure"); // "configure" | "loading" | "confirm"
  const [confirmMessage, setConfirmMessage] = useState("");
  const [validationError, setValidationError] = useState("");

  const stepDefs = [
    { id: "general", title: "General" },
    { id: "environment", title: "Environment & Target" },
    { id: "parameters", title: "Parameters" },
    { id: "power", title: "Power Configuration" },
    { id: "stage1", title: "Stage 1: Filtering" },
    { id: "review", title: "Review & Submit" },
  ];

  const {
    activeIndex: currentStep,
    next: goNext,
    prev: goBack,
    reset: resetSteps,
  } = useStepNavigator(stepDefs.length);

  const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  async function waitForRunCompletion(runId, timeoutMs = 30 * 60 * 1000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const statusRes = await fetchRunStatus(runId);
      const status = String(statusRes?.status || "").toLowerCase();
      if (status === "complete" || status === "pass") {
        return statusRes;
      }
      if (status === "failed" || status === "fail") {
        throw new Error("Audio processing failed");
      }
      await delay(2000);
    }
    throw new Error("Audio processing timed out");
  }

  function updateComponent(key, field, value) {
    setComponents((prev) => ({
      ...prev,
      [key]: { ...prev[key], [field]: value === "" ? null : Number(value) },
    }));
  }

  function updateStage1(key, value) {
    setStage1Config((prev) => ({
      ...prev,
      [key]: value === "" ? "" : Number(value),
    }));
  }

  function toggleTargetSpecies(species) {
    setTargetSpecies((prev) =>
      prev.includes(species)
        ? prev.filter((s) => s !== species)
        : [...prev, species],
    );
  }

  function validateStep(stepIndex) {
    if (stepIndex === 0) {
      if (!runName.trim()) {
        return "Run Name is required.";
      }
      if (!scenario.trim()) {
        return "Scenario is required.";
      }
    }
    if (stepIndex === 1) {
      if (!environment.trim()) {
        return "Please select an environment.";
      }
      if (targetSpecies.length === 0) {
        return "Select at least one target species.";
      }
    }
    if (stepIndex === 2) {
      if (!(Number(sensitivity) > 0 && Number(sensitivity) <= 1)) {
        return "Sensitivity must be between 0 and 1.";
      }
      if (
        !(Number(confidenceThreshold) > 0 && Number(confidenceThreshold) <= 1)
      ) {
        return "Confidence Threshold must be between 0 and 1.";
      }
      if (!(Number(sampleRate) >= 8000 && Number(sampleRate) <= 192000)) {
        return "Sample Rate must be between 8000 and 192000 Hz.";
      }
    }
    return "";
  }

  function handleNext() {
    const error = validateStep(currentStep);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError("");
    goNext();
  }

  async function submitRun() {
    setWorkflow("loading");

    try {
      let mediaFiles = {};
      if (audioFile) {
        const response = await uploadAudio({
          file: audioFile,
          nodeId: "SHAMAN",
        });
        if (response?.saved_path) {
          mediaFiles.SHAMAN = response.saved_path;
        }
      }

      const runData = {
        name:
          runName ||
          `Run-${new Date().toISOString().split("T")[0]}-${Date.now() % 10000}`,
        description,
        scenario,
        environment,
        targetSpecies,
        sensitivity: Number(sensitivity),
        confidenceThreshold: Number(confidenceThreshold),
        sampleRate: Number(sampleRate),
        shamanProcessor,
        duration,
        status: "pass",
        nodes: [
          {
            id: "SHAMAN",
            label: "Shaman Node",
            role: "sensor",
            x: 0.5,
            y: 0.5,
          },
        ],
        edges: [],
        mediaFiles,
        shamanConfig: {
          batteryLife: batteryCapacity,
          components,
        },
        stage1Config,
      };

      const result = await createRun(runData);

      if (Object.keys(mediaFiles).length > 0) {
        await waitForRunCompletion(result.id);
      }

      setWorkflow("confirm");
      setConfirmMessage(
        `Simulation created successfully!\n\nRun ID: ${result.id}\nRun Name: ${result.name}`,
      );
    } catch (err) {
      setWorkflow("confirm");
      setConfirmMessage(`Simulation failed: ${err.message || "Unknown error"}`);
    }
  }

  function closeConfirmation() {
    setWorkflow("configure");
    resetSteps();
    setConfirmMessage("");
    setValidationError("");
    setRunName("");
    setDescription("");
    setEnvironment("Tropical Forest");
    setTargetSpecies([]);
    setSensitivity(0.5);
    setConfidenceThreshold(0.75);
    setSampleRate(48000);
    setDuration("24h");
    setScenario("MVP Simulation");
    setShamanProcessor("ESP32");
    setBatteryCapacity(30);
    setComponents(buildDefaultComponents());
    setStage1Config({ ...STAGE1_DEFAULTS });
    setAudioFile(null);
    if (onRunCreated) onRunCreated();
  }

  const stepContent = [
    // Step 0: General
    <div key="general" className="modal-section">
      <div className="modal-label">General Configuration</div>

      <div className="scp-input-group">
        <label className="scp-label">Run Name *</label>
        <input
          type="text"
          className="scp-input"
          value={runName}
          onChange={(e) => setRunName(e.target.value)}
          placeholder="My Shaman Run"
        />
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Description</label>
        <textarea
          className="scp-input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Short summary of what this run is testing…"
          rows={3}
          style={{ resize: "vertical", minHeight: 60, fontFamily: "inherit" }}
        />
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Scenario *</label>
        <input
          type="text"
          className="scp-input"
          value={scenario}
          onChange={(e) => setScenario(e.target.value)}
        />
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Duration</label>
        <select
          className="scp-input"
          value={duration}
          onChange={(e) => setDuration(e.target.value)}
        >
          {DURATION_OPTIONS.map((d) => (
            <option key={d} value={d}>
              {d}
            </option>
          ))}
        </select>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Shaman Processor</label>
        <select
          className="scp-input"
          value={shamanProcessor}
          onChange={(e) => setShamanProcessor(e.target.value)}
        >
          {PROCESSOR_OPTIONS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Node Audio (optional)</label>
        <input
          type="file"
          accept="audio/*"
          onChange={(e) => setAudioFile(e.target.files?.[0] || null)}
        />
        {audioFile && (
          <div
            style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 6 }}
          >
            {audioFile.name}
          </div>
        )}
      </div>
    </div>,

    // Step 1: Environment & Target
    <div key="environment" className="modal-section">
      <div className="modal-label">Environment & Target</div>

      <div className="scp-input-group">
        <label className="scp-label">Environment *</label>
        <select
          className="scp-input"
          value={environment}
          onChange={(e) => setEnvironment(e.target.value)}
        >
          {ENVIRONMENT_OPTIONS.map((env) => (
            <option key={env} value={env}>
              {env}
            </option>
          ))}
        </select>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Target Species *</label>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 6,
            padding: 6,
            border: "1px solid var(--border)",
            borderRadius: 4,
            background: "var(--bg-tertiary)",
          }}
        >
          {TARGET_SPECIES_PRESETS.map((species) => {
            const checked = targetSpecies.includes(species);
            return (
              <label
                key={species}
                className="scp-radio"
                style={{ padding: "4px 6px" }}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleTargetSpecies(species)}
                />
                <span style={{ fontSize: 10 }}>{species}</span>
              </label>
            );
          })}
        </div>
        <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
          {targetSpecies.length} selected
        </div>
      </div>
    </div>,

    // Step 2: Parameters
    <div key="parameters" className="modal-section">
      <div className="modal-label">Parameters</div>

      <div className="scp-input-group">
        <label className="scp-label">
          Detection Sensitivity ({Number(sensitivity).toFixed(2)})
        </label>
        <input
          type="range"
          min="0"
          max="1"
          step="0.01"
          value={sensitivity}
          onChange={(e) => setSensitivity(Number(e.target.value))}
          style={{ width: "100%" }}
        />
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Confidence Threshold</label>
        <input
          type="number"
          className="scp-input"
          value={confidenceThreshold}
          onChange={(e) => setConfidenceThreshold(e.target.value)}
          step="0.01"
          min="0"
          max="1"
        />
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Target Sample Rate (Hz)</label>
        <input
          type="number"
          className="scp-input"
          value={sampleRate}
          onChange={(e) => setSampleRate(e.target.value)}
          step="1000"
          min="8000"
          max="192000"
        />
      </div>
    </div>,

    // Step 1: Power
    <div key="power" className="modal-section">
      <div className="modal-label">Shaman Power Configuration</div>

      <div className="scp-input-group">
        <label className="scp-label">Battery Capacity (Wh)</label>
        <input
          type="number"
          className="scp-input"
          value={batteryCapacity}
          onChange={(e) => setBatteryCapacity(Number(e.target.value))}
          step="0.1"
        />
      </div>

      <div
        style={{
          fontSize: 10,
          color: "var(--text-muted)",
          margin: "12px 0",
          lineHeight: 1.4,
        }}
      >
        Enter <strong>Current (mA) + Voltage (V)</strong> OR just{" "}
        <strong>Power (W)</strong> for each component.
      </div>

      <div style={{ overflowX: "auto" }}>
        <table
          style={{ width: "100%", fontSize: 10, borderCollapse: "collapse" }}
        >
          <thead>
            <tr
              style={{
                borderBottom: "1px solid var(--border)",
                fontWeight: 600,
              }}
            >
              <th style={{ padding: "8px 4px", textAlign: "left" }}>
                Component
              </th>
              <th style={{ padding: "8px 4px", textAlign: "right" }}>
                Current (mA)
              </th>
              <th style={{ padding: "8px 4px", textAlign: "right" }}>
                Voltage (V)
              </th>
              <th style={{ padding: "8px 4px", textAlign: "right" }}>
                Power (W)
              </th>
            </tr>
          </thead>
          <tbody>
            {COMPONENT_FIELDS.map(({ key, label }) => {
              const cvp = components[key] || Cvp();
              return (
                <tr
                  key={key}
                  style={{ borderBottom: "1px solid var(--border-muted)" }}
                >
                  <td style={{ padding: "8px 4px" }}>{label}</td>
                  <td style={{ padding: "4px" }}>
                    <input
                      type="number"
                      className="scp-input"
                      placeholder="—"
                      value={formatNumber(cvp.current)}
                      onChange={(e) =>
                        updateComponent(key, "current", e.target.value)
                      }
                      step="0.1"
                      style={{ width: "100%" }}
                    />
                  </td>
                  <td style={{ padding: "4px" }}>
                    <input
                      type="number"
                      className="scp-input"
                      placeholder="—"
                      value={formatNumber(cvp.voltage)}
                      onChange={(e) =>
                        updateComponent(key, "voltage", e.target.value)
                      }
                      step="0.1"
                      style={{ width: "100%" }}
                    />
                  </td>
                  <td style={{ padding: "4px" }}>
                    <input
                      type="number"
                      className="scp-input"
                      placeholder="—"
                      value={formatNumber(cvp.power)}
                      onChange={(e) =>
                        updateComponent(key, "power", e.target.value)
                      }
                      step="0.001"
                      style={{ width: "100%" }}
                    />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>,

    // Step 2: Stage 1
    <div key="stage1" className="modal-section">
      <div className="modal-label">Stage 1: Audio Filtering</div>
      <div
        style={{
          fontSize: 10,
          color: "var(--text-muted)",
          marginBottom: 12,
          lineHeight: 1.4,
        }}
      >
        Configure the parameters for the first stage of the audio pipeline.
      </div>

      {STAGE1_FIELDS.map((field) => (
        <div className="scp-input-group" key={field.key}>
          <label className="scp-label">{field.label}</label>
          <input
            type={field.type}
            className="scp-input"
            value={stage1Config[field.key]}
            onChange={(e) => updateStage1(field.key, e.target.value)}
            step={field.step}
          />
        </div>
      ))}
    </div>,

    // Step 5: Review
    <div key="review" className="modal-section">
      <div className="modal-label">Review Configuration</div>
      <div
        style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 12 }}
      >
        Confirm the run settings before submitting.
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Run Name</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {runName || "(auto-generated)"}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Description</label>
        <div
          className="scp-input"
          style={{ background: "var(--bg-muted)", whiteSpace: "pre-wrap" }}
        >
          {description || "(none)"}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Scenario</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {scenario}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Environment</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {environment}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Target Species</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {targetSpecies.length > 0 ? targetSpecies.join(", ") : "(none)"}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">
          Sensitivity / Confidence / Sample Rate
        </label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {Number(sensitivity).toFixed(2)} /{" "}
          {Number(confidenceThreshold).toFixed(2)} / {sampleRate} Hz
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Duration</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {duration}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Shaman Processor</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {shamanProcessor}
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Battery Capacity</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {batteryCapacity} Wh
        </div>
      </div>

      <div className="scp-input-group">
        <label className="scp-label">Reference Audio</label>
        <div className="scp-input" style={{ background: "var(--bg-muted)" }}>
          {audioFile ? audioFile.name : "(none)"}
        </div>
      </div>
    </div>,
  ];

  return (
    <div style={{ overflowY: "auto", padding: 24 }}>
      <div className="pg-header">
        <div>
          <div className="pg-title">Create New Run</div>
          <p>Configure a simulation run for a single Shaman node.</p>
        </div>
      </div>

      {workflow === "configure" && (
        <div className="create-run-config">
          <ModalStepper
            steps={stepDefs.map((s) => s.title)}
            currentStep={currentStep}
          />
          <div className="modal-content">
            {validationError && (
              <div
                style={{
                  padding: "8px 12px",
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: 4,
                  color: "var(--red)",
                  fontSize: 12,
                  marginBottom: 12,
                }}
              >
                {validationError}
              </div>
            )}
            {stepContent[currentStep]}
            <div className="modal-actions">
              <button
                className="btn"
                onClick={goBack}
                disabled={currentStep === 0}
              >
                Back
              </button>
              {currentStep < stepDefs.length - 1 ? (
                <button className="btn btn-primary" onClick={handleNext}>
                  Next
                </button>
              ) : (
                <button className="btn btn-primary" onClick={submitRun}>
                  Submit Run
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {workflow === "loading" && (
        <div className="create-run-config">
          <div
            className="modal-content"
            style={{ textAlign: "center", padding: 48 }}
          >
            <div className="loading-spinner" />
            <div style={{ marginTop: 12, color: "var(--text-muted)" }}>
              Submitting run…
            </div>
          </div>
        </div>
      )}

      {workflow === "confirm" && (
        <div className="create-run-config">
          <div
            className="modal-content"
            style={{ textAlign: "center", padding: 48 }}
          >
            <div className="pg-title" style={{ marginBottom: 12 }}>
              {confirmMessage.startsWith("Simulation created")
                ? "Run Created"
                : "Run Failed"}
            </div>
            <pre
              style={{
                color: "var(--text-muted)",
                fontSize: 12,
                whiteSpace: "pre-wrap",
                marginBottom: 24,
              }}
            >
              {confirmMessage}
            </pre>
            <button className="btn btn-primary" onClick={closeConfirmation}>
              Continue
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
