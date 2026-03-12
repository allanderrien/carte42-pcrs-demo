import React, { useState, useEffect, useRef } from 'react'
import sde35Logo from '../assets/sde35.jpg'

export default function Onboarding() {
  const [step, setStep] = useState('welcome')  // 'welcome' | 1 | 2 | 3 | 'done'
  const [exportTop, setExportTop] = useState(430)

  useEffect(() => {
    if (step === 3) {
      const el = document.querySelector('[data-ob-anchor="export"]')
      if (el) {
        const rect = el.getBoundingClientRect()
        // Flèche ◀ en bas de la carte alignée avec le centre du bouton
        setExportTop(Math.round(rect.top + rect.height / 2 - 85))
      }
    }
  }, [step])

  function next() {
    if (step === 'welcome') setStep(1)
    else if (step === 1) setStep(2)
    else if (step === 2) setStep(3)
    else setStep('done')
  }

  if (step === 'done') return null

  return (
    <div className="ob-overlay">

      {/* ── Écran de bienvenue ── */}
      {step === 'welcome' && (
        <div className="ob-welcome-card">
          <div className="ob-glow" />
          <div className="ob-welcome-logos">
            <img src={sde35Logo} alt="SDE35" className="ob-logo-sde35" />
          </div>
          <div className="ob-welcome-title">Bienvenue sur votre interface de détection des changements du PCRS</div>
          <div className="ob-welcome-subtitle">Zone échantillon · Châteaugiron et environs · Ille-et-Vilaine</div>
          <div className="ob-welcome-text">
            Cette interface présente les résultats de l'analyse automatique
            de voirie et de bâti réalisée par Carte42 —
            croisement orthophotographies IGN, données OSM et registre Sitadel.
          </div>
          <button className="ob-start" onClick={next}>Commencer →</button>
        </div>
      )}

      {/* ── Étape 1 : fond de plan ── */}
      {step === 1 && (
        <div className="ob-card ob-card--bottom">
          <div className="ob-glow" />
          <div className="ob-body">
            <div className="ob-emoji">🗺</div>
            <div className="ob-title">Choisissez votre fond de plan</div>
            <div className="ob-text">
              Appuyez sur une date pour afficher la carte correspondante —
              comparez l'état PCRS de référence avec la vue satellite actuelle.
            </div>
          </div>
          <button className="ob-ok" onClick={next}>OK, compris →</button>
          <div className="ob-arrow--down">▼</div>
        </div>
      )}

      {/* ── Étape 2 : slider ── */}
      {step === 2 && (
        <div className="ob-card ob-card--left">
          <div className="ob-glow" />
          <div className="ob-arrow--left-ext">◀</div>
          <div className="ob-body">
            <div className="ob-emoji">★</div>
            <div className="ob-title">Filtrez par niveau de priorité</div>
            <div className="ob-text">
              Utilisez le slider pour afficher les niveaux d'importance
              des mises à jour PCRS détectées — de la MAJ très probable
              jusqu'aux signaux faibles.
            </div>
          </div>
          <button className="ob-ok" onClick={next}>OK, compris →</button>
        </div>
      )}

      {/* ── Étape 3 : export ── */}
      {step === 3 && (
        <div className="ob-card ob-card--left-low" style={{ top: exportTop }}>
          <div className="ob-glow" />
          <div className="ob-body">
            <div className="ob-emoji">📥</div>
            <div className="ob-title">Téléchargez vos données</div>
            <div className="ob-text">
              Exportez la couche d'identification des changements PCRS
              au format GeoJSON (compatible QGIS), ou générez un rapport
              PDF détaillé par commune.
            </div>
          </div>
          <button className="ob-ok" onClick={next}>C'est parti ✓</button>
          <div className="ob-arrow--left-ext-bottom">◀</div>
        </div>
      )}
    </div>
  )
}
