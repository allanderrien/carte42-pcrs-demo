"""
03_change_detection.py — Détection de changement, tuile par tuile
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pipeline :
  1. Échantillonnage des tuiles d'amplitude → seuil d'Otsu global
  2. Pour chaque tuile : seuillage, nettoyage morphologique, polygonisation
  3. Fusion de tous les polygones → GeoJSON WGS84

Le seuil Otsu est calculé globalement (sur un échantillon de toutes les tuiles)
pour être représentatif de l'ensemble du territoire, pas d'une seule tuile.

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
from skimage.filters import threshold_otsu
from skimage.morphology import binary_opening, binary_closing, disk
import geopandas as gpd
from tqdm import tqdm
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import os

_WGS84_TO_L93 = Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
_L93_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

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

def calculer_seuil_global(tuiles_amp: list[Path]) -> float:
    """
    Échantillonne toutes les tuiles d'amplitude pour calculer un seuil d'Otsu global.

    5 000 pixels par tuile suffisent pour un histogramme stable.
    Le seuil final est le max(Otsu, config.SEUIL_DIFFERENCE).
    """
    log.info("Calcul du seuil Otsu global (échantillonnage des tuiles)…")
    rng    = np.random.default_rng(42)
    sample = []

    for tuile in tuiles_amp:
        with rasterio.open(tuile) as src:
            data = src.read(1).ravel()
        idx = rng.choice(len(data), min(5_000, len(data)), replace=False)
        sample.append(data[idx])

    all_vals   = np.concatenate(sample).astype(np.float32)
    seuil_otsu = float(threshold_otsu(all_vals))
    seuil      = max(seuil_otsu, float(config.SEUIL_DIFFERENCE))

    log.info(f"Otsu={seuil_otsu:.1f}, config={config.SEUIL_DIFFERENCE}, seuil appliqué={seuil:.1f}")
    return seuil


def traiter_tuile(chemin_amp: Path, seuil: float, element) -> tuple[list, str]:
    """
    Charge une tuile d'amplitude, seuille, nettoie et polygonise.

    Retourne (liste de dicts feature, crs_string).
    """
    with rasterio.open(chemin_amp) as src:
        amp       = src.read(1)
        transform = src.transform
        crs       = src.crs.to_string()

    masque = binary_closing(
        binary_opening(amp >= seuil, element), element
    ).astype(np.uint8)

    features = []
    for geom_dict, val in rasterio_shapes(masque, transform=transform):
        if val != 1:
            continue

        geom     = shape(geom_dict)
        geom_l93 = shp_transform(_WGS84_TO_L93.transform, geom)
        surface  = geom_l93.area      # m² en Lambert 93
        if surface < config.SURFACE_MIN_M2:
            continue

        # Filtre compacité : élimine les formes très allongées (ombres portées)
        perimetre  = geom_l93.length
        compacite  = (4 * math.pi * surface / perimetre ** 2) if perimetre > 0 else 0
        if compacite < config.COMPACITE_MIN:
            continue

        msk    = geometry_mask([mapping(geom)], transform=transform, invert=True, out_shape=amp.shape)
        pixels = amp[msk]
        if len(pixels) == 0:
            continue

        ampl_moy = float(pixels.mean())
        ampl_max = float(pixels.max())
        classe   = "fort" if ampl_moy >= config.SEUIL_DIFFERENCE * 1.5 else "modere"

        features.append({
            "geometry":   geom,           # WGS84 — pour GeoJSON direct
            "surface_m2": round(surface, 1),  # m² calculé en L93
            "ampl_moy":   round(ampl_moy, 2),
            "ampl_max":   round(ampl_max, 2),
            "classe":     classe,
        })

    return features, crs


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline() -> bool:
    tuiles_amp = sorted(config.TILES_AMP_DIR.glob("amp_*.tif"))
    if not tuiles_amp:
        log.error(f"Aucune tuile d'amplitude dans {config.TILES_AMP_DIR} → lancez d'abord l'étape 2")
        return False

    test_bbox = get_test_bbox()
    if test_bbox:
        tuiles_amp = [t for t in tuiles_amp if tuile_dans_bbox(t, test_bbox)]
        log.info(f"Zone de test active : {len(tuiles_amp)} tuile(s) sélectionnée(s)")
    else:
        log.info(f"{len(tuiles_amp)} tuiles d'amplitude à traiter")

    # --- Seuil global ---
    seuil   = calculer_seuil_global(tuiles_amp)
    element = disk(config.MORPH_KERNEL_RADIUS)

    # --- Détection par tuile ---
    all_features = []
    crs_ref      = None
    erreurs      = 0

    for tuile in tqdm(tuiles_amp, desc="Détection", unit="tuile"):
        try:
            feats, crs = traiter_tuile(tuile, seuil, element)
            if feats:
                all_features.extend(feats)
                if crs_ref is None:
                    crs_ref = crs
        except Exception as e:
            log.warning(f"Tuile {tuile.name} ignorée : {e}")
            erreurs += 1

    log.info(f"Polygones bruts : {len(all_features)} ({erreurs} tuile(s) en erreur)")

    # --- Assemblage GeoDataFrame ---
    if all_features:
        gdf = gpd.GeoDataFrame(all_features, crs=crs_ref or "EPSG:2154")
    else:
        log.warning("Aucun changement détecté sur l'ensemble des tuiles.")
        gdf = gpd.GeoDataFrame(
            columns=["geometry", "surface_m2", "ampl_moy", "ampl_max", "classe"],
            crs="EPSG:2154",
        )

    # --- Export GeoJSON (WGS84 — tuiles déjà en EPSG:4326) ---
    config.VECTORS_OUT.mkdir(parents=True, exist_ok=True)
    gdf.to_file(config.GEOJSON_CHANGEMENTS, driver="GeoJSON")

    # --- Rapport ---
    n_fort   = int((gdf["classe"] == "fort").sum())   if len(gdf) else 0
    n_modere = int((gdf["classe"] == "modere").sum()) if len(gdf) else 0
    surf_ha  = gdf["surface_m2"].sum() / 1e4          if len(gdf) else 0

    log.info("=" * 60)
    log.info("RAPPORT DE DÉTECTION")
    log.info("=" * 60)
    log.info(f"Millésimes comparés  : {config.MILLESIME_ANCIEN} → {config.MILLESIME_RECENT}")
    log.info(f"Seuil appliqué       : {seuil:.1f}")
    log.info(f"Polygones détectés   : {len(gdf)}")
    log.info(f"  dont forts         : {n_fort}")
    log.info(f"  dont modérés       : {n_modere}")
    log.info(f"Surface totale       : {surf_ha:.2f} ha")
    if len(gdf) > 0:
        log.info(f"Plus grande zone     : {gdf['surface_m2'].max() / 1e4:.2f} ha")
        log.info(f"Amplitude moy. moy.  : {gdf['ampl_moy'].mean():.1f}")
    log.info(f"GeoJSON exporté      : {config.GEOJSON_CHANGEMENTS}")
    log.info("=" * 60)

    emprise_m2  = ((config.BBOX_L93["xmax"] - config.BBOX_L93["xmin"])
                   * (config.BBOX_L93["ymax"] - config.BBOX_L93["ymin"]))
    pct_emprise = surf_ha * 1e4 / emprise_m2 * 100
    if pct_emprise > config.SEUIL_ALERTE_PCT:
        log.warning(f"ALERTE : {pct_emprise:.1f}% de l'emprise a changé "
                    f"(seuil alerte = {config.SEUIL_ALERTE_PCT}%)")

    return True


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 03 — Détection de changement tuile par tuile")
    sys.exit(0 if pipeline() else 1)
