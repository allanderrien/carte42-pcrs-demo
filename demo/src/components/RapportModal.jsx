import React, { useState, useEffect, useMemo } from 'react'
import { RAPPORTS_BASE_URL, RAPPORTS_ZIP_FILE } from '../config.js'
import { buildZip } from '../lib/zip.js'

// Normalisation pour la recherche : sans accents, minuscules
const fold = s =>
  (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

// Nom de fichier ZIP sûr : sans accents, alphanum + tirets
const slugify = s =>
  (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '-').replace(/^-+|-+$/g, '')

export default function RapportModal({ onClose }) {
  const [manifest, setManifest] = useState(null)
  const [query, setQuery]       = useState('')
  // Sélection multiple : ensemble des `file` cochés
  const [selected, setSelected] = useState(() => new Set())
  const [progress, setProgress] = useState(null) // { phase:'fetch'|'zip', done, total }
  const [error, setError]       = useState(null)

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

  const canDownload = !!RAPPORTS_BASE_URL
  const busy = progress !== null

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

  // ── Téléchargement direct d'un lien (PDF unique ou ZIP départemental) ─────
  // Le serveur renvoie Content-Disposition: attachment → le lien se télécharge.
  function triggerLink(url, name) {
    const a = Object.assign(document.createElement('a'), { href: url, download: name })
    document.body.appendChild(a)
    a.click()
    a.remove()
  }

  function triggerBlob(blob, name) {
    const url = URL.createObjectURL(blob)
    triggerLink(url, name)
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  }

  // ── Récupère les PDF puis les regroupe dans UNE archive ZIP ───────────────
  async function fetchAndZip(items, zipName) {
    const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
    setError(null)
    setProgress({ phase: 'fetch', done: 0, total: items.length })
    try {
      const files = []
      for (let i = 0; i < items.length; i++) {
        // cache:'no-store' → évite de réutiliser une réponse en cache SANS
        // en-tête CORS (mise en cache avant l'ajout d'Access-Control-Allow-Origin),
        // qui ferait échouer la requête cross-origin.
        const res = await fetch(`${base}/${items[i].file}`, { cache: 'no-store', mode: 'cors' })
        if (!res.ok) throw new Error(`${items[i].label} : HTTP ${res.status}`)
        files.push({
          name: items[i].file.split('/').pop(),
          data: new Uint8Array(await res.arrayBuffer()),
        })
        setProgress({ phase: 'fetch', done: i + 1, total: items.length })
      }
      setProgress({ phase: 'zip', done: items.length, total: items.length })
      // Laisse le navigateur peindre l'état « compression » avant le travail bloquant
      await new Promise(r => setTimeout(r, 30))
      triggerBlob(buildZip(files), zipName)
    } catch (e) {
      setError(e?.message || 'Échec du téléchargement. Réessayez.')
    } finally {
      setProgress(null)
    }
  }

  // Dispatch : 1 rapport → PDF direct ; plusieurs → ZIP
  function download(items, zipBaseName) {
    if (!canDownload || busy || !items.length) return
    if (items.length === 1) {
      const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
      triggerLink(`${base}/${items[0].file}`, items[0].file.split('/').pop())
      return
    }
    fetchAndZip(items, `${zipBaseName}.zip`)
  }

  function downloadEpci(epci) {
    download(epci.communes, `Rapports_PCRS_${slugify(epci.label)}`)
  }

  function downloadSelection() {
    const items = []
    if (manifest) for (const e of manifest.epci)
      for (const c of e.communes) if (selected.has(c.file)) items.push(c)
    download(items, 'Rapports_PCRS_selection')
  }

  const canZip = RAPPORTS_BASE_URL && RAPPORTS_ZIP_FILE

  function handleDownloadAll() {
    if (!canZip || busy) return
    // ZIP départemental (~1,3 Go) déjà généré côté serveur → lien direct
    const base = RAPPORTS_BASE_URL.replace(/\/$/, '')
    triggerLink(`${base}/${RAPPORTS_ZIP_FILE}`, RAPPORTS_ZIP_FILE)
  }

  const selCount = selected.size

  const progressLabel = !progress ? ''
    : progress.phase === 'zip'
      ? 'Compression du ZIP…'
      : `Téléchargement… ${progress.done}/${progress.total}`

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
                disabled={busy}
              >
                ⬇ Télécharger tous les rapports (ZIP)
              </button>
              <div className="rapport-all-hint">
                Une seule archive — 283 rapports communaux, ~1,3 Go.
              </div>
            </div>
          )}

          <p className="rapport-hint">
            …ou cochez une ou plusieurs communes (ou un EPCI entier) : les
            rapports sélectionnés sont regroupés dans une seule archive ZIP.
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
                      title={`Télécharger les ${e.communes.length} rapports de ${e.label} (ZIP)`}
                      onClick={() => downloadEpci(e)}
                      disabled={!canDownload || busy}
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
          {error && <div className="rapport-error">⚠ {error}</div>}
          {selCount > 0 && (
            <div className="rapport-sel-bar">
              <span>{selCount} commune{selCount > 1 ? 's' : ''} sélectionnée{selCount > 1 ? 's' : ''}</span>
              <button className="rapport-sel-clear" onClick={clearSelection} disabled={busy}>
                Tout décocher
              </button>
            </div>
          )}
          <button
            className="rapport-dl-btn"
            onClick={downloadSelection}
            disabled={!selCount || !canDownload || busy}
          >
            {busy
              ? progressLabel
              : selCount > 1
                ? `⬇ Télécharger la sélection (${selCount}) — ZIP`
                : `⬇ Télécharger la sélection${selCount ? ` (${selCount})` : ''}`}
          </button>
        </div>
      </div>
    </div>
  )
}
