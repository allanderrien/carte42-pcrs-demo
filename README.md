# Carte42 — Détection automatique de changement d'occupation du sol
## Démo technique · SDE35 / PCRS Ille-et-Vilaine

---

## Présentation du projet

**Carte42** est une démonstration de détection automatique de changements d'occupation du sol
développée dans le cadre d'un appel d'offres du **Syndicat Départemental d'Énergie 35 (SDE35)**
pour la mise en œuvre du **Plan Corps de Rue Simplifié (PCRS)** en Ille-et-Vilaine.

L'objectif est de comparer deux millésimes d'orthophotographies IGN sur une emprise test
de ~12 × 12 km centrée sur la région de **Vitré (35)** et de produire automatiquement :

- une **carte de chaleur des changements** géoréférencée ;
- des **polygones vectoriels** des zones ayant significativement évolué entre les deux dates ;
- une **carte interactive HTML** exploitable sans logiciel SIG.

---

## Méthodologie

```
Orthophoto T1 (2020)  ──┐
                         ├──► Prétraitement ──► Différence radiométrique ──► Masque binaire
Orthophoto T2 (2023)  ──┘         │                                               │
                             (normalisation,                              (seuillage, lissage
                              recalage, égalisation                       morphologique)
                              histogramme)                                         │
                                                                     Polygonisation ──► GeoJSON
                                                                                        │
                                                                              Carte interactive
```

### Étapes du pipeline

| Script | Rôle |
|--------|------|
| `01_download_ign.py` | Téléchargement des orthophotos via WMS IGN Géoportail |
| `02_preprocess.py` | Recalage spatial, normalisation radiométrique, reprojection |
| `03_change_detection.py` | Calcul de la différence, seuillage, nettoyage morphologique |
| `04_export_results.py` | Export GeoJSON, génération de la carte interactive Folium |

---

## Zone d'étude

- **Localisation** : Région de Vitré, Ille-et-Vilaine (35)
- **Emprise** : ~12 × 12 km
- **Coordonnées** (Lambert 93 / EPSG:2154) :
  - xmin = 359 373 m, ymin = 6 778 649 m
  - xmax = 370 361 m, ymax = 6 790 860 m
- **Résolution de travail** : 20 cm/pixel (téléchargement), 50 cm/pixel (détection)

---

## Installation

### Prérequis

- Python 3.10+
- pip ou conda

### Environnement virtuel

```bash
# Créer et activer l'environnement
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate.bat       # Windows

# Installer les dépendances
pip install -r requirements.txt
```

---

## Utilisation

### Exécution complète (pipeline end-to-end)

```bash
python processing/01_download_ign.py
python processing/02_preprocess.py
python processing/03_change_detection.py
python processing/04_export_results.py
```

### Exécution d'un seul script

Chaque script est autonome et peut être lancé indépendamment :

```bash
# Téléchargement uniquement
python processing/01_download_ign.py

# Vérifier les données téléchargées
ls data/raw/
```

### Résultats

Après exécution complète, les sorties se trouvent dans `output/` :

```
output/
├── vectors/changements_detectes.geojson   ← Polygones de changement
├── tiles/                                 ← Tuiles raster (si générées)
└── map/carte_changements.html             ← Carte interactive (ouvrir dans un navigateur)
```

---

## Configuration

Tous les paramètres sont centralisés dans `config.py` :

| Paramètre | Valeur par défaut | Description |
|-----------|:-----------------:|-------------|
| `RESOLUTION_CIBLE` | `0.20` m/px | Résolution des orthophotos téléchargées |
| `DETECTION_RESOLUTION` | `0.50` m/px | Résolution de travail pour la détection |
| `SEUIL_DIFFERENCE` | `30` | Seuil radiométrique (0–255) |
| `SURFACE_MIN_M2` | `50` m² | Surface minimale des polygones conservés |
| `MORPH_KERNEL_RADIUS` | `3` px | Rayon lissage morphologique |
| `TILE_SIZE_PX` | `4096` px | Taille max des tuiles WMS |

---

## Structure du projet

```
carte42-pcrs-demo/
├── data/
│   ├── raw/          ← Orthophotos téléchargées (GeoTIFF bruts)
│   ├── processed/    ← Images prétraitées et normalisées
│   └── vector/       ← Shapefiles d'emprise
├── processing/
│   ├── 01_download_ign.py
│   ├── 02_preprocess.py
│   ├── 03_change_detection.py
│   └── 04_export_results.py
├── output/
│   ├── vectors/      ← GeoJSON des zones de changement
│   ├── tiles/        ← Tuiles raster
│   └── map/          ← Carte interactive HTML
├── assets/
│   └── carte42_logo.png
├── config.py         ← Paramètres centralisés
├── requirements.txt
└── README.md
```

---

## Données sources

| Source | Description | Accès |
|--------|-------------|-------|
| IGN BD ORTHO | Orthophotos France entière, 20 cm/px | WMS public Géoportail |
| PCRS 2020–2021 | Orthophoto très haute résolution SDE35, 5 cm/px | Données internes SDE35 |

---

## Licence & contact

Développé par **Carte42** dans le cadre d'une réponse à appel d'offres SDE35.
Données IGN © Institut national de l'information géographique et forestière.

---

*Dernière mise à jour : mars 2026*
