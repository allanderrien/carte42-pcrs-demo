import React from 'react'

const LEGEND = [
  { stars: 5, label: 'Mise à jour très probable — giratoires, réfections voirie, grands lotissements', color: '#e74c3c' },
  { stars: 4, label: 'Mise à jour probable — extensions de lotissements, programmes résidentiels', color: '#e67e22' },
  { stars: 3, label: 'Mise à jour potentielle — petites opérations, chantiers voirie', color: '#f1c40f' },
  { stars: 2, label: 'Mise à jour à investiguer — constructions sur plusieurs parcelles en bord de voirie', color: '#3498db' },
  { stars: 1, label: 'Mise à jour minime à investiguer — constructions isolées en bord de voirie', color: '#9b59b6' },
  { stars: 0, label: 'Probablement hors périmètre PCRS', color: '#95a5a6' },
]

function starColor(value) {
  if (value >= 5) return '#e74c3c'
  if (value >= 4) return '#e67e22'
  if (value >= 3) return '#f1c40f'
  if (value >= 2) return '#3498db'
  if (value >= 1) return '#9b59b6'
  return '#95a5a6'
}

function renderStars(value) {
  const color = starColor(value)
  const full = '★'.repeat(value)
  const empty = '☆'.repeat(5 - value)
  return (
    <span className="star-display">
      <span style={{ color }}>{full}</span>
      <span style={{ color: '#3a4a6a' }}>{empty}</span>
    </span>
  )
}

export default function StarSlider({ value, onChange }) {
  return (
    <div className="star-slider">
      <label>Priorité</label>
      {renderStars(value)}
      <input
        type="range"
        min={0}
        max={5}
        step={1}
        value={value}
        onChange={e => onChange(parseInt(e.target.value, 10))}
      />
      <ul className="star-legend">
        {LEGEND.map(({ stars, label, color }) => (
          <li key={stars} style={{ opacity: stars >= value ? 1 : 0.4 }}>
            <span className="star-key" style={{ color }}>
              {'★'.repeat(stars) || '○'}
            </span>
            <span>{label}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
