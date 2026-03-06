"""
02_preprocess.py — Prétraitement des orthophotos, tuile par tuile
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pour chaque tuile T2 (WMS IGN), lit la fenêtre T1 correspondante (WCS GéoBretagne),
recale, normalise et calcule l'amplitude CVA. Sauve une tuile d'amplitude float32.

Le traitement est tuile par tuile : jamais plus de ~30 Mo en RAM à la fois.
Les tuiles déjà traitées sont ignorées (reprise possible).

Usage :
  python processing/02_preprocess.py
"""

import sys
import logging
from pathlib import Path

import numpy as np
import rasterio
import cv2
from skimage.exposure import match_histograms
from tqdm import tqdm
from pyproj import Transformer

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
import os

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
    """Retourne True si la tuile intersecte le bbox de test (WGS84)."""
    with rasterio.open(chemin) as src:
        b = src.bounds
    return not (b.right < bbox['xmin'] or b.left > bbox['xmax'] or
                b.top  < bbox['ymin'] or b.bottom > bbox['ymax'])

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("02_preprocess")


# =============================================================================
# FONCTIONS
# =============================================================================

def lire_paire(chemin_t1: Path, chemin_t2: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """
    Lit une paire de tuiles T1/T2 de même emprise.

    Les tuiles T1 et T2 ont été téléchargées sur la même grille → même bbox,
    même résolution, même dimensions. Pas de recalcul de fenêtre nécessaire.

    Retourne (t1_data, t2_data, profil_t2) en float32 (C, H, W).
    """
    with rasterio.open(chemin_t1) as src:
        t1     = src.read().astype(np.float32)
    with rasterio.open(chemin_t2) as src:
        t2     = src.read().astype(np.float32)
        profil = src.profile.copy()

    # Recadrage au minimum commun si dimensions légèrement différentes (bord de grille)
    h = min(t1.shape[1], t2.shape[1])
    w = min(t1.shape[2], t2.shape[2])
    return t1[:, :h, :w], t2[:, :h, :w], profil


def recaler(t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """
    Recale t2 sur t1 par corrélation de phase (bande verte).
    Retourne t2 recalée (même shape).
    """
    ref = (t1[1] / (t1[1].max() + 1e-6)).astype(np.float32)
    mob = (t2[1] / (t2[1].max() + 1e-6)).astype(np.float32)

    (dx, dy), _ = cv2.phaseCorrelate(ref, mob)

    if abs(dx) < 0.5 and abs(dy) < 0.5:
        return t2

    M  = np.float32([[1, 0, -dx], [0, 1, -dy]])
    h, w = t2.shape[1], t2.shape[2]
    out = np.zeros_like(t2)
    for c in range(t2.shape[0]):
        out[c] = cv2.warpAffine(
            t2[c], M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT_101,
        )
    return out


def normaliser(t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """
    Normalise la radiométrie de t2 pour correspondre à t1 (histogram matching).
    Retourne t2 normalisée en float32 (C, H, W).
    """
    t1_hwc = np.clip(t1, 0, 255).astype(np.uint8).transpose(1, 2, 0)
    t2_hwc = np.clip(t2, 0, 255).astype(np.uint8).transpose(1, 2, 0)
    norm   = match_histograms(t2_hwc, t1_hwc, channel_axis=2)
    return norm.transpose(2, 0, 1).astype(np.float32)


def cva_amplitude(t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """
    Change Vector Analysis : norme euclidienne du vecteur de différence spectrale.
    Retourne une carte d'amplitude (H, W) float32.
    """
    diff = (t2.astype(np.float64) - t1.astype(np.float64)) ** 2
    return np.sqrt(diff.sum(axis=0)).astype(np.float32)


def masquer_ombres(amp: np.ndarray, t1: np.ndarray, t2: np.ndarray) -> np.ndarray:
    """
    Zéro les pixels d'amplitude où T1 ou T2 est trop sombre (ombre portée).
    t1/t2 : (C, H, W) float32 0–255.
    """
    seuil = config.SEUIL_OMBRE
    ombre = (t1.mean(axis=0) < seuil) | (t2.mean(axis=0) < seuil)
    amp   = amp.copy()
    amp[ombre] = 0.0
    return amp


def sauver_amplitude(amp: np.ndarray, profil: dict, chemin: Path) -> None:
    """Sauvegarde la tuile d'amplitude (1 bande float32) en GeoTIFF."""
    p = profil.copy()
    p.update({"count": 1, "dtype": "float32", "compress": "lzw"})
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(chemin, "w", **p) as dst:
        dst.write(amp[np.newaxis, :, :])


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline() -> bool:
    # Vérifications
    tuiles_t1 = sorted(config.TILES_T1_DIR.glob("tuile_t1_*.tif")) \
                if config.TILES_T1_DIR.exists() else []
    tuiles_t2 = sorted(config.TILES_T2_DIR.glob("tuile_t2_*.tif")) \
                if config.TILES_T2_DIR.exists() else []

    if not tuiles_t1:
        log.error(f"Aucune tuile T1 dans {config.TILES_T1_DIR} → lancez d'abord l'étape 1")
        return False
    if not tuiles_t2:
        log.error(f"Aucune tuile T2 dans {config.TILES_T2_DIR} → lancez d'abord l'étape 1")
        return False

    test_bbox = get_test_bbox()
    if test_bbox:
        tuiles_t2 = [t for t in tuiles_t2 if tuile_dans_bbox(t, test_bbox)]
        log.info(f"Zone de test active : {len(tuiles_t2)} tuile(s) sélectionnée(s)")
    else:
        log.info(f"T1 : {len(tuiles_t1)} tuiles dans {config.TILES_T1_DIR}")
        log.info(f"T2 : {len(tuiles_t2)} tuiles dans {config.TILES_T2_DIR}")
    config.TILES_AMP_DIR.mkdir(parents=True, exist_ok=True)

    deja_traites = 0
    erreurs      = 0

    for tuile_t2 in tqdm(tuiles_t2, desc="Prétraitement tuiles", unit="tuile"):
        # Tuile T1 correspondante : même nom, répertoire différent
            nom_t1   = tuile_t2.name.replace("tuile_t2_", "tuile_t1_")
            tuile_t1 = config.TILES_T1_DIR / nom_t1
            amp_out  = config.TILES_AMP_DIR / tuile_t2.name.replace("tuile_t2_", "amp_")

            if amp_out.exists():
                deja_traites += 1
                continue

            if not tuile_t1.exists():
                log.warning(f"Tuile T1 manquante pour {tuile_t2.name} — ignorée")
                erreurs += 1
                continue

            try:
                t1, t2, profil = lire_paire(tuile_t1, tuile_t2)
                t2_norm        = normaliser(t1, t2)
                amp            = cva_amplitude(t1, t2_norm)
                amp            = masquer_ombres(amp, t1, t2_norm)
                sauver_amplitude(amp, profil, amp_out)
            except Exception as e:
                log.warning(f"Tuile {tuile_t2.name} ignorée : {e}")
                erreurs += 1

    n_amp = len(list(config.TILES_AMP_DIR.glob("amp_*.tif")))
    log.info(f"Tuiles d'amplitude : {n_amp}/{len(tuiles_t2)} "
             f"(dont {deja_traites} déjà traitées, {erreurs} erreurs)")
    log.info(f"Répertoire : {config.TILES_AMP_DIR}")

    return n_amp > 0


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 02 — Prétraitement tuile par tuile (CVA amplitude)")
    sys.exit(0 if pipeline() else 1)
