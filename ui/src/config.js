// Miroir JS de config.py — paramètres partagés entre le pipeline et l'UI

export const CENTER_WGS84 = [48.077, -1.503]

export const BBOX_WGS84 = {
  lonMin: -1.590,
  latMin:  48.018,
  lonMax: -1.432,
  latMax:  48.136,
}

// Périodes Sentinel-2 (synchronisées avec config.py)
export const S2_BASELINE_LABEL = 'Avril 2024 (S2 RGB)'
export const S2_DETECT_LABEL   = 'Octobre 2025 (S2 RGB)'

// WMS IGN data.geopf.fr (couches vérifiées sur GetCapabilities mars 2026)
export const IGN_WMS_URL = 'https://data.geopf.fr/wms-r/wms'

export const IGN_LAYER_T1         = 'ORTHOIMAGERY.ORTHOPHOTOS2020'                  // BD ORTHO 2020
export const IGN_LAYER_T2         = 'ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023'   // Ortho-express 2023
export const IGN_LAYER_T2_2024    = 'ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2024'   // Ortho-express 2024
export const IGN_LAYER_T2_2023    = 'ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023'   // Ortho-express 2023
export const IGN_LAYER_PCRS_SDE35 = 'PCRS_SDE35'                                    // PCRS SDE35

// Alias pour compatibilité
export const IGN_LAYER = IGN_LAYER_T2

export const MILLESIME_ANCIEN = '2020'
export const MILLESIME_RECENT = '2023'

export const COULEURS = {
  construction: '#e74c3c',   // rouge   — nouveau bâti / voirie
  chantier:     '#f39c12',   // orange  — chantier en cours
}

// Étapes du pipeline Sentinel-2 — ordre et métadonnées
export const PIPELINE_STEPS = [
  {
    id: 1,
    label: 'Téléchargement Sentinel-2',
    script: '01_download_sentinel2.py',
    outputKeys: ['s2_images'],
    description: 'CDSE Copernicus → B04 + B08 + SCL · 2019-2023 · nuages < 20%',
  },
  {
    id: 2,
    label: 'Série temporelle NDVI',
    script: '02_ndvi_timeseries.py',
    outputKeys: ['s2_ndvi', 's2_change'],
    description: 'NDVI mensuel · Baseline 2019-2020 · Détection rupture persistante',
  },
  {
    id: 3,
    label: 'Détection de changement',
    script: '03_change_detection.py',
    outputKeys: ['geojson'],
    description: 'Seuillage ΔNDVI · Polygonisation · Filtres surface/compacité',
  },
  {
    id: 4,
    label: 'Export carte',
    script: '04_export_results.py',
    outputKeys: ['carte_html'],
    description: 'Carte Folium interactive HTML',
  },
]
