import React from 'react'

export default function DetailPanel(){
  return (
    <div style={{padding:16}}>
      <div className="dp-header">
        <div>
          <div className="dp-title">Details</div>
          <div className="dp-subtitle">Select a node</div>
        </div>
        <div className="dp-close">×</div>
      </div>
      <div className="dp-section">
        <div className="dp-section-title">Info</div>
        <div className="dp-row"><div className="dp-row-l">Selected</div><div className="dp-row-v">None</div></div>
      </div>
    </div>
  )
}
