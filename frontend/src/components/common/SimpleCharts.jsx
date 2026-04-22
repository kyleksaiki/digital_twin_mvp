import React from 'react'

const BAR_PALETTE = [
  '#3b82f6',
  '#ef4444',
  '#10b981',
  '#f59e0b',
  '#6366f1',
  '#14b8a6',
  '#f97316',
  '#ec4899',
]

function safeNumber(value) {
  const n = Number(value)
  return Number.isFinite(n) ? n : 0
}

function normalizeData(data = []) {
  return data
    .map((item, index) => ({
      label: String(item.label ?? item.event_type ?? item.rank ?? `Item ${index + 1}`),
      value: safeNumber(item.value ?? item.count ?? item.latency_ms),
      color: item.color,
    }))
    .filter((item) => item.label)
}

export function ResponsiveBarChart({
  data,
  emptyText = 'No data available',
  valueFormatter = (v) => `${v}`,
  compact = false,
  compactRowLimit = 8,
}) {
  const normalized = normalizeData(data).sort((a, b) => b.value - a.value)

  if (!normalized.length) {
    return <div className="chart-empty">{emptyText}</div>
  }

  const rows = compact ? normalized.slice(0, compactRowLimit) : normalized
  const maxValue = Math.max(...rows.map((row) => row.value), 1)

  return (
    <div className={`bar-chart ${compact ? 'compact' : ''}`}>
      {rows.map((row, idx) => {
        const widthPct = (row.value / maxValue) * 100
        return (
          <div className="bar-chart-row" key={`${row.label}-${idx}`}>
            <div className="bar-chart-label" title={row.label}>{row.label}</div>
            <div className="bar-chart-track">
              <div
                className="bar-chart-fill"
                style={{
                  width: `${Math.max(2, widthPct)}%`,
                  background: row.color || BAR_PALETTE[idx % BAR_PALETTE.length],
                }}
              ></div>
            </div>
            <div className="bar-chart-value">{valueFormatter(row.value)}</div>
          </div>
        )
      })}
      {compact && normalized.length > compactRowLimit ? (
        <div className="chart-note">Showing top {compactRowLimit} of {normalized.length} categories</div>
      ) : null}
    </div>
  )
}

export function LineTrendChart({
  points,
  xLabel = 'Time',
  yLabel = 'Value',
  valueFormatter = (v) => `${Math.round(v)}`,
}) {
  if (!points || points.length < 2) {
    return <div className="chart-empty">Not enough data points</div>
  }

  const width = 920
  const height = 360
  const padLeft = 66
  const padRight = 20
  const padTop = 20
  const padBottom = 42
  const plotWidth = width - padLeft - padRight
  const plotHeight = height - padTop - padBottom

  const xMin = Math.min(...points.map((p) => p.x))
  const xMax = Math.max(...points.map((p) => p.x))
  const yMin = Math.min(...points.map((p) => p.y), 0)
  const yMax = Math.max(...points.map((p) => p.y), 1)

  const xRange = xMax - xMin || 1
  const yRange = yMax - yMin || 1

  const toX = (x) => padLeft + ((x - xMin) / xRange) * plotWidth
  const toY = (y) => padTop + (1 - (y - yMin) / yRange) * plotHeight

  const linePath = points
    .map((point, idx) => `${idx === 0 ? 'M' : 'L'} ${toX(point.x)} ${toY(point.y)}`)
    .join(' ')

  const yTicks = 5
  const xTicks = 6

  return (
    <div className="line-chart-wrap">
      <svg className="line-chart" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet">
        <rect x="0" y="0" width={width} height={height} fill="transparent" />

        {Array.from({ length: yTicks + 1 }).map((_, i) => {
          const t = i / yTicks
          const y = padTop + t * plotHeight
          const value = yMax - t * yRange
          return (
            <g key={`y-${i}`}>
              <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="var(--border)" strokeWidth="1" />
              <text x={padLeft - 8} y={y + 4} textAnchor="end" className="line-chart-tick">{valueFormatter(value)}</text>
            </g>
          )
        })}

        {Array.from({ length: xTicks + 1 }).map((_, i) => {
          const t = i / xTicks
          const x = padLeft + t * plotWidth
          const value = xMin + t * xRange
          return (
            <g key={`x-${i}`}>
              <line x1={x} y1={padTop} x2={x} y2={height - padBottom} stroke="var(--border)" strokeWidth="1" />
              <text x={x} y={height - padBottom + 16} textAnchor="middle" className="line-chart-tick">{Math.round(value)}</text>
            </g>
          )
        })}

        <path d={linePath} fill="none" stroke="#3b82f6" strokeWidth="3" />

        {points.map((point, idx) => (
          <circle key={`p-${idx}`} cx={toX(point.x)} cy={toY(point.y)} r="3.5" fill="#ef4444" />
        ))}

        <text x={width / 2} y={height - 8} textAnchor="middle" className="line-chart-axis-label">{xLabel}</text>
        <text
          x="16"
          y={height / 2}
          transform={`rotate(-90 16 ${height / 2})`}
          textAnchor="middle"
          className="line-chart-axis-label"
        >
          {yLabel}
        </text>
      </svg>
    </div>
  )
}
