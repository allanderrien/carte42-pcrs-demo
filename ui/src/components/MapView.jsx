import React, { useEffect, useRef } from 'react'
import {
  MapContainer, TileLayer, WMSTileLayer, GeoJSON, useMap, Rectangle,
} from 'react-leaflet'
import L from 'leaflet'
import { CENTER_WGS84, IGN_WMS_URL,
         IGN_LAYER_T1, IGN_LAYER_T2, IGN_LAYER_T2_2024, IGN_LAYER_T2_2023, IGN_LAYER_PCRS_SDE35, COULEURS } from '../config.js'

// ── WMS avec contrôle d'opacité sans re-montage ──────────────────────────────

function WMSLayer({ visible, opacity, ...props }) {
  const layerRef = useRef(null)
  useEffect(() => {
    if (layerRef.current) layerRef.current.setOpacity(visible ? opacity : 0)
  }, [visible, opacity])
  return (
    <WMSTileLayer ref={layerRef} opacity={visible ? opacity : 0} {...props} />
  )
}

// ── Centrage sur l'emprise réelle au premier chargement ───────────────────────
// Source de vérité : empriseZone (shapefile réel, pas les coordonnées hardcodées).
// padding généreux → zoom légèrement plus large pour voir le contexte.
// fitted.current évite de recadrer à chaque re-render.

function FitToEmprise({ empriseZone }) {
  const map    = useMap()
  const fitted = useRef(false)

  useEffect(() => {
    if (fitted.current || !empriseZone?.features?.length) return
    try {
      const bounds = L.geoJSON(empriseZone).getBounds()
      if (bounds.isValid()) {
        map.fitBounds(bounds, { padding: [80, 80] })
        fitted.current = true
      }
    } catch (_) {}
  }, [empriseZone, map])

  return null
}

// ── Styles des couches ────────────────────────────────────────────────────────

function styleChangement(feature) {
  const color = feature.properties?.classe === 'fort' ? COULEURS.fort : COULEURS.modere
  return { fillColor: color, color, weight: 1.5, fillOpacity: 0.55, opacity: 0.9 }
}

const STYLE_EMPRISE_ZONE = {
  color: '#2c3e50', weight: 2.5, fillOpacity: 0, dashArray: '10 5',
}

const STYLE_EMPRISE_VOIES = {
  color: '#1abc9c', weight: 1.8, fillOpacity: 0.12, fillColor: '#1abc9c',
}

const STYLE_EMPRISE_VOIES_HOVER = {
  color: '#16a085', weight: 2.5, fillOpacity: 0.25,
}

// ── Interactions ──────────────────────────────────────────────────────────────

function onEachChangement(feature, layer) {
  const p = feature.properties ?? {}
  const color = COULEURS[p.classe] ?? '#888'
  layer.bindPopup(`
    <div style="font-family:sans-serif;font-size:13px;min-width:180px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid ${color};padding-bottom:4px">
        Changement ${p.classe ?? '—'}
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555">Surface</td>
            <td style="text-align:right;font-weight:600">${p.surface_m2 != null ? p.surface_m2.toFixed(0) + ' m²' : '—'}</td></tr>
        <tr><td style="color:#555">Amplitude moy.</td>
            <td style="text-align:right;font-weight:600">${p.ampl_moy?.toFixed(1) ?? '—'}</td></tr>
        <tr><td style="color:#555">Amplitude max</td>
            <td style="text-align:right;font-weight:600">${p.ampl_max?.toFixed(1) ?? '—'}</td></tr>
      </table>
    </div>
  `)
  layer.on('mouseover', () => layer.setStyle({ fillOpacity: 0.85, weight: 2.5 }))
  layer.on('mouseout',  () => layer.setStyle(styleChangement(feature)))
}

function onEachVoie(feature, layer) {
  const p = feature.properties ?? {}
  const lines = Object.entries(p)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `<tr><td style="color:#555;padding-right:8px">${k}</td><td><b>${v}</b></td></tr>`)
    .join('')
  if (lines) {
    layer.bindPopup(`
      <div style="font-family:sans-serif;font-size:12px">
        <div style="font-weight:700;margin-bottom:5px;color:#1abc9c">Emprise voie</div>
        <table style="border-collapse:collapse">${lines}</table>
      </div>
    `)
  }
  layer.on('mouseover', () => layer.setStyle(STYLE_EMPRISE_VOIES_HOVER))
  layer.on('mouseout',  () => layer.setStyle(STYLE_EMPRISE_VOIES))
}

function onEachZone(feature, layer) {
  const p = feature.properties ?? {}
  const lines = Object.entries(p)
    .filter(([, v]) => v != null && v !== '')
    .map(([k, v]) => `<tr><td style="color:#555;padding-right:8px">${k}</td><td><b>${v}</b></td></tr>`)
    .join('')
  if (lines) {
    layer.bindPopup(`
      <div style="font-family:sans-serif;font-size:12px">
        <div style="font-weight:700;margin-bottom:5px;color:#2c3e50">Emprise zone</div>
        <table style="border-collapse:collapse">${lines}</table>
      </div>
    `)
  }
}

// ── Dessin de la zone de test ─────────────────────────────────────────────────

function DrawTestZone({ drawing, onBboxDefined }) {
  const map        = useMap()
  const corner1Ref = useRef(null)

  useEffect(() => {
    const container = map.getContainer()

    if (!drawing) {
      corner1Ref.current = null
      container.style.cursor = ''
      return
    }

    container.style.cursor = 'crosshair'

    const onClick = (e) => {
      // Conversion coords DOM → LatLng Leaflet
      const rect   = container.getBoundingClientRect()
      const point  = L.point(e.clientX - rect.left, e.clientY - rect.top)
      const latlng = map.containerPointToLatLng(point)

      if (!corner1Ref.current) {
        corner1Ref.current = latlng
      } else {
        const c1 = corner1Ref.current
        corner1Ref.current = null
        onBboxDefined({
          latMin: Math.min(c1.lat, latlng.lat),
          lonMin: Math.min(c1.lng, latlng.lng),
          latMax: Math.max(c1.lat, latlng.lat),
          lonMax: Math.max(c1.lng, latlng.lng),
        })
      }
    }

    container.addEventListener('click', onClick)
    return () => {
      container.removeEventListener('click', onClick)
      container.style.cursor = ''
    }
  }, [drawing, map, onBboxDefined])

  return null
}

// ── Composant principal ───────────────────────────────────────────────────────

export default function MapView({ layers, geojson, empriseZone, empriseVoies, testZone, onTestZoneBbox }) {
  return (
    <MapContainer
      center={CENTER_WGS84}
      zoom={11}
      style={{ width: '100%', height: '100%' }}
    >
      {/* Fond OSM */}
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='© <a href="https://openstreetmap.org">OpenStreetMap</a>'
        maxZoom={20}
      />

      {/* WMS T1 — BD ORTHO IGN 2020 */}
      <WMSLayer
        url={IGN_WMS_URL} layers={IGN_LAYER_T1}
        format="image/png" transparent version="1.3.0"
        attribution="© IGN — BD ORTHO 2020"
        visible={layers.wms_t1?.visible ?? false}
        opacity={layers.wms_t1?.opacity ?? 0.85}
      />

      {/* WMS T2 — Ortho-express IGN 2025 */}
      <WMSLayer
        url={IGN_WMS_URL} layers={IGN_LAYER_T2}
        format="image/png" transparent version="1.3.0"
        attribution="© IGN — Ortho-express 2025"
        visible={layers.wms_t2?.visible ?? true}
        opacity={layers.wms_t2?.opacity ?? 0.85}
      />

      {/* WMS T2 2024 — Ortho-express IGN 2024 */}
      <WMSLayer
        url={IGN_WMS_URL} layers={IGN_LAYER_T2_2024}
        format="image/png" transparent version="1.3.0"
        attribution="© IGN — Ortho-express 2024"
        visible={layers.wms_t2_2024?.visible ?? false}
        opacity={layers.wms_t2_2024?.opacity ?? 0.85}
      />

      {/* WMS T2 2023 — Ortho-express IGN 2023 */}
      <WMSLayer
        url={IGN_WMS_URL} layers={IGN_LAYER_T2_2023}
        format="image/png" transparent version="1.3.0"
        attribution="© IGN — Ortho-express 2023"
        visible={layers.wms_t2_2023?.visible ?? false}
        opacity={layers.wms_t2_2023?.opacity ?? 0.85}
      />

      {/* WMS PCRS SDE35 */}
      {layers.pcrs_sde35?.visible && (
        <WMSLayer
          url={IGN_WMS_URL} layers={IGN_LAYER_PCRS_SDE35}
          format="image/png" transparent version="1.3.0"
          attribution="© SDE35 / IGN — PCRS"
          visible={true}
          opacity={layers.pcrs_sde35?.opacity ?? 0.9}
        />
      )}

      {/* Emprise voies — affiché en dessous de la zone pour ne pas masquer */}
      {layers.emprise_voies?.visible !== false && empriseVoies && (
        <GeoJSON
          key="emprise_voies"
          data={empriseVoies}
          style={STYLE_EMPRISE_VOIES}
          onEachFeature={onEachVoie}
        />
      )}

      {/* Emprise zone */}
      {layers.emprise_zone?.visible !== false && empriseZone && (
        <GeoJSON
          key="emprise_zone"
          data={empriseZone}
          style={STYLE_EMPRISE_ZONE}
          onEachFeature={onEachZone}
        />
      )}

      {/* Changements détectés */}
      {layers.geojson?.visible !== false && geojson && (
        <GeoJSON
          key={geojson.features?.length}
          data={geojson}
          style={styleChangement}
          onEachFeature={onEachChangement}
        />
      )}

      {/* Fit centré sur l'emprise réelle dès qu'elle est disponible */}
      <FitToEmprise empriseZone={empriseZone} />

      {/* Zone de test */}
      <DrawTestZone drawing={testZone?.drawing} onBboxDefined={onTestZoneBbox} />
      {testZone?.enabled && testZone?.bbox && (
        <Rectangle
          bounds={[
            [testZone.bbox.latMin, testZone.bbox.lonMin],
            [testZone.bbox.latMax, testZone.bbox.lonMax],
          ]}
          pathOptions={{ color: '#f39c12', weight: 2, dashArray: '6 4', fillOpacity: 0.08 }}
        />
      )}
    </MapContainer>
  )
}
