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

  if(loading) return <div style={{padding:24}}>Loading runs…</div>
  const runs = data?.runs || []

  function selectRun(i){ setSelectedIdx(selectedIdx===i? null: i) }

  async function openSelected(){
    if(selectedIdx===null) return
    const r = runs[selectedIdx]
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
          <div className="pg-subtitle">Select a simulation run to analyze</div>
        </div>
        <button className="btn btn-primary" disabled={selectedIdx===null} onClick={openSelected}>Open Run</button>
      </div>
      
      <div className="controls-row">
        <input type="text" className="search-input" placeholder="Search by run name…" />
        <select className="ai-filter">
          <option>Model: All</option>
          <option>BirdNET v2.4</option>
          <option>BirdNET v2.3</option>
        </select>
        <select className="ai-filter">
          <option>Hardware: All</option>
          <option>ESP32</option>
          <option>Radxa Zero</option>
        </select>
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
              <th>Hardware</th>
              <th>Duration</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="runsTableBody">
            {runs.map((r,i) => (
              <tr key={r.id} onClick={()=>selectRun(i)} className={`${selectedIdx===i? 'selected':''}`}>
                <td className="cb-cell">
                  <div className={`custom-cb ${selectedIdx===i? 'checked':''}`} onClick={(e)=>{ e.stopPropagation(); selectRun(i) }}></div>
                </td>
                <td>{r.name}</td>
                <td style={{fontFamily:'var(--font-mono)',fontSize:11}}>{r.date}</td>
                <td>{r.scenario}</td>
                <td><span className="badge badge-model">{r.model}</span></td>
                <td><span className="badge badge-hw">{r.hw}</span></td>
                <td style={{fontFamily:'var(--font-mono)',fontSize:11}}>{r.duration}</td>
                <td><span className={`status-dot ${r.status}`}></span>{r.status.charAt(0).toUpperCase()+r.status.slice(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
