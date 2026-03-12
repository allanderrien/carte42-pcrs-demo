import React, { useRef, useEffect, useState, useCallback } from 'react'
import ReactDOM from 'react-dom'
import {
  MapContainer,
  TileLayer,
  WMSTileLayer,
  GeoJSON,
  Circle,
  useMap,
  useMapEvents,
} from 'react-leaflet'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import '@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css'
import '@geoman-io/leaflet-geoman-free'
import buffer from '@turf/buffer'
import { lineString } from '@turf/helpers'
import FeatureDetail from './FeatureDetail.jsx'
import { IGN_WMS_URL, IGN_LAYER_T1, GOOGLE_SAT_URL, MAP_CENTER, MAP_ZOOM } from '../config.js'

// Fix default icon paths broken by Vite bundling
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: new URL('leaflet/dist/images/marker-icon-2x.png', import.meta.url).href,
  iconUrl:       new URL('leaflet/dist/images/marker-icon.png',   import.meta.url).href,
  shadowUrl:     new URL('leaflet/dist/images/marker-shadow.png', import.meta.url).href,
})

const OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'

const STAR_STYLES = {
  5: { fillColor: '#e74c3c', color: '#c0392b', weight: 2, fillOpacity: 0.7 },
  4: { fillColor: '#e67e22', color: '#d35400', weight: 2, fillOpacity: 0.65 },
  3: { fillColor: '#f1c40f', color: '#f39c12', weight: 2, fillOpacity: 0.6 },
  2: { fillColor: '#3498db', color: '#2980b9', weight: 1.5, fillOpacity: 0.5 },
  1: { fillColor: '#9b59b6', color: '#8e44ad', weight: 1,   fillOpacity: 0.4 },
  0: { fillColor: '#95a5a6', color: '#7f8c8d', weight: 1,   fillOpacity: 0.3, dashArray: '4' },
}

function featureStyle(feature) {
  const stars = feature?.properties?.ia_etoiles ?? 0
  return STAR_STYLES[stars] || STAR_STYLES[0]
}

// ── Geoman draw controller ─────────────────────────────────────────────────
function GeomEditorControl({ editingGeom, onGeomEdited, onCancel }) {
  const map = useMap()

  useEffect(() => {
    map.pm.disableDraw()
    map.off('pm:create')

    if (!editingGeom) return

    const { id, mode } = editingGeom

    if (mode === 'polygon') {
      map.pm.enableDraw('Polygon', {
        snappable: true, snapDistance: 15,
        allowSelfIntersection: false, continueDrawing: false,
      })
    } else if (mode === 'line15m') {
      map.pm.enableDraw('Line', {
        snappable: true, snapDistance: 15, continueDrawing: false,
      })
    }

    function handleCreate(e) {
      const layer = e.layer
      let geometry = null
      if (mode === 'line15m') {
        const coords = layer.getLatLngs().map(ll => [ll.lng, ll.lat])
        if (coords.length >= 2) {
          try { geometry = buffer(lineString(coords), 15, { units: 'meters' }).geometry } catch {}
        }
      } else if (mode === 'polygon') {
        try { geometry = buffer(layer.toGeoJSON(), 15, { units: 'meters' }).geometry } catch {}
      }
      if (!geometry) geometry = layer.toGeoJSON().geometry
      map.removeLayer(layer)
      map.pm.disableDraw()
      map.off('pm:create')
      onGeomEdited(id, geometry)
    }

    map.on('pm:create', handleCreate)
    return () => { map.pm.disableDraw(); map.off('pm:create') }
  }, [editingGeom])

  return null
}

// ── Floating panel — anchored to a geographic latlng ──────────────────────
function FloatingPanel({ latlng, wrapperRef, children }) {
  const map = useMap()
  const [pos, setPos] = useState(null)

  const update = useCallback(() => {
    if (!latlng || !wrapperRef.current) return
    const pt = map.latLngToContainerPoint(latlng)
    const W = wrapperRef.current.clientWidth
    const H = wrapperRef.current.clientHeight
    const PANEL_W = 308, PANEL_H = 420
    setPos({
      left: Math.min(pt.x + 16, W - PANEL_W - 8),
      top:  Math.min(Math.max(pt.y - 20, 8), H - PANEL_H - 8),
    })
  }, [map, latlng, wrapperRef])

  useMapEvents({ move: update, zoom: update, moveend: update, zoomend: update })
  useEffect(() => { update() }, [update])

  if (!pos || !latlng || !wrapperRef.current) return null

  return ReactDOM.createPortal(
    <div className="map-feature-panel" style={{ top: pos.top, left: pos.left, right: 'auto' }}>
      {children}
    </div>,
    wrapperRef.current
  )
}

const EMPRISE_STYLE = {
  color: '#7eb3ff', weight: 3, fill: false, dashArray: '8 5', opacity: 0.85,
}

// ── Main component ─────────────────────────────────────────────────────────
export default function MapView({
  features, selectedFeature, clickLatlng, onSelectFeature,
  basemap, onBasemapChange, editingGeom, geomVersion, onGeomEdited, onCancelGeomEdit,
  onCloseFeature, onEditFeature, onEditGeomFeature,
}) {
  const wrapperRef = useRef(null)
  const [emprise, setEmprise] = useState(null)
  useEffect(() => {
    fetch('./data/emprise_zone.geojson').then(r => r.json()).then(setEmprise).catch(() => {})
  }, [])

  const editingGeomId = editingGeom?.id ?? null
  const pointFeatures = features.filter(f => f.geometry?.type === 'Point')
  const polyFeatures  = features.filter(f => f.geometry?.type !== 'Point')
  const polyGeoJSON   = { type: 'FeatureCollection', features: polyFeatures }
  const geoJsonKey    = features.map(f => f.properties?._demo_id || '').join(',') + '-v' + geomVersion

  function featureStyleWithEdit(feature) {
    const base = featureStyle(feature)
    if (feature.properties?._demo_id !== editingGeomId) return base
    return { ...base, dashArray: '6 4', weight: 3, fillOpacity: 0.25, color: '#fff' }
  }

  function handleEachFeature(feature, layer) {
    layer.on('click', e => onSelectFeature(feature, e.latlng))
  }

  const BASEMAPS = [
    { id: 'osm',        label: 'Plan OSM',   icon: '🗺' },
    { id: 'ortho2020',  label: 'Image 2020', icon: '📷' },
    { id: 'google2025', label: 'Image 2025', icon: '🛰' },
  ]

  return (
    <div ref={wrapperRef} style={{ position: 'relative', width: '100%', height: '100%' }}>

      <div className="basemap-switcher">
        {BASEMAPS.map(bm => (
          <button
            key={bm.id}
            className={`basemap-switch-btn${basemap === bm.id ? ' active' : ''}`}
            onClick={() => onBasemapChange(bm.id)}
          >
            <span className="basemap-switch-icon">{bm.icon}</span>
            <span>{bm.label}</span>
          </button>
        ))}
      </div>

      {editingGeomId && (
        <div className="geom-edit-banner">
          ✏ Mode dessin actif — utilisez les boutons dans le panneau latéral
          <button onClick={onCancelGeomEdit}>Annuler</button>
        </div>
      )}

      <MapContainer
        center={MAP_CENTER}
        zoom={MAP_ZOOM}
        style={{ width: '100%', height: '100%' }}
        preferCanvas={false}
      >
        {basemap === 'osm' && (
          <TileLayer key="osm" url={OSM_URL} maxZoom={19}
            attribution="© OpenStreetMap contributors" className="osm-faded" />
        )}
        {basemap === 'ortho2020' && (
          <WMSTileLayer key="wms2020" url={IGN_WMS_URL} layers={IGN_LAYER_T1}
            version="1.3.0" crs={L.CRS.EPSG4326} format="image/png"
            transparent={false} maxZoom={20} attribution="IGN BD ORTHO 2020" />
        )}
        {basemap === 'google2025' && (
          <TileLayer key="google" url={GOOGLE_SAT_URL} maxZoom={20}
            attribution="Google Satellite" />
        )}

        {emprise && (
          <GeoJSON key="emprise" data={emprise} style={EMPRISE_STYLE} interactive={false} />
        )}

        {polyFeatures.length > 0 && (
          <GeoJSON
            key={geoJsonKey + '-poly'}
            data={polyGeoJSON}
            style={featureStyleWithEdit}
            onEachFeature={handleEachFeature}
          />
        )}

        {pointFeatures.map((feat, i) => {
          const stars = feat.properties?.ia_etoiles ?? 0
          const style = STAR_STYLES[stars] || STAR_STYLES[0]
          const [lng, lat] = feat.geometry.coordinates
          const radiusM = feat.properties?.r_road_m || 40
          return (
            <Circle key={`pt-${i}`} center={[lat, lng]} radius={radiusM}
              pathOptions={style}
              eventHandlers={{ click: e => onSelectFeature(feat, e.latlng) }} />
          )
        })}

        <GeomEditorControl
          editingGeom={editingGeom}
          onGeomEdited={onGeomEdited}
          onCancel={onCancelGeomEdit}
        />

        {selectedFeature && clickLatlng && (
          <FloatingPanel latlng={clickLatlng} wrapperRef={wrapperRef}>
            <FeatureDetail
              feature={selectedFeature}
              onClose={onCloseFeature}
              onEdit={patch => onEditFeature(selectedFeature.properties._demo_id, patch)}
              onEditGeom={onEditGeomFeature}
              editingGeomId={editingGeomId}
            />
          </FloatingPanel>
        )}
      </MapContainer>
    </div>
  )
}
