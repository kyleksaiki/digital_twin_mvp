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
      <div className={`sb-item ${active==='overview'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navOverview" onClick={()=>isRunLoaded?onNavigate('overview'):''}><span className="sb-icon">◫</span> Overview Dashboard</div>
      <div className={`sb-item ${active==='netmap'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navNetMap" onClick={()=>isRunLoaded?onNavigate('netmap'):''}><span className="sb-icon">⬡</span> Network Map</div>
      <div className={`sb-item ${active==='aisummary'?'active':''} ${isRunLoaded?'':'disabled'}`} id="navAISummary" onClick={()=>isRunLoaded?onNavigate('aisummary'):''}><span className="sb-icon">◈</span> AI Assistant</div>

      <div className={`sb-ctx ${active==='netmap'?'visible':''}`} id="ctxNetMap">
        <div className="sb-divider"></div>
        <div className="sb-label">Map Filters</div>
        <div className="f-section">
          <div className="f-group">
            <div className="f-group-label">Traffic Type <span className="help-icon">?<span className="help-tip">Filter edges by traffic category to isolate congestion sources.</span></span></div>
            <select className="f-select" id="trafficSelect">
              <option value="all">All Traffic</option>
              <option value="alerts">Alerts Only</option>
              <option value="heartbeat">Heartbeat Only</option>
              <option value="ai">AI Detections Only</option>
            </select>
          </div>
        </div>
        <div className="sb-divider"></div>
        <div className="sb-label">Reroutes</div>
        <details className="reroutes-panel">
          <summary className="reroutes-header" id="reroutesHdr">Reroute Events ({reroutes.length})</summary>
          <div className="reroutes-body" id="reroutesBody">
            {reroutes.length > 0 ? reroutes.map((r, i) => (
              <div className="reroute-item" key={i}>
                <div className="reroute-dot"></div>
                <span className="reroute-from">{r.from}</span> → <span className="reroute-to">{r.to}</span>
              </div>
            )) : (
              <div style={{fontSize:11,color:'var(--text-muted)',padding:'4px 0'}}>No reroute events</div>
            )}
          </div>
        </details>
      </div>
    </div>
  )
}
