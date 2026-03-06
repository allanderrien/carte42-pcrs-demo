"""
config.py — Paramètres centralisés du projet Carte42 / PCRS Ille-et-Vilaine
Tous les paramètres globaux sont définis ici. Ne jamais hardcoder dans les scripts.
"""

from pathlib import Path

# =============================================================================
# CHEMINS DU PROJET
# =============================================================================

BASE_DIR = Path(__file__).parent

DATA_DIR       = BASE_DIR / "data"
RAW_DIR        = DATA_DIR / "raw"
PROCESSED_DIR  = DATA_DIR / "processed"
VECTOR_DIR     = DATA_DIR / "vector"

OUTPUT_DIR     = BASE_DIR / "output"
VECTORS_OUT    = OUTPUT_DIR / "vectors"
TILES_OUT      = OUTPUT_DIR / "tiles"
MAP_OUT        = OUTPUT_DIR / "map"

ASSETS_DIR     = BASE_DIR / "assets"

# =============================================================================
# EMPRISE ZONE TEST — Lambert 93 (EPSG:2154), région de Vitré (35)
# ~12 x 12 km
# =============================================================================

BBOX_L93 = {
    "xmin": 359373,
    "ymin": 6778649,
    "xmax": 370361,
    "ymax": 6790860,
}

CRS_PROJET = "EPSG:2154"   # Lambert 93 (sortie)
CRS_WGS84  = "EPSG:4326"   # WGS84 (pour folium / flux WMS géographiques)

# Emprise en WGS84 (approximative, pour affichage Folium)
# Convertie manuellement depuis L93 — centre Vitré 35500
BBOX_WGS84 = {
    "lon_min": -1.28,
    "lat_min":  47.97,
    "lon_max": -1.11,
    "lat_max":  48.08,
}

CENTER_WGS84 = (
    (BBOX_WGS84["lat_min"] + BBOX_WGS84["lat_max"]) / 2,
    (BBOX_WGS84["lon_min"] + BBOX_WGS84["lon_max"]) / 2,
)

# =============================================================================
# SOURCES DE DONNÉES
# =============================================================================

# --- T1 : WCS GéoBretagne — Orthophoto Ille-et-Vilaine 2020 (20 cm natif) ---
# Service WCS GeoServer GéoBretagne
GEOBRETAGNE_WCS_URL      = "https://geobretagne.fr/geoserver/photo/wcs"
GEOBRETAGNE_COVERAGE_RVB = "photo:ortho-35"       # RVB 20 cm — WCS 1.0.0
GEOBRETAGNE_COVERAGE_IRC = "photo:ir-35-2020"     # IRC 50 cm (végétation)

# Choix de la couche T1 (RVB ou IRC)
GEOBRETAGNE_COVERAGE_T1  = GEOBRETAGNE_COVERAGE_RVB

# --- T2 : WMS IGN data.geopf.fr — Ortho-express 2023 -----------------------
# Ortho-express 2025 ne couvre pas encore l'Ille-et-Vilaine (en cours de déploiement)
# Ortho-express 2023 couvre le département 35 — vérifiée sur GetCapabilities mars 2026
IGN_WMS_URL = "https://data.geopf.fr/wms-r/wms"

# Couches disponibles (vérifiées sur GetCapabilities mars 2026) :
IGN_LAYER_T1          = "ORTHOIMAGERY.ORTHOPHOTOS2020"                 # BD ORTHO 2020
IGN_LAYER_T2          = "ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023"  # Ortho-express 2023
IGN_LAYER_T2_IRC      = "ORTHOIMAGERY.ORTHOPHOTOS.IRC-EXPRESS.2023"    # IRC 2023
IGN_LAYER_PCRS_SDE35  = "PCRS_SDE35"                                   # PCRS SDE35 sur IGN

# Alias utilisé dans les scripts
IGN_LAYER_ORTHO = IGN_LAYER_T2   # couche principale T2

WMS_VERSION = "1.3.0"
WMS_FORMAT  = "image/png"
WMS_SRS     = "EPSG:2154"

# --- Millésimes ---
MILLESIME_ANCIEN = "2020"
MILLESIME_RECENT = "2023"

# Tuiles WMS téléchargées (permanentes, pas de merge — traitement tuile par tuile)
TILES_T1_DIR = RAW_DIR / "tiles_t1"   # T1 — WMS IGN ORTHOPHOTOS2020
TILES_T2_DIR = RAW_DIR / "tmp_t2"     # T2 — WMS IGN ORTHO-EXPRESS.2023

# Tuiles d'amplitude CVA produites par l'étape 2 (float32, mono-bande, ~400 Ko chacune)
TILES_AMP_DIR = PROCESSED_DIR / "tiles_amplitude"

# =============================================================================
# PARAMÈTRES DE TÉLÉCHARGEMENT
# =============================================================================

# Résolution de téléchargement — 0.50 m/px pour la démo (raisonnable sur 12×12 km)
# À 0.20 m/px : 210 tuiles, ~3 Go → trop lourd pour une démo
# À 0.50 m/px :  35 tuiles, ~200 Mo → bon compromis qualité/temps
RESOLUTION_CIBLE = 0.50   # m/pixel

# Taille maximale d'une tuile WMS en pixels
TILE_SIZE_PX = 2048        # pixels — valeur sûre pour data.geopf.fr

# Nombre de threads pour le téléchargement parallèle des tuiles
DOWNLOAD_THREADS = 4

# Timeout requête HTTP (secondes)
HTTP_TIMEOUT = 120

# Nombre de tentatives en cas d'erreur réseau
HTTP_RETRIES = 3

# =============================================================================
# PARAMÈTRES DE DÉTECTION DE CHANGEMENT
# =============================================================================

# Résolution de travail pour la détection (peut différer du raster brut)
DETECTION_RESOLUTION = 0.50   # m/pixel (compromis vitesse / précision)

# Seuil de différence radiométrique (0-255) en dessous duquel on ignore
SEUIL_DIFFERENCE = 30

# Surface minimale d'un polygone de changement à conserver (m²)
SURFACE_MIN_M2 = 50.0

# Rayon de lissage morphologique (pixels) pour nettoyer le masque binaire
MORPH_KERNEL_RADIUS = 3

# Seuil de luminosité (0–255) en dessous duquel un pixel est considéré en ombre.
# Les pixels sombres dans T1 OU T2 sont exclus du calcul CVA.
SEUIL_OMBRE = 45

# Compacité minimale d'un polygone pour être conservé (4π·surface/périmètre²).
# Cercle = 1.0, forme très allongée → 0.  Les ombres portées de bâtiments
# ont typiquement une compacité < 0.10.
COMPACITE_MIN = 0.12

# Seuil de pourcentage de changement par dalle pour alerter (%)
SEUIL_ALERTE_PCT = 5.0

# Bandes à utiliser pour la comparaison (indices 0-based)
# Pour orthophoto RVB standard : 0=Rouge, 1=Vert, 2=Bleu
BANDES_COMPARAISON = [0, 1, 2]

# =============================================================================
# PARAMÈTRES DE SORTIE & EXPORT
# =============================================================================

# Fichier GeoJSON des zones de changement
GEOJSON_CHANGEMENTS = VECTORS_OUT / "changements_detectes.geojson"

# Carte interactive HTML
HTML_CARTE = MAP_OUT / "carte_changements.html"

# Palette de couleurs pour la visualisation des changements
COULEUR_CHANGEMENT_FORT  = "#e74c3c"   # Rouge — changement significatif
COULEUR_CHANGEMENT_MOYEN = "#f39c12"   # Orange — changement modéré
COULEUR_INCHANGE         = "#27ae60"   # Vert — zone stable

# Opacité des couches sur la carte interactive (0.0 – 1.0)
OPACITE_RASTER = 0.85
OPACITE_VECTEUR = 0.70

# Titre affiché sur la carte HTML
TITRE_CARTE = "Carte42 — Détection de changement d'occupation du sol · Vitré (35)"
