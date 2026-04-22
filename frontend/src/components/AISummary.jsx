import React, { useState, useRef, useEffect, useMemo } from 'react'
import { fetchAiSummary, postChat } from '../api'
import { useApi } from '../hooks/useApi'
import { buildAssistantContext } from '../utils/aiContext'

/**
 * AIAssistant - AI-generated insights and chat interface
 * 
 * Props:
 *   loadedRun: object - Currently loaded run object with id, name, etc.
 * 
 * Fetches:
 *   1. GET /api/ai/summary?run_id={runId}
 *   2. POST /api/ai/chat (when user sends message)
 * 
 * Expected responses:
 *   
 *   GET /api/ai/summary:
 *   {
 *     title: string
 *     content: string (AI-generated summary of the run)
 *   }
 *   
 *   POST /api/ai/chat (request):
 *   {
 *     q: string (user question)
 *   }
 *   
 *   POST /api/ai/chat (response):
 *   {
 *     answer: string
 *   }
 */
export default function AIAssistant({loadedRun}){
  const { data, loading } = useApi(()=>fetchAiSummary(loadedRun?.id), [loadedRun?.id])
  const [q, setQ] = useState('')
  const [messages, setMessages] = useState([])
  const [isSending, setIsSending] = useState(false)
  const messagesEndRef = useRef(null)

  const assistantContext = useMemo(
    () => buildAssistantContext(loadedRun, data),
    [loadedRun, data],
  )

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    setMessages([])
  }, [loadedRun?.id])

  async function send(){
    if (!q.trim()) return
    
    const userMessage = q.trim()
    setQ('')
    setMessages(prev => [...prev, { type: 'user', text: userMessage }])
    setIsSending(true)
    
    try {
      const r = await postChat(userMessage, assistantContext)
      setMessages(prev => [...prev, { type: 'assistant', text: r.answer }])
    } catch (err) {
      setMessages(prev => [...prev, { type: 'assistant', text: 'Sorry, I encountered an error. Please try again.' }])
    } finally {
      setIsSending(false)
    }
  }

  if(loading) return <div style={{padding:24}}>Loading AI Assistant…</div>

  return (
    <div style={{padding:24, display:'flex', flexDirection:'column', height:'100%', overflow:'hidden'}}>
      <div className="ai-intro-banner">
        <div className="ai-intro-title">Ask the Assistant</div>
        <div className="ai-intro-text">
          Ask about run metrics, visualizations, or system behavior.
          The assistant supports both general guidance and run-specific analysis as context grows.
        </div>
        <div className="ai-intro-meta">
          <span className="ai-intro-chip">Mode: {assistantContext.mode === 'run-specific' ? 'Run-Specific' : 'General'}</span>
          {assistantContext.run ? <span className="ai-intro-chip">Run: {assistantContext.run.name}</span> : null}
        </div>
      </div>

      <div className="summary-card">
        <div className="summary-card-title">AI Assistant</div>
        <div className="summary-text">{data?.content || "No summary available"}</div>
      </div>
      
      <div className="chat-container" style={{display:'flex', flexDirection:'column', flex:1, marginTop:16}}>
        <div className="chat-messages" style={{flex:1, overflowY:'auto', marginBottom:12}}>
          {messages.map((msg, idx) => (
            <div key={idx} className={`chat-msg ${msg.type}`}>
              <div className="chat-bubble">{msg.text}</div>
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
        
        <div className="chat-input-row">
          <input 
            className="chat-input" 
            value={q} 
            onChange={e=>setQ(e.target.value)} 
            onKeyDown={e=>{if(e.key==="Enter" && !isSending) send();}} 
            placeholder={assistantContext.mode === 'run-specific' ? 'Ask about this run, e.g. latency spikes or battery trends...' : 'Ask general questions, e.g. what is confidence threshold?'}
            disabled={isSending}
          />
          <button className="chat-send" onClick={send} disabled={isSending}>↩</button>
        </div>
      </div>
    </div>
  )
}
