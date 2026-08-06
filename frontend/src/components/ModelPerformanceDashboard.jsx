import React, { useEffect, useState } from "react";
import { fetchDashboard } from "../api";
import { ResponsiveBarChart } from "./common/SimpleCharts";

/**
 * Model Performance — tabbed by pipeline model.
 *
 * Only the AED (acoustic event detection) model is integrated today, so only
 * that tab shows data. The remaining stages run as pass-through placeholders
 * in the pipeline; their tabs say so plainly instead of rendering fake stats.
 * Each will become a real page when its trained model lands.
 *
 * Everything on the AED tab is measured from this run's actual processing.
 * When a ground-truth log was supplied at run creation, recall and precision
 * are measured against it; otherwise those cards fall back to what is
 * measurable without labels (confidence, clips scored).
 */

const MODEL_TABS = [
  { id: "aed", label: "AED Detection", ready: true },
  { id: "features", label: "Feature Extraction", ready: false },
  { id: "context", label: "Context Enrichment", ready: false },
  { id: "presence", label: "Human Presence", ready: false },
];

const PLACEHOLDER_COPY = {
  features: {
    title: "Feature Extraction",
    body:
      "This stage currently computes spectral and MFCC features as a fixed " +
      "pass-through — there is no trained model to evaluate yet. When the " +
      "feature model is integrated, this page will show its performance.",
  },
  context: {
    title: "Context Enrichment",
    body:
      "This stage currently merges node metadata and time-of-day context as " +
      "a fixed pass-through — there is no trained model to evaluate yet. " +
      "When the context model is integrated, this page will show its " +
      "performance.",
  },
  presence: {
    title: "Human Presence Classification",
    body:
      "The human-presence classifier is a placeholder awaiting the trained " +
      "model. Until it lands, every AED detection is labeled Wildlife and " +
      "this page intentionally shows nothing. When the model is integrated, " +
      "this page will show its measured performance.",
  },
};

function metricClassHigherBetter(value, goodMin, warnMin) {
  if (value == null) return "";
  if (value >= goodMin) return "pass-state";
  if (value >= warnMin) return "warn-state";
  return "fail-state";
}

function formatAudioDuration(seconds) {
  const s = Number(seconds) || 0;
  if (s <= 0) return "0 min";
  if (s < 90) return `${s.toFixed(0)} s`;
  if (s < 5400) return `${(s / 60).toFixed(1)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

function formatWall(ms) {
  const s = (Number(ms) || 0) / 1000;
  if (s <= 0) return "—";
  if (s < 90) return `${s.toFixed(1)} s`;
  return `${(s / 60).toFixed(1)} min`;
}

export default function ModelPerformanceDashboard({ run }) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("aed");

  useEffect(() => {
    if (!run?.id) return;
    let mounted = true;
    setLoading(true);
    fetchDashboard(run.id)
      .then((data) => {
        if (!mounted) return;
        setDashboard(data);
        setLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setDashboard(null);
        setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [run?.id]);

  if (!run) {
    return (
      <div id="pageModelPerformance" style={{ overflowY: "auto", padding: 24 }}>
        <div
          style={{
            color: "var(--text-muted)",
            textAlign: "center",
            marginTop: 60,
            fontSize: 14,
          }}
        >
          Select a run from the Run Selector to view model performance.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div id="pageModelPerformance" style={{ overflowY: "auto", padding: 24 }}>
        <div
          style={{
            color: "var(--text-muted)",
            textAlign: "center",
            marginTop: 60,
            fontSize: 14,
          }}
        >
          Loading model performance…
        </div>
      </div>
    );
  }

  const metrics = dashboard?.metrics || {};
  const runData = dashboard?.run || run;
  const pipelineStats = dashboard?.pipeline_stats || {};
  const processing = dashboard?.processing || null;
  const groundTruth = dashboard?.ground_truth || null;
  const hasProcessed = Boolean(processing && processing.clips_scored > 0);
  const hasTruth = Boolean(groundTruth && groundTruth.total_events > 0);

  const s1 = pipelineStats.stage1 || {};

  // Detection funnel: how one hour of audio narrows to confirmed detections.
  // Neutral wording on purpose — windows without a trigger are background the
  // prefilter correctly discarded, not failures.
  const funnelData = [
    { label: "3 s windows scanned", value: Number(s1.entered) || 0, color: "#334155" },
    { label: "Prefilter triggers", value: Number(s1.passed) || 0, color: "#3b82f6" },
  ];

  const meanConfidence = processing ? Number(processing.mean_confidence) || 0 : 0;
  const confidenceData = (processing?.confidence_histogram || []).map((bin) => ({
    label: bin.label,
    value: Number(bin.count) || 0,
    color: "#6366f1",
  }));

  const truthTypeData = hasTruth
    ? (groundTruth.by_type || []).map((t) => ({
        label: `${t.label} (${t.matched}/${t.total})`,
        value: Math.round((Number(t.recall) || 0) * 100),
        color: "#10b981",
      }))
    : [];

  const statusChipClass =
    runData.status === "fail"
      ? "chip-fail"
      : runData.status === "warning"
        ? "chip-warn"
        : "chip-pass";

  const activeTab = MODEL_TABS.find((t) => t.id === tab) || MODEL_TABS[0];

  return (
    <div id="pageModelPerformance" style={{ overflowY: "auto", padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="pg-title">Model Performance</div>
          <div className="loaded-run-bar" style={{ marginTop: 6 }}>
            <div className="dot"></div>
            <span>Loaded Run: {runData.name}</span>
            <span className={statusChipClass} style={{ marginLeft: 8 }}>
              {runData.status || "unknown"}
            </span>
            <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
              {hasProcessed
                ? `${formatAudioDuration(processing.audio_seconds)} of audio processed`
                : "No audio processed for this run"}
            </span>
          </div>
        </div>

        <div
          style={{
            display: "flex",
            gap: 6,
            marginBottom: 18,
            flexWrap: "wrap",
          }}
        >
          {MODEL_TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={tab === t.id ? "btn-primary" : "btn-secondary"}
              style={{
                opacity: t.ready || tab === t.id ? 1 : 0.55,
                fontSize: 12,
                padding: "6px 12px",
              }}
            >
              {t.label}
              {!t.ready && (
                <span style={{ marginLeft: 6, fontSize: 10, opacity: 0.8 }}>
                  (pending)
                </span>
              )}
            </button>
          ))}
        </div>

        {activeTab.ready ? (
          <>
            <div className="metrics-row">
              <div className="metric-card pass-state">
                <div className="m-label">
                  Detections{" "}
                  <span className="help-icon">
                    ?
                    <span className="help-tip">
                      Clips the AED model confirmed as meaningful audio in this
                      run.
                    </span>
                  </span>
                </div>
                <div className="m-value">
                  {Number(metrics.detection_count) || 0}
                </div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  {hasProcessed ? "From processed audio" : "No audio processed yet"}
                </div>
              </div>

              {hasTruth ? (
                <div
                  className={`metric-card ${metricClassHigherBetter(groundTruth.recall * 100, 85, 60)}`}
                >
                  <div className="m-label">
                    Event Recall{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Measured on this run: share of ground-truth events the
                        AED pipeline detected at least once.
                      </span>
                    </span>
                  </div>
                  <div className="m-value">
                    {(groundTruth.recall * 100).toFixed(1)}%
                  </div>
                  <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                    {`${groundTruth.matched_events} of ${groundTruth.total_events} events found`}
                  </div>
                </div>
              ) : (
                <div
                  className={`metric-card ${hasProcessed ? metricClassHigherBetter(meanConfidence * 100, 70, 40) : ""}`}
                >
                  <div className="m-label">
                    Mean Detection Confidence{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Average AED confidence across every scored clip. Supply
                        the generator's ground-truth log at run creation to see
                        measured recall instead.
                      </span>
                    </span>
                  </div>
                  <div className="m-value">
                    {(meanConfidence * 100).toFixed(1)}%
                  </div>
                  <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                    {hasProcessed
                      ? `Across ${processing.clips_scored} scored clips`
                      : "No clips scored yet"}
                  </div>
                </div>
              )}

              {hasTruth ? (
                <div
                  className={`metric-card ${metricClassHigherBetter(groundTruth.precision * 100, 85, 60)}`}
                >
                  <div className="m-label">
                    Detection Precision{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Measured on this run: share of detections that landed on
                        a real ground-truth event.
                      </span>
                    </span>
                  </div>
                  <div className="m-value">
                    {(groundTruth.precision * 100).toFixed(1)}%
                  </div>
                  <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                    {`${groundTruth.false_positive_detections} false alarms`}
                  </div>
                </div>
              ) : (
                <div className="metric-card">
                  <div className="m-label">
                    Clips Scored{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Candidate clips the AED model actually scored in this
                        run.
                      </span>
                    </span>
                  </div>
                  <div className="m-value">
                    {processing ? processing.clips_scored : 0}
                  </div>
                  <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                    {hasProcessed ? "By the AED model" : "No clips scored yet"}
                  </div>
                </div>
              )}

              <div className="metric-card">
                <div className="m-label">
                  Inference Latency{" "}
                  <span className="help-icon">
                    ?
                    <span className="help-tip">
                      Mean per-clip AED model inference time on the backend.
                    </span>
                  </span>
                </div>
                <div className="m-value">{Number(metrics.latency_ms) || 0} ms</div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  {hasProcessed
                    ? `On ${processing.device || "cpu"}`
                    : "Not yet measured"}
                </div>
              </div>

              <div className="metric-card">
                <div className="m-label">
                  Audio Processed{" "}
                  <span className="help-icon">
                    ?
                    <span className="help-tip">
                      Length of uploaded audio analyzed, and how long the
                      pipeline took to process it.
                    </span>
                  </span>
                </div>
                <div className="m-value">
                  {formatAudioDuration(processing?.audio_seconds)}
                </div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  {hasProcessed
                    ? `Processed in ${formatWall(processing.wall_ms)}`
                    : "Upload audio in Configure Run"}
                </div>
              </div>
            </div>

            <div className="charts-grid">
              <div className="chart-box">
                <div className="chart-hdr">
                  <div className="chart-title">
                    Detection Funnel{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        How the audio narrows to detections: every 3 s window is
                        scanned, the prefilter flags candidate windows, and the
                        AED model confirms which contain meaningful audio.
                        Windows without a trigger are background the prefilter
                        correctly discarded.
                      </span>
                    </span>
                  </div>
                </div>
                <ResponsiveBarChart
                  data={funnelData}
                  compact
                  preserveOrder
                  emptyText="No pipeline data yet"
                  valueFormatter={(value) => `${value}`}
                />
              </div>

              <div className="chart-box">
                <div className="chart-hdr">
                  <div className="chart-title">
                    AED Confidence Distribution{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Model confidence across every scored clip (10% bins). A
                        healthy run clusters at the extremes — the model is sure
                        either way.
                      </span>
                    </span>
                  </div>
                </div>
                <ResponsiveBarChart
                  data={confidenceData}
                  compact
                  compactRowLimit={10}
                  preserveOrder
                  emptyText="No clips scored yet"
                  valueFormatter={(value) => `${value}`}
                />
              </div>

              {hasTruth && (
                <div className="chart-box">
                  <div className="chart-hdr">
                    <div className="chart-title">
                      Measured Against Ground Truth{" "}
                      <span className="help-icon">
                        ?
                        <span className="help-tip">
                          Detections compared against the event log supplied at
                          run creation. Everything here is measured on this
                          run's own audio.
                        </span>
                      </span>
                    </div>
                  </div>
                  <ResponsiveBarChart
                    data={truthTypeData}
                    compact
                    preserveOrder
                    emptyText="No per-type breakdown"
                    valueFormatter={(value) => `${value}%`}
                  />
                </div>
              )}

            </div>
          </>
        ) : (
          <div className="chart-box" style={{ maxWidth: 640 }}>
            <div className="chart-hdr">
              <div className="chart-title">
                {PLACEHOLDER_COPY[activeTab.id]?.title || activeTab.label}
              </div>
              <div className="chip">model pending</div>
            </div>
            <div
              style={{
                color: "var(--text-muted)",
                fontSize: 13,
                lineHeight: 1.7,
                padding: "8px 2px 12px",
              }}
            >
              {PLACEHOLDER_COPY[activeTab.id]?.body}
            </div>
            <div
              style={{
                display: "flex",
                gap: 16,
                paddingTop: 10,
                borderTop: "1px solid var(--border, rgba(148,163,184,0.25))",
              }}
            >
              {["Passed", "Failed", "Mean ms"].map((label) => (
                <div key={label}>
                  <div className="m-label">{label}</div>
                  <div className="m-value" style={{ opacity: 0.35 }}>
                    0
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}