import React, { useState } from 'react'
import Topbar from './components/Topbar'
import Sidebar from './components/Sidebar'
import RunSelector from './components/RunSelector'
import Overview from './components/Overview'
import NetMap from './components/NetMap'
import AISummary from './components/AISummary'
import CreateRun from './components/CreateRun'
import DetailPanel from './components/DetailPanel'

// Styles
import './styles/globals.css'
import './styles/components.css'
import './styles/Topbar.css'
import './styles/Sidebar.css'
import './styles/RunSelector.css'
import './styles/Overview.css'
import './styles/NetMap.css'
import './styles/DetailPanel.css'
import './styles/AISummary.css'
import './styles/CreateRun.css'

export default function App(){
  const [page, setPage] = useState('runsel')
  const [loadedRun, setLoadedRun] = useState(null)
  const [panelOpen, setPanelOpen] = useState(false)
 
  return (
    <div className={`app ${panelOpen ? 'panel-open':''}`} id="app">
      <Topbar title={page} />
      <Sidebar onNavigate={setPage} active={page} />

      <div className={`page ${page==='runsel'?'active':''}`} id="pageRunSelector">
        <div className="loaded-run-bar" id="loadedRunBar" style={{display: loadedRun? 'flex':'none'}}>
          <div className="dot"></div>
          <span id="loadedRunText">{loadedRun? `Loaded: ${loadedRun.name} (${loadedRun.hw}, ${loadedRun.duration})` : ''}</span>
        </div>
        <RunSelector page={page} onOpen={async (r)=>{ setLoadedRun(r); setPage('overview') }} />
      </div>

      <div className={`page ${page==='overview'?'active':''}`} id="pageOverview">
        <Overview run={loadedRun} />
      </div>

      <div className={`page ${page==='netmap'?'active':''}`} id="pageNetMap">
        <NetMap run={loadedRun} onPanelOpen={(open)=>setPanelOpen(open)} />
      </div>

      <div className={`page ${page==='aisummary'?'active':''}`} id="pageAISummary">
        <AISummary />
      </div>

      <div className={`page ${page==='create'?'active':''}`} id="pageCreateRun">
        <CreateRun onNavigate={setPage} onRunCreated={() => { setLoadedRun(null); setPage('runsel'); }} />
      </div>

      <div className="detail-panel" id="detailPanel"><DetailPanel/></div>
    </div>
  )
}
