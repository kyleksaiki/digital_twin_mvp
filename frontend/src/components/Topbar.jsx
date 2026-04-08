import React from 'react'

/**
 * Topbar - Top navigation bar with branding and page title
 * 
 * Props:
 *   title: string - current page key ("overview", "netmap", "aisummary", "runsel")
 */
export default function Topbar({title}){
  const titles = { runsel:'Run Selector', overview:'Overview Dashboard', netmap:'Network Map', aisummary:'AI Assistant', create:'Create New Run' }
  return (
    <div className="topbar">
      <div className="topbar-brand">DT Results</div>
      <div className="topbar-sep" />
      <div className="topbar-title" id="topbarTitle">{titles[title]||''}</div>
      <div className="topbar-spacer" />
      {title === 'overview' && <button className="topbar-btn">Export Report</button>}
    </div>
  )
}
