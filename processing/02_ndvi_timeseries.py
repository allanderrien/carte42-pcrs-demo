"""
02_ndvi_timeseries.py — Indices spectraux multi-dates + détection de changement
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pour chaque date dans data/raw/sentinel2/ :
  - NDVI  = (B08 - B04) / (B08 + B04)          → végétation
  - NDBI  = (B11 - B08) / (B11 + B08)          → surfaces imperméables / bâti
  - BSI   = ((B11+B04) - (B08+B02)) /
            ((B11+B04) + (B08+B02))             → sol nu / chantier
  - Masque nuage via SCL (classes valides : 4, 5, 6, 11)

Détection de changement permanent (baseline vs détection) :
  - Baseline  : médiane des dates S2_BASELINE_DEBUT → S2_BASELINE_FIN
  - Détection : médiane mensuelle S2_DETECT_DEBUT → S2_DETECT_FIN
  - Δ index   : valeur_détection − valeur_baseline
  - Flagge les pixels dont ΔIndex dépasse le seuil ≥ S2_PERSISTANCE_MOIS mois
  - Stratégie voirie : ΔNDVI < seuil ET/OU ΔNDBI > seuil_pos

Sortie : data/processed/s2_change_mask.tif

Usage :
  python processing/02_ndvi_timeseries.py
  TEST_XMIN=... TEST_YMIN=... TEST_XMAX=... TEST_YMAX=... python processing/02_ndvi_timeseries.py
"""

import os
import sys
import logging
from pathlib import Path
from collections import defaultdict

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.windows import from_bounds as window_from_bounds
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("02_timeseries")

# Classes SCL valides (non nuage, non ombre)
# 4=végétation, 5=sol nu, 6=eau, 11=neige
SCL_VALIDES = {4, 5, 6, 11}

_L93_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)


# =============================================================================
# BBOX DE TEST
# =============================================================================

def get_test_bbox():
    """Retourne le bbox de test en WGS84 (depuis env vars L93), ou None."""
    try:
        xmin = float(os.environ["TEST_XMIN"])
        ymin = float(os.environ["TEST_YMIN"])
        xmax = float(os.environ["TEST_XMAX"])
        ymax = float(os.environ["TEST_YMAX"])
        lon_min, lat_min = _L93_TO_WGS84.transform(xmin, ymin)
        lon_max, lat_max = _L93_TO_WGS84.transform(xmax, ymax)
        log.info(f"Mode test : bbox WGS84 [{lon_min:.4f},{lat_min:.4f} → {lon_max:.4f},{lat_max:.4f}]")
        return (lon_min, lat_min, lon_max, lat_max)
    except KeyError:
        return None


def lire_bande_recadree(path, ref_shape, ref_transform, ref_crs, bbox_wgs84=None):
    """
    Lit une bande raster, la rééchantillonne à ref_shape si besoin.
    Si bbox_wgs84 fourni, découpe à cette fenêtre.
    Retourne un tableau float32 (H, W).
    """
    with rasterio.open(path) as src:
        if bbox_wgs84 is not None:
            lon_min, lat_min, lon_max, lat_max = bbox_wgs84
            win = window_from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
            data = src.read(1, window=win,
                            out_shape=ref_shape,
                            resampling=Resampling.bilinear).astype(np.float32)
        elif src.shape != ref_shape:
            data = src.read(1, out_shape=ref_shape,
                            resampling=Resampling.bilinear).astype(np.float32)
        else:
            data = src.read(1).astype(np.float32)
    return data


# =============================================================================
# CALCUL DES INDICES
# =============================================================================

def charger_indices(date_dir: Path, bbox_wgs84=None):
    """
    Charge les bandes et calcule NDVI, NDBI, BSI masqués par SCL.
    Retourne (ndvi, ndbi, bsi, profil) ou None si bandes manquantes.
    """
    requis = ["B04", "B08", "B11"]
    for b in requis:
        if not (date_dir / f"{b}.tif").exists():
            return None

    # Référence : grille B08 (10m)
    with rasterio.open(date_dir / "B08.tif") as src:
        if bbox_wgs84 is not None:
            lon_min, lat_min, lon_max, lat_max = bbox_wgs84
            win = window_from_bounds(lon_min, lat_min, lon_max, lat_max, src.transform)
            b08 = src.read(1, window=win).astype(np.float32)
            ref_transform = src.window_transform(win)
        else:
            b08 = src.read(1).astype(np.float32)
            ref_transform = src.transform
        profil = src.profile.copy()
        ref_shape = b08.shape
        ref_crs   = src.crs

    profil.update(
        width=ref_shape[1], height=ref_shape[0],
        transform=ref_transform, count=1,
        dtype="float32", compress="lzw", nodata=np.nan
    )

    b04 = lire_bande_recadree(date_dir / "B04.tif", ref_shape, ref_transform, ref_crs, bbox_wgs84)
    b11 = lire_bande_recadree(date_dir / "B11.tif", ref_shape, ref_transform, ref_crs, bbox_wgs84)

    # B02 optionnel pour BSI
    b02_path = date_dir / "B02.tif"
    b02 = lire_bande_recadree(b02_path, ref_shape, ref_transform, ref_crs, bbox_wgs84) \
          if b02_path.exists() else np.zeros_like(b08)

    # Masque nuage SCL (20m → rééchantillonné)
    scl_path = date_dir / "SCL.tif"
    if scl_path.exists():
        scl = lire_bande_recadree(scl_path, ref_shape, ref_transform, ref_crs, bbox_wgs84)
        valide = np.isin(scl.astype(np.int16), list(SCL_VALIDES))
    else:
        valide = np.ones(ref_shape, dtype=bool)

    eps = 1e-6

    ndvi = (b08 - b04) / (b08 + b04 + eps)
    ndbi = (b11 - b08) / (b11 + b08 + eps)
    bsi  = ((b11 + b04) - (b08 + b02)) / ((b11 + b04) + (b08 + b02) + eps)

    ndvi = np.clip(ndvi, -1.0, 1.0)
    ndbi = np.clip(ndbi, -1.0, 1.0)
    bsi  = np.clip(bsi,  -1.0, 1.0)

    ndvi[~valide] = np.nan
    ndbi[~valide] = np.nan
    bsi[~valide]  = np.nan

    return ndvi, ndbi, bsi, profil


def mediane_nan(arrays):
    stack = np.stack(arrays, axis=0)
    with np.errstate(all="ignore"):
        return np.nanmedian(stack, axis=0)


def _sauver_rgb_date(date, shape_ref, out_path):
    """Sauvegarde l'image RGB (B04/B03/B02) d'une date précise en PNG."""
    from PIL import Image as PILImage

    date_dir = config.S2_DIR / date
    arrays = {}
    for bande in ("B04", "B03", "B02"):
        p = date_dir / f"{bande}.tif"
        if not p.exists():
            log.warning(f"  {date} : bande {bande} manquante pour export RGB")
            return
        with rasterio.open(p) as s:
            arrays[bande] = s.read(1, out_shape=shape_ref,
                                   resampling=Resampling.bilinear).astype(np.float32)

    def stretch(arr, lo=200, hi=2800):
        return np.clip((arr - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8)

    r = np.where(np.isnan(arrays["B04"]), 0.0, arrays["B04"])
    g = np.where(np.isnan(arrays["B03"]), 0.0, arrays["B03"])
    b = np.where(np.isnan(arrays["B02"]), 0.0, arrays["B02"])

    rgb = np.stack([stretch(r), stretch(g), stretch(b)], axis=-1)
    PILImage.fromarray(rgb, "RGB").save(str(out_path))
    log.info(f"  Composite {out_path.name} ← {date} ({shape_ref[1]}×{shape_ref[0]} px)")


def date_vers_mois(date_str):
    return date_str[:6]


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline():
    if not config.S2_DIR.exists() or not any(config.S2_DIR.iterdir()):
        log.error(f"Aucune donnée S2 dans {config.S2_DIR} — lancez d'abord l'étape 1")
        return False

    bbox_wgs84 = get_test_bbox()

    dates = sorted([d.name for d in config.S2_DIR.iterdir()
                    if d.is_dir() and len(d.name) == 8])
    log.info(f"{len(dates)} dates disponibles : {dates[0]} → {dates[-1]}")

    baseline_dates = [d for d in dates if d.startswith(config.S2_BASELINE_ANNEE)]
    detect_dates   = [d for d in dates if d.startswith(config.S2_DETECT_ANNEE)]

    log.info(f"Baseline {config.S2_BASELINE_ANNEE} : {len(baseline_dates)} dates | "
             f"Détection {config.S2_DETECT_ANNEE} : {len(detect_dates)} dates")

    if not baseline_dates:
        log.error(f"Aucune date pour l'année baseline {config.S2_BASELINE_ANNEE}")
        return False
    if not detect_dates:
        log.error(f"Aucune date pour l'année de détection {config.S2_DETECT_ANNEE}")
        return False

    config.S2_NDVI_DIR.mkdir(parents=True, exist_ok=True)

    # --- Calcul et cache des indices par date ---
    log.info("Calcul indices spectraux (NDVI / NDBI / BSI)…")
    profil_ref = None
    cache = {}   # date → {"ndvi": path, "ndbi": path, "bsi": path}

    for date in dates:
        date_dir = config.S2_DIR / date
        out = {}
        manquant = False

        for idx in ("ndvi", "ndbi", "bsi"):
            p = config.S2_NDVI_DIR / f"{date}_{idx}.tif"
            out[idx] = p
            if not p.exists():
                manquant = True

        if not manquant:
            cache[date] = out
            if profil_ref is None:
                with rasterio.open(out["ndvi"]) as s:
                    profil_ref = s.profile.copy()
            continue

        result = charger_indices(date_dir, bbox_wgs84)
        if result is None:
            log.warning(f"  {date} : bandes manquantes — ignoré")
            continue

        ndvi, ndbi, bsi, profil = result

        if profil_ref is None:
            profil_ref = profil.copy()

        for idx, arr in (("ndvi", ndvi), ("ndbi", ndbi), ("bsi", bsi)):
            with rasterio.open(out[idx], "w", **profil) as dst:
                dst.write(arr[np.newaxis, :, :])

        cache[date] = out
        log.info(f"  {date} : NDVI μ={np.nanmean(ndvi):.3f}  NDBI μ={np.nanmean(ndbi):.3f}")

    if profil_ref is None:
        log.error("Aucun indice calculé — vérifiez les bandes téléchargées")
        return False

    shape_ref = (profil_ref["height"], profil_ref["width"])
    log.info(f"Indices calculés pour {len(cache)} dates | grille {shape_ref}")

    # --- Composites saisonniers : médiane de toutes les images été de chaque année ---
    # Fenêtre avril–octobre : ciel dégagé, pas de neige, même phénologie → pas de biais
    # ~15-20 images par composite → médiane robuste, pas besoin de persistance temporelle
    log.info(f"Composites saisonniers {config.S2_SAISON_DEBUT}→{config.S2_SAISON_FIN} "
             f"({config.S2_BASELINE_ANNEE} vs {config.S2_DETECT_ANNEE})…")

    def filtrer_saison(dates_list):
        return [d for d in dates_list
                if d in cache
                and config.S2_SAISON_DEBUT <= d[4:6] <= config.S2_SAISON_FIN]

    baseline_ete = filtrer_saison(baseline_dates)
    detect_ete   = filtrer_saison(detect_dates)

    log.info(f"  {config.S2_BASELINE_ANNEE} été : {len(baseline_ete)} images")
    log.info(f"  {config.S2_DETECT_ANNEE} été : {len(detect_ete)} images")

    if not baseline_ete:
        log.error(f"Aucune image estivale pour {config.S2_BASELINE_ANNEE}")
        return False
    if not detect_ete:
        log.error(f"Aucune image estivale pour {config.S2_DETECT_ANNEE}")
        return False

    def lire_idx(cache_path, shape_ref):
        with rasterio.open(cache_path) as s:
            return s.read(1, out_shape=shape_ref, resampling=Resampling.bilinear)

    ndvi_b = mediane_nan([lire_idx(cache[d]["ndvi"], shape_ref) for d in baseline_ete])
    ndbi_b = mediane_nan([lire_idx(cache[d]["ndbi"], shape_ref) for d in baseline_ete])
    ndvi_d = mediane_nan([lire_idx(cache[d]["ndvi"], shape_ref) for d in detect_ete])
    ndbi_d = mediane_nan([lire_idx(cache[d]["ndbi"], shape_ref) for d in detect_ete])

    log.info(f"  NDVI baseline μ={np.nanmean(ndvi_b):.3f} | détection μ={np.nanmean(ndvi_d):.3f}")
    log.info(f"  NDBI baseline μ={np.nanmean(ndbi_b):.3f} | détection μ={np.nanmean(ndbi_d):.3f}")

    delta_ndvi = ndvi_d - ndvi_b
    delta_ndbi = ndbi_d - ndbi_b

    # Changement détecté si : forte baisse NDVI OU forte hausse NDBI
    masque_change = (
        ((delta_ndvi < config.S2_SEUIL_DELTA) |
         (delta_ndbi > -config.S2_SEUIL_DELTA))
        & ~np.isnan(delta_ndvi)
    )
    n_px = int(masque_change.sum())
    log.info(f"Pixels changement : {n_px} (ΔNDVI < {config.S2_SEUIL_DELTA})")

    # Score = amplitude du changement (valeur positive → stockée dans le masque)
    score = np.zeros(shape_ref, dtype=np.float32)
    score[masque_change] = (-delta_ndvi + delta_ndbi)[masque_change]

    masque = masque_change

    change_mask = score

    # --- Sauvegarde masque ---
    config.S2_CHANGE.parent.mkdir(parents=True, exist_ok=True)
    p = profil_ref.copy()
    p.update(count=1, dtype="float32", compress="lzw", nodata=0.0)
    with rasterio.open(config.S2_CHANGE, "w", **p) as dst:
        dst.write(change_mask[np.newaxis, :, :])

    surface_ha = n_px * 100 / 10000
    log.info(f"Masque sauvegardé : {config.S2_CHANGE}")
    log.info(f"Surface détectée (brut) : {surface_ha:.1f} ha")

    # --- Images RGB pour visualisation : première date avril baseline, dernière octobre détection ---
    log.info("Export images RGB (visualisation UI)…")
    dates_avril_baseline = sorted(d for d in baseline_ete if d[4:6] == config.S2_SAISON_DEBUT)
    dates_oct_detect     = sorted(d for d in detect_ete   if d[4:6] == config.S2_SAISON_FIN)

    if dates_avril_baseline:
        _sauver_rgb_date(dates_avril_baseline[0], shape_ref, config.S2_NDVI_DIR / "baseline_composite.png")
    else:
        log.warning(f"  Aucune image en {config.S2_SAISON_DEBUT}/{config.S2_BASELINE_ANNEE} — utilisation première date été")
        _sauver_rgb_date(baseline_ete[0], shape_ref, config.S2_NDVI_DIR / "baseline_composite.png")

    if dates_oct_detect:
        _sauver_rgb_date(dates_oct_detect[-1], shape_ref, config.S2_NDVI_DIR / "detect_composite.png")
    else:
        log.warning(f"  Aucune image en {config.S2_SAISON_FIN}/{config.S2_DETECT_ANNEE} — utilisation dernière date été")
        _sauver_rgb_date(detect_ete[-1], shape_ref, config.S2_NDVI_DIR / "detect_composite.png")

    return True


if __name__ == "__main__":
    log.info("Script 02 — Indices spectraux S2 + détection changement (NDVI/NDBI/BSI)")
    sys.exit(0 if pipeline() else 1)
