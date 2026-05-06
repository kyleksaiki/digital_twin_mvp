import React, { useEffect, useMemo, useState } from 'react'
import { exportReport } from '../../api'

function getFilenameFromHeaders(headers) {
  const disposition = headers.get('Content-Disposition') || headers.get('content-disposition')
  if (!disposition) return null

  const filenameStarMatch = disposition.match(/filename\*=UTF-8''([^;]+)/i)
  if (filenameStarMatch?.[1]) {
    try {
      return decodeURIComponent(filenameStarMatch[1])
    } catch {
      return filenameStarMatch[1]
    }
  }

  const filenameMatch = disposition.match(/filename="?([^";]+)"?/i)
  return filenameMatch?.[1] || null
}

function buildFallbackFilename(runId, format) {
  const dateStamp = new Date().toISOString().slice(0, 10)
  if (runId) {
    return `run_${runId}_export.${format}`
  }
  return `report_${dateStamp}.${format}`
}

export default function ExportReportButton({
  runId,
  format = 'csv',
  includeNodes = true,
  includeEdges = true,
}) {
  const [isExporting, setIsExporting] = useState(false)
  const [error, setError] = useState('')

  const exportLabel = useMemo(
    () => (isExporting ? 'Exporting…' : 'Export Report'),
    [isExporting],
  )

  useEffect(() => {
    if (!error) return undefined
    const timeout = setTimeout(() => setError(''), 4000)
    return () => clearTimeout(timeout)
  }, [error])

  async function handleExport() {
    if (isExporting) return
    if (!runId) {
      setError('Load a run to export.')
      return
    }
    setIsExporting(true)
    setError('')

    try {
      const response = await exportReport(runId, includeNodes, includeEdges)
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const filename =
        getFilenameFromHeaders(response.headers) || buildFallbackFilename(runId, format)

      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Export failed:', err)
      setError('Export failed. Please try again.')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div className="export-report">
      <button
        className="topbar-btn"
        onClick={handleExport}
        disabled={isExporting || !runId}
        type="button"
      >
        {exportLabel}
      </button>
      {error ? (
        <span className="export-error" role="status">
          {error}
        </span>
      ) : null}
    </div>
  )
}
