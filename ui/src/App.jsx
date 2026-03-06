import React, { useState, useEffect, useCallback, useRef } from 'react'
import { MILLESIME_ANCIEN, MILLESIME_RECENT } from './config.js'
import MapView from './components/MapView.jsx'
import StepList from './components/StepList.jsx'
import LayerControls from './components/LayerControls.jsx'
import LogPanel from './components/LogPanel.jsx'

const INITIAL_LAYERS = {
  wms_t1:        { visible: false, opacity: 0.85 },
  wms_t2:        { visible: true,  opacity: 0.85 },
  wms_t2_2024:   { visible: false, opacity: 0.85 },
  wms_t2_2023:   { visible: false, opacity: 0.85 },
  pcrs_sde35:    { visible: false, opacity: 0.90 },
  geojson:       { visible: true },
  emprise_zone:  { visible: true },
  emprise_voies: { visible: true },
}

function computeStats(geojson) {
  if (!geojson?.features?.length) return null
  const features   = geojson.features
  const total      = features.length
  const n_fort     = features.filter(f => f.properties?.classe === 'fort').length
  const n_modere   = features.filter(f => f.properties?.classe === 'modere').length
  const surface_m2 = features.reduce((s, f) => s + (f.properties?.surface_m2 ?? 0), 0)
  const ampl_vals  = features.map(f => f.properties?.ampl_moy ?? 0).filter(Boolean)
  const ampl_moy   = ampl_vals.length
    ? (ampl_vals.reduce((a, b) => a + b, 0) / ampl_vals.length).toFixed(1) : '—'
  return { total, n_fort, n_modere, surface_ha: (surface_m2 / 1e4).toFixed(2), ampl_moy }
}

async function fetchJson(url, opts) {
  const r = await fetch(url, opts)
  const data = await r.json()
  if (!r.ok || data.error) throw new Error(data.error ?? `HTTP ${r.status}`)
  return data
}

export default function App() {
  const [layers,          setLayers]          = useState(INITIAL_LAYERS)
  const [geojson,         setGeojson]         = useState(null)
  const [geojsonError,    setGeojsonError]    = useState(null)
  const [empriseZone,     setEmpriseZone]     = useState(null)
  const [empriseZoneErr,  setEmpriseZoneErr]  = useState(null)
  const [empriseVoies,    setEmpriseVoies]    = useState(null)
  const [empriseVoiesErr, setEmpriseVoiesErr] = useState(null)
  const [pipelineStatus,  setPipelineStatus]  = useState(null)
  const [loading,         setLoading]         = useState(false)
  const [testZone, setTestZone] = useState({ enabled: false, bbox: null, drawing: false })

  // ── Pipeline runner state ────────────────────────────────────────────────
  const [runningSteps, setRunningSteps] = useState([])   // ['1', '3', ...]
  const [activeLogStep, setActiveLogStep] = useState(null)
  const [logsByStep,    setLogsByStep]    = useState({})  // { '1': string[] }
  const sseRefs = useRef({})  // step → EventSource

  // ── Chargement données ───────────────────────────────────────────────────
  const loadEmprises = useCallback(() => {
    fetchJson('/api/emprise/zone')
      .then(d => { setEmpriseZone(d); setEmpriseZoneErr(null) })
      .catch(e => setEmpriseZoneErr(e.message))
    fetchJson('/api/emprise/voies')
      .then(d => { setEmpriseVoies(d); setEmpriseVoiesErr(null) })
      .catch(e => setEmpriseVoiesErr(e.message))
  }, [])

  const refreshAll = useCallback(() => {
    setLoading(true)
    setGeojsonError(null)
    fetchJson('/api/status').then(setPipelineStatus).catch(() => {})
    loadEmprises()
    fetchJson('/api/geojson')
      .then(d => setGeojson(d))
      .catch(e => { setGeojson(null); setGeojsonError(e.message) })
      .finally(() => setLoading(false))
  }, [loadEmprises])

  useEffect(() => { refreshAll() }, [])

  // ── Connexion SSE pour une étape ─────────────────────────────────────────
  const connectSSE = useCallback((step) => {
    // Ferme si déjà connecté
    if (sseRefs.current[step]) {
      sseRefs.current[step].close()
    }

    // Réinitialise les logs de cette étape
    setLogsByStep(prev => ({ ...prev, [step]: [] }))

    const es = new EventSource(`/api/logs/${step}`)
    sseRefs.current[step] = es

    es.onmessage = (e) => {
      const line = JSON.parse(e.data)
      setLogsByStep(prev => ({
        ...prev,
        [step]: [...(prev[step] ?? []), line],
      }))
    }

    es.addEventListener('start', () => {
      setRunningSteps(prev => [...new Set([...prev, step])])
    })

    es.addEventListener('done', (e) => {
      const { code } = JSON.parse(e.data)
      setRunningSteps(prev => prev.filter(s => s !== step))
      es.close()
      delete sseRefs.current[step]
      // Rafraîchit le statut et les données après chaque étape terminée
      setTimeout(() => refreshAll(), 500)
    })

    es.onerror = () => {
      setRunningSteps(prev => prev.filter(s => s !== step))
    }
  }, [refreshAll])

  // ── Arrêt d'une étape ───────────────────────────────────────────────────
  const handleStop = useCallback((step) => {
    fetch(`/api/stop/${step}`, { method: 'POST' })
      .then(() => {
        setRunningSteps(prev => prev.filter(s => s !== step))
        setLogsByStep(prev => ({
          ...prev,
          [step]: [...(prev[step] ?? []), '■ Arrêté par l\'utilisateur'],
        }))
      })
      .catch(() => {})
  }, [])

  // ── Lancement d'une étape ────────────────────────────────────────────────
  const handleRun = useCallback((step, label) => {
    // Ouvre le panel de logs avant même de lancer
    setActiveLogStep(step)
    setLogsByStep(prev => ({ ...prev, [step]: [] }))

    // Connecte le SSE d'abord (pour ne pas rater les premiers logs)
    connectSSE(step)

    // Puis lance le script (avec bbox de test si activée)
    const bbox = testZone.enabled && testZone.bbox ? testZone.bbox : null
    fetchJson(`/api/run/${step}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(bbox ? { bbox } : {}),
    })
      .then(() => {
        setRunningSteps(prev => [...new Set([...prev, step])])
      })
      .catch(e => {
        setLogsByStep(prev => ({
          ...prev,
          [step]: [...(prev[step] ?? []), `✗ Erreur : ${e.message}`],
        }))
      })
  }, [connectSSE, testZone])

  // Nettoyage SSE au démontage
  useEffect(() => {
    return () => Object.values(sseRefs.current).forEach(es => es.close())
  }, [])

  const toggleLayer = (id) =>
    setLayers(prev => ({ ...prev, [id]: { ...prev[id], visible: !prev[id].visible } }))
  const setOpacity = (id, val) =>
    setLayers(prev => ({ ...prev, [id]: { ...prev[id], opacity: val } }))

  const geojsonStats  = computeStats(geojson)
  const activeLogs    = logsByStep[activeLogStep] ?? []
  const isActiveRunning = runningSteps.includes(activeLogStep)

  const activeStepLabel = activeLogStep
    ? `Étape ${activeLogStep} — ${['', 'Téléchargement', 'Prétraitement', 'Détection', 'Export'][+activeLogStep]}`
    : ''

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <span className="logo-badge">C42</span>
          <div>
            <div className="logo-title">Carte42</div>
            <div className="logo-sub">PCRS · SDE35 · Vitré (35)</div>
          </div>
        </div>

        <StepList
          pipelineStatus={pipelineStatus}
          onRefresh={refreshAll}
          onRun={handleRun}
          onStop={handleStop}
          runningSteps={runningSteps}
          activeLogStep={activeLogStep}
        />

        <section className="sidebar-section">
          <div className="section-header">Zone de calcul</div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 0', cursor: 'pointer' }}>
            <input
              type="checkbox"
              checked={testZone.enabled}
              onChange={e => setTestZone(z => ({ ...z, enabled: e.target.checked, drawing: false }))}
            />
            <span style={{ fontSize: 13 }}>Limiter à une zone de test</span>
          </label>
          {testZone.enabled && (
            <div style={{ paddingTop: 4 }}>
              <button
                className={`btn-draw${testZone.drawing ? ' active' : ''}`}
                onClick={() => setTestZone(z => ({ ...z, drawing: !z.drawing, bbox: z.drawing ? z.bbox : null }))}
                style={{ width: '100%', marginBottom: 4 }}
              >
                {testZone.drawing ? '✕ Annuler le dessin' : '⬚ Dessiner la zone'}
              </button>
              {testZone.bbox && !testZone.drawing && (
                <div style={{ fontSize: 11, color: '#aaa', lineHeight: 1.5 }}>
                  Zone définie ✓<br/>
                  {testZone.bbox.latMin.toFixed(4)}°N {testZone.bbox.lonMin.toFixed(4)}°E<br/>
                  → {testZone.bbox.latMax.toFixed(4)}°N {testZone.bbox.lonMax.toFixed(4)}°E
                </div>
              )}
              {testZone.drawing && (
                <div style={{ fontSize: 11, color: '#f39c12' }}>
                  Cliquez deux coins sur la carte…
                </div>
              )}
            </div>
          )}
        </section>

        <LayerControls
          layers={layers}
          onToggle={toggleLayer}
          onOpacity={setOpacity}
          geojsonStats={geojsonStats}
          empriseZoneState={empriseZone ? 'ok' : empriseZoneErr ? 'error' : 'loading'}
          empriseVoiesState={empriseVoies ? 'ok' : empriseVoiesErr ? 'error' : 'loading'}
          empriseZoneErr={empriseZoneErr}
          empriseVoiesErr={empriseVoiesErr}
        />

        {geojsonError && (
          <div className="geo-error"><strong>GeoJSON :</strong> {geojsonError}</div>
        )}
        {loading && <div className="geo-loading">Chargement…</div>}
      </aside>

      <main className="map-area">
        <MapView
          layers={layers}
          geojson={geojson}
          empriseZone={empriseZone}
          empriseVoies={empriseVoies}
          testZone={testZone}
          onTestZoneBbox={useCallback(bbox => setTestZone(z => ({ ...z, bbox, drawing: false })), [])}
        />

        {/* Panel de logs — flottant sur la carte */}
        {activeLogStep && (
          <LogPanel
            step={activeLogStep}
            stepLabel={activeStepLabel}
            logs={activeLogs}
            running={isActiveRunning}
            onClose={() => setActiveLogStep(null)}
            onStop={handleStop}
          />
        )}

        <div className="map-badge">
          <span className={`badge-pill ${layers.wms_t1?.visible ? 'active' : ''}`} style={{ '--c': '#3498db' }}>
            T1 · {MILLESIME_ANCIEN}
          </span>
          <span className="badge-sep">→</span>
          <span className={`badge-pill ${layers.wms_t2?.visible ? 'active' : ''}`} style={{ '--c': '#9b59b6' }}>
            T2 · {MILLESIME_RECENT}
          </span>
          {geojson && (
            <span className="badge-pill active" style={{ '--c': '#e74c3c' }}>
              {geojsonStats?.total ?? 0} zones détectées
            </span>
          )}
        </div>
      </main>
    </div>
  )
}
