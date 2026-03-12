import React, { useState } from 'react'
import logo from '../assets/logo.png'
import StarSlider from './StarSlider.jsx'
import { EDIT_MODE } from '../config.js'
import RapportModal from './RapportModal.jsx'

export default function Sidebar({
  minEtoiles, onMinEtoilesChange,
  totalVisible, totalAll, loading,
  hasOverrides, onExport, onResetOverrides,
}) {
  const [showRapport, setShowRapport] = useState(false)

  return (
    <div className="sidebar">
      {/* Header */}
      <div className="header">
        <img src={logo} alt="Carte42" />
        <h1>
          PCRS SDE35
          <span>Détection des changements PCRS</span>
        </h1>
      </div>

      {/* Star slider */}
      <StarSlider value={minEtoiles} onChange={onMinEtoilesChange} />

      {/* Compteur */}
      <div className="counter">
        {loading ? 'Chargement…' : (
          <>
            <strong>{totalVisible}</strong> détection{totalVisible !== 1 ? 's' : ''} sur <strong>{totalAll}</strong>
          </>
        )}
      </div>

      <hr className="divider" />

      {/* Téléchargement — toujours visible */}
      <div className="export-row">
        <button className="export-btn" onClick={onExport} title="Télécharger les données au format GeoJSON (compatible QGIS)"
          data-ob-anchor="export">
          ⬇ Télécharger les données
        </button>
        {/* Reset overrides — visible uniquement en EDIT_MODE */}
        {EDIT_MODE && hasOverrides && (
          <button className="reset-btn" onClick={onResetOverrides} title="Effacer toutes les modifications">
            ↺
          </button>
        )}
      </div>

      {/* Rapport PDF */}
      <div className="export-row">
        <button className="rapport-btn" onClick={() => setShowRapport(true)}
          title="Générer un rapport PDF par commune">
          ☰ Générer le rapport
        </button>
      </div>

      {showRapport && <RapportModal onClose={() => setShowRapport(false)} />}

      {/* À propos */}
      <div className="about-section">
        <details>
          <summary>À propos</summary>
          <div className="about-content">
            <p>Zone échantillon : Châteaugiron et communes environnantes (Ille-et-Vilaine)</p>
            <p>Analyse : orthophotographies IGN 2020 vs 2025</p>
            <p>Données : OSM, BD TOPO IGN, Sitadel</p>
          </div>
        </details>
      </div>
    </div>
  )
}
