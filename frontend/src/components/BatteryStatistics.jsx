import React, { useEffect, useState } from "react";
import { fetchBatteryStats } from "../api";
import { LineTrendChart, PieChart } from "./common/SimpleCharts";

/**
 * BatteryStatistics
 *
 * Shows the single-node battery simulation for the loaded run:
 *   1. Battery over time (line chart)
 *   2. Energy consumption breakdown by component (bar chart)
 *
 * Every number comes from the stored simulator output (GET /runs/{id}/battery).
 * There is no fabricated or back-extrapolated data: if a run has no simulation
 * recorded, the page renders its full layout with zeroed values rather than
 * inventing a curve or blanking out.
 */

const SIM_COMPONENT_LABELS = {
  microphone: "Microphone",
  processor_lp: "Processor (Stage 1 DSP, always on)",
  processor_hp: "Processor (AED inference burst)",
  transmitter: "Transmitter",
};

function parseDurationHours(duration) {
  if (typeof duration === "number" && Number.isFinite(duration)) {
    return Math.max(1, duration);
  }
  const match = String(duration || "").match(/(\d+(?:\.\d+)?)/);
  if (!match) return 24;
  return Math.max(1, Number(match[1]));
}

function formatEnergyWh(wh) {
  const value = Number(wh) || 0;
  if (value === 0) return "0 Wh";
  if (value >= 1) return `${value.toFixed(2)} Wh`;
  if (value >= 0.001) return `${(value * 1000).toFixed(2)} mWh`;
  return `${(value * 1e6).toFixed(2)} µWh`;
}

function formatProjectedLife(hours) {
  if (hours == null || !Number.isFinite(Number(hours)) || Number(hours) <= 0) {
    return "—";
  }
  const h = Number(hours);
  if (h > 48) return `${(h / 24).toFixed(1)} days`;
  return `${h.toFixed(1)} h`;
}

export default function BatteryStatistics({ run }) {
  const [battery, setBattery] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setBattery(null);

    if (!run?.id) {
      setLoading(false);
      return () => {
        mounted = false;
      };
    }

    fetchBatteryStats(run.id)
      .then((data) => {
        if (mounted) setBattery(data);
      })
      .catch(() => {
        if (mounted) setBattery(null);
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });

    return () => {
      mounted = false;
    };
  }, [run?.id]);

  if (!run) {
    return (
      <div id="pageBatteryStats" style={{ overflowY: "auto", padding: 24 }}>
        <div
          style={{
            color: "var(--text-muted)",
            textAlign: "center",
            marginTop: 60,
            fontSize: 14,
          }}
        >
          Select a run from the Run Selector to view battery statistics.
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div id="pageBatteryStats" style={{ overflowY: "auto", padding: 24 }}>
        <div
          style={{
            color: "var(--text-muted)",
            textAlign: "center",
            marginTop: 60,
            fontSize: 14,
          }}
        >
          Loading battery statistics…
        </div>
      </div>
    );
  }

  const hasSimData = Boolean(battery?.available && battery.summary);
  const summary = hasSimData ? battery.summary : null;

  const durationHours = hasSimData
    ? Number(battery.duration_hours) || 0
    : parseDurationHours(run?.duration);

  const durationLabel = hasSimData
    ? battery.duration_source === "audio"
      ? `After ${durationHours.toFixed(1)} h of audio`
      : `After ${durationHours.toFixed(1)} h (estimated from duration setting)`
    : "No simulation recorded";

  const finalBattery = hasSimData ? Number(summary.final_battery_percent) || 0 : 0;
  const avgDrain = hasSimData ? Number(summary.avg_drain_percent_per_hour) || 0 : 0;
  const capacityWh = hasSimData ? Number(summary.battery_wh) || 0 : 0;
  const averagePowerW = hasSimData ? Number(summary.average_power_w) || 0 : 0;
  const projectedLifeHours = hasSimData ? summary.projected_total_life_hours : null;

  const batterySeries = hasSimData
    ? (battery.battery_over_time || []).map((point) => ({
        x: Number(point.time_seconds) / 3600,
        y: Number(point.battery_percent),
      }))
    : [
        { x: 0, y: 0 },
        { x: durationHours, y: 0 },
      ];

  let powerBreakdown;
  if (hasSimData) {
    const breakdown = battery.component_energy_breakdown || {};
    const total = Object.values(breakdown).reduce(
      (sum, value) => sum + (Number(value) || 0),
      0,
    );
    const hours = Number(summary?.duration_hours) || 0;
    powerBreakdown = Object.entries(breakdown).map(([key, value]) => ({
      label: SIM_COMPONENT_LABELS[key] || key,
      value: Number(value) || 0,
      pct: total > 0 ? ((Number(value) || 0) / total) * 100 : 0,
      mw: hours > 0 ? ((Number(value) || 0) / hours) * 1000 : 0,
    }));
  } else {
    powerBreakdown = Object.values(SIM_COMPONENT_LABELS).map((label) => ({
      label,
      value: 0,
      pct: 0,
    }));
  }

  const sourceNote = hasSimData
    ? "Single-node battery simulation"
    : "No simulation data recorded for this run";

  const barFormatter = (value) => {
    const row = powerBreakdown.find((item) => item.value === value);
    if (hasSimData && row) {
      if (row.value <= 0) return "0 — no activity this run";
      const mw = row.mw >= 1 ? `${row.mw.toFixed(1)} mW` : `${(row.mw * 1000).toFixed(0)} µW`;
      return `${formatEnergyWh(value)} · avg ${mw} · ${row.pct.toFixed(1)}%`;
    }
    return formatEnergyWh(value);
  };

  return (
    <div id="pageBatteryStats" style={{ overflowY: "auto", padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="pg-title">Battery Statistics</div>
          <div className="loaded-run-bar" style={{ marginTop: 6 }}>
            <div className="dot"></div>
            <span>Loaded Run: {run.name}</span>
            <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
              Duration: {durationHours.toFixed(1)}h
              {hasSimData && battery.duration_source === "audio"
                ? " (measured from audio)"
                : ""}
            </span>
            <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
              {sourceNote}
            </span>
          </div>
        </div>

        <div className="metrics-row">
          <div className="metric-card pass-state">
            <div className="m-label">Final Battery</div>
            <div className="m-value">{finalBattery.toFixed(1)}%</div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              {durationLabel}
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Avg Drain Rate</div>
            <div className="m-value">
              {avgDrain > 0 && avgDrain < 0.01
                ? `${avgDrain.toFixed(4)}%/h`
                : `${avgDrain >= 1 ? avgDrain.toFixed(2) : avgDrain.toFixed(4)}%/h`}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              {hasSimData ? "From simulation" : "Not yet simulated"}
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Capacity</div>
            <div className="m-value">{capacityWh} Wh</div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Battery pack
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Average Power</div>
            <div className="m-value">{(averagePowerW * 1000).toFixed(2)} mW</div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Mean draw across the run
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Projected Battery Life</div>
            <div className="m-value">{formatProjectedLife(projectedLifeHours)}</div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              At the observed average power
            </div>
          </div>
        </div>

        <div className="charts-grid">
          <div className="chart-box">
            <div className="chart-hdr">
              <div className="chart-title">
                Battery Over Time{" "}
                <span className="help-icon">
                  ?
                  <span className="help-tip">
                    {hasSimData
                      ? "Simulated remaining battery percentage across the measured run duration. Starts at 100% by construction."
                      : "No battery simulation has been recorded for this run. Create a run through Configure Run to populate this chart."}
                  </span>
                </span>
              </div>
            </div>
            <LineTrendChart
              points={batterySeries}
              xLabel="Hours"
              yLabel="Battery %"
              autoScaleY
              valueFormatter={(v) => `${v.toFixed(3)}%`}
            />
          </div>

          <div className="chart-box">
            <div className="chart-hdr">
              <div className="chart-title">
                Energy Consumption by Component{" "}
                <span className="help-icon">
                  ?
                  <span className="help-tip">
                    {hasSimData
                      ? "Simulated energy per component, with its average power draw and share of the total. The always-on Stage 1 DSP dominates; the AED inference burst is nearly free — that is the design working as intended."
                      : "No battery simulation has been recorded for this run."}
                  </span>
                </span>
              </div>
            </div>
            <PieChart
              data={powerBreakdown}
              emptyText="No component data recorded"
              valueFormatter={(total) => formatEnergyWh(total)}
            />
            <div
              style={{
                marginTop: 12,
                paddingTop: 10,
                borderTop: "1px solid var(--border, rgba(148,163,184,0.25))",
                fontSize: 11,
                lineHeight: 1.8,
                color: "var(--text-muted)",
              }}
            >
              {powerBreakdown.map((row) => (
                <div
                  key={row.label}
                  style={{ display: "flex", justifyContent: "space-between", gap: 12 }}
                >
                  <span
                    style={{
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {row.label}
                  </span>
                  <span style={{ whiteSpace: "nowrap" }}>{barFormatter(row.value)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}