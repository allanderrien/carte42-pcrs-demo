# Carte42 — PCRS Ille-et-Vilaine / SDE35

Démo de détection automatique de changements de voirie pour appel d'offres SDE35.
Comparer orthos IGN 2020 vs 2023 sur ~12×12 km autour de Vitré (35).

## Lancer le projet

```bash
cd ui && npm run dev    # → http://localhost:5173
```

Python venv : `.venv/Scripts/python.exe` (Windows)

## Architecture

```
config.py                     # tous les paramètres centralisés
processing/
  01_download_ign.py           # téléchargement WMS IGN (RGB + IRC) → tuiles WGS84
  02_preprocess.py             # classification NDVI pixel → tuiles transition chg_*.tif
  03_change_detection.py       # polygonisation + filtres → GeoJSON
  04_export_results.py         # carte Folium HTML
ui/
  vite.config.js               # plugin API (SSE logs, run/stop, shapefiles, geojson)
  src/App.jsx                  # état global React
  src/components/MapView.jsx   # Leaflet + WMS + GeoJSON + zone de test
  src/components/StepList.jsx  # pipeline UI
  src/components/LayerControls.jsx
  src/components/LogPanel.jsx
  src/config.js                # miroir JS de config.py
data/
  emprise/emprise_zone.shp     # zone d'étude (L93)
  emprise/emprise_voies.shp    # réseau viaire (L93) — filtre spatial étape 3
  raw/tiles_t1/                # tuiles RGB 2020
  raw/tiles_t2/                # tuiles RGB 2023
  raw/tiles_t1_irc/            # tuiles IRC 2020 (NIR,R,G)
  raw/tiles_t2_irc/            # tuiles IRC 2023 (NIR,R,G)
  processed/tiles_changement/  # tuiles transition chg_*.tif (uint8)
output/vectors/changements_detectes.geojson
```

## Données IGN (WMS data.geopf.fr/wms-r/wms)

| Variable config | Couche | Notes |
|---|---|---|
| IGN_LAYER_T1 | ORTHOIMAGERY.ORTHOPHOTOS2020 | RGB 2020 |
| IGN_LAYER_T2 | ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023 | RGB 2023 |
| IGN_LAYER_T1_IRC | ORTHOIMAGERY.ORTHOPHOTOS.IRC.2020 | IRC 2020 ✅ |
| IGN_LAYER_T2_IRC | ORTHOIMAGERY.ORTHOPHOTOS.IRC-EXPRESS.2023 | IRC 2023 ✅ |

WMS 1.3.0 / EPSG:4326 — bbox = `(latmin, lonmin, latmax, lonmax)`
Tuiles sauvegardées en WGS84 natif (pas de reprojection raster).

## Méthode de détection — PCC NDVI 4 bandes

**Étape 2** : pour chaque paire T1/T2, classifie chaque pixel via :
- NDVI = (NIR − Rouge) / (NIR + Rouge)  [NIR = canal 0 de l'IRC IGN]
- Classes : 0=ombre | 1=végétation (NDVI>0.25) | 2=sol_nu (NDVI>0.05) | 3=imperméable
- Encode transition : `classe_T1 × 4 + classe_T2` → uint8, sauvé en chg_rXXX_cXXX.tif

**Étape 3** : transitions d'intérêt = {6, 7, 11, 13, 14}
- 6=veg→sol_nu (chantier), 7=veg→imperméable (construction)
- 11=sol_nu→imperméable (enrobé), 13=imperm→veg, 14=imperm→sol_nu (démolition)
- Filtres : surface > 50 m², compacité > 0.12, intersection emprise_voies

## Paramètres clés (config.py)

```python
RESOLUTION_CIBLE = 0.50       # m/px
TILE_SIZE_PX     = 2048
SEUIL_NDVI_VEG   = 0.25       # seuil végétation
SEUIL_NDVI_SOL   = 0.05       # seuil sol nu / imperméable
SEUIL_OMBRE      = 45         # luminosité minimale (0–255)
MORPH_KERNEL_RADIUS = 2
SURFACE_MIN_M2   = 50.0
COMPACITE_MIN    = 0.12
BUFFER_EMPRISE_VOIES = 5      # m
```

## Points d'attention

- Tuiles en **WGS84 natif** (EPSG:4326) — pas de reprojection raster
- Surface des polygones calculée en **L93** (via shp_transform avant .area)
- Test zone : bbox WGS84 passé en env vars L93 (TEST_XMIN/YMIN/XMAX/YMAX)
- `tuile_dans_bbox` compare bounds WGS84 vs bbox WGS84 (converti de L93)
- Shapefiles emprise en L93, reprojetés WGS84 par vite.config.js pour l'UI

## Git

- Remote : https://github.com/allanderrien/carte42-pcrs-demo
- `data/` ignoré (tuiles trop lourdes) sauf `output/vectors/*.geojson`
- Email git : allanderrien@users.noreply.github.com
