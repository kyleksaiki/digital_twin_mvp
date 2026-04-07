import React from 'react'

/**
 * Topbar - Top navigation bar with branding and page title
 * 
 * Props:
 *   title: string - current page key ("overview", "netmap", "aisummary", "runsel")
 *   isDarkMode: boolean - current theme mode
 *   onToggleTheme: function - callback to toggle theme
 */
export default function Topbar({title, isDarkMode, onToggleTheme}){
  const titles = { runsel:'Run Selector', overview:'Overview Dashboard', netmap:'Network Map', aisummary:'AI Assistant' }
  return (
    <div className="topbar">
      <div className="topbar-brand">DT Results</div>
      <div className="topbar-sep" />
      <div className="topbar-title" id="topbarTitle">{titles[title]||''}</div>
      <div className="topbar-spacer" />
      {title === 'overview' && <button className="topbar-btn">Export Report</button>}
      <button 
        className="topbar-btn theme-toggle"
        onClick={onToggleTheme}
        title={isDarkMode ? 'Switch to light mode' : 'Switch to dark mode'}
        aria-label="Toggle theme"
      >
        {isDarkMode ? '☀️' : '🌙'}
      </button>
    </div>
  )
}
