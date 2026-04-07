import React, { useState } from 'react'
import { fetchRuns, fetchRun } from '../api'
import { useApi } from '../hooks/useApi'

/**
 * Run Selector - displays list of available simulation runs
 * 
 * Fetches: GET /api/runs
 * 
 * Expected response:
 *   {
 *     runs: [
 *       {
 *         id: number
 *         name: string
 *         date: string (YYYY-MM-DD)
 *         scenario: string
 *         model: string (e.g., "BirdNET v2.4")
 *         hw: string (e.g., "Radxa Zero" or "ESP32")
 *         duration: string (e.g., "24h", "12h", "8h")
 *         status: "pass" | "warning" | "fail"
 *       }
 *     ]
 *   }
 * 
 * Props:
 *   page: string - current page (used to trigger refetch when navigating back)
 *   onOpen: (run) => void - called when user opens a run
 */
export default function RunSelector({page, onOpen}){
  const { data, loading } = useApi(()=>fetchRuns(), [page])
  const [selectedIdx, setSelectedIdx] = useState(null)
  const [searchQuery, setSearchQuery] = useState('')

  if(loading) return <div style={{padding:24}}>Loading runs…</div>
  const runs = data?.runs || []

  // Filter runs based on search query
  const filteredRuns = runs.filter(r => {
    if (!searchQuery.trim()) return true
    const query = searchQuery.toLowerCase()
    return (
      r.name.toLowerCase().includes(query) ||
      r.scenario.toLowerCase().includes(query) ||
      r.model.toLowerCase().includes(query) ||
      (r.shamanIProcessor && r.shamanIProcessor.toLowerCase().includes(query)) ||
      (r.shamanIIProcessor && r.shamanIIProcessor.toLowerCase().includes(query)) ||
      (r.hw && r.hw.toLowerCase().includes(query)) ||
      r.status.toLowerCase().includes(query) ||
      r.date.includes(query)
    )
  })

  function selectRun(i){ setSelectedIdx(selectedIdx===i? null: i) }

  async function openSelected(){
    if(selectedIdx===null) return
    const r = filteredRuns[selectedIdx]
    try{
      const detail = await fetchRun(r.id)
      onOpen(detail)
    }catch(e){ onOpen(r) }
  }

  return (
    <div style={{overflowY:'auto', padding:24}}>
      <div className="pg-header">
        <div>
          <div className="pg-title">Run Selector</div>
        </div>
        <button className="btn btn-primary" disabled={selectedIdx===null} onClick={openSelected}>Open Run</button>
      </div>
      
      <div className="controls-row">
        <input 
          type="text" 
          className="search-input" 
          placeholder="Search…" 
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value)
            setSelectedIdx(null)
          }}
        />
      </div>

      <div className="table-container">
        <table className="data-table">
          <thead>
            <tr>
              <th className="cb-cell"></th>
              <th>Run Name</th>
              <th>Date</th>
              <th>Scenario</th>
              <th>AI Model</th>
              <th>Shaman I Processor</th>
              <th>Shaman II Processor</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="runsTableBody">
            {filteredRuns.length > 0 ? (
              filteredRuns.map((r,i) => (
                <tr key={r.id} onClick={()=>selectRun(i)} className={`${selectedIdx===i? 'selected':''}`}>
                  <td className="cb-cell">
                    <div className={`custom-cb ${selectedIdx===i? 'checked':''}`} onClick={(e)=>{ e.stopPropagation(); selectRun(i) }}></div>
                  </td>
                  <td>{r.name}</td>
                  <td style={{fontFamily:'var(--font-mono)',fontSize:11}}>{r.date}</td>
                  <td>{r.scenario}</td>
                  <td><span className="badge badge-model">{r.model}</span></td>
                  <td><span className="badge badge-hw">{r.shamanIProcessor || r.hw || "—"}</span></td>
                  <td><span className="badge badge-hw">{r.shamanIIProcessor || "—"}</span></td>
                  <td style={{fontFamily:'var(--font-mono)',fontSize:11}}>{r.duration}</td>
                  <td><span className={`status-dot ${r.status}`}></span>{r.status.charAt(0).toUpperCase()+r.status.slice(1)}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="9" style={{textAlign:'center', padding:'24px', color:'var(--text-muted)'}}>
                  No runs match "{searchQuery}"
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
