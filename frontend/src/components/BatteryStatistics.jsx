import React, { useEffect, useState } from "react";
import { fetchBatteryStats, fetchNetmap } from "../api";
import { LineTrendChart, ResponsiveBarChart } from "./common/SimpleCharts";

/**
 * BatteryStatistics
 *
 * Shows the single-node battery simulation for the loaded run:
 *   1. Battery over time (line chart) — real simulator output
 *   2. Energy consumption breakdown by component (bar chart) — real Wh values
 *
 * Data source priority:
 *   1. GET /runs/{id}/battery — stored simulator output (source of truth)
 *   2. Legacy netmap node battery/drain — runs created before the simulator
 *   3. Zeroed-out display — the page always renders; it never blanks out
 *      with a "no data" message.
 */

const SIM_COMPONENT_LABELS = {
  microphone: "Microphone",
  processor_lp: "Processor (LP idle)",
  processor_hp: "Processor (HP burst)",
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

// Legacy fallback only (runs created before the battery simulator existed):
// back-extrapolate a straight line from the node's stored battery + drain.
function buildLegacyBatterySeries(node, durationHours) {
  const drainPerHour = Math.max(0.01, Number(node?.drain) || 0.01);
  const finalBattery = Math.max(0, Math.min(100, Number(node?.battery) || 0));
  const startBattery = Math.min(100, finalBattery + drainPerHour * durationHours);
  const samples = Math.max(12, Math.min(72, Math.round(durationHours * 2)));
  const points = [];
  for (let i = 0; i <= samples; i++) {
    const hour = (durationHours * i) / samples;
    points.push({
      x: hour,
      y: Math.max(0, startBattery - drainPerHour * hour),
    });
  }
  return points;
}

function findShamanNode(data) {
  if (!data) return null;
  const nodes = data.nodes || [];
  return (
    nodes.find((n) => n.id === "SHAMAN" || n.role === "sensor" || n.role === "shaman") ||
    nodes[0] ||
    null
  );
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
  const [battery, setBattery] = useState(null); // /runs/{id}/battery payload
  const [netmap, setNetmap] = useState(null); // legacy fallback
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setBattery(null);
    setNetmap(null);

    if (!run?.id) {
      setLoading(false);
      return () => {
        mounted = false;
      };
    }

    Promise.allSettled([fetchBatteryStats(run.id), fetchNetmap(run.id)]).then(
      ([batteryResult, netmapResult]) => {
        if (!mounted) return;
        if (batteryResult.status === "fulfilled") {
          setBattery(batteryResult.value);
        }
        if (netmapResult.status === "fulfilled") {
          setNetmap(netmapResult.value);
        }
        setLoading(false);
      },
    );
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
  const node = findShamanNode(netmap);
  const hasLegacyData = Boolean(
    !hasSimData && node && (Number(node.battery) > 0 || Number(node.drain) > 0),
  );

  // --- Resolve everything the page renders from one of three sources ---
  let durationHours;
  let durationLabel;
  let finalBattery;
  let avgDrain;
  let capacityWh = null;
  let averagePowerW = null;
  let projectedLifeHours = null;
  let batterySeries;
  let powerBreakdown;
  let sourceNote;

  if (hasSimData) {
    const summary = battery.summary;
    durationHours = Number(battery.duration_hours) || 0;
    durationLabel =
      battery.duration_source === "audio"
        ? `After ${durationHours.toFixed(1)} h of audio`
        : `After ${durationHours.toFixed(1)} h (estimated from duration setting)`;
    finalBattery = Number(summary.final_battery_percent) || 0;
    avgDrain = Number(summary.avg_drain_percent_per_hour) || 0;
    capacityWh = Number(summary.battery_wh) || 0;
    averagePowerW = Number(summary.average_power_w) || 0;
    projectedLifeHours = summary.projected_total_life_hours;
    batterySeries = (battery.battery_over_time || []).map((point) => ({
      x: Number(point.time_seconds) / 3600,
      y: Number(point.battery_percent),
    }));
    const breakdown = battery.component_energy_breakdown || {};
    const total = Object.values(breakdown).reduce(
      (sum, value) => sum + (Number(value) || 0),
      0,
    );
    powerBreakdown = Object.entries(breakdown).map(([key, value]) => ({
      label: SIM_COMPONENT_LABELS[key] || key,
      value: Number(value) || 0,
      pct: total > 0 ? ((Number(value) || 0) / total) * 100 : 0,
    }));
    sourceNote = "Single-node battery simulation";
  } else if (hasLegacyData) {
    durationHours = parseDurationHours(run?.duration);
    durationLabel = `After ${durationHours}h run (legacy estimate)`;
    finalBattery = Math.max(0, Math.min(100, Number(node.battery) || 0));
    avgDrain = Number(node.drain) || 0;
    batterySeries = buildLegacyBatterySeries(node, durationHours);
    const legacyBreakdown =
      node?.powerBreakdown && typeof node.powerBreakdown === "object"
        ? Object.entries(node.powerBreakdown)
            .map(([label, value]) => ({ label, value: Number(value) || 0 }))
            .filter((item) => item.value > 0)
        : [];
    powerBreakdown = legacyBreakdown;
    sourceNote = "Legacy run — created before the battery simulator";
  } else {
    // No data anywhere: render the full layout with zeroed values rather
    // than a blank "no data" message.
    durationHours = parseDurationHours(run?.duration);
    durationLabel = `After ${durationHours}h run`;
    finalBattery = 0;
    avgDrain = 0;
    capacityWh = 0;
    averagePowerW = 0;
    batterySeries = [
      { x: 0, y: 0 },
      { x: durationHours, y: 0 },
    ];
    powerBreakdown = Object.values(SIM_COMPONENT_LABELS).map((label) => ({
      label,
      value: 0,
    }));
    sourceNote = "No simulation data recorded for this run";
  }

  const barFormatter = (value) => {
    const row = powerBreakdown.find((item) => item.value === value);
    const pct = row?.pct;
    if (hasSimData && pct != null) {
      return `${formatEnergyWh(value)} (${pct.toFixed(1)}%)`;
    }
    if (hasSimData || (!hasSimData && !hasLegacyData)) {
      return formatEnergyWh(value);
    }
    return `${Number(value).toFixed(2)} W`;
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
            <div className="m-value">
              {hasSimData ? finalBattery.toFixed(1) : Math.round(finalBattery)}%
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              {durationLabel}
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Avg Drain Rate</div>
            <div className="m-value">
              {hasSimData
                ? `${avgDrain < 0.01 && avgDrain > 0 ? avgDrain.toFixed(4) : avgDrain.toFixed(2)}%/h`
                : `${Number(avgDrain).toFixed(2)}%/h`}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              {hasSimData ? "From simulation" : "Reported by run data"}
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Capacity</div>
            <div className="m-value">
              {capacityWh != null ? `${capacityWh} Wh` : "—"}
            </div>
            <div className="m-trend" style={{ color: "var(--text-muted)" }}>
              Battery pack
            </div>
          </div>
          <div className="metric-card">
            <div className="m-label">Average Power</div>
            <div className="m-value">
              {averagePowerW != null
                ? `${(averagePowerW * 1000).toFixed(2)} mW`
                : "—"}
            </div>
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
                      : "Estimated remaining battery percentage across the run duration."}
                  </span>
                </span>
              </div>
            </div>
            <LineTrendChart
              points={batterySeries}
              xLabel="Hours"
              yLabel="Battery %"
            />
          </div>

          <div className="chart-box">
            <div className="chart-hdr">
              <div className="chart-title">
                {hasSimData || (!hasSimData && !hasLegacyData)
                  ? "Energy Consumption by Component (Wh)"
                  : "Power Consumption by Component"}{" "}
                <span className="help-icon">
                  ?
                  <span className="help-tip">
                    {hasSimData
                      ? "Simulated energy (Wh) consumed by each modeled component. Burst components (HP processor, transmitter) are orders of magnitude below the always-on components — percentages show each share of the total."
                      : "Energy attributed to each Shaman component during the run."}
                  </span>
                </span>
              </div>
            </div>
            <ResponsiveBarChart
              data={powerBreakdown}
              emptyText="No component data recorded"
              valueFormatter={barFormatter}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
