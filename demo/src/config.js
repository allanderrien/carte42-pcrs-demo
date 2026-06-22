// ── Passer à true pour activer les fonctions d'édition (annotations, géométrie, export)
export const EDIT_MODE = false

export const IGN_WMS_URL = 'https://data.geopf.fr/wms-r/wms'
export const IGN_LAYER_T1 = 'ORTHOIMAGERY.ORTHOPHOTOS2020'                 // BD ORTHO 2020 (RGB)
export const IGN_LAYER_T2 = 'ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023'  // Ortho-express 2023 (RGB)
export const MAP_CENTER = [48.18, -1.63]   // Ille-et-Vilaine (hors Rennes Métropole)
export const MAP_ZOOM = 9

// ── Hébergement externe des rapports PDF (1,5 Go, hors GitHub Pages) ─────────
// Les chemins du manifeste (data/rapports_manifest.json) sont relatifs :
//   "<epci_slug>/Rapport_PCRS_<Commune>.pdf"
// RAPPORTS_BASE_URL est préfixé devant. Uploader l'arborescence
// "4. Livraison/rapports/" telle quelle sur cet hébergement (Drive public, S3,
// serveur statique…) puis renseigner l'URL ci-dessous (sans / final).
// Tant qu'elle est vide, le bouton de téléchargement reste désactivé.
export const RAPPORTS_BASE_URL = 'https://rapports.carte42.fr'
