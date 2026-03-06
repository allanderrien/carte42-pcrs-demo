"""
01_download_ign.py — Téléchargement des orthophotos
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Sources :
  T1 (2020) : WMS IGN data.geopf.fr → ORTHOIMAGERY.ORTHOPHOTOS2020
  T2 (2023) : WMS IGN data.geopf.fr → ORTHOIMAGERY.ORTHOPHOTOS.ORTHO-EXPRESS.2023

Les tuiles sont sauvegardées en WGS84 (EPSG:4326) — pas de reprojection raster.
T1 et T2 du même rang/colonne ont le même bbox WGS84 → alignement pixel parfait.
La reprojection est réservée aux vecteurs de sortie (étape 3).

Les tuiles déjà présentes sont ignorées (reprise possible sans re-téléchargement).

Usage :
  python processing/01_download_ign.py
"""

import sys
import logging
import math
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

import numpy as np
import requests
import rasterio
from rasterio.transform import from_bounds
from rasterio.crs import CRS
from tqdm import tqdm
from PIL import Image
from pyproj import Transformer

_L93_TO_WGS84 = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("01_download")


# =============================================================================
# GRILLE DE TUILES
# =============================================================================

def calculer_grille_tuiles(bbox: dict, resolution: float, taille_px: int) -> list:
    """Calcule la grille de tuiles couvrant le bbox à la résolution donnée."""
    n_cols = math.ceil(((bbox["xmax"] - bbox["xmin"]) / resolution) / taille_px)
    n_rows = math.ceil(((bbox["ymax"] - bbox["ymin"]) / resolution) / taille_px)

    log.info(f"Grille WMS : {n_cols} col × {n_rows} lig = {n_cols * n_rows} tuiles")

    tuiles = []
    for row in range(n_rows):
        for col in range(n_cols):
            t_xmin = bbox["xmin"] + col * taille_px * resolution
            t_ymax = bbox["ymax"] - row * taille_px * resolution
            t_xmax = min(t_xmin + taille_px * resolution, bbox["xmax"])
            t_ymin = max(t_ymax - taille_px * resolution, bbox["ymin"])
            tuiles.append({
                "xmin": t_xmin, "ymin": t_ymin,
                "xmax": t_xmax, "ymax": t_ymax,
                "col": col, "row": row,
            })
    return tuiles


# =============================================================================
# TÉLÉCHARGEMENT D'UNE TUILE WMS
# =============================================================================

def telecharger_tuile_wms(tuile: dict, dossier: Path, layer: str, prefix: str) -> Path | None:
    """
    Télécharge une tuile WMS IGN et la sauvegarde en GeoTIFF WGS84 (EPSG:4326).

    Pas de reprojection raster : les tuiles T1 et T2 du même rang/colonne
    ont le même bbox WGS84, donc leurs pixels sont directement comparables.

    Args:
        tuile   : dict avec xmin/ymin/xmax/ymax/row/col en Lambert 93
        dossier : répertoire de destination
        layer   : nom de la couche WMS IGN
        prefix  : préfixe du nom de fichier (ex. 'tuile_t1' ou 'tuile_t2')
    """
    nom    = f"{prefix}_r{tuile['row']:03d}_c{tuile['col']:03d}.tif"
    chemin = dossier / nom

    if chemin.exists() and chemin.stat().st_size > 1024:
        return chemin

    res = config.RESOLUTION_CIBLE
    w   = max(1, round((tuile["xmax"] - tuile["xmin"]) / res))
    h   = max(1, round((tuile["ymax"] - tuile["ymin"]) / res))

    # WMS 1.3.0 EPSG:4326 : bbox = (latmin, lonmin, latmax, lonmax)
    lon_min, lat_min = _L93_TO_WGS84.transform(tuile["xmin"], tuile["ymin"])
    lon_max, lat_max = _L93_TO_WGS84.transform(tuile["xmax"], tuile["ymax"])
    bbox_str = f"{lat_min},{lon_min},{lat_max},{lon_max}"

    params = {
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS":  layer,  "STYLES": "",
        "CRS":     "EPSG:4326", "BBOX": bbox_str,
        "WIDTH":   w, "HEIGHT": h,
        "FORMAT":  "image/png", "TRANSPARENT": "FALSE",
    }

    for tentative in range(1, config.HTTP_RETRIES + 1):
        try:
            r = requests.get(config.IGN_WMS_URL, params=params,
                             timeout=config.HTTP_TIMEOUT)
            r.raise_for_status()

            if "image" not in r.headers.get("Content-Type", ""):
                log.warning(f"{prefix} r{tuile['row']}c{tuile['col']} — réponse non-image : "
                            f"{r.text[:200]}")
                return None

            contenu = r.content
            if len(contenu) < 256:
                raise OSError(f"Réponse trop courte ({len(contenu)} octets)")

            img = Image.open(BytesIO(contenu)).convert("RGB")
            arr = np.array(img)

            # Sauvegarde directe en WGS84 — le bbox WGS84 est le transform exact
            transform = from_bounds(lon_min, lat_min, lon_max, lat_max,
                                    arr.shape[1], arr.shape[0])

            dossier.mkdir(parents=True, exist_ok=True)
            with rasterio.open(chemin, "w", driver="GTiff",
                               height=arr.shape[0], width=arr.shape[1],
                               count=3, dtype="uint8",
                               crs=CRS.from_epsg(4326),
                               transform=transform, compress="lzw") as dst:
                for i in range(3):
                    dst.write(arr[:, :, i], i + 1)
            return chemin

        except (requests.exceptions.RequestException, OSError) as e:
            log.warning(f"Tentative {tentative}/{config.HTTP_RETRIES} "
                        f"{prefix} r{tuile['row']}c{tuile['col']} : {e}")
            if tentative < config.HTTP_RETRIES:
                time.sleep(2 ** tentative)

    return None


# =============================================================================
# TÉLÉCHARGEMENT COMPLET D'UN MILLÉSIME
# =============================================================================

def telecharger_wms(label: str, layer: str, dossier: Path, prefix: str) -> bool:
    """Télécharge un millésime complet via WMS tuilé IGN."""
    log.info("=" * 60)
    log.info(f"{label} — {layer}")
    log.info("=" * 60)

    dossier.mkdir(parents=True, exist_ok=True)
    tuiles    = calculer_grille_tuiles(config.BBOX_L93, config.RESOLUTION_CIBLE,
                                       config.TILE_SIZE_PX)
    chemins_ok = []

    with ThreadPoolExecutor(max_workers=config.DOWNLOAD_THREADS) as executor:
        futures = {
            executor.submit(telecharger_tuile_wms, t, dossier, layer, prefix): t
            for t in tuiles
        }
        with tqdm(total=len(tuiles), desc=label, unit="tuile") as bar:
            for future in as_completed(futures):
                result = future.result()
                if result:
                    chemins_ok.append(result)
                bar.update(1)

    n_ok    = len(chemins_ok)
    n_total = len(tuiles)
    log.info(f"Tuiles téléchargées : {n_ok} / {n_total}")

    if n_ok == 0:
        log.error(f"Aucune tuile {label} récupérée.")
        return False
    if n_ok < n_total:
        log.warning(f"{n_total - n_ok} tuile(s) manquante(s) — relancez pour compléter.")

    log.info(f"Tuiles conservées dans : {dossier} (WGS84 / EPSG:4326)")
    return True


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 01 — Téléchargement orthophotos (WGS84, sans reprojection raster)")
    log.info(f"T1 : WMS IGN {config.IGN_LAYER_T1} — {config.MILLESIME_ANCIEN}")
    log.info(f"T2 : WMS IGN {config.IGN_LAYER_T2} — {config.MILLESIME_RECENT}")

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)

    n_t1 = len(list(config.TILES_T1_DIR.glob("tuile_t1_*.tif"))) \
           if config.TILES_T1_DIR.exists() else 0
    log.info(f"T1 : {n_t1} tuile(s) déjà présentes")
    ok_t1 = telecharger_wms(
        label=f"T1 ({config.MILLESIME_ANCIEN})",
        layer=config.IGN_LAYER_T1,
        dossier=config.TILES_T1_DIR,
        prefix="tuile_t1",
    )

    n_t2 = len(list(config.TILES_T2_DIR.glob("tuile_t2_*.tif"))) \
           if config.TILES_T2_DIR.exists() else 0
    log.info(f"T2 : {n_t2} tuile(s) déjà présentes")
    ok_t2 = telecharger_wms(
        label=f"T2 ({config.MILLESIME_RECENT})",
        layer=config.IGN_LAYER_T2,
        dossier=config.TILES_T2_DIR,
        prefix="tuile_t2",
    )

    if ok_t1 and ok_t2:
        log.info("Téléchargement terminé avec succès.")
        sys.exit(0)
    else:
        log.error("Des erreurs sont survenues.")
        sys.exit(1)
