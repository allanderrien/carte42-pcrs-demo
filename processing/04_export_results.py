"""
04_export_results.py — Génération de la carte interactive et exports finaux
Projet Carte42 / PCRS Ille-et-Vilaine — SDE35

Produit :
  - Carte interactive HTML (Folium) avec :
      * Fond de plan OSM + Géoportail IGN
      * Couche WMS orthophoto T1 (2020)
      * Couche WMS orthophoto T2 (2023)
      * Polygones de changement (colorés par classe, cliquables)
      * Légende, contrôle des couches, miniature de localisation
  - Statistiques globales dans les logs

Usage :
  python processing/04_export_results.py
"""

import sys
import logging
import json
from pathlib import Path

import geopandas as gpd
import folium
from folium import plugins
from folium.plugins import MeasureControl, Fullscreen, MiniMap

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# =============================================================================
# LOGGER
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("04_export")


# =============================================================================
# STYLE DES POLYGONES
# =============================================================================

def style_polygone(feature: dict) -> dict:
    """
    Retourne le style Folium d'un polygone selon sa classe de changement.
    """
    classe = feature["properties"].get("classe", "modere")
    couleur = (
        config.COULEUR_CHANGEMENT_FORT
        if classe == "fort"
        else config.COULEUR_CHANGEMENT_MOYEN
    )
    return {
        "fillColor":   couleur,
        "color":       couleur,
        "weight":      1.5,
        "fillOpacity": config.OPACITE_VECTEUR,
    }


def style_survol(feature: dict) -> dict:
    """Style au survol (highlight)."""
    return {
        "fillColor": "#ffffff",
        "color":     "#2c3e50",
        "weight":    2.5,
        "fillOpacity": 0.85,
    }


# =============================================================================
# CONSTRUCTION DE LA CARTE
# =============================================================================

def construire_carte(gdf: gpd.GeoDataFrame) -> folium.Map:
    """
    Construit la carte Folium complète.

    Args:
        gdf : GeoDataFrame des zones de changement (en WGS84)

    Returns:
        Objet folium.Map prêt à être exporté en HTML.
    """
    # ------------------------------------------------------------------ #
    # Carte de base centrée sur la zone d'étude
    # ------------------------------------------------------------------ #
    carte = folium.Map(
        location=config.CENTER_WGS84,
        zoom_start=13,
        tiles=None,              # On ajoute les fonds manuellement
        control_scale=True,
    )

    # ------------------------------------------------------------------ #
    # Fonds de plan
    # ------------------------------------------------------------------ #
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="OpenStreetMap",
        show=True,
    ).add_to(carte)

    folium.TileLayer(
        tiles=(
            "https://wxs.ign.fr/essentiels/geoportail/wmts?"
            "SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
            "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2"
            "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
            "&STYLE=normal&FORMAT=image/png"
        ),
        attr="IGN-F/Géoportail",
        name="Plan IGN",
        show=False,
        overlay=False,
        control=True,
    ).add_to(carte)

    # ------------------------------------------------------------------ #
    # Couche WMS orthophoto T1 (millésime ancien)
    # ------------------------------------------------------------------ #
    folium.WmsTileLayer(
        url=config.IGN_WMS_URL,
        name=f"Orthophoto {config.MILLESIME_ANCIEN} (T1 référence)",
        layers=config.IGN_LAYER_ORTHO,
        fmt="image/png",
        transparent=True,
        version=config.WMS_VERSION,
        attr="IGN-F/Géoportail",
        show=False,
        overlay=True,
        control=True,
        opacity=config.OPACITE_RASTER,
    ).add_to(carte)

    # ------------------------------------------------------------------ #
    # Couche WMS orthophoto T2 (millésime récent)
    # ------------------------------------------------------------------ #
    folium.WmsTileLayer(
        url=config.IGN_WMS_URL,
        name=f"Orthophoto {config.MILLESIME_RECENT} (T2 actuel)",
        layers=config.IGN_LAYER_ORTHO,
        fmt="image/png",
        transparent=True,
        version=config.WMS_VERSION,
        attr="IGN-F/Géoportail",
        show=True,
        overlay=True,
        control=True,
        opacity=config.OPACITE_RASTER,
    ).add_to(carte)

    # ------------------------------------------------------------------ #
    # Couche emprise de la zone d'étude
    # ------------------------------------------------------------------ #
    emprise_coords = [
        [config.BBOX_WGS84["lat_min"], config.BBOX_WGS84["lon_min"]],
        [config.BBOX_WGS84["lat_max"], config.BBOX_WGS84["lon_max"]],
    ]
    folium.Rectangle(
        bounds=emprise_coords,
        color="#2c3e50",
        weight=2,
        fill=False,
        dash_array="8 4",
        tooltip="Zone d'étude (~12 × 12 km)",
        name="Emprise zone d'étude",
    ).add_to(carte)

    # ------------------------------------------------------------------ #
    # Polygones de changement
    # ------------------------------------------------------------------ #
    if len(gdf) > 0:
        couche_changements = folium.FeatureGroup(
            name=f"Changements détectés ({len(gdf)} zones)",
            show=True,
        )

        folium.GeoJson(
            gdf.__geo_interface__,
            style_function=style_polygone,
            highlight_function=style_survol,
            tooltip=folium.GeoJsonTooltip(
                fields=["surface_m2", "ampl_moy", "ampl_max", "classe"],
                aliases=["Surface (m²)", "Amplitude moy.", "Amplitude max.", "Classe"],
                localize=True,
                sticky=True,
                labels=True,
            ),
            popup=folium.GeoJsonPopup(
                fields=["surface_m2", "ampl_moy", "ampl_max", "classe"],
                aliases=["Surface (m²)", "Amplitude moyenne", "Amplitude max", "Classe"],
                max_width=300,
            ),
            name="Changements détectés",
        ).add_to(couche_changements)

        couche_changements.add_to(carte)
    else:
        log.warning("Aucun polygone de changement à afficher sur la carte.")

    # ------------------------------------------------------------------ #
    # Plugins
    # ------------------------------------------------------------------ #
    Fullscreen(
        position="topright",
        title="Plein écran",
        title_cancel="Quitter le plein écran",
    ).add_to(carte)

    MeasureControl(
        position="topleft",
        primary_length_unit="meters",
        secondary_length_unit="kilometers",
        primary_area_unit="sqmeters",
        secondary_area_unit="hectares",
    ).add_to(carte)

    MiniMap(
        tile_layer="OpenStreetMap",
        position="bottomright",
        width=150,
        height=150,
        toggle_display=True,
    ).add_to(carte)

    # ------------------------------------------------------------------ #
    # Contrôle des couches
    # ------------------------------------------------------------------ #
    folium.LayerControl(position="topright", collapsed=False).add_to(carte)

    # ------------------------------------------------------------------ #
    # Légende HTML personnalisée
    # ------------------------------------------------------------------ #
    legende_html = _construire_legende_html(gdf)
    carte.get_root().html.add_child(folium.Element(legende_html))

    # Titre dans la page
    titre_html = f"""
    <div style="
        position: fixed;
        top: 10px; left: 50%;
        transform: translateX(-50%);
        z-index: 1000;
        background: rgba(255,255,255,0.93);
        padding: 8px 20px;
        border-radius: 6px;
        border-left: 5px solid #e74c3c;
        font-family: 'Segoe UI', sans-serif;
        font-size: 15px;
        font-weight: 600;
        color: #2c3e50;
        box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        pointer-events: none;
    ">
        {config.TITRE_CARTE}
    </div>
    """
    carte.get_root().html.add_child(folium.Element(titre_html))

    return carte


def _construire_legende_html(gdf: gpd.GeoDataFrame) -> str:
    """
    Génère le HTML de la légende flottante.
    """
    n_fort   = int((gdf["classe"] == "fort").sum())   if len(gdf) > 0 else 0
    n_modere = int((gdf["classe"] == "modere").sum()) if len(gdf) > 0 else 0
    surface_ha = gdf["surface_m2"].sum() / 1e4         if len(gdf) > 0 else 0.0

    return f"""
    <div style="
        position: fixed;
        bottom: 40px; left: 15px;
        z-index: 1000;
        background: rgba(255,255,255,0.95);
        padding: 14px 18px;
        border-radius: 8px;
        border-top: 4px solid #2c3e50;
        font-family: 'Segoe UI', sans-serif;
        font-size: 13px;
        color: #2c3e50;
        box-shadow: 0 2px 10px rgba(0,0,0,0.18);
        min-width: 220px;
    ">
        <div style="font-weight:700; font-size:14px; margin-bottom:10px;">
            Légende — Changements détectés
        </div>

        <div style="display:flex; align-items:center; margin-bottom:6px;">
            <div style="width:16px;height:16px;border-radius:3px;
                        background:{config.COULEUR_CHANGEMENT_FORT};
                        margin-right:8px; flex-shrink:0;"></div>
            <span>Changement fort ({n_fort} zones)</span>
        </div>

        <div style="display:flex; align-items:center; margin-bottom:6px;">
            <div style="width:16px;height:16px;border-radius:3px;
                        background:{config.COULEUR_CHANGEMENT_MOYEN};
                        margin-right:8px; flex-shrink:0;"></div>
            <span>Changement modéré ({n_modere} zones)</span>
        </div>

        <div style="display:flex; align-items:center; margin-bottom:12px;">
            <div style="width:16px;height:16px;border-radius:3px;
                        background:transparent;
                        border:2px dashed #2c3e50;
                        margin-right:8px; flex-shrink:0;"></div>
            <span>Emprise zone d'étude</span>
        </div>

        <div style="border-top:1px solid #ddd; padding-top:8px; font-size:12px; color:#555;">
            Surface totale changée : <b>{surface_ha:.1f} ha</b><br>
            Millésimes : <b>{config.MILLESIME_ANCIEN}</b> → <b>{config.MILLESIME_RECENT}</b><br>
            Résolution détection : <b>{config.DETECTION_RESOLUTION} m/px</b>
        </div>

        <div style="margin-top:8px; font-size:11px; color:#888;">
            © IGN Géoportail · Carte42 / SDE35
        </div>
    </div>
    """


# =============================================================================
# PIPELINE PRINCIPAL
# =============================================================================

def pipeline_export() -> bool:
    """
    Charge les résultats et génère la carte interactive.
    """
    log.info("=" * 60)
    log.info("ÉTAPE 1 — Chargement du GeoJSON de changements")
    log.info("=" * 60)

    if not config.GEOJSON_CHANGEMENTS.exists():
        log.error(
            f"GeoJSON introuvable : {config.GEOJSON_CHANGEMENTS}\n"
            f"→ Lancez d'abord : python processing/03_change_detection.py"
        )
        return False

    gdf = gpd.read_file(config.GEOJSON_CHANGEMENTS)
    log.info(f"{len(gdf)} polygone(s) chargé(s), CRS={gdf.crs}")

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        log.info("Reprojection en WGS84...")
        gdf = gdf.to_crs("EPSG:4326")

    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("ÉTAPE 2 — Construction de la carte interactive")
    log.info("=" * 60)

    carte = construire_carte(gdf)

    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("ÉTAPE 3 — Export HTML")
    log.info("=" * 60)

    config.MAP_OUT.mkdir(parents=True, exist_ok=True)
    carte.save(str(config.HTML_CARTE))

    taille_ko = config.HTML_CARTE.stat().st_size / 1024
    log.info(f"Carte sauvegardée : {config.HTML_CARTE} ({taille_ko:.0f} Ko)")
    log.info(f"→ Ouvrir dans un navigateur : file:///{config.HTML_CARTE}")

    # ------------------------------------------------------------------ #
    log.info("=" * 60)
    log.info("STATISTIQUES FINALES")
    log.info("=" * 60)

    if len(gdf) > 0:
        emprise_m2 = (
            (config.BBOX_L93["xmax"] - config.BBOX_L93["xmin"])
            * (config.BBOX_L93["ymax"] - config.BBOX_L93["ymin"])
        )
        surface_totale = gdf.to_crs("EPSG:2154")["geometry"].area.sum()
        pct = surface_totale / emprise_m2 * 100

        log.info(f"Polygones totaux       : {len(gdf)}")
        log.info(f"Surface changée        : {surface_totale / 1e4:.2f} ha")
        log.info(f"Part de l'emprise      : {pct:.2f}%")
        log.info(f"Changements forts      : {(gdf['classe']=='fort').sum()}")
        log.info(f"Changements modérés    : {(gdf['classe']=='modere').sum()}")
    else:
        log.info("Aucun changement détecté sur la zone d'étude.")

    return True


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    log.info("Script 04 — Export carte interactive et résultats finaux")

    succes = pipeline_export()
    sys.exit(0 if succes else 1)
