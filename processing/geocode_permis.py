"""
geocode_permis.py — Géocode les permis d'aménager de Châteaugiron
via l'API adresse.data.gouv.fr et exporte un GeoJSON de points.

Usage :
  python processing/geocode_permis.py
"""

import csv
import json
import time
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("geocode_permis")

CSV_PATH  = Path(__file__).parent.parent / "data/registre_permis_amenager/Liste-des-permis-damenager.2026-02.csv"
OUT_PATH  = Path(__file__).parent.parent / "data/registre_permis_amenager/permis_chateaugiron.geojson"
API_URL   = "https://api-adresse.data.gouv.fr/search/"

COMMUNES = {
    "35069": "Châteaugiron",
    "35039": "Brecé",
    "35099": "Domloup",
    "35204": "Nouvoitou",
    "35207": "Noyal-sur-Vilaine",
    "35327": "Servon-sur-Vilaine",
}

ETAT_LABEL = {
    "1": "En cours d'instruction",
    "2": "Autorisé",
    "3": "Chantier ouvert",
    "4": "Achèvement déclaré",
    "5": "Périmé",
    "6": "Retiré",
}


def lire_permis():
    rows = []
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)          # ligne 1 : libellés longs
        headers = next(reader)  # ligne 2 : codes
        idx = {h: i for i, h in enumerate(headers)}
        for row in reader:
            if row[idx["COMM"]] in COMMUNES:
                rows.append({h: row[i] for h, i in idx.items()})
    return rows


def geocoder(adresse_str):
    """Appelle l'API BAN et retourne (lon, lat) ou None."""
    try:
        r = requests.get(API_URL, params={"q": adresse_str, "limit": 1}, timeout=10)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if feats:
            coords = feats[0]["geometry"]["coordinates"]
            score  = feats[0]["properties"].get("score", 0)
            return coords, score
    except Exception as e:
        log.warning(f"  Erreur geocodage '{adresse_str}' : {e}")
    return None, 0


def main():
    rows = lire_permis()
    noms = ", ".join(COMMUNES.values())
    log.info(f"{len(rows)} permis à géocoder ({noms})")

    features = []
    for r in rows:
        adresse_parts = [
            r.get("ADR_NUM_TER", ""),
            r.get("ADR_TYPEVOIE_TER", ""),
            r.get("ADR_LIBVOIE_TER", ""),
            r.get("ADR_LIEUDIT_TER", ""),
        ]
        adresse = " ".join(p for p in adresse_parts if p).strip()
        commune_nom = COMMUNES.get(r.get("COMM", ""), r.get("ADR_LOCALITE_TER", ""))
        cp = r.get("ADR_CODPOST_TER", "")
        if not adresse:
            adresse = commune_nom  # fallback centre commune

        query = f"{adresse} {commune_nom} {cp}".strip()
        coords, score = geocoder(query)

        if coords:
            log.info(f"  {r['NUM_PA']} | {query[:50]} → {coords} (score {score:.2f})")
        else:
            log.warning(f"  {r['NUM_PA']} | non trouvé : {query}")

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords} if coords else None,
            "properties": {
                "num_pa":       r.get("NUM_PA"),
                "commune":      COMMUNES.get(r.get("COMM", ""), r.get("ADR_LOCALITE_TER", "")),
                "etat":         int(r.get("ETAT_PA", 0)),
                "etat_label":   ETAT_LABEL.get(r.get("ETAT_PA", ""), "Inconnu"),
                "date_aut":     r.get("DATE_REELLE_AUTORISATION") or None,
                "date_doc":     r.get("DATE_REELLE_DOC") or None,
                "adresse":      " ".join(p for p in adresse_parts if p).strip() or None,
                "localite":     r.get("ADR_LOCALITE_TER") or None,
                "surface_m2":  int(r["SUPERFICIE_TERRAIN"]) if r.get("SUPERFICIE_TERRAIN") else None,
                "demandeur":    r.get("DENOM_DEM") or None,
                "score_geo":    round(score, 3),
            },
        })
        time.sleep(0.1)  # politesse API

    # Filtre les features sans géométrie
    ok  = [f for f in features if f["geometry"]]
    nok = [f for f in features if not f["geometry"]]
    log.info(f"Géocodés : {len(ok)} / {len(features)} ({len(nok)} échecs)")

    geojson = {"type": "FeatureCollection", "features": ok}
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(geojson, f, ensure_ascii=False, indent=2)
    log.info(f"Exporté : {OUT_PATH}")


if __name__ == "__main__":
    main()
