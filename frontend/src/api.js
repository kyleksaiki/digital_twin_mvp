const API_BASE = 'http://localhost:8000/api'

async function getJson(path){
  const res = await fetch(`${API_BASE}${path}`)
  if(!res.ok) throw new Error('Network error')
  return res.json()
}

async function postJson(path, body){
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  })
  if(!res.ok) throw new Error('Network error')
  return res.json()
}

export function fetchRuns(){ return getJson('/runs') }
export function fetchRun(id){ return getJson(`/runs/${id}`) }
export function fetchNetmap(runId){ 
  if(runId) return getJson(`/runs/${runId}/netmap`)
  return getJson('/netmap')
}
export function fetchAiSummary(runId){ 
  if(runId) return getJson(`/ai/summary?run_id=${runId}`)
  return getJson('/ai/summary')
}
export function createRun(runData){ return postJson('/runs/create', runData) }
export async function postChat(q){
  const res = await fetch(`${API_BASE}/ai/chat`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({q}) })
  return res.json()
}
