import React, { useEffect, useRef } from 'react'
import {
  MapContainer, TileLayer, WMSTileLayer, GeoJSON, ImageOverlay, useMap, Rectangle,
} from 'react-leaflet'
import L from 'leaflet'
import { CENTER_WGS84, BBOX_WGS84, IGN_WMS_URL,
         IGN_LAYER_T1, IGN_LAYER_T2, COULEURS } from '../config.js'

const S2_BOUNDS = [
  [BBOX_WGS84.latMin, BBOX_WGS84.lonMin],
  [BBOX_WGS84.latMax, BBOX_WGS84.lonMax],
]

// ── TileLayer / WMS avec contrôle d'opacité sans re-montage ─────────────────

function TileLayerControlled({ visible, opacity, ...props }) {
  const layerRef = useRef(null)
  useEffect(() => {
    if (layerRef.current) layerRef.current.setOpacity(visible ? opacity : 0)
  }, [visible, opacity])
  return (
    <TileLayer ref={layerRef} opacity={visible ? opacity : 0} {...props} />
  )
}

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
  const color = COULEURS[feature.properties?.classe] ?? '#888'
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
        ${p.classe ?? 'changement'}
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555">Transition</td>
            <td style="text-align:right;font-weight:600">${p.transition ?? '—'}</td></tr>
        <tr><td style="color:#555">Surface</td>
            <td style="text-align:right;font-weight:600">${p.surface_m2 != null ? p.surface_m2.toFixed(0) + ' m²' : '—'}</td></tr>
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

const ETAT_PA_LABEL = { 2: 'Autorisé', 3: 'Chantier ouvert', 4: 'Achèvement déclaré', 5: 'Périmé', 6: 'Retiré' }
const ETAT_PA_COLOR = { 2: '#8e44ad', 3: '#e67e22', 4: '#27ae60', 5: '#95a5a6', 6: '#bdc3c7' }

function demolirPopupHtml(p) {
  return `
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #c0392b;padding-bottom:4px;color:#c0392b">
        Permis de démolir
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555;padding:2px 6px 2px 0">Numéro</td>
            <td style="font-weight:600">${p.num ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Commune</td>
            <td style="font-weight:600">${p.commune ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">État</td>
            <td style="font-weight:600;color:#c0392b">${p.etat_label ?? '—'}</td></tr>
        ${p.adresse ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Adresse</td>
            <td>${p.adresse}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Autorisation</td>
            <td>${p.date_aut ?? '—'}</td></tr>
      </table>
    </div>`
}

function demolirPointToLayer(feature, latlng) {
  const marker = L.circleMarker(latlng, {
    radius: 7, color: '#c0392b', fillColor: '#c0392b',
    weight: 1.5, fillOpacity: 0.75, opacity: 1,
  })
  marker.bindPopup(demolirPopupHtml(feature.properties ?? {}))
  marker.on('mouseover', () => marker.setStyle({ radius: 10, fillOpacity: 1 }))
  marker.on('mouseout',  () => marker.setStyle({ radius: 7,  fillOpacity: 0.75 }))
  return marker
}

function locauxPopupHtml(p) {
  return `
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #2980b9;padding-bottom:4px;color:#2980b9">
        Local non résidentiel
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555;padding:2px 6px 2px 0">Numéro</td>
            <td style="font-weight:600">${p.num ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Commune</td>
            <td style="font-weight:600">${p.commune ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Destination</td>
            <td style="font-weight:600">${p.destination ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">État</td>
            <td style="font-weight:600;color:#2980b9">${p.etat_label ?? '—'}</td></tr>
        ${p.adresse ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Adresse</td>
            <td>${p.adresse}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Autorisation</td>
            <td>${p.date_aut ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Surface créée</td>
            <td style="font-weight:700">${p.surf_creee != null ? p.surf_creee.toLocaleString('fr') + ' m²' : '—'}</td></tr>
      </table>
    </div>`
}

function locauxPointToLayer(feature, latlng) {
  const marker = L.circleMarker(latlng, {
    radius: 7, color: '#2980b9', fillColor: '#2980b9',
    weight: 1.5, fillOpacity: 0.75, opacity: 1,
  })
  marker.bindPopup(locauxPopupHtml(feature.properties ?? {}))
  marker.on('mouseover', () => marker.setStyle({ radius: 10, fillOpacity: 1 }))
  marker.on('mouseout',  () => marker.setStyle({ radius: 7,  fillOpacity: 0.75 }))
  return marker
}

function permisPopupHtml(p) {
  const color = ETAT_PA_COLOR[p.etat] ?? '#8e44ad'
  return `
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid ${color};padding-bottom:4px;color:${color}">
        Permis d'aménager
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555;padding:2px 6px 2px 0">Numéro</td>
            <td style="font-weight:600">${p.num_pa ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Commune</td>
            <td style="font-weight:600">${p.commune ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">État</td>
            <td style="font-weight:600;color:${color}">${p.etat_label ?? '—'}</td></tr>
        ${p.adresse ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Adresse</td>
            <td>${p.adresse}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Autorisation</td>
            <td>${p.date_aut ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Surface</td>
            <td>${p.surface_m2 != null ? p.surface_m2.toLocaleString('fr') + ' m²' : '—'}</td></tr>
      </table>
    </div>`
}

function pcLogPopupHtml(p) {
  return `
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #e67e22;padding-bottom:4px;color:#e67e22">
        Permis de construire · logements
      </div>
      <table style="width:100%;border-collapse:collapse">
        <tr><td style="color:#555;padding:2px 6px 2px 0">Numéro</td>
            <td style="font-weight:600">${p.num_dau ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Commune</td>
            <td style="font-weight:600">${p.commune ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">État</td>
            <td style="font-weight:600;color:#e67e22">${p.etat_label ?? '—'}</td></tr>
        ${p.adresse ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Adresse</td>
            <td>${p.adresse}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Autorisation</td>
            <td>${p.date_aut ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Logements</td>
            <td style="font-weight:700;font-size:14px">${p.nb_logements ?? '—'}</td></tr>
        ${p.nb_indiv ? `<tr><td style="color:#555;padding:2px 6px 2px 0">dont individuels</td>
            <td>${p.nb_indiv}</td></tr>` : ''}
        ${p.nb_collec ? `<tr><td style="color:#555;padding:2px 6px 2px 0">dont collectifs</td>
            <td>${p.nb_collec}</td></tr>` : ''}
      </table>
    </div>`
}

function pcLogPointToLayer(feature, latlng) {
  const nb = feature.properties?.nb_logements ?? 1
  const r  = Math.min(4 + nb * 0.8, 18)
  const marker = L.circleMarker(latlng, {
    radius: r, color: '#e67e22', fillColor: '#e67e22',
    weight: 1.5, fillOpacity: 0.65, opacity: 1,
  })
  marker.bindPopup(pcLogPopupHtml(feature.properties ?? {}))
  marker.on('mouseover', () => marker.setStyle({ fillOpacity: 1 }))
  marker.on('mouseout',  () => marker.setStyle({ fillOpacity: 0.65 }))
  return marker
}

function permisPointToLayer(feature, latlng) {
  const color  = ETAT_PA_COLOR[feature.properties?.etat] ?? '#8e44ad'
  const marker = L.circleMarker(latlng, {
    radius: 7, color, fillColor: color,
    weight: 1.5, fillOpacity: 0.75, opacity: 1,
  })
  marker.bindPopup(permisPopupHtml(feature.properties ?? {}))
  marker.on('mouseover', () => marker.setStyle({ radius: 10, fillOpacity: 1 }))
  marker.on('mouseout',  () => marker.setStyle({ radius: 7,  fillOpacity: 0.75 }))
  return marker
}

function osmVoieStyle(feature) {
  return { color: '#f9ca24', weight: 3, opacity: 0.85, fillOpacity: 0 }
}

function onEachOsmVoie(feature, layer) {
  const p = feature.properties ?? {}
  layer.bindPopup(`
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #f9ca24;padding-bottom:4px;color:#d4a017">
        Voie OSM
      </div>
      <table style="width:100%;border-collapse:collapse">
        ${p.name ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Nom</td>
            <td style="font-weight:600">${p.name}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Type</td>
            <td>${p.highway_label ?? p.highway ?? '—'}</td></tr>
        ${p.surface ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Revêtement</td>
            <td>${p.surface}</td></tr>` : ''}
        ${p.maxspeed ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Vitesse max</td>
            <td>${p.maxspeed} km/h</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Dernière modif. OSM</td>
            <td style="font-weight:600">${p.timestamp ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">OSM ID</td>
            <td style="font-size:11px;color:#888">${p.osm_id ?? '—'}</td></tr>
      </table>
    </div>
  `)
  layer.on('mouseover', () => layer.setStyle({ weight: 5, opacity: 1 }))
  layer.on('mouseout',  () => layer.setStyle(osmVoieStyle(feature)))
}

const STYLE_LOTISSEMENT = {
  color: '#e17055', weight: 2, opacity: 0.9,
  fillColor: '#e17055', fillOpacity: 0.2,
}
const STYLE_LOTISSEMENT_HOVER = {
  color: '#c0392b', weight: 3, fillOpacity: 0.4,
}

function onEachLotissement(feature, layer) {
  const p = feature.properties ?? {}
  layer.bindPopup(`
    <div style="font-family:sans-serif;font-size:13px;min-width:200px">
      <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #e17055;padding-bottom:4px;color:#e17055">
        Lotissement détecté
      </div>
      <table style="width:100%;border-collapse:collapse">
        ${p.noms_voies ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Voies</td>
            <td style="font-weight:600">${p.noms_voies}</td></tr>` : ''}
        <tr><td style="color:#555;padding:2px 6px 2px 0">Voies OSM nouvelles</td>
            <td style="font-weight:600">${p.nb_voies ?? '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Surface estimée</td>
            <td style="font-weight:700">${p.surface_m2 != null ? p.surface_m2.toLocaleString('fr') + ' m²' : '—'}</td></tr>
        <tr><td style="color:#555;padding:2px 6px 2px 0">Soit</td>
            <td>${p.surface_ha ?? '—'} ha</td></tr>
      </table>
    </div>
  `)
  layer.on('mouseover', () => layer.setStyle(STYLE_LOTISSEMENT_HOVER))
  layer.on('mouseout',  () => layer.setStyle(STYLE_LOTISSEMENT))
}

export default function MapView({ layers, permisPA, pcLogements, permisDemloir, locauxNonResid, osmVoies, osmPieton, osmExistantes, osmConstruction, osmChantiersTermines, lotissements, empriseZone, empriseVoies, testZone, onTestZoneBbox, s2Years }) {
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

      {/* Google Satellite */}
      <TileLayerControlled
        url="https://mt{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
        subdomains={['0','1','2','3']}
        attribution="© Google"
        maxZoom={21}
        visible={layers.google_sat?.visible ?? false}
        opacity={layers.google_sat?.opacity ?? 1}
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


      {/* Composites NDVI Sentinel-2 annuels */}
      {(s2Years ?? []).map(year =>
        layers[`s2_${year}`]?.visible && (
          <ImageOverlay
            key={year}
            url={`/api/s2/composite/${year}`}
            bounds={S2_BOUNDS}
            opacity={layers[`s2_${year}`]?.opacity ?? 0.75}
            zIndex={10}
          />
        )
      )}

      {/* Réseau viaire existant OSM (avant 2020) — référence détection */}
      {layers.voies_existantes?.visible && osmExistantes && (
        <GeoJSON
          key="voies_existantes"
          data={osmExistantes}
          style={() => ({ color: '#e74c3c', weight: 1.5, opacity: 0.7 })}
        />
      )}

      {/* Lotissements détectés — polygones buffer 20 m */}
      {layers.lotissements?.visible !== false && lotissements && (
        <GeoJSON
          key="lotissements"
          data={lotissements}
          style={() => STYLE_LOTISSEMENT}
          onEachFeature={onEachLotissement}
        />
      )}

      {/* Chantiers OSM terminés depuis 2021 */}
      {layers.osm_chantiers_termines?.visible !== false && osmChantiersTermines && (
        <GeoJSON
          key="osm_chantiers_termines"
          data={osmChantiersTermines}
          style={() => ({ color: '#00b894', weight: 4, opacity: 0.9 })}
          onEachFeature={(feature, layer) => {
            const p = feature.properties ?? {}
            layer.bindPopup(`
              <div style="font-family:sans-serif;font-size:13px;min-width:200px">
                <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #00b894;padding-bottom:4px;color:#00b894">
                  Chantier terminé ✓
                </div>
                <table style="width:100%;border-collapse:collapse">
                  ${p.name ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Nom</td><td style="font-weight:600">${p.name}</td></tr>` : ''}
                  <tr><td style="color:#555;padding:2px 6px 2px 0">Type</td>
                      <td>${p.type_label ?? '—'}</td></tr>
                  <tr><td style="color:#555;padding:2px 6px 2px 0">Début chantier</td>
                      <td>${p.date_chantier ?? '—'}</td></tr>
                  <tr><td style="color:#555;padding:2px 6px 2px 0">Complétion OSM</td>
                      <td style="font-weight:700;color:#00b894">${p.date_completion ?? '—'}</td></tr>
                  <tr><td style="color:#555;padding:2px 6px 2px 0">OSM ID</td>
                      <td style="font-size:11px;color:#888">${p.osm_id ?? '—'}</td></tr>
                </table>
              </div>`)
            layer.on('mouseover', () => layer.setStyle({ weight: 6, opacity: 1 }))
            layer.on('mouseout',  () => layer.setStyle({ color: '#00b894', weight: 4, opacity: 0.9 }))
          }}
        />
      )}

      {/* Voies OSM en construction (highway=construction) */}
      {layers.osm_construction?.visible !== false && osmConstruction && (
        <GeoJSON
          key="osm_construction"
          data={osmConstruction}
          style={() => ({ color: '#fd79a8', weight: 4, opacity: 0.95, dashArray: '8 5' })}
          onEachFeature={(feature, layer) => {
            const p = feature.properties ?? {}
            layer.bindPopup(`
              <div style="font-family:sans-serif;font-size:13px;min-width:190px">
                <div style="font-weight:700;margin-bottom:6px;border-bottom:2px solid #fd79a8;padding-bottom:4px;color:#fd79a8">
                  Voie en construction
                </div>
                <table style="width:100%;border-collapse:collapse">
                  ${p.name ? `<tr><td style="color:#555;padding:2px 6px 2px 0">Nom</td><td style="font-weight:600">${p.name}</td></tr>` : ''}
                  <tr><td style="color:#555;padding:2px 6px 2px 0">Type futur</td>
                      <td style="font-weight:600">${p.type_label ?? '—'}</td></tr>
                  <tr><td style="color:#555;padding:2px 6px 2px 0">Modif. OSM</td>
                      <td>${p.timestamp ?? '—'}</td></tr>
                  <tr><td style="color:#555;padding:2px 6px 2px 0">OSM ID</td>
                      <td style="font-size:11px;color:#888">${p.osm_id ?? '—'}</td></tr>
                </table>
              </div>`)
            layer.on('mouseover', () => layer.setStyle({ weight: 6, opacity: 1 }))
            layer.on('mouseout',  () => layer.setStyle({ color: '#fd79a8', weight: 4, opacity: 0.95, dashArray: '8 5' }))
          }}
        />
      )}

      {/* Nouvelles voies OSM 2020+ — voirie carrossable */}
      {layers.osm_nouvelles_voies?.visible !== false && osmVoies && (
        <GeoJSON
          key="osm_nouvelles_voies"
          data={osmVoies}
          style={osmVoieStyle}
          onEachFeature={onEachOsmVoie}
        />
      )}

      {/* Nouveaux trottoirs / pistes cyclables OSM 2020+ */}
      {layers.osm_pieton?.visible && osmPieton && (
        <GeoJSON
          key="osm_pieton"
          data={osmPieton}
          style={() => ({ color: '#74b9ff', weight: 2, opacity: 0.8, dashArray: '4 3' })}
          onEachFeature={onEachOsmVoie}
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

      {/* PC logements — cercles proportionnels au nb de logements */}
      {layers.pc_logements?.visible !== false && pcLogements && (
        <GeoJSON
          key="pc_logements"
          data={pcLogements}
          pointToLayer={pcLogPointToLayer}
        />
      )}

      {/* Permis de démolir */}
      {layers.permis_demolir?.visible !== false && permisDemloir && (
        <GeoJSON
          key="permis_demolir"
          data={permisDemloir}
          pointToLayer={demolirPointToLayer}
        />
      )}

      {/* Locaux non résidentiels */}
      {layers.locaux_non_resid?.visible !== false && locauxNonResid && (
        <GeoJSON
          key="locaux_non_resid"
          data={locauxNonResid}
          pointToLayer={locauxPointToLayer}
        />
      )}

      {/* Permis d'aménager — points géocodés Châteaugiron */}
      {layers.permis_pa?.visible !== false && permisPA && (
        <GeoJSON
          key="permis_pa"
          data={permisPA}
          pointToLayer={permisPointToLayer}
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
