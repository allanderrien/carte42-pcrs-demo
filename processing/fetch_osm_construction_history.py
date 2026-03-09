"""
fetch_osm_construction_history.py — Récupère via Overpass adiff les voies
qui étaient en construction (highway=construction) depuis 2021 et sont
maintenant terminées.

Méthode :
  - adiff depuis 2021-01-01 sur highway=construction
  - action="delete" + visible=true = chantier terminé (n'est plus construction)
  - La géométrie et les tags sont ceux de l'état "en construction" (<old>)
  - La date de complétion est le timestamp de la version finale (<new>)

Usage :
  python processing/fetch_osm_construction_history.py
"""

import json, logging
from pathlib import Path
from xml.etree import ElementTree as ET

import requests
import geopandas as gpd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("osm_constr_history")

PROJECT_ROOT = Path(__file__).parent.parent
EMPRISE_SHP  = PROJECT_ROOT / "data/emprise/emprise_zone.shp"
OUT_DIR      = PROJECT_ROOT / "data/osm"
OUT_FILE     = OUT_DIR / "chantiers_termines_osm.geojson"

OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
DATE_DEBUT = "2021-01-01T00:00:00Z"

CONSTRUCTION_LABEL = {
    "motorway": "Autoroute", "trunk": "Route nationale",
    "primary": "Route principale", "secondary": "Route secondaire",
    "tertiary": "Route tertiaire", "residential": "Voie résidentielle",
    "unclassified": "Voie non classée", "service": "Voie de service",
    "living_street": "Zone de rencontre", "track": "Chemin",
    "footway": "Trottoir", "cycleway": "Piste cyclable",
}


def get_bbox():
    gdf = gpd.read_file(EMPRISE_SHP).to_crs("EPSG:4326")
    b = gdf.total_bounds
    margin = 0.002
    return b[1] - margin, b[0] - margin, b[3] + margin, b[2] + margin


def fetch_adiff(latmin, lonmin, latmax, lonmax):
    import time
    bbox_str = f"{latmin:.6f},{lonmin:.6f},{latmax:.6f},{lonmax:.6f}"
    query = (
        f'[timeout:60][adiff:"{DATE_DEBUT}"];'
        f'(way["highway"="construction"]({bbox_str}););'
        f'out meta geom;'
    )
    log.info(f"Overpass adiff depuis {DATE_DEBUT} — bbox {bbox_str}")
    # overpass-api.de a la base historique (attic) — on l'essaie en priorité,
    # plusieurs fois avec des pauses croissantes car la requête adiff est lourde
    servers_order = [OVERPASS_SERVERS[0]] * 5 + [OVERPASS_SERVERS[1]] * 2
    for attempt, url in enumerate(servers_order):
        try:
            r = requests.post(url, data={"data": query}, timeout=90)
            if r.status_code == 200 and r.text.strip().startswith("<?xml"):
                log.info(f"  Réponse OK ({url})")
                return r.text
            log.warning(f"  {url} → {r.status_code}, retry dans 20s…")
        except Exception as e:
            log.warning(f"  {url} → {e}, retry dans 20s…")
        time.sleep(20)
    raise RuntimeError("Tous les serveurs Overpass ont échoué")


def parse_adiff_xml(xml_text):
    """
    Parse le XML adiff Overpass.
    Retourne une liste de features GeoJSON pour les chantiers terminés.

    Structure XML :
      <action type="delete">       ← n'est plus highway=construction
        <old>                      ← état "en construction" (avec géométrie)
          <way id="..." version="..." timestamp="...">
            <nd ref="..." lat="..." lon="..."/>
            <tag k="construction" v="residential"/>
          </way>
        </old>
        <new>                      ← état actuel
          <way id="..." visible="true" version="..." timestamp="..."/>
        </new>
      </action>
    """
    root = ET.fromstring(xml_text)
    features = []

    for action in root.findall("action"):
        action_type = action.get("type")

        # On ne garde que les "delete" (n'est plus construction)
        if action_type not in ("delete", "modify"):
            continue

        old_el = action.find("old/way")
        new_el = action.find("new/way")
        if old_el is None:
            continue

        # "delete" avec visible=false = supprimé d'OSM → on ignore
        if new_el is not None and new_el.get("visible") == "false":
            continue

        # Reconstruit la géométrie depuis les <nd lat="" lon=""> de <old>
        coords = []
        for nd in old_el.findall("nd"):
            lat = nd.get("lat")
            lon = nd.get("lon")
            if lat and lon:
                coords.append([float(lon), float(lat)])

        if len(coords) < 2:
            continue

        # Tags de l'état construction
        tags = {t.get("k"): t.get("v") for t in old_el.findall("tag")}
        type_futur = tags.get("construction", "")

        # Date de complétion = timestamp de la version finale
        date_completion = None
        if new_el is not None:
            ts = new_el.get("timestamp", "")
            date_completion = ts[:10] if ts else None

        # Date de début de chantier = timestamp de <old>
        date_chantier = old_el.get("timestamp", "")[:10]

        features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "osm_id":          int(old_el.get("id", 0)),
                "action":          action_type,
                "name":            tags.get("name") or tags.get("ref") or None,
                "type_futur":      type_futur,
                "type_label":      CONSTRUCTION_LABEL.get(type_futur, type_futur or "Voirie"),
                "date_chantier":   date_chantier,
                "date_completion": date_completion,
                "surface":         tags.get("surface") or None,
            },
        })

    return {"type": "FeatureCollection", "features": features}


if __name__ == "__main__":
    latmin, lonmin, latmax, lonmax = get_bbox()
    xml_text = fetch_adiff(latmin, lonmin, latmax, lonmax)
    geojson  = parse_adiff_xml(xml_text)

    # Stats
    n_total   = len(geojson["features"])
    n_delete  = sum(1 for f in geojson["features"] if f["properties"]["action"] == "delete")
    n_modify  = sum(1 for f in geojson["features"] if f["properties"]["action"] == "modify")
    log.info(f"{n_total} chantiers trouvés : {n_delete} terminés, {n_modify} modifiés encore en cours")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(geojson, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    log.info(f"Exporté : {OUT_FILE}")
