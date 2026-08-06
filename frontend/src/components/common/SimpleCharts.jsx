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
  preserveOrder = false,
}) {
  const mapped = normalizeData(data)
  // Histograms and stage sequences are meaningful in their given order;
  // sorting them by value scrambles the axis.
  const normalized = preserveOrder ? mapped : [...mapped].sort((a, b) => b.value - a.value)

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

function defaultAxisFormatter(range) {
  // Pick decimal places from the span so short ranges don't collapse to
  // duplicate integer labels (0 0 0 1 1 1 over a one-hour run).
  if (range >= 12) return (v) => `${Math.round(v)}`
  if (range >= 3) return (v) => v.toFixed(1)
  return (v) => v.toFixed(2)
}

export function PieChart({
  data,
  emptyText = 'No data available',
  valueFormatter = (v) => `${v}`,
  size = 210,
  donut = true,
}) {
  const normalized = normalizeData(data)
  const total = normalized.reduce((sum, row) => sum + Math.max(0, row.value), 0)

  if (!normalized.length || total <= 0) {
    return <div className="chart-empty">{emptyText}</div>
  }

  const cx = size / 2
  const cy = size / 2
  const r = size / 2 - 6
  const innerR = donut ? r * 0.58 : 0

  const point = (radius, angle) => [
    cx + radius * Math.cos(angle - Math.PI / 2),
    cy + radius * Math.sin(angle - Math.PI / 2),
  ]

  let cursor = 0
  const slices = normalized
    .map((row, idx) => {
      const value = Math.max(0, row.value)
      const color = row.color || BAR_PALETTE[idx % BAR_PALETTE.length]
      const pct = (value / total) * 100
      if (value <= 0) return { ...row, color, pct, path: null }

      const start = (value === total ? 0 : cursor / total) * Math.PI * 2
      const end = start + (value / total) * Math.PI * 2
      cursor += value

      // A single 100% slice can't be drawn as an arc (start === end), so it
      // renders as a ring instead.
      if (value === total) {
        return { ...row, color, pct, path: null, full: true }
      }

      const [x1, y1] = point(r, start)
      const [x2, y2] = point(r, end)
      const [x3, y3] = point(innerR, end)
      const [x4, y4] = point(innerR, start)
      const largeArc = end - start > Math.PI ? 1 : 0
      const path = donut
        ? `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} L ${x3} ${y3} A ${innerR} ${innerR} 0 ${largeArc} 0 ${x4} ${y4} Z`
        : `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
      return { ...row, color, pct, path }
    })
    .filter(Boolean)

  const fullSlice = slices.find((s) => s.full)

  return (
    <div className="pie-chart-wrap" style={{ display: 'flex', alignItems: 'center', gap: 18, flexWrap: 'wrap' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flex: '0 0 auto' }}>
        {fullSlice ? (
          <circle
            cx={cx}
            cy={cy}
            r={(r + innerR) / 2}
            fill="none"
            stroke={fullSlice.color}
            strokeWidth={r - innerR}
          />
        ) : (
          slices.map((slice, idx) =>
            slice.path ? (
              <path
                key={`${slice.label}-${idx}`}
                d={slice.path}
                fill={slice.color}
                stroke="var(--panel, #0f172a)"
                strokeWidth="1"
              />
            ) : null,
          )
        )}
        {donut && (
          <text x={cx} y={cy + 4} textAnchor="middle" className="line-chart-tick" style={{ fontSize: 13 }}>
            {valueFormatter(total)}
          </text>
        )}
      </svg>

      <div style={{ flex: '1 1 200px', minWidth: 0, fontSize: 12 }}>
        {slices.map((slice, idx) => (
          <div
            key={`legend-${slice.label}-${idx}`}
            style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '3px 0' }}
          >
            <span
              style={{
                width: 10,
                height: 10,
                borderRadius: 2,
                background: slice.color,
                flex: '0 0 auto',
                opacity: slice.value > 0 ? 1 : 0.3,
              }}
            ></span>
            <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {slice.label}
            </span>
            <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
              {slice.value > 0 ? `${slice.pct.toFixed(1)}%` : '0%'}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function LineTrendChart({
  points,
  xLabel = 'Time',
  yLabel = 'Value',
  valueFormatter = (v) => `${Math.round(v)}`,
  xFormatter = null,
  autoScaleY = false,
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
  // autoScaleY zooms to the data's own range. Without it a 0.02% battery drop
  // is invisible on a forced 0-100 axis.
  const rawYMin = Math.min(...points.map((p) => p.y))
  const rawYMax = Math.max(...points.map((p) => p.y))
  let yMin
  let yMax
  if (autoScaleY) {
    const spread = rawYMax - rawYMin
    const pad = spread > 0 ? spread * 0.15 : Math.max(Math.abs(rawYMax) * 0.001, 0.01)
    yMin = rawYMin - pad
    yMax = rawYMax + pad
  } else {
    yMin = Math.min(rawYMin, 0)
    yMax = Math.max(rawYMax, 1)
  }

  const xRange = xMax - xMin || 1
  const yRange = yMax - yMin || 1
  const xTickFormatter = xFormatter || defaultAxisFormatter(xRange)

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
              <text x={x} y={height - padBottom + 16} textAnchor="middle" className="line-chart-tick">{xTickFormatter(value)}</text>
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