// Miroir JS de config.py — paramètres partagés entre le pipeline et l'UI

export const CENTER_WGS84 = [48.025, -1.195]

export const BBOX_WGS84 = {
  lonMin: -1.28,
  latMin:  47.97,
  lonMax: -1.11,
  latMax:  48.08,
}

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
  construction: '#e74c3c',   // rouge   — vég/sol→imperméable
  demolition:   '#9b59b6',   // violet  — imperméable→sol/vég
  chantier:     '#f39c12',   // orange  — vég→sol nu
}

// Étapes du pipeline — ordre et métadonnées
export const PIPELINE_STEPS = [
  {
    id: 1,
    label: 'Téléchargement orthophotos',
    script: '01_download_ign.py',
    outputKeys: ['ortho_t1', 'ortho_t2'],
    description: 'WMS IGN Géoportail → GeoTIFF Lambert 93',
  },
  {
    id: 2,
    label: 'Prétraitement',
    script: '02_preprocess.py',
    outputKeys: ['proc_t1', 'proc_t2'],
    description: 'Classification spectrale VARI/ExR · Encodage transitions T1→T2',
  },
  {
    id: 3,
    label: 'Détection de changement',
    script: '03_change_detection.py',
    outputKeys: ['diff', 'geojson'],
    description: 'PCC · Transitions spectrales · Polygonisation',
  },
  {
    id: 4,
    label: 'Export carte',
    script: '04_export_results.py',
    outputKeys: ['carte_html'],
    description: 'Carte Folium interactive HTML',
  },
]
