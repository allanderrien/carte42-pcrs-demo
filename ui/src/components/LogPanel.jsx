import React, { useEffect, useRef } from 'react'

export default function LogPanel({ step, stepLabel, logs, running, onClose, onStop }) {
  const bottomRef = useRef(null)

  // Auto-scroll vers le bas à chaque nouveau log
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="log-panel">
      <div className="log-header">
        <div className="log-title">
          <span className="log-indicator" data-running={running} />
          {stepLabel}
        </div>
        <button className="log-close" onClick={onClose}>✕</button>
      </div>

      <div className="log-body">
        {logs.length === 0 && (
          <span className="log-empty">En attente de logs…</span>
        )}
        {logs.map((line, i) => (
          <div
            key={i}
            className={
              'log-line' +
              (line.startsWith('✓') ? ' log-line--ok'   : '') +
              (line.startsWith('✗') ? ' log-line--err'  : '') +
              (line.startsWith('⚠') ? ' log-line--warn' : '') +
              (line.startsWith('▶') ? ' log-line--info' : '') +
              (line.startsWith('─') ? ' log-line--sep'  : '')
            }
          >
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {running && (
        <div className="log-footer">
          <span className="log-spinner" />
          <span>Exécution en cours…</span>
          <button className="stop-btn stop-btn--sm" onClick={() => onStop(step)}>
            ■ Arrêter
          </button>
        </div>
      )}
    </div>
  )
}
