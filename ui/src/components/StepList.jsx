import React from 'react'
import { PIPELINE_STEPS } from '../config.js'

function stepStatus(step, pipelineStatus) {
  if (!pipelineStatus) return 'pending'
  const allOk  = step.outputKeys.every(k => pipelineStatus[k]?.ok)
  const someOk = step.outputKeys.some(k  => pipelineStatus[k]?.ok)
  if (allOk)  return 'done'
  if (someOk) return 'partial'
  return 'pending'
}

const STATUS_ICON  = { done: '✓', partial: '~', pending: '○' }
const STATUS_COLOR = { done: '#27ae60', partial: '#f39c12', pending: '#bdc3c7' }

export default function StepList({ pipelineStatus, onRefresh, onRun, onStop, runningSteps, activeLogStep }) {
  return (
    <section className="sidebar-section">
      <div className="section-header">
        <span>Pipeline</span>
        <button className="refresh-btn" onClick={onRefresh} title="Rafraîchir le statut">↺</button>
      </div>

      <ol className="step-list">
        {PIPELINE_STEPS.map(step => {
          const status  = stepStatus(step, pipelineStatus)
          const color   = STATUS_COLOR[status]
          const isRunning = runningSteps?.includes(String(step.id))
          const isActive  = activeLogStep === String(step.id)

          const sizes = pipelineStatus
            ? step.outputKeys
                .filter(k => pipelineStatus[k]?.ok)
                .map(k => `${pipelineStatus[k].size_kb} Ko`)
                .join(', ')
            : null

          return (
            <li key={step.id} className="step-item" data-status={status}>
              <div className="step-icon" style={{ background: isRunning ? '#e67e22' : color }}>
                {isRunning ? '…' : STATUS_ICON[status]}
              </div>

              <div className="step-body">
                <div className="step-label-row">
                  <span className="step-label">{step.id}. {step.label}</span>
                  {isRunning ? (
                    <button
                      className="stop-btn"
                      onClick={() => onStop(String(step.id))}
                      title="Arrêter le script"
                    >
                      ■
                    </button>
                  ) : (
                    <button
                      className={`run-btn ${isActive ? 'run-btn--active' : ''}`}
                      onClick={() => onRun(String(step.id), step.label)}
                      title={`Lancer ${step.script}`}
                    >
                      ▶
                    </button>
                  )}
                </div>
                <div className="step-script">{step.script}</div>
                <div className="step-desc">{step.description}</div>
                {sizes && <div className="step-size">{sizes}</div>}
              </div>
            </li>
          )
        })}
      </ol>

      <div className="run-hint">
        Cliquez <b>▶</b> pour lancer une étape · ↺ pour actualiser
      </div>
    </section>
  )
}
