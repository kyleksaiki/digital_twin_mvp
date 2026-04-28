import React from 'react'

export default function ModalStepper({
  open,
  steps,
  activeIndex,
  onStepChange,
  onClose,
  footer,
  dialogClassName,
}) {
  if (!open || !steps || steps.length === 0) return null

  const clampedIndex = Math.max(0, Math.min(activeIndex, steps.length - 1))
  const activeStep = steps[clampedIndex]
  const showDots = steps.length > 1
  const dialogClasses = ['modal-dialog', dialogClassName].filter(Boolean).join(' ')

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className={dialogClasses}>
        
        {showDots ? (
          <div className="modal-stepper">
            {steps.map((step, index) => (
              <button
                key={step.id || step.title || index}
                type="button"
                className={`modal-step-dot ${index === clampedIndex ? 'active' : ''}`}
                onClick={() => onStepChange?.(index)}
                aria-label={`Step ${index + 1}: ${step.title}`}
                aria-current={index === clampedIndex ? 'step' : undefined}
              />
            ))}
          </div>
        ) : null}
        <div className="modal-header">
          <div className="modal-title">{activeStep?.title}</div>
          {onClose ? (
            <button
              className="modal-close"
              onClick={onClose}
              type="button"
              aria-label="Close dialog"
            >
              🞬
            </button>
          ) : null}
        </div>
        <div className="modal-body">{activeStep?.content}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  )
}
