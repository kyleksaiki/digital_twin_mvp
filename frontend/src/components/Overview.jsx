import React, { useState, useEffect } from 'react'
import { fetchDashboard } from '../api'

const TYPE_COLORS = {
  Bird:      'rgba(0,230,138,0.6)',
  Gunshot:   'rgba(255,77,106,0.6)',
  Chainsaw:  'rgba(255,190,46,0.6)',
  Voice:     'rgba(59,130,246,0.6)',
  Vehicle:   'rgba(167,139,250,0.6)',
}
const FALLBACK_COLOR = 'rgba(120,160,200,0.5)'

function latencyColor(ms) {
  if (ms < 50) return '#00e68a'
  if (ms < 120) return '#ffbe2e'
  return '#ff4d6a'
}

function metricState(val, good, warn) {
  if (val <= good) return 'pass-state'
  if (val <= warn) return 'warn-state'
  return 'fail-state'
}

function DetectionsByTypeChart({ data }) {
  if (!data || data.length === 0) return <div style={{color:'var(--text-muted)',fontSize:12}}>No detection data</div>
  const maxCount = Math.max(...data.map(d => d.count))
  const barMaxWidth = 360
  const rowH = 30
  const startY = 20
  const labelX = 75
  const barX = 90

  return (
    <svg className="svg-chart" viewBox={`0 0 500 ${startY + data.length * rowH + 10}`} preserveAspectRatio="none">
      <line x1="80" y1={startY - 2} x2="80" y2={startY + data.length * rowH} stroke="#1e2d48" strokeWidth="1" />
      <line x1="80" y1={startY + data.length * rowH} x2="490" y2={startY + data.length * rowH} stroke="#1e2d48" strokeWidth="1" />
      {data.map((d, i) => {
        const y = startY + i * rowH
        const w = maxCount > 0 ? (d.count / maxCount) * barMaxWidth : 0
        const color = TYPE_COLORS[d.event_type] || FALLBACK_COLOR
        return (
          <g key={d.event_type}>
            <text x={labelX} y={y + 15} fill="#7e93b0" fontSize="10" textAnchor="end" fontFamily="DM Sans">{d.event_type}</text>
            <rect x={barX} y={y} width={w} height="22" rx="3" fill={color} />
            <text x={barX + w + 10} y={y + 15} fill="#7e93b0" fontSize="10" fontFamily="JetBrains Mono">{d.count}</text>
          </g>
        )
      })}
    </svg>
  )
}

function LatencyByRankChart({ data }) {
  if (!data || data.length === 0) return <div style={{color:'var(--text-muted)',fontSize:12}}>No latency data</div>
  const maxLat = Math.max(...data.map(d => d.latency_ms), 1)
  const chartTop = 20
  const chartBottom = 175
  const chartH = chartBottom - chartTop
  const barW = 80
  const gap = 120 / Math.max(data.length, 1)
  const startX = 100

  const gridLines = [0, Math.round(maxLat / 3), Math.round((maxLat * 2) / 3), maxLat]

  return (
    <svg className="svg-chart" viewBox="0 0 500 200" preserveAspectRatio="none">
      <line x1="60" y1={chartTop} x2="60" y2={chartBottom} stroke="#1e2d48" strokeWidth="1" />
      <line x1="60" y1={chartBottom} x2="490" y2={chartBottom} stroke="#1e2d48" strokeWidth="1" />
      {gridLines.map((v, i) => {
        const y = chartBottom - (v / maxLat) * chartH
        return (
          <g key={i}>
            <line x1="60" y1={y} x2="490" y2={y} stroke="#1e2d48" strokeWidth="0.5" strokeDasharray="4" />
            <text x="55" y={y + 4} fill="#4a5f7a" fontSize="9" textAnchor="end" fontFamily="JetBrains Mono">{v}ms</text>
          </g>
        )
      })}
      {data.map((d, i) => {
        const h = (d.latency_ms / maxLat) * chartH
        const x = startX + i * (barW + gap)
        const y = chartBottom - h
        const color = latencyColor(d.latency_ms)
        return (
          <g key={d.rank}>
            <rect x={x} y={y} width={barW} height={h} rx="4" fill={color} opacity="0.5" />
            <text x={x + barW / 2} y={chartBottom + 15} fill="#7e93b0" fontSize="10" textAnchor="middle" fontFamily="JetBrains Mono">Rank {d.rank}</text>
            <text x={x + barW / 2} y={y - 5} fill={color} fontSize="10" textAnchor="middle" fontFamily="JetBrains Mono" fontWeight="600">{d.latency_ms}ms</text>
          </g>
        )
      })}
    </svg>
  )
}

function AccuracyCurveChart({ data, confThreshold }) {
  if (!data || data.length === 0) return <div style={{color:'var(--text-muted)',fontSize:12}}>No curve data</div>
  const chartLeft = 50
  const chartRight = 470
  const chartTop = 20
  const chartBottom = 175
  const chartW = chartRight - chartLeft
  const chartH = chartBottom - chartTop

  const tMin = Math.min(...data.map(d => d.threshold))
  const tMax = Math.max(...data.map(d => d.threshold))
  const tRange = tMax - tMin || 1

  function tx(t) { return chartLeft + ((t - tMin) / tRange) * chartW }
  function ty(v) { return chartBottom - (v / 100) * chartH }

  const accPoints = data.map(d => `${tx(d.threshold)},${ty(d.accuracy)}`).join(' ')
  const fprPoints = data.map(d => `${tx(d.threshold)},${ty(d.fpr)}`).join(' ')

  const ctX = confThreshold != null ? tx(confThreshold) : null

  return (
    <svg className="svg-chart" viewBox="0 0 500 200" preserveAspectRatio="none">
      <line x1={chartLeft} y1={chartTop} x2={chartLeft} y2={chartBottom} stroke="#1e2d48" strokeWidth="1" />
      <line x1={chartLeft} y1={chartBottom} x2={chartRight + 20} y2={chartBottom} stroke="#1e2d48" strokeWidth="1" />
      <text x={(chartLeft + chartRight) / 2} y="198" fill="#4a5f7a" fontSize="9" textAnchor="middle" fontFamily="DM Sans">Confidence Threshold →</text>
      <text x={chartLeft - 5} y={chartBottom + 4} fill="#4a5f7a" fontSize="8" textAnchor="end" fontFamily="JetBrains Mono">0%</text>
      <text x={chartLeft - 5} y={(chartTop + chartBottom) / 2 + 4} fill="#4a5f7a" fontSize="8" textAnchor="end" fontFamily="JetBrains Mono">50%</text>
      <text x={chartLeft - 5} y={chartTop + 4} fill="#4a5f7a" fontSize="8" textAnchor="end" fontFamily="JetBrains Mono">100%</text>
      <text x={tx(tMin)} y="193" fill="#4a5f7a" fontSize="8" fontFamily="JetBrains Mono">{tMin.toFixed(2)}</text>
      <text x={(tx(tMin) + tx(tMax)) / 2} y="193" fill="#4a5f7a" fontSize="8" textAnchor="middle" fontFamily="JetBrains Mono">{((tMin + tMax) / 2).toFixed(2)}</text>
      <text x={tx(tMax)} y="193" fill="#4a5f7a" fontSize="8" textAnchor="end" fontFamily="JetBrains Mono">{tMax.toFixed(2)}</text>

      <polyline fill="none" stroke="#00e68a" strokeWidth="2" points={accPoints} />
      <polyline fill="none" stroke="#ff4d6a" strokeWidth="2" strokeDasharray="6,3" points={fprPoints} />

      {ctX != null && (
        <>
          <line x1={ctX} y1={chartTop} x2={ctX} y2={chartBottom} stroke="var(--cyan)" strokeWidth="1.5" strokeDasharray="4,3" />
          <text x={ctX} y={chartTop - 5} fill="var(--cyan)" fontSize="9" textAnchor="middle" fontFamily="JetBrains Mono">current: {confThreshold}</text>
        </>
      )}

      <line x1="350" y1="28" x2="370" y2="28" stroke="#00e68a" strokeWidth="2" />
      <text x="375" y="32" fill="#7e93b0" fontSize="9" fontFamily="DM Sans">Accuracy</text>
      <line x1="350" y1="42" x2="370" y2="42" stroke="#ff4d6a" strokeWidth="2" strokeDasharray="4,2" />
      <text x="375" y="46" fill="#7e93b0" fontSize="9" fontFamily="DM Sans">False Positive Rate</text>
    </svg>
  )
}

export default function Overview({ run }) {
  const [dashboard, setDashboard] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!run?.id) return
    let mounted = true
    setLoading(true)
    setError(null)
    fetchDashboard(run.id)
      .then(d => { if (mounted) { setDashboard(d); setLoading(false) } })
      .catch(e => { if (mounted) { setError(e); setLoading(false) } })
    return () => { mounted = false }
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
  const detections = dashboard?.detections_by_type || []
  const latencyRanks = dashboard?.latency_by_rank || []
  const accCurve = dashboard?.accuracy_confidence_curve || []

  const accuracy = metrics.accuracy
  const fpr = metrics.fpr
  const latency = metrics.latency_ms
  const detectionCount = metrics.detection_count
  const battery = metrics.battery_health
  const congestion = metrics.congestion
  const throughput = metrics.throughput
  const confThreshold = metrics.conf_threshold

  const statusChipClass = runData.status === 'fail' ? 'chip-fail' : runData.status === 'warning' ? 'chip-warn' : 'chip-pass'

  return (
    <div id="pageOverview" style={{ overflowY: 'auto', padding: 24 }}>
      <div className="run-meta-card">
        <span className="run-meta-label">Loaded Run: {runData.name}</span>
        <span className={`run-chip ${statusChipClass}`}>{runData.status ? runData.status.toUpperCase() : '—'}</span>
      </div>

      <div className="metrics-row">
        <div className={`metric-card ${accuracy != null && accuracy >= 90 ? 'pass-state' : accuracy != null && accuracy >= 80 ? 'warn-state' : 'fail-state'}`}>
          <div className="m-label">AI Accuracy <span className="help-icon">?<span className="help-tip">Percentage of correct detections out of total events in the scenario pack. Higher is better.</span></span></div>
          <div className="m-value">{accuracy != null ? `${accuracy}%` : '—'}</div>
          <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
        </div>

        <div className={`metric-card ${fpr != null && fpr <= 5 ? 'pass-state' : fpr != null && fpr <= 10 ? 'warn-state' : 'fail-state'}`}>
          <div className="m-label">False Positive Rate <span className="help-icon">?<span className="help-tip">Percentage of false detections out of all positive detections. Lower is better.</span></span></div>
          <div className="m-value">{fpr != null ? `${fpr}%` : '—'}</div>
          <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
        </div>

        <div className={`metric-card ${latency != null && latency <= 50 ? 'pass-state' : latency != null && latency <= 100 ? 'warn-state' : 'fail-state'}`}>
          <div className="m-label">Avg Inference Latency <span className="help-icon">?<span className="help-tip">Mean time from audio input to model output on the node's hardware.</span></span></div>
          <div className="m-value">{latency != null ? `${latency}ms` : '—'}</div>
          <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Baseline pending</div>
        </div>

        <div className="metric-card pass-state">
          <div className="m-label">Detection Count <span className="help-icon">?<span className="help-tip">Total number of AI detections during this run.</span></span></div>
          <div className="m-value">{detectionCount != null ? detectionCount : '—'}</div>
          <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Total for run</div>
        </div>

        <div className={`metric-card ${battery != null && battery >= 60 ? 'pass-state' : battery != null && battery >= 30 ? 'warn-state' : 'fail-state'}`}>
          <div className="m-label">Battery Health <span className="help-icon">?<span className="help-tip">Average remaining battery across all sensor nodes at end of run.</span></span></div>
          <div className="m-value">{battery != null ? `${battery}%` : '—'}</div>
          <div className="m-trend" style={{ color: 'var(--text-muted)' }}>Avg across nodes</div>
        </div>
      </div>

      <div className="charts-grid">
        <div className="chart-box">
          <div className="chart-hdr"><div className="chart-title">Detections by Type <span className="help-icon">?<span className="help-tip">Breakdown of what the AI system is detecting most often during this run.</span></span></div></div>
          <DetectionsByTypeChart data={detections} />
        </div>

        <div className="chart-box">
          <div className="chart-hdr"><div className="chart-title">Latency by Network Rank <span className="help-icon">?<span className="help-tip">Average end-to-end latency grouped by hop distance from the Command Center. Rank 1 = direct connection.</span></span></div></div>
          <LatencyByRankChart data={latencyRanks} />
        </div>
      </div>

      <div className="chart-box" style={{ marginBottom: 20 }}>
        <div className="chart-hdr"><div className="chart-title">Accuracy vs Confidence Threshold <span className="help-icon">?<span className="help-tip">Shows tradeoff: higher threshold reduces false positives but may miss real events. The dotted line shows false positive rate at each threshold.</span></span></div></div>
        <AccuracyCurveChart data={accCurve} confThreshold={confThreshold} />
      </div>
    </div>
  )
}
