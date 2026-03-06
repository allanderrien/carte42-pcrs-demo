"""
02_preprocess.py — Classification spectrale NDVI (PCC 4 bandes)
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pour chaque paire de tuiles T1/T2 (RGB + IRC), extrait la bande NIR
de l'image IRC IGN, calcule le NDVI, puis classifie chaque pixel :

  0 = ombre / eau très sombre  (brightness < SEUIL_OMBRE)
  1 = végétation dense         (NDVI > SEUIL_NDVI_VEG)
  2 = sol nu / chantier        (SEUIL_NDVI_SOL < NDVI ≤ SEUIL_NDVI_VEG)
  3 = surface imperméable      (NDVI ≤ SEUIL_NDVI_SOL, non-ombre)

La transition T1→T2 est encodée : valeur = classe_T1 × 4 + classe_T2 (uint8).

Format IRC IGN : bande 1 = NIR, bande 2 = Rouge, bande 3 = Vert.

Usage :
  python processing/02_preprocess.py
"""

import sys
import logging
from pathlib import Path

import numpy as np
import rasterio
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

def lire_quadruplet(chemin_t1: Path, chemin_t2: Path,
                    chemin_t1_irc: Path, chemin_t2_irc: Path,
                    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Lit les 4 tuiles (T1 RGB, T2 RGB, T1 IRC, T2 IRC).
    Retourne (t1, t2, t1_irc, t2_irc, profil_t2) en float32 (C, H, W).
    Recadre toutes les tuiles à la dimension minimale commune.
    """
    def lire(p):
        with rasterio.open(p) as src:
            return src.read().astype(np.float32), src.profile.copy()

    t1,     _      = lire(chemin_t1)
    t2,     profil = lire(chemin_t2)
    t1_irc, _      = lire(chemin_t1_irc)
    t2_irc, _      = lire(chemin_t2_irc)

    h = min(t1.shape[1], t2.shape[1], t1_irc.shape[1], t2_irc.shape[1])
    w = min(t1.shape[2], t2.shape[2], t1_irc.shape[2], t2_irc.shape[2])
    return (t1[:, :h, :w], t2[:, :h, :w],
            t1_irc[:, :h, :w], t2_irc[:, :h, :w], profil)


def classifier_pixel(rgb: np.ndarray, irc: np.ndarray) -> np.ndarray:
    """
    Classifie chaque pixel en 4 classes à partir de RGB + IRC (C, H, W) float32.

    Format IRC IGN : bande 0 = NIR, bande 1 = Rouge, bande 2 = Vert.

    NDVI = (NIR − Rouge) / (NIR + Rouge)
      > SEUIL_NDVI_VEG (0.25) → végétation dense
      > SEUIL_NDVI_SOL (0.05) → sol nu / chantier / végétation clairsemée
      ≤ SEUIL_NDVI_SOL        → surface imperméable (route, toit, béton)

    Classes :
      0 = ombre   1 = végétation   2 = sol nu/chantier   3 = imperméable
    """
    r, g, b = rgb[0], rgb[1], rgb[2]
    nir     = irc[0]   # canal 0 de l'IRC IGN = NIR
    red_irc = irc[1]   # canal 1 de l'IRC IGN = Rouge (cohérent avec NIR)

    brightness = (r + g + b) / 3.0
    ndvi       = (nir - red_irc) / (nir + red_irc + 1e-6)

    classe = np.full(brightness.shape, 3, dtype=np.uint8)  # défaut : imperméable

    ombre         = brightness < config.SEUIL_OMBRE
    classe[ombre] = 0

    veget         = ~ombre & (ndvi > config.SEUIL_NDVI_VEG)
    classe[veget] = 1

    sol_nu         = ~ombre & ~veget & (ndvi > config.SEUIL_NDVI_SOL)
    classe[sol_nu] = 2

    return classe


def sauver_transition(chg: np.ndarray, profil: dict, chemin: Path) -> None:
    """Sauvegarde la tuile de transition T1→T2 (uint8, 1 bande, valeurs 0–15)."""
    p = profil.copy()
    p.update({"count": 1, "dtype": "uint8", "compress": "lzw"})
    chemin.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(chemin, "w", **p) as dst:
        dst.write(chg[np.newaxis, :, :])


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline() -> bool:
    for label, d in [("T1 RGB", config.TILES_T1_DIR), ("T2 RGB", config.TILES_T2_DIR),
                     ("T1 IRC", config.TILES_T1_IRC_DIR), ("T2 IRC", config.TILES_T2_IRC_DIR)]:
        if not d.exists() or not any(d.iterdir()):
            log.error(f"Dossier {label} vide ou absent : {d} → lancez d'abord l'étape 1")
            return False

    tuiles_t2 = sorted(config.TILES_T2_DIR.glob("tuile_t2_*.tif"))

    test_bbox = get_test_bbox()
    if test_bbox:
        tuiles_t2 = [t for t in tuiles_t2 if tuile_dans_bbox(t, test_bbox)]
        log.info(f"Zone de test active : {len(tuiles_t2)} tuile(s) sélectionnée(s)")
    else:
        log.info(f"T2 : {len(tuiles_t2)} tuiles à traiter")

    log.info("Méthode : PCC NDVI (NIR extrait de l'IRC IGN)")
    log.info(f"NDVI > {config.SEUIL_NDVI_VEG} → végétation | "
             f"> {config.SEUIL_NDVI_SOL} → sol nu | sinon → imperméable")

    config.TILES_CHG_DIR.mkdir(parents=True, exist_ok=True)
    deja_traites = 0
    erreurs      = 0

    for tuile_t2 in tqdm(tuiles_t2, desc="Classification NDVI", unit="tuile"):
        # Convention de nommage : tuile_t2_rXXX_cXXX.tif → suffixe = rXXX_cXXX.tif
        suffixe  = tuile_t2.name[len("tuile_t2_"):]
        tuile_t1     = config.TILES_T1_DIR     / f"tuile_t1_{suffixe}"
        tuile_t1_irc = config.TILES_T1_IRC_DIR / f"tuile_t1_irc_{suffixe}"
        tuile_t2_irc = config.TILES_T2_IRC_DIR / f"tuile_t2_irc_{suffixe}"
        chg_out      = config.TILES_CHG_DIR    / f"chg_{suffixe}"

        if chg_out.exists():
            deja_traites += 1
            continue

        for label, p in [("T1 RGB", tuile_t1), ("T1 IRC", tuile_t1_irc),
                         ("T2 IRC", tuile_t2_irc)]:
            if not p.exists():
                log.warning(f"Tuile {label} manquante pour {tuile_t2.name} — ignorée")
                erreurs += 1
                break
        else:
            try:
                t1, t2, t1_irc, t2_irc, profil = lire_quadruplet(
                    tuile_t1, tuile_t2, tuile_t1_irc, tuile_t2_irc
                )
                c1  = classifier_pixel(t1, t1_irc)
                c2  = classifier_pixel(t2, t2_irc)
                chg = (c1 * 4 + c2).astype(np.uint8)
                sauver_transition(chg, profil, chg_out)
            except Exception as e:
                log.warning(f"Tuile {tuile_t2.name} ignorée : {e}")
                erreurs += 1

    n_chg = len(list(config.TILES_CHG_DIR.glob("chg_*.tif")))
    log.info(f"Tuiles de transition : {n_chg}/{len(tuiles_t2)} "
             f"(dont {deja_traites} déjà traitées, {erreurs} erreurs)")
    log.info(f"Répertoire : {config.TILES_CHG_DIR}")
    return n_chg > 0


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 02 — Classification NDVI tuile par tuile (RGB + IRC IGN)")
    sys.exit(0 if pipeline() else 1)
