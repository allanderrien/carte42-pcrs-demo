# Carte42 — PCRS Ille-et-Vilaine / SDE35

Démo de détection automatique de changements de voirie pour appel d'offres SDE35.
Zone d'étude : ~12×12 km autour de Vitré (35).

## Lancer le projet

```bash
cd ui && npm run dev    # → http://localhost:5173
```

Python venv : `.venv/Scripts/python.exe` (Windows)

## Architecture

```
config.py                                   # paramètres centralisés
processing/
  01_download_ign.py                         # téléchargement WMS IGN → tuiles WGS84
  02_ndvi_timeseries.py                      # NDVI Sentinel-2 (non utilisé en démo)
  03_change_detection.py                     # polygonisation PCC NDVI
  geocode_permis.py                          # permis d'aménager → GeoJSON points
  geocode_pc_logements.py                    # PC logements → GeoJSON points
  geocode_autres_permis.py                   # permis démolir + locaux non résid
  fetch_osm_roads.py                         # réseau OSM complet → 4 GeoJSON
  fetch_osm_construction_history.py          # historique adiff chantiers terminés
  detect_lotissements.py                     # détection lotissements (double filtre)
ui/
  vite.config.js               # plugin API (SSE logs, run/stop, endpoints GeoJSON)
  src/App.jsx                  # état global React + fetch toutes les sources
  src/components/MapView.jsx   # Leaflet + toutes les couches
  src/components/LayerControls.jsx
  src/components/StepList.jsx
  src/components/LogPanel.jsx
  src/config.js                # miroir JS de config.py
data/
  emprise/emprise_zone.shp     # zone d'étude (L93) — NON versionné
  emprise/emprise_voies.shp    # réseau viaire PCRS (L93) — NON versionné
  raw/tiles_t1/                # 132 tuiles RGB 2020 (WGS84, uint8) — NON versionné
  raw/tiles_t2/                # tuiles RGB 2023 — NON versionné
  raw/tiles_t1_irc/            # tuiles IRC 2020 (NIR,R,G) — NON versionné
  raw/tiles_t2_irc/            # tuiles IRC 2023 — NON versionné
  osm/                         # GeoJSON OSM générés — versionnés
    nouvelles_voies_osm.geojson
    nouvelles_voies_pieton_osm.geojson
    voies_existantes_osm.geojson
    voies_construction_osm.geojson
    chantiers_termines_osm.geojson
    lotissements_detectes.geojson
  registre_permis_amenager/    # GeoJSON permis géocodés — versionnés
    permis_chateaugiron.geojson
    pc_logements.geojson
    permis_demolir.geojson
    locaux_non_resid.geojson
output/vectors/changements_detectes.geojson
```

## Approche principale — Données administratives + OSM

L'analyse satellite a été abandonnée (instabilité, 60% détection max en milieu urbain).
L'approche retenue croise trois familles de données :

### 1. Permis Sitadel (6 communes)
Châteaugiron (35069), Brecé (35039), Domloup (35099),
Nouvoitou (35204), Noyal-sur-Vilaine (35207), Servon-sur-Vilaine (35327)

Géocodage via BAN (`api-adresse.data.gouv.fr/search/`).
CSV Sitadel : 2 lignes de header (ligne 1 = labels, ligne 2 = codes).

### 2. OSM — réseau viaire (fetch_osm_roads.py)
Requête Overpass sans filtre de date (`way["highway"](bbox)`) + `out meta geom`.
Split en Python :
- `version=1 + timestamp >= "2020-01-01"` → nouvelles voies
- tout le reste → réseau existant (référence spatiale)
- `highway=construction` (toutes versions) → chantiers en cours

**Règles Overpass critiques :**
- Format date : `"2020-01-01T00:00:00Z"` obligatoire pour `newer`
- `[out:json]` incompatible avec `[adiff]` → utiliser XML (sans `[out:...]`)
- Seul `overpass-api.de` a la base attic (historique) pour adiff
- Requêtes adiff lourdes → retry avec sleep 20s

### 3. Historique construction (fetch_osm_construction_history.py)
Overpass adiff XML depuis 2021-01-01 :
- `action="delete"` + `visible=true` = chantier terminé
- Géométrie dans `<old>`, date complétion dans `<new timestamp>`

## Détection lotissements (detect_lotissements.py)

Double filtre sur les nouvelles voies OSM :
1. **Spatial** : >50% de longueur hors buffer 25m du réseau OSM existant
2. **Spectral** : ExG (2G-R-B normalisé) > 0.08 sur ≥35% des pixels T1 2020
   → terrain vert/végétation en 2020 = vraiment nouveau
3. Buffer 20m + dissolve + filtre surface ≥ 500m²
→ 51 polygones de lotissement · 46,9 ha

## Données IGN (WMS data.geopf.fr/wms-r/wms)

| Variable config | Couche | Notes |
|---|---|---|
| IGN_LAYER_T1 | ORTHOIMAGERY.ORTHOPHOTOS2020 | RGB 2020 |
| IGN_LAYER_T2 | ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023 | RGB 2023 |
| IGN_LAYER_T1_IRC | ORTHOIMAGERY.ORTHOPHOTOS.IRC.2020 | IRC 2020 ✅ |
| IGN_LAYER_T2_IRC | ORTHOIMAGERY.ORTHOPHOTOS.IRC-EXPRESS.2023 | IRC 2023 ✅ |

WMS 1.3.0 / EPSG:4326 — bbox = `(latmin, lonmin, latmax, lonmax)`
Tuiles sauvegardées en WGS84 natif (pas de reprojection raster).
EPSG:2154 retourne des tuiles blanches — toujours EPSG:4326.

## Points d'attention

- Tuiles en **WGS84 natif** (EPSG:4326) — pas de reprojection raster
- Surface des polygones calculée en **L93** (via shp_transform avant .area)
- Pyproj `always_xy=True` pour transformer L93↔WGS84
- Test zone : bbox WGS84 passé en env vars L93 (TEST_XMIN/YMIN/XMAX/YMAX)
- Shapefiles emprise en L93, reprojetés WGS84 par vite.config.js pour l'UI

## Paramètres détection PCC NDVI (config.py)

```python
RESOLUTION_CIBLE = 0.50       # m/px
TILE_SIZE_PX     = 2048
SEUIL_NDVI_VEG   = 0.25
SEUIL_NDVI_SOL   = 0.05
SEUIL_OMBRE      = 45
MORPH_KERNEL_RADIUS = 2
SURFACE_MIN_M2   = 50.0
COMPACITE_MIN    = 0.12
BUFFER_EMPRISE_VOIES = 5      # m
```

## Git

- Remote : https://github.com/allanderrien/carte42-pcrs-demo
- `data/raw/`, `data/processed/`, `data/emprise/` ignorés (lourds / client)
- `data/osm/*.geojson` et `data/registre_permis_amenager/*.geojson` versionnés
- Email git : allanderrien@users.noreply.github.com
