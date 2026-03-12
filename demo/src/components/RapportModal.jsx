import React, { useState } from 'react'

const COMMUNES = [
  { label: 'Brecé',              file: 'Rapport_PCRS_Brece.pdf' },
  { label: 'Châteaugiron',       file: 'Rapport_PCRS_Chateaugiron.pdf' },
  { label: 'Domloup',            file: 'Rapport_PCRS_Domloup.pdf' },
  { label: 'Nouvoitou',          file: 'Rapport_PCRS_Nouvoitou.pdf' },
  { label: 'Noyal-sur-Vilaine',  file: 'Rapport_PCRS_Noyal-sur-Vilaine.pdf' },
  { label: 'Servon-sur-Vilaine', file: 'Rapport_PCRS_Servon-sur-Vilaine.pdf' },
]

export default function RapportModal({ onClose }) {
  const [selected, setSelected] = useState('')

  function handleGenerate() {
    if (!selected) return
    const commune = COMMUNES.find(c => c.label === selected)
    if (!commune) return
    const a = Object.assign(document.createElement('a'), {
      href: `./rapports/${commune.file}`,
      download: commune.file,
      target: '_blank',
    })
    a.click()
  }

  return (
    <div className="rapport-overlay" onClick={onClose}>
      <div className="rapport-modal" onClick={e => e.stopPropagation()}>
        <div className="rapport-modal-header">
          <span>Rapport PCRS par commune</span>
          <button className="rapport-close" onClick={onClose}>✕</button>
        </div>
        <div className="rapport-modal-body">
          <p className="rapport-hint">
            Sélectionnez une commune pour télécharger son rapport de détection des changements PCRS.
          </p>
          <div className="rapport-commune-list">
            {COMMUNES.map(c => (
              <button
                key={c.label}
                className={`rapport-commune-btn${selected === c.label ? ' active' : ''}`}
                onClick={() => setSelected(c.label)}
              >
                {c.label}
              </button>
            ))}
          </div>
        </div>
        <div className="rapport-modal-footer">
          <button
            className="rapport-dl-btn"
            onClick={handleGenerate}
            disabled={!selected}
          >
            ⬇ Télécharger le rapport — {selected || '…'}
          </button>
        </div>
      </div>
    </div>
  )
}
