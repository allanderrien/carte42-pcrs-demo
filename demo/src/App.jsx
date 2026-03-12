import React, { useState, useEffect } from 'react'
import MapView from './components/MapView.jsx'
import Sidebar from './components/Sidebar.jsx'
import Onboarding from './components/Onboarding.jsx'

const LS_KEY = 'carte42_overrides'

function loadOverrides() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') }
  catch { return {} }
}

function saveOverrides(ov) {
  localStorage.setItem(LS_KEY, JSON.stringify(ov))
}

export default function App() {
  const [rawFeatures, setRawFeatures] = useState([])
  const [loading, setLoading]         = useState(true)
  const [minEtoiles, setMinEtoiles]   = useState(2)
  const [selectedId, setSelectedId]   = useState(null)
  const [clickLatlng, setClickLatlng] = useState(null)
  const [basemap, setBasemap]         = useState('osm')
  const [overrides, setOverrides]     = useState(loadOverrides)
  const [editingGeom, setEditingGeom] = useState(null)
  const [geomVersion, setGeomVersion] = useState(0)

  useEffect(() => {
    fetch('./data/detections.geojson')
      .then(r => r.json())
      .then(gj => {
        const feats = (gj.features || []).map((f, i) => ({
          ...f,
          properties: { ...f.properties, _demo_id: String(f.properties?.id || i) },
        }))
        setRawFeatures(feats)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [])

  const features = rawFeatures.map(f => {
    const ov = overrides[f.properties._demo_id]
    if (!ov) return f
    const { _geometry, ...propOv } = ov
    return {
      ...f,
      geometry:   _geometry || f.geometry,
      properties: { ...f.properties, ...propOv },
    }
  })

  const visibleFeatures = features.filter(
    f => (f.properties?.ia_etoiles ?? 0) >= minEtoiles
  )

  const selectedFeature = selectedId != null
    ? features.find(f => f.properties._demo_id === selectedId) ?? null
    : null

  function handleEdit(demoId, patch) {
    const next = { ...overrides, [demoId]: { ...(overrides[demoId] || {}), ...patch } }
    setOverrides(next)
    saveOverrides(next)
  }

  function handleGeomEdited(demoId, newGeometry) {
    handleEdit(demoId, { _geometry: newGeometry })
    setEditingGeom(null)
    setGeomVersion(v => v + 1)
  }

  function handleExport() {
    const exported = {
      type: 'FeatureCollection',
      features: features.map(({ properties: { _demo_id, ...rest }, ...f }) => ({
        ...f, properties: rest,
      })),
    }
    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = Object.assign(document.createElement('a'), {
      href: url, download: 'Changements_PCRS_2020-2025_Demo.geojson',
    })
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleResetOverrides() {
    setOverrides({})
    saveOverrides({})
  }

  function handleClose() {
    setSelectedId(null)
    setEditingGeom(null)
    setClickLatlng(null)
  }

  return (
    <div className="app">
      <Onboarding />
      <Sidebar
        minEtoiles={minEtoiles}
        onMinEtoilesChange={setMinEtoiles}
        totalVisible={visibleFeatures.length}
        totalAll={features.length}
        loading={loading}
        hasOverrides={Object.keys(overrides).length > 0}
        onExport={handleExport}
        onResetOverrides={handleResetOverrides}
      />
      <div className="map-container">
        <MapView
          features={visibleFeatures}
          selectedFeature={selectedFeature}
          clickLatlng={clickLatlng}
          onSelectFeature={(f, latlng) => { setSelectedId(f.properties._demo_id); setClickLatlng(latlng) }}
          basemap={basemap}
          onBasemapChange={setBasemap}
          editingGeom={editingGeom}
          geomVersion={geomVersion}
          onGeomEdited={handleGeomEdited}
          onCancelGeomEdit={() => setEditingGeom(null)}
          onCloseFeature={handleClose}
          onEditFeature={handleEdit}
          onEditGeomFeature={(demoId, mode) => demoId ? setEditingGeom({ id: demoId, mode }) : setEditingGeom(null)}
        />
      </div>
    </div>
  )
}
