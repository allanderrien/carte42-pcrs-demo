import React from 'react'
import { COULEURS, MILLESIME_ANCIEN, MILLESIME_RECENT } from '../config.js'

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
}) {
  const layerDefs = [
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
      id: 'wms_t2_2024',
      label: 'Ortho-express 2024',
      sub: 'WMS IGN data.geopf.fr',
      color: '#8e44ad',
      hasOpacity: true,
    },
    {
      id: 'wms_t2_2023',
      label: 'Ortho-express 2023',
      sub: 'WMS IGN data.geopf.fr',
      color: '#6c3483',
      hasOpacity: true,
    },
    {
      id: 'pcrs_sde35',
      label: 'PCRS SDE35',
      sub: 'WMS IGN — PCRS D035',
      color: '#e67e22',
      hasOpacity: true,
    },
    {
      id: 'geojson',
      label: 'Changements détectés',
      sub: geojsonStats
        ? `${geojsonStats.total} zones · ${geojsonStats.surface_ha} ha`
        : 'GeoJSON non chargé',
      color: COULEURS.fort,
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
