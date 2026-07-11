import React, { useState, useEffect, useMemo } from 'react'
import { RAPPORTS_BASE_URL, RAPPORTS_ZIP_FILE } from '../config.js'

// Normalisation pour la recherche : sans accents, minuscules
const fold = s =>
  (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

const sleep = ms => new Promise(r => setTimeout(r, ms))

export default function RapportModal({ onClose }) {
  const [manifest, setManifest] = useState(null)
  const [query, setQuery]       = useState('')
  // Sélection multiple : ensemble des `file` cochés
  const [selected, setSelected] = useState(() => new Set())
  const [progress, setProgress] = useState(null) // { done, total } pendant un téléchargement

  useEffect(() => {
    fetch('./data/rapports_manifest.json')
      .then(r => r.json())
      .then(setManifest)
      .catch(() => setManifest({ epci: [] }))
  }, [])

  // Index file -> commune (toutes communes, indépendant du filtre de recherche)
  const byFile = useMemo(() => {
    const m = new Map()
    if (manifest) for (const e of manifest.epci)
      for (const c of e.communes) m.set(c.file, c)
    return m
  }, [manifest])

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

  const canDownload = !!RAPPORTS_BASE_URL
  const downloading = progress !== null

  function toggleCommune(file) {
    setSelected(prev => {
      const next = new Set(prev)
      next.has(file) ? next.delete(file) : next.add(file)
      return next
    })
  }

  // Coche / décoche toutes les communes VISIBLES d'un EPCI
  function toggleEpci(epci, allSel) {
    setSelected(prev => {
      const next = new Set(prev)
      for (const c of epci.communes) allSel ? next.delete(c.file) : next.add(c.file)
      return next
    })
  }

  function clearSelection() {
    setSelected(new Set())
  }

  // ── Téléchargement séquentiel d'une liste de rapports ─────────────────────
  // Les PDF sont servis par l'hébergement externe avec Content-Disposition:
  // attachment → chaque lien se télécharge (au lieu de s'ouvrir dans un onglet).
  async function downloadFiles(files) {
    if (!canDownload || downloading || !files.length) return
    const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
    setProgress({ done: 0, total: files.length })
    for (let i = 0; i < files.length; i++) {
      const a = Object.assign(document.createElement('a'), {
        href: `${base}/${files[i]}`,
        download: files[i].split('/').pop(),
        target: '_blank',
        rel: 'noopener',
      })
      document.body.appendChild(a)
      a.click()
      a.remove()
      setProgress({ done: i + 1, total: files.length })
      // Petit délai : évite que le navigateur ignore des téléchargements rapprochés
      if (i < files.length - 1) await sleep(500)
    }
    await sleep(400)
    setProgress(null)
  }

  function downloadEpci(epci) {
    downloadFiles(epci.communes.map(c => c.file))
  }

  function downloadSelection() {
    // Ordre du manifeste pour un téléchargement déterministe
    const files = []
    if (manifest) for (const e of manifest.epci)
      for (const c of e.communes) if (selected.has(c.file)) files.push(c.file)
    downloadFiles(files)
  }

  const canZip = RAPPORTS_BASE_URL && RAPPORTS_ZIP_FILE

  function handleDownloadAll() {
    if (!canZip) return
    downloadFiles([RAPPORTS_ZIP_FILE])
  }

  const selCount = selected.size

  return (
    <div className="rapport-overlay" onClick={onClose}>
      <div className="rapport-modal" onClick={e => e.stopPropagation()}>
        <div className="rapport-modal-header">
          <span>Rapports PCRS par commune</span>
          <button className="rapport-close" onClick={onClose}>✕</button>
        </div>

        <div className="rapport-modal-body">
          {canZip && (
            <div className="rapport-all">
              <button
                className="rapport-dl-all-btn"
                onClick={handleDownloadAll}
                disabled={downloading}
              >
                ⬇ Télécharger tous les rapports (ZIP)
              </button>
              <div className="rapport-all-hint">
                Une seule archive — 283 rapports communaux, ~1,3 Go.
              </div>
            </div>
          )}

          <p className="rapport-hint">
            …ou cochez une ou plusieurs communes (ou un EPCI entier) pour
            télécharger les rapports de détection des changements PCRS.
          </p>

          {!canDownload && (
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
            {groups.map(e => {
              const selInGroup = e.communes.filter(c => selected.has(c.file)).length
              const allSel = selInGroup === e.communes.length && e.communes.length > 0
              const someSel = selInGroup > 0 && !allSel
              return (
                <div className="rapport-epci-group" key={e.slug}>
                  <div className="rapport-epci-row">
                    <label className="rapport-epci-check">
                      <input
                        type="checkbox"
                        checked={allSel}
                        ref={el => { if (el) el.indeterminate = someSel }}
                        onChange={() => toggleEpci(e, allSel)}
                      />
                      <span className="rapport-epci-label">
                        {e.label}
                        <span className="rapport-epci-count"> ({e.communes.length})</span>
                      </span>
                    </label>
                    <button
                      className="rapport-epci-dl"
                      title={`Télécharger les ${e.communes.length} rapports de ${e.label}`}
                      onClick={() => downloadEpci(e)}
                      disabled={!canDownload || downloading}
                    >
                      ⬇ EPCI
                    </button>
                  </div>
                  {e.communes.map(c => (
                    <label
                      key={c.file}
                      className={`rapport-commune-row${selected.has(c.file) ? ' active' : ''}`}
                    >
                      <input
                        type="checkbox"
                        checked={selected.has(c.file)}
                        onChange={() => toggleCommune(c.file)}
                      />
                      <span>{c.label}</span>
                    </label>
                  ))}
                </div>
              )
            })}
          </div>
        </div>

        <div className="rapport-modal-footer">
          {selCount > 0 && (
            <div className="rapport-sel-bar">
              <span>{selCount} commune{selCount > 1 ? 's' : ''} sélectionnée{selCount > 1 ? 's' : ''}</span>
              <button className="rapport-sel-clear" onClick={clearSelection} disabled={downloading}>
                Tout décocher
              </button>
            </div>
          )}
          <button
            className="rapport-dl-btn"
            onClick={downloadSelection}
            disabled={!selCount || !canDownload || downloading}
          >
            {downloading
              ? `Téléchargement… ${progress.done}/${progress.total}`
              : `⬇ Télécharger la sélection${selCount ? ` (${selCount})` : ''}`}
          </button>
          {selCount > 1 && !downloading && (
            <div className="rapport-multi-hint">
              Votre navigateur peut demander d'autoriser les téléchargements multiples.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
