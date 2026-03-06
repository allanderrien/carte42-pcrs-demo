"""
03_change_detection.py — Détection par comparaison post-classification (PCC)
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pipeline :
  1. Pour chaque tuile de transition (uint8, valeur = classe_T1 × 4 + classe_T2) :
     - Masque binaire des transitions d'intérêt (voirie, construction, démolition)
     - Nettoyage morphologique, polygonisation
  2. Fusion → filtres géométriques (surface, compacité)
  3. Filtre spatial emprise voies → export GeoJSON WGS84

Transitions détectées (classes 0=ombre 1=vég 2=sol_nu 3=imperm) :
   6 = 1→2 : végétation → sol nu      (terrassement, débroussaillement)
   7 = 1→3 : végétation → imperméable (construction directe)
  11 = 2→3 : sol nu → imperméable     (mise en œuvre enrobé/béton)
  13 = 3→1 : imperméable → végétation (réhabilitation, rare)
  14 = 3→2 : imperméable → sol nu     (démolition, décaissement)

Usage :
  python processing/03_change_detection.py
"""

import sys
import math
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes as rasterio_shapes, geometry_mask
from shapely.geometry import shape, mapping
from shapely.ops import transform as shp_transform
from skimage.morphology import binary_opening, binary_closing, disk
import geopandas as gpd
from tqdm import tqdm
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import os

_WGS84_TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
_L93_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

# Libellés lisibles par code de transition
LABELS_TRANSITION = {
    6:  ("veg→sol_nu",          "chantier"),
    7:  ("veg→imperméable",     "construction"),
    11: ("sol_nu→imperméable",  "construction"),
    13: ("imperméable→veg",     "demolition"),
    14: ("imperméable→sol_nu",  "demolition"),
}


def get_test_bbox():
    """Retourne le bbox de test en WGS84 (converti depuis L93), ou None."""
    try:
        xmin = float(os.environ['TEST_XMIN'])
        ymin = float(os.environ['TEST_YMIN'])
        xmax = float(os.environ['TEST_XMAX'])
        ymax = float(os.environ['TEST_YMAX'])
        lon_min, lat_min = _L93_TO_WGS84.transform(xmin, ymin)
        lon_max, lat_max = _L93_TO_WGS84.transform(xmax, ymax)
        return {'xmin': lon_min, 'ymin': lat_min, 'xmax': lon_max, 'ymax': lat_max}
    except KeyError:
        return None


def tuile_dans_bbox(chemin: Path, bbox: dict) -> bool:
    with rasterio.open(chemin) as src:
        b = src.bounds
    return not (b.right < bbox['xmin'] or b.left > bbox['xmax'] or
                b.top  < bbox['ymin'] or b.bottom > bbox['ymax'])


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("03_detection")


# =============================================================================
# FONCTIONS
# =============================================================================

def traiter_tuile(chemin_chg: Path, element) -> tuple[list, str]:
    """
    Charge une tuile de transition, extrait les pixels d'intérêt,
    nettoie morphologiquement et polygonise.
    Retourne (liste de features, crs_string).
    """
    with rasterio.open(chemin_chg) as src:
        chg       = src.read(1)
        transform = src.transform
        crs       = src.crs.to_string()

    # Masque binaire des transitions d'intérêt
    masque = np.isin(chg, config.TRANSITIONS_VOIRIE).astype(bool)

    # Nettoyage morphologique : supprime le bruit isolé et rebouche les trous
    masque = binary_closing(
        binary_opening(masque, element), element
    ).astype(np.uint8)

    features = []
    for geom_dict, val in rasterio_shapes(masque, transform=transform):
        if val != 1:
            continue

        geom     = shape(geom_dict)
        geom_l93 = shp_transform(_WGS84_TO_L93.transform, geom)
        surface  = geom_l93.area          # m² en Lambert 93
        if surface < config.SURFACE_MIN_M2:
            continue

        perimetre = geom_l93.length
        compacite = (4 * math.pi * surface / perimetre ** 2) if perimetre > 0 else 0
        if compacite < config.COMPACITE_MIN:
            continue

        # Transition dominante dans le polygone
        msk       = geometry_mask([mapping(geom)], transform=transform,
                                  invert=True, out_shape=chg.shape)
        pix       = chg[msk]
        pix_int   = pix[np.isin(pix, config.TRANSITIONS_VOIRIE)]
        if len(pix_int) == 0:
            continue

        codes, counts  = np.unique(pix_int, return_counts=True)
        code_dom       = int(codes[np.argmax(counts)])
        transition, classe = LABELS_TRANSITION.get(code_dom, ("inconnu", "chantier"))

        features.append({
            "geometry":   geom,           # WGS84
            "surface_m2": round(surface, 1),
            "transition": transition,
            "classe":     classe,
        })

    return features, crs


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline() -> bool:
    tuiles_chg = sorted(config.TILES_CHG_DIR.glob("chg_*.tif"))
    if not tuiles_chg:
        log.error(f"Aucune tuile de transition dans {config.TILES_CHG_DIR} "
                  f"→ lancez d'abord l'étape 2")
        return False

    test_bbox = get_test_bbox()
    if test_bbox:
        tuiles_chg = [t for t in tuiles_chg if tuile_dans_bbox(t, test_bbox)]
        log.info(f"Zone de test active : {len(tuiles_chg)} tuile(s) sélectionnée(s)")
    else:
        log.info(f"{len(tuiles_chg)} tuiles de transition à analyser")

    element      = disk(config.MORPH_KERNEL_RADIUS)
    all_features = []
    crs_ref      = None
    erreurs      = 0

    for tuile in tqdm(tuiles_chg, desc="Détection PCC", unit="tuile"):
        try:
            feats, crs = traiter_tuile(tuile, element)
            if feats:
                all_features.extend(feats)
                if crs_ref is None:
                    crs_ref = crs
        except Exception as e:
            log.warning(f"Tuile {tuile.name} ignorée : {e}")
            erreurs += 1

    log.info(f"Polygones bruts : {len(all_features)} ({erreurs} tuile(s) en erreur)")

    if all_features:
        gdf = gpd.GeoDataFrame(all_features, crs=crs_ref or "EPSG:4326")
    else:
        log.warning("Aucun changement détecté.")
        gdf = gpd.GeoDataFrame(
            columns=["geometry", "surface_m2", "transition", "classe"],
            crs="EPSG:4326",
        )

    # --- Filtre spatial : emprise voies ---
    if config.EMPRISE_VOIES.exists():
        log.info("Filtre spatial : emprise voies…")
        emprise = gpd.read_file(config.EMPRISE_VOIES)
        if emprise.crs is None:
            emprise = emprise.set_crs("EPSG:2154")
        emprise_union = emprise.buffer(config.BUFFER_EMPRISE_VOIES).union_all()
        gdf_l93   = gdf.to_crs("EPSG:2154")
        dans_voie = gdf_l93.geometry.intersects(emprise_union)
        n_avant   = len(gdf)
        gdf       = gdf[dans_voie.values].copy()
        log.info(f"Polygones après filtre voirie : {len(gdf)} / {n_avant}")
    else:
        log.warning(f"Emprise voies introuvable ({config.EMPRISE_VOIES}) — filtre ignoré")

    # --- Export GeoJSON (WGS84 — géométries déjà en EPSG:4326) ---
    config.VECTORS_OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(config.GEOJSON_CHANGEMENTS, driver="GeoJSON")

    # --- Rapport ---
    n_const = int((gdf["classe"] == "construction").sum()) if len(gdf) else 0
    n_demol = int((gdf["classe"] == "demolition").sum())   if len(gdf) else 0
    n_chant = int((gdf["classe"] == "chantier").sum())     if len(gdf) else 0
    surf_ha = gdf["surface_m2"].sum() / 1e4                if len(gdf) else 0

    log.info("=" * 60)
    log.info("RAPPORT DE DÉTECTION (PCC)")
    log.info("=" * 60)
    log.info(f"Millésimes comparés : {config.MILLESIME_ANCIEN} → {config.MILLESIME_RECENT}")
    log.info(f"Polygones détectés  : {len(gdf)}")
    log.info(f"  construction      : {n_const}")
    log.info(f"  démolition        : {n_demol}")
    log.info(f"  chantier          : {n_chant}")
    log.info(f"Surface totale      : {surf_ha:.2f} ha")
    log.info(f"GeoJSON exporté     : {config.GEOJSON_CHANGEMENTS}")
    log.info("=" * 60)

    return True


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 03 — Détection PCC (Post-Classification Comparison)")
    sys.exit(0 if pipeline() else 1)
