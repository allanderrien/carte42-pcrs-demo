"""
detect_lotissements.py — Détecte les lotissements récents à partir des
nouvelles voies OSM (2020+) avec double validation :
  1. Filtre spatial  : voie >50% hors du réseau OSM existant (avant 2020)
  2. Filtre spectral : sous la voie en 2020, l'ortho T1 montre de la végétation
                       → ExG (Excess Green) = 2G-R-B normalisé > seuil

Méthode :
  - Échantillonne N points le long de chaque voie nouvelle
  - Lit les pixels de l'ortho T1 2020 (tuiles locales WGS84)
  - Calcule le ratio de pixels "végétation" (ExG > EXG_SEUIL)
  - Ne retient que les voies avec ratio >= VEG_RATIO_MIN
  - Buffèrise + dissolve → polygones de lotissement

Usage :
  python processing/detect_lotissements.py
"""

import json, logging
from collections import defaultdict
from pathlib import Path

import numpy as np
import rasterio
import rasterio.windows
import geopandas as gpd
from pyproj import Transformer
from shapely.ops import unary_union

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("lotissements")

PROJECT_ROOT   = Path(__file__).parent.parent
OSM_VOIES      = PROJECT_ROOT / "data/osm/nouvelles_voies_osm.geojson"
OSM_EXISTANTES = PROJECT_ROOT / "data/osm/voies_existantes_osm.geojson"
TILES_T1_DIR   = PROJECT_ROOT / "data/raw/tiles_t1"
OUT_FILE       = PROJECT_ROOT / "data/osm/lotissements_detectes.geojson"

CRS_PROJ = "EPSG:2154"

# ── Paramètres ────────────────────────────────────────────────────────────────

DIST_RESEAU_EXISTANT = 25    # m — buffer réseau existant pour filtre spatial
RATIO_HORS_MIN       = 0.50  # fraction minimale de la voie hors réseau existant

N_SAMPLE_POINTS = 25         # points d'échantillonnage par voie
EXG_SEUIL       = 0.08       # ExG normalisé : 2g-r-b > seuil → végétation
VEG_RATIO_MIN   = 0.35       # fraction minimale de pixels végétation en T1 2020

BUFFER_VOIE  = 20            # m — buffer pour former les polygones
SURFACE_MIN  = 500           # m² — filtre surface minimale


# ── Index tuiles T1 ───────────────────────────────────────────────────────────

def build_tile_index(tiles_dir):
    """Retourne [(path, BoundingBox), ...] pour toutes les tuiles T1."""
    index = []
    for tif in sorted(tiles_dir.glob("tuile_t1_*.tif")):
        with rasterio.open(tif) as src:
            index.append((tif, src.bounds))
    log.info(f"Index tuiles T1 : {len(index)} tuiles")
    return index


# ── Filtre végétation ─────────────────────────────────────────────────────────

def filter_par_vegetation(osm_gdf_l93, tile_index):
    """
    Pour chaque voie en L93, échantillonne les pixels T1 2020 et calcule
    le ratio ExG > EXG_SEUIL. Retourne (masque_bool, ratios_dict).
    """
    t = Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)

    # 1. Génère les points d'échantillonnage (L93 → WGS84)
    road_pts = {}   # idx → [(lon, lat), ...]
    for idx, row in osm_gdf_l93.iterrows():
        geom = row.geometry
        length = geom.length
        if length == 0:
            road_pts[idx] = []
            continue
        step = length / N_SAMPLE_POINTS
        pts = [geom.interpolate(i * step) for i in range(N_SAMPLE_POINTS + 1)]
        road_pts[idx] = [t.transform(p.x, p.y) for p in pts]

    # 2. Groupe les points par tuile
    tile_pts = defaultdict(list)   # path → [(idx, lon, lat), ...]
    for idx, pts in road_pts.items():
        for lon, lat in pts:
            for tif_path, bounds in tile_index:
                if (bounds.left <= lon <= bounds.right and
                        bounds.bottom <= lat <= bounds.top):
                    tile_pts[tif_path].append((idx, lon, lat))
                    break

    # 3. Lit chaque tuile une seule fois et collecte les valeurs ExG
    road_exg = defaultdict(list)   # idx → [exg_values]
    for tif_path, pts in tile_pts.items():
        with rasterio.open(tif_path) as src:
            for idx, lon, lat in pts:
                try:
                    row_px, col_px = src.index(lon, lat)
                    if not (0 <= row_px < src.height and 0 <= col_px < src.width):
                        continue
                    # Patch 3×3 autour du point
                    win = rasterio.windows.Window(
                        max(0, col_px - 1), max(0, row_px - 1),
                        min(3, src.width  - max(0, col_px - 1)),
                        min(3, src.height - max(0, row_px - 1)),
                    )
                    data = src.read(window=win)   # (3, h, w) uint8
                    if data.shape[0] < 3 or data.size == 0:
                        continue
                    r = data[0].astype(np.float32) / 255
                    g = data[1].astype(np.float32) / 255
                    b = data[2].astype(np.float32) / 255
                    exg = 2 * g - r - b
                    road_exg[idx].extend(exg.flatten().tolist())
                except Exception:
                    pass

    # 4. Calcule ratio et masque
    ratios = {}
    mask   = []
    for idx in osm_gdf_l93.index:
        vals = road_exg.get(idx, [])
        if not vals:
            ratio = None   # pas de tuile → on garde par défaut
        else:
            ratio = sum(1 for v in vals if v > EXG_SEUIL) / len(vals)
        ratios[idx] = ratio
        mask.append(ratio is None or ratio >= VEG_RATIO_MIN)

    n_ok  = sum(mask)
    n_tot = len(mask)
    n_nd  = sum(1 for r in ratios.values() if r is None)
    log.info(f"  Filtre végétation : {n_ok}/{n_tot} voies retenues "
             f"({n_tot - n_ok} éliminées, {n_nd} sans données tuile)")
    return mask, ratios


# ── Pipeline principal ────────────────────────────────────────────────────────

def run():
    # ── Chargement ────────────────────────────────────────────────────────────
    log.info("Chargement des nouvelles voies OSM…")
    osm = gpd.read_file(OSM_VOIES).to_crs(CRS_PROJ)
    log.info(f"  {len(osm)} voies OSM nouvelles (version=1, 2020+)")

    log.info("Chargement du réseau OSM existant (avant 2020)…")
    existant = gpd.read_file(OSM_EXISTANTES).to_crs(CRS_PROJ)
    log.info(f"  {len(existant)} voies réseau existant OSM")

    # ── Filtre 1 : spatial — voies >50% hors réseau existant ─────────────────
    log.info(f"Filtre spatial (buffer {DIST_RESEAU_EXISTANT} m réseau existant)…")
    existant_buffer = unary_union(existant.geometry).buffer(DIST_RESEAU_EXISTANT)

    def ratio_hors(geom):
        hors = geom.difference(existant_buffer)
        return hors.length / geom.length if geom.length > 0 else 0.0

    ratios_spat = osm.geometry.apply(ratio_hors)
    mask_spat   = ratios_spat >= RATIO_HORS_MIN
    osm_spat    = osm[mask_spat].copy()
    log.info(f"  {mask_spat.sum()} voies après filtre spatial "
             f"({(~mask_spat).sum()} éliminées)")

    if osm_spat.empty:
        log.warning("Aucune voie après filtre spatial — ajustez RATIO_HORS_MIN")
        return

    # ── Filtre 2 : végétation T1 2020 ────────────────────────────────────────
    log.info(f"Filtre végétation T1 (ExG>{EXG_SEUIL}, ratio≥{VEG_RATIO_MIN})…")
    tile_index = build_tile_index(TILES_T1_DIR)
    mask_veg, veg_ratios = filter_par_vegetation(osm_spat, tile_index)

    osm_nouvelles = osm_spat[mask_veg].copy()
    osm_nouvelles["veg_ratio"] = [
        round(veg_ratios[idx], 3) if veg_ratios[idx] is not None else -1
        for idx in osm_nouvelles.index
    ]
    log.info(f"  {len(osm_nouvelles)} voies après double filtre")

    if osm_nouvelles.empty:
        log.warning("Aucune voie après filtre végétation — ajustez VEG_RATIO_MIN")
        return

    # ── Buffer + dissolve ─────────────────────────────────────────────────────
    log.info(f"Buffer {BUFFER_VOIE} m + dissolve…")
    osm_buf = osm_nouvelles.copy()
    osm_buf["geometry"] = osm_buf.geometry.buffer(BUFFER_VOIE)

    dissolved = (
        osm_buf
        .dissolve()
        .explode(index_parts=False)
        .reset_index(drop=True)
    )
    dissolved = dissolved[dissolved.geometry.area >= SURFACE_MIN].copy()
    log.info(f"  {len(dissolved)} polygones après filtre surface ≥ {SURFACE_MIN} m²")

    # ── Propriétés par polygone ───────────────────────────────────────────────
    rows = []
    for _, poly in dissolved.iterrows():
        voies_dans = osm_nouvelles[osm_nouvelles.geometry.intersects(poly.geometry)]
        noms = sorted({n for n in voies_dans["name"] if isinstance(n, str) and n})
        surface = round(poly.geometry.area)
        vr_vals  = [v for v in voies_dans["veg_ratio"] if v >= 0]
        rows.append({
            "nb_voies":   len(voies_dans),
            "noms_voies": ", ".join(noms) if noms else None,
            "surface_m2": surface,
            "surface_ha": round(surface / 1e4, 3),
            "veg_ratio_moy": round(sum(vr_vals) / len(vr_vals), 2) if vr_vals else None,
        })

    dissolved = dissolved[["geometry"]].copy()
    for col, vals in {k: [r[k] for r in rows] for k in rows[0]}.items():
        dissolved[col] = vals

    # ── Export WGS84 ─────────────────────────────────────────────────────────
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    dissolved.to_crs("EPSG:4326").to_file(OUT_FILE, driver="GeoJSON")

    surface_totale = dissolved["surface_m2"].sum()
    log.info(f"Exporté : {OUT_FILE}")
    log.info(f"  {len(dissolved)} lotissements · {surface_totale/1e4:.1f} ha")


if __name__ == "__main__":
    run()
