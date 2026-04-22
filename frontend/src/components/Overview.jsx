import React, { useEffect, useState } from 'react'
import { fetchDashboard } from '../api'
import Modal from './common/Modal'
import { ResponsiveBarChart } from './common/SimpleCharts'

function metricClassHigherBetter(value, goodMin, warnMin) {
  if (value == null) return ''
  if (value >= goodMin) return 'pass-state'
  if (value >= warnMin) return 'warn-state'
  return 'fail-state'
}

function metricClassLowerBetter(value, goodMax, warnMax) {
  if (value == null) return ''
  if (value <= goodMax) return 'pass-state'
  if (value <= warnMax) return 'warn-state'
  return 'fail-state'
}

export default function Overview({ run }) {
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(false)
  const [chartModal, setChartModal] = useState({ open: false, type: null, expanded: false })

  useEffect(() => {
    if (!run?.id) return
    let mounted = true
    setLoading(true)
    fetchDashboard(run.id)
      .then((data) => {
        if (!mounted) return
        setDashboard(data)
        setLoading(false)
      })
      .catch(() => {
        if (!mounted) return
        setDashboard(null)
        setLoading(false)
      })
    return () => {
      mounted = false
    }
  }, [run?.id])

  if (!run) {
    return (
      <div id="pageOverview" style={{ overflowY: 'auto', padding: 24 }}>
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 60, fontSize: 14 }}>
          Select a run from the Run Selector to view the dashboard.
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div id="pageOverview" style={{ overflowY: 'auto', padding: 24 }}>
        <div style={{ color: 'var(--text-muted)', textAlign: 'center', marginTop: 60, fontSize: 14 }}>
          Loading dashboard...
        </div>
      </div>
    )
  }

  const metrics = dashboard?.metrics || {}
  const runData = dashboard?.run || run

  const detectionsData = (dashboard?.detections_by_type || [])
    .map((item) => ({
      label: item.event_type || item.label || 'Unknown',
      value: Number(item.count) || 0,
    }))
    .sort((a, b) => b.value - a.value)

  const latencyByRankData = (dashboard?.latency_by_rank || [])
    .map((item) => ({
      label: `Rank ${item.rank}`,
      value: Number(item.latency_ms) || 0,
    }))
    .sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }))

  const chartConfig = chartModal.type === 'latency'
    ? {
        title: 'Latency by Network Rank',
        subtitle: 'Full rank distribution for the selected run',
        data: latencyByRankData,
        formatter: (value) => `${value}ms`,
      }
    : {
        title: 'Detections by Type',
        subtitle: 'Full detection category distribution for the selected run',
        data: detectionsData,
        formatter: (value) => `${value}`,
      }

  const statusChipClass = runData.status === 'fail' ? 'chip-fail' : runData.status === 'warning' ? 'chip-warn' : 'chip-pass'

  return (
    <div id="pageOverview" style={{ overflowY: 'auto', padding: 24 }}>
      <div className="overview-shell">
        <div className="overview-topbar">
          <div className="run-meta-card" style={{ marginBottom: 0 }}>
            <span className="run-meta-label">Loaded Run: {runData.name}</span>
            <span className={`run-chip ${statusChipClass}`}>{runData.status ? runData.status.toUpperCase() : '—'}</span>
          </div>
          <button className="btn btn-secondary export-btn">Export Report</button>
        </div>

        <div className="metrics-row">
          <div className={`metric-card ${metricClassHigherBetter(metrics.accuracy, 90, 80)}`}>
            <div className="m-label">AI Accuracy <span className="help-icon">?<span className="help-tip">Percentage of correct detections out of total events in the scenario pack. Higher is better.</span></span></div>
            <div className="m-value">{metrics.accuracy != null ? `${metrics.accuracy}%` : '—'}</div>
            <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
          </div>

          <div className={`metric-card ${metricClassLowerBetter(metrics.fpr, 5, 10)}`}>
            <div className="m-label">False Positive Rate <span className="help-icon">?<span className="help-tip">Percentage of false detections out of all positive detections. Lower is better.</span></span></div>
            <div className="m-value">{metrics.fpr != null ? `${metrics.fpr}%` : '—'}</div>
            <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
          </div>

          <div className={`metric-card ${metricClassLowerBetter(metrics.latency_ms, 50, 100)}`}>
            <div className="m-label">Avg Inference Latency <span className="help-icon">?<span className="help-tip">Mean time from audio input to model output on node hardware.</span></span></div>
            <div className="m-value">{metrics.latency_ms != null ? `${metrics.latency_ms}ms` : '—'}</div>
            <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
          </div>

          <div className="metric-card pass-state">
            <div className="m-label">Detection Count <span className="help-icon">?<span className="help-tip">Total number of AI detections during this run.</span></span></div>
            <div className="m-value">{metrics.detection_count != null ? metrics.detection_count : '—'}</div>
            <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Total for run</div>
          </div>

          <div className={`metric-card ${metricClassHigherBetter(metrics.battery_health, 60, 30)}`}>
            <div className="m-label">Battery Health <span className="help-icon">?<span className="help-tip">Average remaining battery across all sensor nodes at run end.</span></span></div>
            <div className="m-value">{metrics.battery_health != null ? `${metrics.battery_health}%` : '—'}</div>
            <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Avg across nodes</div>
          </div>
        </div>

        <div className="charts-grid">
          <div className="chart-box chart-clickable" onClick={() => setChartModal({ open: true, type: 'detections', expanded: false })}>
            <div className="chart-hdr">
              <div className="chart-title">Detections by Type <span className="help-icon">?<span className="help-tip">Data-driven category chart. Click to expand full dataset.</span></span></div>
              <div className="chart-expand-hint">Expand</div>
            </div>
            <ResponsiveBarChart
              data={detectionsData}
              compact
              emptyText="No detection data"
              valueFormatter={(value) => `${value}`}
            />
          </div>

          <div className="chart-box chart-clickable" onClick={() => setChartModal({ open: true, type: 'latency', expanded: false })}>
            <div className="chart-hdr">
              <div className="chart-title">Latency by Network Rank <span className="help-icon">?<span className="help-tip">Rank-specific latency values. Click to inspect all ranks.</span></span></div>
              <div className="chart-expand-hint">Expand</div>
            </div>
            <ResponsiveBarChart
              data={latencyByRankData}
              compact
              emptyText="No latency data"
              valueFormatter={(value) => `${value}ms`}
            />
          </div>
        </div>
      </div>

      <Modal
        open={chartModal.open}
        title={chartConfig.title}
        subtitle={chartConfig.subtitle}
        expanded={chartModal.expanded}
        onToggleExpand={() => setChartModal((prev) => ({ ...prev, expanded: !prev.expanded }))}
        onClose={() => setChartModal({ open: false, type: null, expanded: false })}
      >
        <ResponsiveBarChart
          data={chartConfig.data}
          emptyText="No data available"
          valueFormatter={chartConfig.formatter}
        />
      </Modal>
    </div>
  )
}
