"""Construit le manifeste des rapports PDF pour l'interface en ligne.

Apparie les communes presentes dans le livrable PCRS (noms accentues) aux
fichiers PDF de rapport (noms desaccentues, separateurs _ et - melanges) via
une normalisation "accent-folding", puis groupe par EPCI.

Sortie : demo/public/data/rapports_manifest.json
  {
    "base_path_hint": "<epci_slug>/<fichier.pdf>",
    "epci": [
      { "slug": "...", "label": "...",
        "communes": [ { "label": "Bréal-sous-Vitré", "file": "17_.../Rapport_PCRS_Breal-sous-Vitre.pdf" } ] }
    ]
  }

Les PDF eux-memes ne sont PAS copies (1,5 Go) : ils sont heberges en externe,
l'UI prefixe `file` par RAPPORTS_BASE_URL (voir demo/src/config.js).

Usage :
  python processing/build_rapports_manifest.py [PROD_LIVRAISON_DIR]
"""
import json
import os
import sys
import glob
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DEFAULT_PROD = os.path.normpath(
    os.path.join(REPO, "..", "carte42-pcrs-prod", "4. Livraison")
)
OUT = os.path.join(REPO, "demo", "public", "data", "rapports_manifest.json")

SMALL_WORDS = {"de", "du", "des", "d", "la", "le", "les", "aux", "en", "sur", "et"}

# Libelles EPCI propres (accents) — sinon derives du slug (sans accents)
EPCI_LABELS = {
    "01_bretagne-porte-de-loire": "Bretagne Porte de Loire",
    "02_bretagne-romantique": "Bretagne romantique",
    "03_cote-d-emeraude": "Côte d'Émeraude",
    "04_couesnon-marches-de-bretagne": "Couesnon Marches de Bretagne",
    "05_fougeres-agglomeration": "Fougères Agglomération",
    "06_liffre-cormier": "Liffré-Cormier Communauté",
    "07_montfort-communaute": "Montfort Communauté",
    "08_pays-de-broceliande": "Pays de Brocéliande",
    "09_pays-de-chateaugiron": "Pays de Châteaugiron",
    "10_pays-de-dol": "Pays de Dol",
    "11_pays-de-redon": "Pays de Redon",
    "12_roche-aux-fees": "Roche aux Fées",
    "13_saint-malo-agglomeration": "Saint-Malo Agglomération",
    "14_saint-meen-montauban": "Saint-Méen Montauban",
    "15_val-d-ille-aubigne": "Val d'Ille-Aubigné",
    "16_vallons-de-haute-bretagne": "Vallons de Haute Bretagne",
    "17_vitre-communaute": "Vitré Communauté",
}


def fold(s):
    """Clef de comparaison compacte : sans accents, minuscules, alphanum colle.

    Compacte (sans espaces) pour absorber les divergences de separateurs et
    d'apostrophes entre donnees et noms de fichiers :
    "Mesnil-Roc'h" -> "mesnilroch" == "Mesnil-Roch" -> "mesnilroch".
    """
    if not s:
        return ""
    s = s.replace("œ", "oe").replace("æ", "ae")  # œ, æ
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s.lower())


def epci_label(slug):
    """01_bretagne-porte-de-loire -> Bretagne Porte de Loire."""
    if slug in EPCI_LABELS:
        return EPCI_LABELS[slug]
    body = re.sub(r"^\d+_", "", slug)
    words = body.split("-")
    out = []
    for i, w in enumerate(words):
        out.append(w if (w in SMALL_WORDS and i > 0) else w.capitalize())
    return " ".join(out)


def main():
    prod = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PROD
    livrable = os.path.join(prod, "livrable_pcrs_SDE35_complet.geojson")
    rapports_dir = os.path.join(prod, "rapports")

    if not os.path.isfile(livrable):
        sys.exit(f"Livrable introuvable : {livrable}")

    # 1. Communes (par EPCI) presentes dans les donnees
    data = json.load(open(livrable, encoding="utf-8"))
    by_epci = {}  # slug -> { folded_commune -> display_label }
    for feat in data["features"]:
        p = feat["properties"]
        slug = p.get("epci_slug")
        commune = p.get("commune")
        if not slug or not commune:
            continue
        by_epci.setdefault(slug, {}).setdefault(fold(commune), commune)

    # 2. Index des PDF : par EPCI + global (repli inter-EPCI car quelques
    #    communes ont leur rapport classe sous un autre EPCI que les donnees)
    pdf_index = {}   # slug -> { folded_commune -> "slug/fichier.pdf" }
    pdf_global = {}  # folded_commune -> "slug/fichier.pdf"
    for path in glob.glob(os.path.join(rapports_dir, "*", "*.pdf")):
        slug = os.path.basename(os.path.dirname(path))
        fn = os.path.basename(path)
        commune_part = re.sub(r"^Rapport_PCRS_", "", fn)
        commune_part = re.sub(r"\.pdf$", "", commune_part, flags=re.I)
        key = fold(commune_part)
        pdf_index.setdefault(slug, {})[key] = f"{slug}/{fn}"
        pdf_global[key] = f"{slug}/{fn}"

    # 3. Appariement : EPCI d'abord, puis repli global
    manifest_epci = []
    unmatched = []
    for slug in sorted(by_epci):
        communes = []
        for folded, label in sorted(by_epci[slug].items(), key=lambda kv: kv[1]):
            rel = pdf_index.get(slug, {}).get(folded) or pdf_global.get(folded)
            if rel is None:
                unmatched.append((slug, label))
                continue
            communes.append({"label": label, "file": rel})
        if communes:
            manifest_epci.append(
                {"slug": slug, "label": epci_label(slug), "communes": communes}
            )

    manifest = {
        "base_path_hint": "<epci_slug>/<fichier.pdf>",
        "epci": manifest_epci,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    total = sum(len(e["communes"]) for e in manifest_epci)
    print(f"EPCI : {len(manifest_epci)} | communes appariees : {total}")
    print(f"Manifeste ecrit : {OUT}")
    if unmatched:
        print(f"\n[!] {len(unmatched)} commune(s) sans PDF :")
        for slug, label in unmatched:
            print(f"    {slug} : {label}")


if __name__ == "__main__":
    main()
