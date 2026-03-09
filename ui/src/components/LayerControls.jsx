import React from 'react'
import { COULEURS, MILLESIME_ANCIEN, MILLESIME_RECENT, S2_BASELINE_LABEL, S2_DETECT_LABEL } from '../config.js'

const STATE_SUB = {
  ok:      (label) => label,
  loading: ()      => 'Chargement…',
  error:   (_, err) => `Erreur : ${err}`,
}

const STATE_DOT_STYLE = {
  ok:      (color, dashed) => dashed
    ? { background: 'transparent', border: `2px dashed ${color}` }
    : { background: color },
  loading: () => ({ background: '#555' }),
  error:   () => ({ background: '#e74c3c' }),
}

export default function LayerControls({
  layers, onToggle, onOpacity, geojsonStats,
  empriseZoneState, empriseVoiesState,
  empriseZoneErr, empriseVoiesErr,
  s2Years,
}) {
  const layerDefs = [
    {
      id: 'google_sat',
      label: 'Google Satellite',
      sub: 'Fond satellite récent',
      color: '#34a853',
      hasOpacity: true,
    },
    {
      id: 'osm_construction',
      label: 'Voies en construction OSM',
      sub: 'highway=construction · chantier en cours',
      color: '#fd79a8',
    },
    {
      id: 'voies_existantes',
      label: 'Réseau viaire existant (PCRS)',
      sub: 'Référence détection · emprise_voies.shp',
      color: '#e74c3c',
    },
    {
      id: 'lotissements',
      label: 'Lotissements détectés (2020+)',
      sub: 'Nouvelles voies OSM · buffer 20 m',
      color: '#e17055',
    },
    {
      id: 'osm_nouvelles_voies',
      label: 'Nouvelles voies OSM (2020+)',
      sub: 'OpenStreetMap · voirie carrossable',
      color: '#f9ca24',
    },
    {
      id: 'osm_pieton',
      label: 'Trottoirs / pistes cyclables OSM (2020+)',
      sub: 'OpenStreetMap · piéton & vélo',
      color: '#74b9ff',
    },
    {
      id: 'wms_t1',
      label: `BD ORTHO ${MILLESIME_ANCIEN} (T1)`,
      sub: 'WMS IGN data.geopf.fr',
      color: '#3498db',
      hasOpacity: true,
    },
    {
      id: 'wms_t2',
      label: `Ortho-express ${MILLESIME_RECENT} (T2)`,
      sub: 'WMS IGN data.geopf.fr',
      color: '#9b59b6',
      hasOpacity: true,
    },
    {
      id: 'permis_pa',
      label: 'Permis d\'aménager',
      sub: 'Sitadel 2026 · 6 communes',
      color: '#8e44ad',
    },
    {
      id: 'pc_logements',
      label: 'PC logements (2019+)',
      sub: 'Sitadel 2026 · 6 communes · actifs',
      color: '#e67e22',
    },
    {
      id: 'permis_demolir',
      label: 'Permis de démolir',
      sub: 'Sitadel 2026 · 6 communes · autorisés',
      color: '#c0392b',
    },
    {
      id: 'locaux_non_resid',
      label: 'Locaux non résidentiels (2019+)',
      sub: 'Sitadel 2026 · 6 communes · actifs',
      color: '#2980b9',
    },
    {
      id: 'emprise_zone',
      label: "Emprise zone d'étude",
      sub: STATE_SUB[empriseZoneState]('Shapefile chargé', empriseZoneErr),
      color: '#2c3e50',
      dashed: true,
      state: empriseZoneState,
      err: empriseZoneErr,
    },
    {
      id: 'emprise_voies',
      label: 'Emprise voies',
      sub: STATE_SUB[empriseVoiesState]('Shapefile chargé', empriseVoiesErr),
      color: '#1abc9c',
      state: empriseVoiesState,
      err: empriseVoiesErr,
    },
  ]

  return (
    <section className="sidebar-section">
      <div className="section-header">Couches</div>

      <ul className="layer-list">
        {layerDefs.map(def => {
          const state = def.state ?? 'ok'
          const dotStyle = STATE_DOT_STYLE[state](def.color, def.dashed)

          return (
            <li key={def.id} className="layer-item">
              <label className="layer-toggle">
                <input
                  type="checkbox"
                  checked={layers[def.id]?.visible ?? true}
                  onChange={() => onToggle(def.id)}
                />
                <span className="layer-dot" style={dotStyle} />
                <span className="layer-label">{def.label}</span>
              </label>
              <div className={`layer-sub ${state === 'error' ? 'layer-sub--error' : ''}`}>
                {def.sub}
              </div>

              {def.hasOpacity && layers[def.id]?.visible && (
                <div className="opacity-row">
                  <span>Opacité</span>
                  <input
                    type="range" min="0" max="1" step="0.05"
                    value={layers[def.id]?.opacity ?? 0.85}
                    onChange={e => onOpacity(def.id, parseFloat(e.target.value))}
                  />
                  <span>{Math.round((layers[def.id]?.opacity ?? 0.85) * 100)}%</span>
                </div>
              )}
            </li>
          )
        })}
      </ul>

      {/* Section Sentinel-2 — visible seulement si des composites sont disponibles */}
      {s2Years?.length > 0 && (
        <li className="layer-item" style={{ marginTop: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#aaa', textTransform: 'uppercase',
                        letterSpacing: '0.08em', marginBottom: 6 }}>
            Sentinel-2 NDVI annuel
          </div>
          {s2Years.map(year => {
            const id = `s2_${year}`
            // Couleur interpolée entre bleu (2019) et vert (2023)
            const hue = 200 + (parseInt(year) - 2019) * 20
            return (
              <div key={year} style={{ marginBottom: 4 }}>
                <label className="layer-toggle">
                  <input
                    type="checkbox"
                    checked={layers[id]?.visible ?? false}
                    onChange={() => onToggle(id)}
                  />
                  <span className="layer-dot" style={{ background: `hsl(${hue},60%,50%)` }} />
                  <span className="layer-label">NDVI {year}</span>
                </label>
                {layers[id]?.visible && (
                  <div className="opacity-row">
                    <span>Opacité</span>
                    <input
                      type="range" min="0" max="1" step="0.05"
                      value={layers[id]?.opacity ?? 0.75}
                      onChange={e => onOpacity(id, parseFloat(e.target.value))}
                    />
                    <span>{Math.round((layers[id]?.opacity ?? 0.75) * 100)}%</span>
                  </div>
                )}
              </div>
            )
          })}
          <div className="layer-sub" style={{ marginTop: 4 }}>
            Rouge = imperméable · Vert = végétation
          </div>
        </li>
      )}

      {geojsonStats && (
        <div className="stats-box">
          <div className="stats-row">
            <span>Zones fort</span>
            <strong style={{ color: COULEURS.fort }}>{geojsonStats.n_fort}</strong>
          </div>
          <div className="stats-row">
            <span>Zones modéré</span>
            <strong style={{ color: COULEURS.modere }}>{geojsonStats.n_modere}</strong>
          </div>
          <div className="stats-row">
            <span>Surface totale</span>
            <strong>{geojsonStats.surface_ha} ha</strong>
          </div>
          <div className="stats-row">
            <span>Ampl. moyenne</span>
            <strong>{geojsonStats.ampl_moy}</strong>
          </div>
        </div>
      )}
    </section>
  )
}
