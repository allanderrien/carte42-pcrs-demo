import React, { useState, useEffect, useMemo } from 'react'
import { RAPPORTS_BASE_URL, RAPPORTS_ZIP_FILE } from '../config.js'

// Normalisation pour la recherche : sans accents, minuscules
const fold = s =>
  (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

export default function RapportModal({ onClose }) {
  const [manifest, setManifest] = useState(null)
  const [query, setQuery]       = useState('')
  const [selected, setSelected] = useState(null)  // { label, file }

  useEffect(() => {
    fetch('./data/rapports_manifest.json')
      .then(r => r.json())
      .then(setManifest)
      .catch(() => setManifest({ epci: [] }))
  }, [])

  // Groupes EPCI filtrés par la recherche
  const groups = useMemo(() => {
    if (!manifest) return []
    const q = fold(query.trim())
    return manifest.epci
      .map(e => ({
        ...e,
        communes: q
          ? e.communes.filter(c => fold(c.label).includes(q))
          : e.communes,
      }))
      .filter(e => e.communes.length > 0)
  }, [manifest, query])

  function handleGenerate() {
    if (!selected || !RAPPORTS_BASE_URL) return
    const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
    const a = Object.assign(document.createElement('a'), {
      href: `${base}/${selected.file}`,
      download: selected.file.split('/').pop(),
      target: '_blank',
      rel: 'noopener',
    })
    a.click()
  }

  const canZip = RAPPORTS_BASE_URL && RAPPORTS_ZIP_FILE

  function handleDownloadAll() {
    if (!canZip) return
    const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
    const a = Object.assign(document.createElement('a'), {
      href: `${base}/${RAPPORTS_ZIP_FILE}`,
      download: RAPPORTS_ZIP_FILE,
      target: '_blank',
      rel: 'noopener',
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
          {canZip && (
            <div className="rapport-all">
              <button className="rapport-dl-all-btn" onClick={handleDownloadAll}>
                ⬇ Télécharger tous les rapports (ZIP)
              </button>
              <div className="rapport-all-hint">
                Une seule archive — 283 rapports communaux, ~1,3 Go.
              </div>
            </div>
          )}

          <p className="rapport-hint">
            …ou recherchez une commune pour télécharger son rapport de détection
            des changements PCRS individuellement.
          </p>

          {!RAPPORTS_BASE_URL && (
            <p className="rapport-warn">
              ⚠ Hébergement des rapports non configuré (RAPPORTS_BASE_URL).
              La sélection fonctionne mais le téléchargement est désactivé.
            </p>
          )}

          <input
            className="rapport-search"
            type="text"
            placeholder="Rechercher une commune…"
            value={query}
            onChange={e => setQuery(e.target.value)}
            autoFocus
          />

          <div className="rapport-commune-list">
            {!manifest && <div className="rapport-empty">Chargement…</div>}
            {manifest && groups.length === 0 && (
              <div className="rapport-empty">Aucune commune trouvée.</div>
            )}
            {groups.map(e => (
              <React.Fragment key={e.slug}>
                <div className="rapport-epci-label">{e.label}</div>
                {e.communes.map(c => (
                  <button
                    key={c.file}
                    className={`rapport-commune-btn${selected?.file === c.file ? ' active' : ''}`}
                    onClick={() => setSelected(c)}
                  >
                    {c.label}
                  </button>
                ))}
              </React.Fragment>
            ))}
          </div>
        </div>

        <div className="rapport-modal-footer">
          <button
            className="rapport-dl-btn"
            onClick={handleGenerate}
            disabled={!selected || !RAPPORTS_BASE_URL}
          >
            ⬇ Télécharger le rapport — {selected?.label || '…'}
          </button>
        </div>
      </div>
    </div>
  )
}
