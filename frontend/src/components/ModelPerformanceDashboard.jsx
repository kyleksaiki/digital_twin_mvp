import React, { useEffect, useState } from "react";
import { fetchDashboard } from "../api";
import Modal from "./common/Modal";
import { ResponsiveBarChart } from "./common/SimpleCharts";

/**
 * ModelPerformanceDashboard
 *
 * Refocused dashboard that highlights the AI model performance and the
 * five-stage audio pipeline. The previous latency and battery sections have
 * been removed; battery information is now surfaced on the dedicated Battery
 * Statistics page.
 */

function metricClassHigherBetter(value, goodMin, warnMin) {
  if (value == null) return "";
  if (value >= goodMin) return "pass-state";
  if (value >= warnMin) return "warn-state";
  return "fail-state";
}

function metricClassLowerBetter(value, goodMax, warnMax) {
  if (value == null) return "";
  if (value <= goodMax) return "pass-state";
  if (value <= warnMax) return "warn-state";
  return "fail-state";
}

const PIPELINE_STAGES = [
  { id: "stage1", label: "Stage 1: Audio Filtering" },
  { id: "stage2", label: "Stage 2: Event Detection" },
  { id: "stage3", label: "Stage 3: Feature Extraction" },
  { id: "stage4", label: "Stage 4: Context Enrichment" },
  { id: "stage5", label: "Stage 5: AI Classification" },
];

function buildStageChartData(pipelineStats) {
  return PIPELINE_STAGES.map((stage) => {
    const stats = pipelineStats?.[stage.id] || {};
    const passed = Number(stats.passed) || 0;
    const failed = Number(stats.failed) || 0;
    return { label: stage.label.replace(/^Stage \d+: /, ""), value: passed, failed };
  });
}

export default function ModelPerformanceDashboard({ run }) {
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [stageModal, setStageModal] = useState({ open: false, stageId: null });

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
  const detectionsData = (dashboard?.detections_by_type || [])
    .map((item) => ({
      label: item.event_type || item.label || "Unknown",
      value: Number(item.count) || 0,
    }))
    .sort((a, b) => b.value - a.value);

  const pipelineStats = dashboard?.pipeline_stats || {};
  const stageChartData = buildStageChartData(pipelineStats);
  const totalEvents = stageChartData.reduce(
    (sum, s) => sum + s.value + (s.failed || 0),
    0,
  );
  const totalFailed = stageChartData.reduce((sum, s) => sum + (s.failed || 0), 0);
  const selectedStage = stageModal.stageId
    ? PIPELINE_STAGES.find((s) => s.id === stageModal.stageId)
    : null;
  const selectedStageData = selectedStage
    ? (() => {
        const stats = pipelineStats[selectedStage.id] || {};
        const detail = Array.isArray(stats.details) ? stats.details : [];
        return detail.map((item) => ({
          label: item.label || item.name || "Unknown",
          value: Number(item.count) || 0,
        }));
      })()
    : [];

  const statusChipClass =
    runData.status === "fail"
      ? "chip-fail"
      : runData.status === "warning"
        ? "chip-warn"
        : "chip-pass";

  return (
    <div id="pageModelPerformance" style={{ overflowY: "auto", padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="pg-title">Model Performance Dashboard</div>
          <div className="loaded-run-bar" style={{ marginTop: 6 }}>
            <div className="dot"></div>
            <span>Loaded Run: {runData.name}</span>
            <span className={statusChipClass} style={{ marginLeft: 8 }}>
              {runData.status || "unknown"}
            </span>
          </div>
        </div>

        <div className="metrics-row">
          <div
            className={`metric-card ${metricClassHigherBetter(metrics.accuracy, 90, 80)}`}
          >
            <div className="m-label">
              AI Accuracy{" "}
              <span className="help-icon">
                ?
                <span className="help-tip">
                  Percentage of correct detections out of total events in the
                  scenario pack. Higher is better.
                </span>
              </span>
            </div>
            <div className="m-value">
              {metrics.accuracy != null ? `${metrics.accuracy}%` : "—"}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Baseline pending
            </div>
          </div>

          <div
            className={`metric-card ${metricClassLowerBetter(metrics.fpr, 5, 10)}`}
          >
            <div className="m-label">
              False Positive Rate{" "}
              <span className="help-icon">
                ?
                <span className="help-tip">
                  Percentage of false detections out of all positive detections.
                  Lower is better.
                </span>
              </span>
            </div>
            <div className="m-value">
              {metrics.fpr != null ? `${metrics.fpr}%` : "—"}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Baseline pending
            </div>
          </div>

          <div className="metric-card pass-state">
            <div className="m-label">
              Detection Count{" "}
              <span className="help-icon">
                ?
                <span className="help-tip">
                  Total number of AI detections during this run.
                </span>
              </span>
            </div>
            <div className="m-value">
              {metrics.detection_count != null ? metrics.detection_count : "—"}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Total for run
            </div>
          </div>

          <div className="metric-card pass-state">
            <div className="m-label">
              Pipeline Pass Rate{" "}
              <span className="help-icon">
                ?
                <span className="help-tip">
                  Share of audio events that successfully completed all five
                  pipeline stages.
                </span>
              </span>
            </div>
            <div className="m-value">
              {totalEvents > 0
                ? `${Math.round(((totalEvents - totalFailed) / totalEvents) * 100)}%`
                : "—"}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              {totalEvents - totalFailed} of {totalEvents} events
            </div>
          </div>
        </div>

        <div className="charts-grid">

          
          <div className="chart-box chart-clickable">
            <div className="chart-hdr">
              <div className="chart-title">
                Detections by Type{" "}
                <span className="help-icon">
                  ?
                  <span className="help-tip">
                    Distribution of detected event categories for this run.
                  </span>
                </span>
              </div>
            </div>
            <ResponsiveBarChart
              data={detectionsData}
              compact
              emptyText="No detection data"
              valueFormatter={(value) => `${value}`}
            />
          </div>
          <div className="chart-box">
            <div className="chart-hdr">
              <div className="chart-title">
                Audio Pipeline Pass / Fail{" "}
                <span className="help-icon">
                  ?
                  <span className="help-tip">
                    Number of audio events that passed or failed at each stage
                    of the five-stage pipeline.
                  </span>
                </span>
              </div>
            </div>
            <ResponsiveBarChart
              data={stageChartData.map((s) => ({ label: s.label, value: s.value }))}
              compact
              emptyText="No pipeline data"
              valueFormatter={(value) => `${value}`}
            />
          </div>

        </div>

        <div className="pipeline-grid">
          {PIPELINE_STAGES.map((stage) => {
            const stats = pipelineStats[stage.id] || {};
            const passed = Number(stats.passed) || 0;
            const failed = Number(stats.failed) || 0;
            const total = passed + failed;
            const passRate = total > 0 ? Math.round((passed / total) * 100) : null;
            return (
              <div
                key={stage.id}
                className="pipeline-card chart-clickable"
                onClick={() => setStageModal({ open: true, stageId: stage.id })}
              >
                <div className="pipeline-card-hdr">
                  <div className="chart-title">{stage.label}</div>
                  <div
                    className={`chip ${passRate == null ? "" : passRate >= 80 ? "chip-pass" : passRate >= 50 ? "chip-warn" : "chip-fail"}`}
                  >
                    {passRate != null ? `${passRate}% pass` : "No data"}
                  </div>
                </div>
                <div className="pipeline-stats">
                  <div className="pipeline-stat">
                    <div className="m-label">Passed</div>
                    <div className="m-value">{passed}</div>
                  </div>
                  <div className="pipeline-stat">
                    <div className="m-label">Failed</div>
                    <div className="m-value">{failed}</div>
                  </div>
                  <div className="pipeline-stat">
                    <div className="m-label">Total</div>
                    <div className="m-value">{total}</div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <Modal
        open={stageModal.open}
        title={selectedStage ? `${selectedStage.label} — Details` : "Stage Details"}
        subtitle="Per-event outcomes for the selected pipeline stage"
        onClose={() => setStageModal({ open: false, stageId: null })}
      >
        <ResponsiveBarChart
          data={selectedStageData}
          emptyText="No detail data"
          valueFormatter={(value) => `${value}`}
        />
      </Modal>
    </div>
  );
}
