import React from 'react'

export default function Modal({
  open,
  title,
  subtitle,
  onClose,
  expanded,
  onToggleExpand,
  children,
  footer,
}) {
  if (!open) return null

  return (
    <div className="ui-modal-overlay" role="dialog" aria-modal="true">
      <div className={`ui-modal ${expanded ? 'expanded' : ''}`}>
        <div className="ui-modal-header">
          <div>
            <div className="ui-modal-title">{title}</div>
            {subtitle ? <div className="ui-modal-subtitle">{subtitle}</div> : null}
          </div>
          <div className="ui-modal-actions">
            {onToggleExpand ? (
              <button className="ui-modal-btn" onClick={onToggleExpand}>
                {expanded ? 'Compact' : 'Expand'}
              </button>
            ) : null}
            <button className="ui-modal-btn" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="ui-modal-body">{children}</div>
        {footer ? <div className="ui-modal-footer">{footer}</div> : null}
      </div>
    </div>
  )
}
