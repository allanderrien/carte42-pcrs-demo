"""
geocode_autres_permis.py — Géocode permis de démolir + locaux non résidentiels
sur les communes de la zone d'étude.

Usage :
  python processing/geocode_autres_permis.py
"""

import csv, json, time, logging
from pathlib import Path
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("geocode_autres")

DATA_DIR = Path(__file__).parent.parent / "data/registre_permis_amenager"
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

DEST_LABEL = {
    "1": "Exploitation agricole", "2": "Artisanat/industrie",
    "3": "Bureau", "4": "Commerce", "5": "Hébergement hôtelier",
    "6": "Entrepôt", "7": "Service public", "8": "Autre",
}


def geocoder(query):
    try:
        r = requests.get(API_URL, params={"q": query, "limit": 1}, timeout=10)
        r.raise_for_status()
        feats = r.json().get("features", [])
        if feats:
            return feats[0]["geometry"]["coordinates"], feats[0]["properties"].get("score", 0)
    except Exception as e:
        log.warning(f"  Timeout/erreur : {e}")
    return None, 0


def adresse_query(row, idx, commune, cp):
    parts = [row.get(h, "") for h in ("ADR_NUM_TER","ADR_TYPEVOIE_TER","ADR_LIBVOIE_TER","ADR_LIEUDIT_TER")]
    adresse = " ".join(p for p in parts if p).strip()
    if not adresse:
        adresse = commune
    return adresse, f"{adresse} {commune} {cp}".strip()


def lire_csv(fname):
    with open(DATA_DIR / fname, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)
        headers = next(reader)
        idx = {h: i for i, h in enumerate(headers)}
        rows = [{h: row[i] for h, i in idx.items()} for row in reader]
    return rows, idx


# ── Permis de démolir ─────────────────────────────────────────────────────────

def geocode_demolir():
    rows, _ = lire_csv("Liste-des-permis-de-demolir.2026-02.csv")
    rows = [r for r in rows if r["COMM"] in COMMUNES and r["ETAT_PD"] == "2"]
    log.info(f"Permis démolir : {len(rows)} à géocoder")

    features = []
    for r in rows:
        commune = COMMUNES[r["COMM"]]
        cp = r.get("ADR_CODPOST_TER", "")
        adresse, query = adresse_query(r, {}, commune, cp)
        coords, score = geocoder(query)
        if coords:
            log.info(f"  {r['NUM_PD']} | {query[:45]} → score {score:.2f}")
        else:
            log.warning(f"  {r['NUM_PD']} | non trouvé : {query[:45]}")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords} if coords else None,
            "properties": {
                "num":      r.get("NUM_PD"),
                "commune":  commune,
                "etat":     int(r.get("ETAT_PD", 0)),
                "etat_label": ETAT_LABEL.get(r.get("ETAT_PD",""), "Inconnu"),
                "date_aut": r.get("DATE_REELLE_AUTORISATION") or None,
                "adresse":  adresse or None,
                "an_depot": int(r["AN_DEPOT"]) if r.get("AN_DEPOT") else None,
                "score_geo": round(score, 3),
            },
        })
        time.sleep(0.1)

    ok = [f for f in features if f["geometry"]]
    log.info(f"  Géocodés : {len(ok)}/{len(features)}")
    out = DATA_DIR / "permis_demolir.geojson"
    out.write_text(json.dumps({"type":"FeatureCollection","features":ok}, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  Exporté : {out}")


# ── Locaux non résidentiels ───────────────────────────────────────────────────

def geocode_non_resid():
    rows, _ = lire_csv("Liste-des-autorisations-durbanisme-creant-des-locaux-non-residentiels.2026-02.csv")
    rows = [r for r in rows if r["COMM"] in COMMUNES
            and r["ETAT_DAU"] in ("2","4") and r.get("AN_DEPOT","") >= "2019"]
    log.info(f"Locaux non résidentiels : {len(rows)} à géocoder")

    features = []
    for r in rows:
        commune = COMMUNES[r["COMM"]]
        cp = r.get("ADR_CODPOST_TER","")
        adresse, query = adresse_query(r, {}, commune, cp)
        coords, score = geocoder(query)
        surf = r.get("SURF_LOC_CREEE","")
        if coords:
            log.info(f"  {r['NUM_DAU']} | {query[:45]} → score {score:.2f} | {surf}m²")
        else:
            log.warning(f"  {r['NUM_DAU']} | non trouvé : {query[:45]}")
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords} if coords else None,
            "properties": {
                "num":         r.get("NUM_DAU"),
                "commune":     commune,
                "etat":        int(r.get("ETAT_DAU", 0)),
                "etat_label":  ETAT_LABEL.get(r.get("ETAT_DAU",""), "Inconnu"),
                "date_aut":    r.get("DATE_REELLE_AUTORISATION") or None,
                "adresse":     adresse or None,
                "an_depot":    int(r["AN_DEPOT"]) if r.get("AN_DEPOT") else None,
                "destination": DEST_LABEL.get(r.get("DESTINATION_PRINCIPALE",""), r.get("DESTINATION_PRINCIPALE","")),
                "surf_creee":  int(surf) if surf else None,
                "score_geo":   round(score, 3),
            },
        })
        time.sleep(0.1)

    ok = [f for f in features if f["geometry"]]
    log.info(f"  Géocodés : {len(ok)}/{len(features)}")
    out = DATA_DIR / "locaux_non_resid.geojson"
    out.write_text(json.dumps({"type":"FeatureCollection","features":ok}, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"  Exporté : {out}")


if __name__ == "__main__":
    geocode_demolir()
    geocode_non_resid()
    log.info("Terminé.")
