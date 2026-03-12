import React, { useState, useEffect } from 'react'
import { EDIT_MODE } from '../config.js'

export const COLORS = {
  5: { bg: '#c0392b', fg: '#fff' },
  4: { bg: '#d35400', fg: '#fff' },
  3: { bg: '#d4ac0d', fg: '#1a1a1a' },
  2: { bg: '#2471a3', fg: '#fff' },
  1: { bg: '#7d3c98', fg: '#fff' },
  0: { bg: '#717d7e', fg: '#fff' },
}

function formatCategorie(cat) {
  if (!cat) return ''
  const map = {
    lotissement_residentiel: 'Lotissement résidentiel',
    chantier_voirie:         'Chantier voirie',
    constructions_isolees:   'Constructions isolées',
    extension_lotissement:   'Extension lotissement',
    giratoire_nouveau:       'Giratoire nouveau',
    refection_voirie:        'Réfection voirie',
    non_pertinent:           'Non pertinent',
    bati_nouveau:            'Bâti nouveau',
    demolition:              'Démolition',
    inconnu:                 'Inconnu',
  }
  return map[cat] || cat.replace(/_/g, ' ')
}

function ConfidenceBadge({ confiance }) {
  const labels = {
    haute:    'Haute confiance',
    moyenne:  'Confiance moyenne',
    hors_pcrs:'Hors périmètre PCRS',
    inconnue: 'Confiance inconnue',
  }
  return (
    <span className={`badge badge-${confiance || 'inconnue'}`}>
      {labels[confiance] || confiance}
    </span>
  )
}

export default function FeatureDetail({ feature, onClose, onEdit, onEditGeom, editingGeomId }) {
  const p = feature?.properties || {}
  const isEditingGeom = editingGeomId === p._demo_id
  const [editMode, setEditMode]   = useState(false)
  const [label, setLabel]         = useState(p.ia_label || '')
  const [justif, setJustif]       = useState(p.ia_justification || '')
  const [stars, setStars]         = useState(p.ia_etoiles ?? 0)

  // Sync local state when selected feature changes
  useEffect(() => {
    setEditMode(false)
    setLabel(p.ia_label || '')
    setJustif(p.ia_justification || '')
    setStars(p.ia_etoiles ?? 0)
  }, [feature?.properties?._demo_id])

  function handleSave() {
    onEdit({ ia_label: label, ia_justification: justif, ia_etoiles: stars })
    setEditMode(false)
  }

  function handleCancel() {
    setLabel(p.ia_label || '')
    setJustif(p.ia_justification || '')
    setStars(p.ia_etoiles ?? 0)
    setEditMode(false)
  }

  const col = COLORS[stars] || COLORS[0]

  return (
    <div className="feature-detail">
      {/* Banner */}
      <div className="feature-detail-banner" style={{ background: col.bg, color: col.fg }}>
        {EDIT_MODE && editMode ? (
          <div className="stars-edit">
            {[0,1,2,3,4,5].map(n => (
              <button
                key={n}
                className={`star-btn${stars === n ? ' active' : ''}`}
                style={{ color: stars >= n && n > 0 ? '#fff' : 'rgba(255,255,255,0.35)' }}
                onClick={() => setStars(n)}
                title={`${n} étoile${n !== 1 ? 's' : ''}`}
              >
                {n === 0 ? '☆' : '★'}
              </button>
            ))}
          </div>
        ) : (
          <div className="stars" style={{ color: col.fg }}>
            {'★'.repeat(Math.max(0, stars))}
            <span style={{ opacity: 0.35 }}>{'★'.repeat(Math.max(0, 5 - stars))}</span>
          </div>
        )}
        <div style={{ display: 'flex', gap: 4 }}>
          {EDIT_MODE && (
            <button
              className="feature-detail-edit"
              onClick={() => editMode ? handleSave() : setEditMode(true)}
              title={editMode ? 'Enregistrer' : 'Modifier'}
            >
              {editMode ? '✓' : '✏'}
            </button>
          )}
          {EDIT_MODE && editMode && (
            <button className="feature-detail-edit" onClick={handleCancel} title="Annuler">✕</button>
          )}
          {(!EDIT_MODE || !editMode) && (
            <button className="feature-detail-close" onClick={onClose} title="Fermer">✕</button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="feature-detail-body">
        {EDIT_MODE && editMode ? (
          <>
            <input
              className="edit-input"
              value={label}
              onChange={e => setLabel(e.target.value)}
              placeholder="Label"
            />
            <textarea
              className="edit-textarea"
              value={justif}
              onChange={e => setJustif(e.target.value)}
              placeholder="Justification"
              rows={5}
            />
          </>
        ) : (
          <>
            {label && <div className="feature-detail-title">{label}</div>}

            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {p.ia_categorie && (
                <span className="badge badge-cat">{formatCategorie(p.ia_categorie)}</span>
              )}
              <ConfidenceBadge confiance={p.confiance} />
            </div>

            {justif && (
              <div className="feature-detail-justif">{justif}</div>
            )}

            {(p.score_t1 != null || p.score_t2 != null) && (
              <div className="feature-detail-scores">
                Score visuel 2020 : {p.score_t1 != null ? Number(p.score_t1).toFixed(1) : '—'}
                {' | '}
                Score visuel 2025 : {p.score_t2 != null ? Number(p.score_t2).toFixed(1) : '—'}
              </div>
            )}

            {p.nom && (
              <div className="feature-detail-meta">
                <strong>Nom :</strong> {p.nom}
              </div>
            )}
            {p.commune && (
              <div className="feature-detail-meta">
                <strong>Commune :</strong> {p.commune}
              </div>
            )}
          </>
        )}

        {/* Geometry edit buttons — visible only in EDIT_MODE */}
        {EDIT_MODE && <div className="geom-edit-section">
          <div className="section-label" style={{ marginBottom: 6 }}>Modifier la géométrie</div>
          {!isEditingGeom ? (
            <div className="geom-btns">
              <button
                className="geom-btn"
                onClick={() => onEditGeom(p._demo_id, 'polygon')}
                title="Dessiner un nouveau polygone"
              >
                ⬡ Nouveau polygone
              </button>
              <button
                className="geom-btn geom-btn-line"
                onClick={() => onEditGeom(p._demo_id, 'line15m')}
                title="Tracer un axe — buffer automatique 15 m"
              >
                ╌ Axe + buffer 15 m
              </button>
            </div>
          ) : (
            <div className="geom-drawing-hint">
              <span>🖊 Cliquez sur la carte pour dessiner…</span>
              <span className="geom-hint-sub">Double-clic pour terminer</span>
              <button
                className="geom-cancel-btn"
                onClick={() => onEditGeom(null, null)}
              >
                Annuler
              </button>
            </div>
          )}
        </div>}
      </div>
    </div>
  )
}
