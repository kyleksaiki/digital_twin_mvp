import React, { useEffect, useState } from "react";
import { fetchNetmap } from "../api";
import { LineTrendChart, ResponsiveBarChart } from "./common/SimpleCharts";

/**
 * BatteryStatistics
 *
 * New page that replaces the previous network map. Focuses on two charts:
 *   1. Battery over time (line chart)
 *   2. Power consumption breakdown by component (bar chart)
 */

function parseDurationHours(duration) {
  if (typeof duration === "number" && Number.isFinite(duration)) {
    return Math.max(1, duration);
  }
  const match = String(duration || "").match(/(\d+(?:\.\d+)?)/);
  if (!match) return 24;
  return Math.max(1, Number(match[1]));
}

function buildBatterySeries(node, durationHours) {
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

function buildPowerBreakdown(node) {
  const breakdown =
    node?.powerBreakdown && typeof node.powerBreakdown === "object"
      ? node.powerBreakdown
      : null;
  if (breakdown) {
    return Object.entries(breakdown)
      .map(([label, value]) => ({ label, value: Number(value) || 0 }))
      .filter((item) => item.value > 0)
      .sort((a, b) => b.value - a.value);
  }
  // Fallback: estimate from the node's drain rate so the page still renders
  // useful information when explicit component breakdown is not available.
  const drainPerHour = Math.max(0.01, Number(node?.drain) || 0.01);
  return [
    { label: "Processor", value: drainPerHour * 0.45 },
    { label: "Radio", value: drainPerHour * 0.25 },
    { label: "Microphone", value: drainPerHour * 0.15 },
    { label: "Camera", value: drainPerHour * 0.1 },
    { label: "Other", value: drainPerHour * 0.05 },
  ];
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

export default function BatteryStatistics({ run }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasData, setHasData] = useState(false);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setData(null);
    setHasData(false);

    fetchNetmap(run?.id)
      .then((d) => {
        if (!mounted) return;
        setData(d);
        setHasData(Boolean(d && (d.nodes || []).length > 0));
        setLoading(false);
      })
      .catch(() => {
        if (!mounted) return;
        setData(null);
        setHasData(false);
        setLoading(false);
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

  const node = findShamanNode(data);
  const durationHours = parseDurationHours(run?.duration);
  const batterySeries = node ? buildBatterySeries(node, durationHours) : [];
  const powerBreakdown = node ? buildPowerBreakdown(node) : [];
  const finalBattery = node ? Number(node.battery) || 0 : 0;

  return (
    <div id="pageBatteryStats" style={{ overflowY: "auto", padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="pg-title">Battery Statistics</div>
          <div className="loaded-run-bar" style={{ marginTop: 6 }}>
            <div className="dot"></div>
            <span>Loaded Run: {run.name}</span>
            <span style={{ marginLeft: 8, color: "var(--text-muted)" }}>
              Duration: {durationHours}h
            </span>
          </div>
        </div>

        {!hasData || !node ? (
          <div
            style={{
              color: "var(--text-muted)",
              textAlign: "center",
              marginTop: 60,
              fontSize: 14,
            }}
          >
            No battery data available for this run.
          </div>
        ) : (
          <>
            <div className="metrics-row">
              <div className="metric-card pass-state">
                <div className="m-label">Final Battery</div>
                <div className="m-value">{Math.round(finalBattery)}%</div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  After {durationHours}h run
                </div>
              </div>
              <div className="metric-card">
                <div className="m-label">Avg Drain Rate</div>
                <div className="m-value">
                  {node?.drain != null ? `${Number(node.drain).toFixed(2)}%/h` : "—"}
                </div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  Reported by simulation
                </div>
              </div>
              <div className="metric-card">
                <div className="m-label">Capacity</div>
                <div className="m-value">
                  {node?.batteryCapacity != null
                    ? `${node.batteryCapacity} Wh`
                    : "—"}
                </div>
                <div className="m-trend" style={{ color: "var(--text-muted)" }}>
                  Battery pack
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
                        Estimated remaining battery percentage across the run
                        duration.
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
                    Power Consumption by Component{" "}
                    <span className="help-icon">
                      ?
                      <span className="help-tip">
                        Average power draw attributed to each Shaman
                        component during the run.
                      </span>
                    </span>
                  </div>
                </div>
                <ResponsiveBarChart
                  data={powerBreakdown}
                  emptyText="No power breakdown data"
                  valueFormatter={(value) => `${value.toFixed(2)} W`}
                />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
