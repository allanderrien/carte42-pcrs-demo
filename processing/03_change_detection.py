"""
03_change_detection.py — Polygonisation du masque de changement Sentinel-2
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pipeline :
  1. Charge le masque ΔNDVI (float32) produit par 02_ndvi_timeseries.py
  2. Seuillage : pixels < 0 → changement détecté
  3. Nettoyage morphologique
  4. Polygonisation → filtres géométriques (surface, compacité)
  5. Export GeoJSON WGS84

Usage :
  python processing/03_change_detection.py
"""

import sys
import math
import logging
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes as rasterio_shapes
from shapely.geometry import shape
from shapely.ops import transform as shp_transform
from skimage.morphology import binary_opening, binary_closing, disk
import geopandas as gpd
from tqdm import tqdm
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

_WGS84_TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("03_detection")


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline():
    if not config.S2_CHANGE.exists():
        log.error(f"Masque de changement introuvable : {config.S2_CHANGE}")
        log.error("Lancez d'abord l'étape 2 (02_ndvi_timeseries.py)")
        return False

    log.info(f"Chargement masque : {config.S2_CHANGE}")

    with rasterio.open(config.S2_CHANGE) as src:
        change_mask = src.read(1).astype(np.float32)
        transform   = src.transform
        crs         = src.crs.to_string()

    log.info(f"Grille : {change_mask.shape[1]}×{change_mask.shape[0]} px "
             f"(résolution ~{abs(transform.a):.0f}m)")

    # Seuillage : toute valeur positive = changement détecté
    masque = (change_mask > 0).astype(bool)
    n_avant = int(masque.sum())
    log.info(f"Pixels changement bruts : {n_avant}")

    # Nettoyage morphologique (rayon adapté à 10m/px)
    element = disk(config.MORPH_KERNEL_RADIUS)
    masque  = binary_closing(
        binary_opening(masque, element), element
    ).astype(np.uint8)

    # Polygonisation
    features = []
    for geom_dict, val in rasterio_shapes(masque, transform=transform):
        if val != 1:
            continue

        geom     = shape(geom_dict)
        geom_l93 = shp_transform(_WGS84_TO_L93.transform, geom)
        surface  = geom_l93.area
        if surface < config.S2_SURFACE_MIN_M2:
            continue

        perimetre = geom_l93.length
        compacite = (4 * math.pi * surface / perimetre ** 2) if perimetre > 0 else 0
        if compacite < config.S2_COMPACITE_MIN:
            continue

        # ΔNDVI moyen dans le polygone (approximation via bbox)
        from rasterio.features import geometry_mask
        from shapely.geometry import mapping
        msk       = geometry_mask([mapping(geom)], transform=transform,
                                  invert=True, out_shape=change_mask.shape)
        delta_moy = float(np.mean(change_mask[msk]))

        features.append({
            "geometry":   geom,
            "surface_m2": round(surface, 0),
            "delta_ndvi": round(delta_moy, 3),
            "classe":     "construction",
        })

    log.info(f"Polygones après filtres : {len(features)} "
             f"(surface > {config.S2_SURFACE_MIN_M2}m², compacité > {config.S2_COMPACITE_MIN})")

    if features:
        gdf = gpd.GeoDataFrame(features, crs=crs)
    else:
        log.warning("Aucun changement détecté après filtrage.")
        gdf = gpd.GeoDataFrame(
            columns=["geometry", "surface_m2", "delta_ndvi", "classe"],
            crs="EPSG:4326",
        )

    # Export GeoJSON
    config.VECTORS_OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(config.GEOJSON_CHANGEMENTS, driver="GeoJSON")

    # Rapport
    surf_ha   = gdf["surface_m2"].sum() / 1e4 if len(gdf) else 0
    delta_moy = gdf["delta_ndvi"].mean()       if len(gdf) else 0

    log.info("=" * 60)
    log.info("RAPPORT DE DÉTECTION (Sentinel-2 ΔNDVI série temporelle)")
    log.info("=" * 60)
    log.info(f"Baseline         : {config.S2_BASELINE_ANNEE}")
    log.info(f"Détection        : {config.S2_DETECT_ANNEE}")
    log.info(f"Fenêtre saison   : mois {config.S2_SAISON_DEBUT} → {config.S2_SAISON_FIN}")
    log.info(f"Seuil ΔNDVI      : {config.S2_SEUIL_DELTA}")
    log.info(f"Polygones        : {len(gdf)}")
    log.info(f"Surface totale   : {surf_ha:.2f} ha")
    log.info(f"ΔNDVI moyen      : {delta_moy:.3f}")
    log.info(f"GeoJSON exporté  : {config.GEOJSON_CHANGEMENTS}")
    log.info("=" * 60)

    return True


if __name__ == "__main__":
    log.info("Script 03 — Polygonisation masque changement Sentinel-2")
    sys.exit(0 if pipeline() else 1)
