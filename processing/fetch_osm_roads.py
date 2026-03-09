"""
fetch_osm_roads.py — Récupère tout le réseau OSM de la zone d'étude
et le sépare en deux catégories :
  - nouvelles voies (version=1, créées après 2020)
  - réseau existant (tout le reste)

Une seule requête Overpass sans filtre de date, split en Python.

Usage :
  python processing/fetch_osm_roads.py
"""

import json, logging
from pathlib import Path
import requests
import geopandas as gpd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("osm_roads")

PROJECT_ROOT    = Path(__file__).parent.parent
EMPRISE_SHP     = PROJECT_ROOT / "data/emprise/emprise_zone.shp"
OUT_DIR         = PROJECT_ROOT / "data/osm"
OUT_FILE        = OUT_DIR / "nouvelles_voies_osm.geojson"
OUT_FILE_PIETON = OUT_DIR / "nouvelles_voies_pieton_osm.geojson"
OUT_FILE_OLD    = OUT_DIR / "voies_existantes_osm.geojson"
OUT_FILE_CONSTR = OUT_DIR / "voies_construction_osm.geojson"

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DATE_MIN     = "2020-01-01"   # comparaison string ISO, ex: "2023-04-12" >= "2020-01-01"

CONSTRUCTION_LABEL = {
    "motorway": "Autoroute", "trunk": "Route nationale",
    "primary": "Route principale", "secondary": "Route secondaire",
    "tertiary": "Route tertiaire", "residential": "Voie résidentielle",
    "unclassified": "Voie non classée", "service": "Voie de service",
    "living_street": "Zone de rencontre", "track": "Chemin",
    "footway": "Trottoir", "cycleway": "Piste cyclable",
    "": "Voirie",
}

HIGHWAY_LABEL = {
    "motorway":      "Autoroute",
    "trunk":         "Route nationale",
    "primary":       "Route principale",
    "secondary":     "Route secondaire",
    "tertiary":      "Route tertiaire",
    "residential":   "Voie résidentielle",
    "unclassified":  "Voie non classée",
    "service":       "Voie de service",
    "living_street": "Zone de rencontre",
    "track":         "Chemin agricole/forestier",
    "footway":       "Trottoir / cheminement piéton",
    "cycleway":      "Piste cyclable",
}

EXCLUDE_ALL  = {"path", "steps", "bridleway"}
PIETON_TYPES = {"footway", "cycleway"}
EXCLUDE_NEW  = EXCLUDE_ALL | {"track", "unclassified"}   # masqués dans couche nouvelles voies


def get_bbox():
    gdf = gpd.read_file(EMPRISE_SHP).to_crs("EPSG:4326")
    b = gdf.total_bounds  # (lonmin, latmin, lonmax, latmax)
    margin = 0.002
    return b[1] - margin, b[0] - margin, b[3] + margin, b[2] + margin


def fetch_overpass(latmin, lonmin, latmax, lonmax):
    """Récupère tout le réseau highway de la bbox, avec métadonnées (version, timestamp)."""
    bbox_str = f"{latmin:.6f},{lonmin:.6f},{latmax:.6f},{lonmax:.6f}"
    query = f"""
[out:json][timeout:180];
(
  way["highway"]({bbox_str});
);
out meta geom;
"""
    log.info(f"Overpass query (réseau complet) — bbox {bbox_str}")
    r = requests.post(OVERPASS_URL, data={"data": query}, timeout=210)
    r.raise_for_status()
    data = r.json()
    log.info(f"  {len(data.get('elements', []))} éléments reçus")
    return data


def _make_feature(el):
    coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
    if len(coords) < 2:
        return None
    tags    = el.get("tags", {})
    highway = tags.get("highway", "")
    ts      = el.get("timestamp", "")[:10]   # "2023-04-12T…" → "2023-04-12"
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            "osm_id":        el["id"],
            "name":          tags.get("name") or tags.get("ref") or None,
            "highway":       highway,
            "highway_label": HIGHWAY_LABEL.get(highway, highway),
            "timestamp":     ts,
            "surface":       tags.get("surface") or None,
            "maxspeed":      tags.get("maxspeed") or None,
        },
    }


def split_geojson(data):
    """
    Sépare les éléments en quatre catégories :
      - voirie_new  : version=1 + timestamp >= DATE_MIN, types voirie (hors piéton)
      - pieton_new  : version=1 + timestamp >= DATE_MIN, types piéton/vélo
      - voirie_old  : tout le reste (réseau existant avant 2020)
      - construction: highway=construction (en cours de travaux, toutes dates)
    """
    voirie_new, pieton_new, voirie_old, construction = [], [], [], []

    for el in data.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        tags    = el.get("tags", {})
        highway = tags.get("highway", "")

        # ── Voies en construction (tag explicite OSM) ─────────────────────────
        if highway == "construction":
            coords = [[pt["lon"], pt["lat"]] for pt in el["geometry"]]
            if len(coords) < 2:
                continue
            # construction=residential/tertiary/... indique le type futur
            type_futur = tags.get("construction", "")
            ts = el.get("timestamp", "")[:10]
            construction.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "osm_id":        el["id"],
                    "name":          tags.get("name") or tags.get("ref") or None,
                    "type_futur":    type_futur,
                    "type_label":    CONSTRUCTION_LABEL.get(type_futur, type_futur or "Voirie"),
                    "timestamp":     ts,
                    "surface":       tags.get("surface") or None,
                },
            })
            continue

        if highway in EXCLUDE_ALL:
            continue

        feat = _make_feature(el)
        if feat is None:
            continue

        is_new = (el.get("version", 0) == 1 and
                  el.get("timestamp", "")[:10] >= DATE_MIN)

        if is_new:
            if highway in PIETON_TYPES:
                pieton_new.append(feat)
            elif highway not in EXCLUDE_NEW:
                voirie_new.append(feat)
        else:
            if highway not in PIETON_TYPES:
                voirie_old.append(feat)

    return (
        {"type": "FeatureCollection", "features": voirie_new},
        {"type": "FeatureCollection", "features": pieton_new},
        {"type": "FeatureCollection", "features": voirie_old},
        {"type": "FeatureCollection", "features": construction},
    )


if __name__ == "__main__":
    latmin, lonmin, latmax, lonmax = get_bbox()
    data = fetch_overpass(latmin, lonmin, latmax, lonmax)

    geojson_voirie, geojson_pieton, geojson_old, geojson_constr = split_geojson(data)

    log.info(f"Nouvelles voies (voirie) : {len(geojson_voirie['features'])}")
    log.info(f"Nouvelles voies (piéton) : {len(geojson_pieton['features'])}")
    log.info(f"Réseau existant          : {len(geojson_old['features'])}")
    log.info(f"Voies en construction    : {len(geojson_constr['features'])}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(geojson_voirie, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_FILE_PIETON.write_text(
        json.dumps(geojson_pieton, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_FILE_OLD.write_text(
        json.dumps(geojson_old, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_FILE_CONSTR.write_text(
        json.dumps(geojson_constr, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Exporté : {OUT_FILE}")
    log.info(f"Exporté : {OUT_FILE_PIETON}")
    log.info(f"Exporté : {OUT_FILE_OLD}")
    log.info(f"Exporté : {OUT_FILE_CONSTR}")
