import React from 'react'
import ExportReportButton from './common/ExportReportButton'

/**
 * Topbar - Top navigation bar with branding and page title
 * 
 * Props:
 *   title: string - current page key ("overview", "netmap", "aisummary", "runsel")
 *   isDarkMode: boolean - current theme mode
 *   onToggleTheme: function - callback to toggle theme
 */
export default function Topbar({title, isDarkMode, onToggleTheme, runId}){
  return (
    <div className="topbar">
      <div className="topbar-brand">Digital Twin</div>
      <div className="topbar-sep" />
      <div className="topbar-title" id="topbarTitle">{title||''}</div>
      <div className="topbar-spacer" />
      {title === 'Overview Dashboard' && <ExportReportButton runId={runId} />}
      <button 
        className="topbar-btn theme-toggle"
        onClick={onToggleTheme}
        title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label="Toggle theme"
      >
        {isDarkMode ? '☼' : '☾'}
      </button>
    </div>
  )
}
