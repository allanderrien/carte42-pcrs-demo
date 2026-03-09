"""
01_download_sentinel2.py — Téléchargement images Sentinel-2 L2A (CDSE)
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Pour chaque image Sentinel-2 L2A disponible sur la zone d'étude entre
S2_DATE_DEBUT et S2_DATE_FIN, avec couverture nuageuse < S2_CLOUD_MAX % :
  - Télécharge les bandes B04 (Rouge), B08 (NIR), SCL (masque nuage) depuis
    le Copernicus Data Space Ecosystem (CDSE)
  - Recadre à la bbox de la zone d'étude (BBOX_WGS84)
  - Reprojette en EPSG:4326 si nécessaire
  - Sauvegarde en GeoTIFF dans data/raw/sentinel2/YYYYMMDD/

Credentials : renseignez credentials.env à la racine du projet.
Compte gratuit : https://dataspace.copernicus.eu

Usage :
  python processing/01_download_sentinel2.py
"""

import sys
import logging
import time
import io
from pathlib import Path
from datetime import datetime

import requests
import boto3
from botocore.client import Config
import numpy as np
import rasterio
from rasterio.transform import from_bounds
from rasterio.warp import calculate_default_transform, reproject, Resampling

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("01_download_s2")

CDSE_TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CDSE_ODATA_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1"
CDSE_S3_ENDPOINT = "https://eodata.dataspace.copernicus.eu"
CDSE_S3_BUCKET   = "EODATA"

BANDES_CIBLES = ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"]
# suffixe recherché dans le nom de fichier JP2
BANDE_SUFFIXE = {
    "B02": "_B02_10m.jp2",   # Bleu
    "B03": "_B03_10m.jp2",   # Vert
    "B04": "_B04_10m.jp2",   # Rouge
    "B08": "_B08_10m.jp2",   # NIR
    "B11": "_B11_20m.jp2",   # SWIR1 — asphalte / chantiers
    "B12": "_B12_20m.jp2",   # SWIR2 — béton / sol nu
    "SCL": "_SCL_20m.jp2",   # Masque nuages
}


# =============================================================================
# CREDENTIALS
# =============================================================================

def lire_credentials():
    """Lit les credentials depuis credentials.env."""
    creds = {}
    if not config.CREDENTIALS_FILE.exists():
        log.error(f"Fichier credentials introuvable : {config.CREDENTIALS_FILE}")
        sys.exit(1)
    with open(config.CREDENTIALS_FILE) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                creds[k.strip()] = v.strip()
    for key in ('CDSE_USER', 'CDSE_PASSWORD', 'CDSE_S3_ACCESS_KEY', 'CDSE_S3_SECRET_KEY'):
        if key not in creds:
            log.error(f"Renseignez {key} dans credentials.env")
            sys.exit(1)
    return creds


def creer_client_s3(creds):
    """Crée un client boto3 pointant sur le S3 CDSE."""
    return boto3.client(
        "s3",
        endpoint_url=CDSE_S3_ENDPOINT,
        aws_access_key_id=creds["CDSE_S3_ACCESS_KEY"],
        aws_secret_access_key=creds["CDSE_S3_SECRET_KEY"],
        config=Config(signature_version="s3v4"),
        region_name="default",
    )


# =============================================================================
# AUTHENTIFICATION
# =============================================================================

def get_token(user, password):
    """Obtient un access token OAuth2 CDSE."""
    r = requests.post(CDSE_TOKEN_URL, data={
        "client_id":  "cdse-public",
        "username":   user,
        "password":   password,
        "grant_type": "password",
    }, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


# =============================================================================
# RECHERCHE DE PRODUITS
# =============================================================================

def search_products(bbox, date_debut, date_fin, cloud_max, token):
    """
    Recherche les produits Sentinel-2 L2A via l'API OData CDSE.
    Retourne une liste de dicts {id, name, date, cloud}.
    """
    lon_min = bbox["lon_min"]
    lat_min = bbox["lat_min"]
    lon_max = bbox["lon_max"]
    lat_max = bbox["lat_max"]
    wkt     = (f"POLYGON(({lon_min} {lat_min},{lon_max} {lat_min},"
               f"{lon_max} {lat_max},{lon_min} {lat_max},{lon_min} {lat_min}))")

    filtre = (
        f"Collection/Name eq 'SENTINEL-2'"
        f" and Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType'"
        f"   and att/Value eq 'S2MSI2A')"
        f" and OData.CSC.Intersects(area=geography'SRID=4326;{wkt}')"
        f" and ContentDate/Start gt {date_debut}T00:00:00.000Z"
        f" and ContentDate/Start lt {date_fin}T23:59:59.000Z"
        f" and Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover'"
        f"   and att/Value lt {float(cloud_max)})"
    )

    produits = []
    url = f"{CDSE_ODATA_URL}/Products?$filter={filtre}&$orderby=ContentDate/Start asc&$top=200&$expand=Attributes"

    while url:
        r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        for p in data.get("value", []):
            if not p.get("Online", True):
                log.debug(f"Produit hors ligne (LTA), ignoré : {p['Name'][:60]}")
                continue
            date_str = p["ContentDate"]["Start"][:10].replace("-", "")
            cloud    = next(
                (a["Value"] for a in p.get("Attributes", [])
                 if a["Name"] == "cloudCover"), 99
            )
            produits.append({"id": p["Id"], "name": p["Name"],
                             "date": date_str, "cloud": round(cloud, 1)})
        url = data.get("@odata.nextLink")

    return produits


# =============================================================================
# NAVIGATION ET TÉLÉCHARGEMENT
# =============================================================================

class _CdseSession(requests.Session):
    """Session qui préserve le header Authorization sur les redirects cross-domaine."""
    def rebuild_auth(self, prepared_request, response):
        pass  # ne pas effacer l'auth sur redirect


_session = _CdseSession()


def _recadrer_et_sauver(src_path, bbox, dest_path):
    """Recadre un JP2 (fichier disque) sur la bbox WGS84 et sauvegarde en GeoTIFF float32."""
    from rasterio.windows import from_bounds as window_from_bounds

    with rasterio.open(src_path) as src:
        if src.crs.to_epsg() != 4326:
            dst_crs = "EPSG:4326"
            transform, width, height = calculate_default_transform(
                src.crs, dst_crs, src.width, src.height, *src.bounds
            )
            data_wgs84 = np.zeros((src.count, height, width), dtype=np.float32)
            for i in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, i),
                    destination=data_wgs84[i - 1],
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=dst_crs,
                    resampling=Resampling.nearest,
                )
            win = window_from_bounds(
                bbox["lon_min"], bbox["lat_min"], bbox["lon_max"], bbox["lat_max"],
                transform
            ).intersection(rasterio.windows.Window(0, 0, width, height))
            row_off, col_off = int(win.row_off), int(win.col_off)
            n_row, n_col    = int(win.height), int(win.width)
            data_crop = data_wgs84[:, row_off:row_off+n_row, col_off:col_off+n_col]
            profil = src.profile.copy()
            profil.update(
                crs=dst_crs, dtype="float32",
                width=n_col, height=n_row,
                transform=rasterio.transform.from_bounds(
                    bbox["lon_min"], bbox["lat_min"], bbox["lon_max"], bbox["lat_max"],
                    n_col, n_row
                )
            )
        else:
            win = window_from_bounds(
                bbox["lon_min"], bbox["lat_min"], bbox["lon_max"], bbox["lat_max"],
                src.transform
            )
            data_crop = src.read(window=win).astype(np.float32)
            profil = src.profile.copy()
            profil.update(
                dtype="float32", count=src.count,
                width=data_crop.shape[2], height=data_crop.shape[1],
                transform=rasterio.transform.from_bounds(
                    bbox["lon_min"], bbox["lat_min"],
                    bbox["lon_max"], bbox["lat_max"],
                    data_crop.shape[2], data_crop.shape[1]
                )
            )

    profil.update(driver="GTiff", compress="lzw")
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(dest_path, "w", **profil) as dst:
        dst.write(data_crop)


def telecharger_bandes_produit(product_name, bbox, dest_dir, s3):
    """
    Télécharge B04, B08, SCL via S3 CDSE (boto3).
    Seuls les fichiers JP2 nécessaires sont téléchargés.
    product_name : ex. "S2A_MSIL2A_20200117T111411_N0500_R137_T30UXU_20230429T141542.SAFE"
    """
    # Chemin S3 : Sentinel-2/MSI/L2A/YYYY/MM/DD/{product.SAFE}/GRANULE/
    safe = product_name if product_name.endswith(".SAFE") else product_name + ".SAFE"
    date_str = safe.split("_")[2]  # ex. "20200117T111411"
    yyyy, mm, dd = date_str[:4], date_str[4:6], date_str[6:8]
    prefix_granule = f"Sentinel-2/MSI/L2A/{yyyy}/{mm}/{dd}/{safe}/GRANULE/"

    try:
        # Lister le dossier GRANULE pour trouver le nom du granule
        resp = s3.list_objects_v2(Bucket=CDSE_S3_BUCKET, Prefix=prefix_granule, Delimiter="/")
        granules = [p["Prefix"] for p in resp.get("CommonPrefixes", [])]
        if not granules:
            # Diagnostic : que contient le dossier date ?
            prefix_date = f"Sentinel-2/MSI/L2A/{yyyy}/{mm}/{dd}/"
            r2 = s3.list_objects_v2(Bucket=CDSE_S3_BUCKET, Prefix=prefix_date, Delimiter="/", MaxKeys=5)
            dossiers = [p["Prefix"].split("/")[-2] for p in r2.get("CommonPrefixes", [])]
            fichiers = [o["Key"].split("/")[-1] for o in r2.get("Contents", [])]
            log.warning(f"  {prefix_date} → dossiers:{dossiers} fichiers:{fichiers}")
            return False
        granule_prefix = granules[0]  # ex. ".../GRANULE/L2A_T30UXU_.../
        log.debug(f"  Granule : {granule_prefix.split('/')[-2]}")

        for bande, suffixe in BANDE_SUFFIXE.items():
            dest_f = dest_dir / f"{bande}.tif"
            if dest_f.exists():
                continue

            # Résolution : R20m pour SCL, B11, B12 — R10m pour les autres
            res = "R20m" if bande in ("SCL", "B11", "B12") else "R10m"
            prefix_img = f"{granule_prefix}IMG_DATA/{res}/"
            r2 = s3.list_objects_v2(Bucket=CDSE_S3_BUCKET, Prefix=prefix_img)
            fichier_key = next(
                (o["Key"] for o in r2.get("Contents", []) if o["Key"].endswith(suffixe)),
                None
            )
            if fichier_key is None:
                log.warning(f"  {bande} introuvable dans {prefix_img}")
                return False

            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".jp2", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                s3.download_file(CDSE_S3_BUCKET, fichier_key, tmp_path)
                _recadrer_et_sauver(tmp_path, bbox, dest_f)
            finally:
                os.unlink(tmp_path)
            log.info(f"  {bande} → {dest_f.name}")

    except Exception as e:
        log.warning(f"  Erreur S3 : {type(e).__name__}: {e}")
        return False

    return True


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline():
    creds = lire_credentials()
    user, password = creds["CDSE_USER"], creds["CDSE_PASSWORD"]
    log.info(f"Authentification CDSE pour : {user}")

    token = get_token(user, password)
    log.info("Token obtenu.")

    s3 = creer_client_s3(creds)
    log.info("Client S3 CDSE initialisé.")

    bbox = {
        "lon_min": config.BBOX_WGS84["lon_min"],
        "lat_min": config.BBOX_WGS84["lat_min"],
        "lon_max": config.BBOX_WGS84["lon_max"],
        "lat_max": config.BBOX_WGS84["lat_max"],
    }

    log.info(f"Recherche produits S2 L2A : {config.S2_DATE_DEBUT} → {config.S2_DATE_FIN} "
             f"| nuages < {config.S2_CLOUD_MAX}%")
    produits = search_products(bbox, config.S2_DATE_DEBUT, config.S2_DATE_FIN,
                               config.S2_CLOUD_MAX, token)
    log.info(f"{len(produits)} produits trouvés.")

    if not produits:
        log.error("Aucun produit trouvé — vérifiez les dates et la bbox.")
        return False

    config.S2_DIR.mkdir(parents=True, exist_ok=True)
    n_ok = 0
    n_skip = 0

    for i, produit in enumerate(produits, 1):
        date   = produit["date"]
        dest_d = config.S2_DIR / date
        dest_d.mkdir(parents=True, exist_ok=True)

        # Vérifier si déjà téléchargé
        if all((dest_d / f"{b}.tif").exists() for b in BANDES_CIBLES):
            n_skip += 1
            log.info(f"[{i}/{len(produits)}] {date} — déjà téléchargé")
            continue

        log.info(f"[{i}/{len(produits)}] {date} | nuages {produit['cloud']}% | {produit['name'][:60]}")

        # Renouvelle le token toutes les 50 images (~45 min) — pour la recherche OData
        if i % 50 == 0:
            token = get_token(user, password)
            log.info("Token renouvelé.")

        ok = telecharger_bandes_produit(produit["name"], bbox, dest_d, s3)
        erreur = not ok

        if not erreur:
            n_ok += 1
        # Pas de nettoyage : le script est résumable, les bandes réussies sont conservées

        time.sleep(0.5)  # politesse envers le serveur

    log.info("=" * 60)
    log.info(f"Téléchargement terminé : {n_ok} nouvelles dates, {n_skip} déjà présentes")
    log.info(f"Répertoire : {config.S2_DIR}")
    log.info("=" * 60)
    return n_ok + n_skip > 0


if __name__ == "__main__":
    log.info("Script 01 — Téléchargement Sentinel-2 L2A (CDSE)")
    sys.exit(0 if pipeline() else 1)
