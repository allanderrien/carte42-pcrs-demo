"""
geocode_pc_logements.py — Géocode les permis de construire créant des logements
(autorisés ou achevés, 2019+) sur les communes de la zone d'étude.

Usage :
  python processing/geocode_pc_logements.py
"""

import csv
import json
import time
import logging
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("geocode_pc")

CSV_PATH = Path(__file__).parent.parent / "data/registre_permis_amenager/Liste-des-autorisations-durbanisme-creant-des-logements.2026-02.csv"
OUT_PATH = Path(__file__).parent.parent / "data/registre_permis_amenager/pc_logements.geojson"
API_URL  = "https://api-adresse.data.gouv.fr/search/"

COMMUNES = {
    "35069": "Châteaugiron",
    "35039": "Brecé",
    "35099": "Domloup",
    "35204": "Nouvoitou",
    "35207": "Noyal-sur-Vilaine",
    "35327": "Servon-sur-Vilaine",
}

ETAT_LABEL = {
    "2": "Autorisé", "3": "Chantier ouvert",
    "4": "Achèvement déclaré", "5": "Périmé", "6": "Retiré",
}

ANNEE_MIN = "2019"


def lire_permis():
    with open(CSV_PATH, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        headers = next(reader)
        idx = {h: i for i, h in enumerate(headers)}
        rows = [
            {h: row[i] for h, i in idx.items()}
            for row in reader
            if row[idx["COMM"]] in COMMUNES
            and row[idx["ETAT_DAU"]] in ("2", "4")
            and row[idx["AN_DEPOT"]] >= ANNEE_MIN
        ]
    return rows


def geocoder(query):
    try:
        r = requests.get(API_URL, params={"q": query, "limit": 1}, timeout=10)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if feats:
            return feats[0]["geometry"]["coordinates"], feats[0]["properties"].get("score", 0)
    except Exception as e:
        log.warning(f"  Erreur : {e}")
    return None, 0


def main():
    rows = lire_permis()
    log.info(f"{len(rows)} permis de construire à géocoder (actifs, {ANNEE_MIN}+)")

    features = []
    for r in rows:
        parts = [r.get("ADR_NUM_TER",""), r.get("ADR_TYPEVOIE_TER",""),
                 r.get("ADR_LIBVOIE_TER",""), r.get("ADR_LIEUDIT_TER","")]
        adresse = " ".join(p for p in parts if p).strip()
        commune = COMMUNES.get(r["COMM"], r.get("ADR_LOCALITE_TER",""))
        cp      = r.get("ADR_CODPOST_TER","")
        if not adresse:
            adresse = commune
        query = f"{adresse} {commune} {cp}".strip()

        coords, score = geocoder(query)

        nb_lgt = r.get("NB_LGT_TOT_CREES","")
        if coords:
            log.info(f"  {r['NUM_DAU']} | {query[:45]} → score {score:.2f} | {nb_lgt} lgts")
        else:
            log.warning(f"  {r['NUM_DAU']} | non trouvé : {query[:45]}")

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords} if coords else None,
            "properties": {
                "num_dau":    r.get("NUM_DAU"),
                "type_dau":   r.get("TYPE_DAU"),
                "commune":    commune,
                "etat":       int(r.get("ETAT_DAU", 0)),
                "etat_label": ETAT_LABEL.get(r.get("ETAT_DAU",""), "Inconnu"),
                "date_aut":   r.get("DATE_REELLE_AUTORISATION") or None,
                "adresse":    adresse or None,
                "an_depot":   int(r["AN_DEPOT"]) if r.get("AN_DEPOT") else None,
                "nb_logements": int(nb_lgt) if nb_lgt else None,
                "nb_indiv":   int(r["NB_LGT_IND_CREES"]) if r.get("NB_LGT_IND_CREES") else None,
                "nb_collec":  int(r["NB_LGT_COL_CREES"]) if r.get("NB_LGT_COL_CREES") else None,
                "score_geo":  round(score, 3),
            },
        })
        time.sleep(0.1)

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
