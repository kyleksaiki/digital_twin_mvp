import React from 'react'

/**
 * Sidebar - Navigation and context filters
 * 
 * Props:
 *   onNavigate: (page: string) => void - called when user clicks nav items
 *   active: string - current active page ("overview", "netmap", "aisummary", "runsel")
 * 
 * Displays different filters depending on active page (e.g., network filters for NetMap)
 */
export default function Sidebar({onNavigate, active, reroutes = [], isRunLoaded}){
  return (
    <div className="sidebar" id="sidebar">
      
      <div className="sb-label">Run Tools</div>
      <div className={`sb-item ${active==='runsel'?'active':''}`} id="navRunSel" onClick={()=>onNavigate('runsel')}><span className="sb-icon">☰</span> Run Selector</div>
      <div className={`sb-item ${active==='create'?'active':''}`} id="navCreate" onClick={()=>onNavigate('create')}><span className="sb-icon">＋</span> Create New Run</div>


      <div className="sb-divider"></div>

      <div className="sb-label">Run Analysis</div>
      <div className={`sb-item ${active==='overview'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navOverview" onClick={()=>isRunLoaded?onNavigate('overview'):''}><span className="sb-icon">◫</span> Model Performance</div>
      <div className={`sb-item ${active==='netmap'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navNetMap" onClick={()=>isRunLoaded?onNavigate('netmap'):''}><span className="sb-icon">⚡</span> Battery Statistics</div>
      <div className={`sb-item ${active==='aisummary'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navAISummary" onClick={()=>isRunLoaded?onNavigate('aisummary'):''}><span className="sb-icon">◈</span> AI Assistant</div>

      <div className={`sb-ctx ${active==='netmap'?'visible':''}`} id="ctxNetMap">
        <div className="sb-divider"></div>
        <div className="sb-label">Battery Filters</div>
        <div className="f-section">
          <div className="f-group">
            <div className="f-group-label">View <span className="help-icon">?<span className="help-tip">Switch between battery telemetry and component power breakdown.</span></span></div>
            <select className="f-select" id="trafficSelect">
              <option value="all">All Components</option>
              <option value="alerts">Processor Only</option>
              <option value="heartbeat">Radio Only</option>
              <option value="ai">Microphone Only</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}
