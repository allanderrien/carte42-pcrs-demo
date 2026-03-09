import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'
import { spawn } from 'child_process'
import proj4 from 'proj4'
import { read as shpRead } from 'shapefile'

// Résolution robuste du répertoire courant (compatible CJS/ESM/Windows)
const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Définition proj4 Lambert 93
const L93 = '+proj=lcc +lat_0=46.5 +lon_0=3 +lat_1=49 +lat_2=44 +x_0=700000 +y_0=6600000 +ellps=GRS80 +towgs84=0,0,0,0,0,0,0 +units=m +no_defs'

const PROJECT_ROOT = path.resolve(__dirname, '..')
const EMPRISE_DIR  = path.resolve(__dirname, '../data/emprise')

// Détecte automatiquement l'exécutable Python :
// 1. .venv/Scripts/python.exe (Windows venv dans le projet)
// 2. .venv/bin/python         (Linux/Mac venv)
// 3. 'python' système
function detectPython() {
  const candidates = [
    path.join(PROJECT_ROOT, '.venv', 'Scripts', 'python.exe'),
    path.join(PROJECT_ROOT, '.venv', 'bin', 'python'),
  ]
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      console.log(`[carte42] Python détecté : ${p}`)
      return p
    }
  }
  console.log('[carte42] Python : utilisation du python système')
  return 'python'
}

const PYTHON_BIN = detectPython()

// ── Pipeline runner ───────────────────────────────────────────────────────────

const SCRIPTS = {
  '1': 'processing/01_download_sentinel2.py',
  '2': 'processing/02_ndvi_timeseries.py',
  '3': 'processing/03_change_detection.py',
  '4': 'processing/04_export_results.py',
}

// État partagé entre les middlewares
const running     = new Map()   // step → ChildProcess
const logBuffers  = new Map()   // step → string[] (50 dernières lignes pour late joiners)
const subscribers = new Map()   // step → Set<res> (clients SSE connectés)

function pushLog(step, line) {
  if (!logBuffers.has(step))  logBuffers.set(step, [])
  if (!subscribers.has(step)) subscribers.set(step, new Set())
  const buf = logBuffers.get(step)
  buf.push(line)
  if (buf.length > 200) buf.shift()   // garde les 200 dernières lignes
  // Broadcast aux clients SSE connectés
  for (const res of subscribers.get(step)) {
    res.write(`data: ${JSON.stringify(line)}\n\n`)
  }
}

function broadcastEvent(step, event, payload) {
  if (!subscribers.has(step)) return
  for (const res of subscribers.get(step)) {
    res.write(`event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`)
  }
}

// Cache mémoire par chemin shapefile
const _cache = {}

/** Reprojette récursivement les coordonnées d'une géométrie GeoJSON L93 → WGS84 */
function reprojecterGeometrie(geom) {
  if (!geom) return geom
  const conv = ([x, y]) => proj4(L93, 'EPSG:4326', [x, y])
  const ring  = coords => coords.map(conv)
  const rings = coords => coords.map(ring)
  switch (geom.type) {
    case 'Point':           return { ...geom, coordinates: conv(geom.coordinates) }
    case 'LineString':
    case 'MultiPoint':      return { ...geom, coordinates: ring(geom.coordinates) }
    case 'Polygon':
    case 'MultiLineString': return { ...geom, coordinates: rings(geom.coordinates) }
    case 'MultiPolygon':    return { ...geom, coordinates: geom.coordinates.map(rings) }
    case 'GeometryCollection':
      return { ...geom, geometries: geom.geometries.map(reprojecterGeometrie) }
    default: return geom
  }
}

/** Lit et reprojette un shapefile, avec cache mémoire */
async function lireShapefile(shpPath, dbfPath) {
  if (_cache[shpPath]) return _cache[shpPath]

  console.log(`[carte42] Lecture shapefile : ${shpPath}`)

  if (!fs.existsSync(shpPath)) {
    throw new Error(`Shapefile introuvable : ${shpPath}`)
  }

  const collection = await shpRead(shpPath, dbfPath, { encoding: 'utf-8' })
  collection.features = collection.features.map(f => ({
    ...f,
    geometry: reprojecterGeometrie(f.geometry),
  }))

  console.log(`[carte42] ${shpPath} → ${collection.features.length} feature(s) chargée(s)`)
  _cache[shpPath] = collection
  return collection
}

/** Crée un handler middleware connect pour servir un shapefile en GeoJSON */
function serveShapefile(shpPath, dbfPath) {
  return (req, res) => {
    lireShapefile(shpPath, dbfPath)
      .then(geojson => {
        res.setHeader('Content-Type', 'application/json')
        res.setHeader('Cache-Control', 'no-cache')
        res.end(JSON.stringify(geojson))
      })
      .catch(err => {
        console.error(`[carte42] Erreur shapefile : ${err.message}`)
        res.statusCode = 500
        res.setHeader('Content-Type', 'application/json')
        res.end(JSON.stringify({ error: err.message }))
      })
  }
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'serve-pipeline-outputs',
      configureServer(server) {

        console.log(`[carte42] EMPRISE_DIR  = ${EMPRISE_DIR}`)
        console.log(`[carte42] PROJECT_ROOT = ${PROJECT_ROOT}`)
        console.log(`[carte42] IGN WMS      = https://data.geopf.fr/wms-r/wms`)

        // ── POST /api/run/:step — Lance un script Python ──────────────────
        server.middlewares.use('/api/run', (req, res) => {
          if (req.method !== 'POST') { res.statusCode = 405; res.end(); return }

          const step = req.url.replace(/^\//, '')  // '/1' → '1'
          const script = SCRIPTS[step]

          if (!script) {
            res.statusCode = 400
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ error: `Étape inconnue : ${step}` }))
            return
          }

          if (running.has(step)) {
            res.statusCode = 409
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ error: `Étape ${step} déjà en cours` }))
            return
          }

          // Lit le body JSON pour récupérer la bbox de test éventuelle
          let body = ''
          req.on('data', chunk => { body += chunk })
          req.on('end', () => {
            let testEnv = {}
            try {
              const params = body ? JSON.parse(body) : {}
              if (params.bbox) {
                const { lonMin, latMin, lonMax, latMax } = params.bbox
                const [xmin, ymin] = proj4('EPSG:4326', L93, [lonMin, latMin])
                const [xmax, ymax] = proj4('EPSG:4326', L93, [lonMax, latMax])
                testEnv = {
                  TEST_XMIN: String(Math.min(xmin, xmax)),
                  TEST_YMIN: String(Math.min(ymin, ymax)),
                  TEST_XMAX: String(Math.max(xmin, xmax)),
                  TEST_YMAX: String(Math.max(ymin, ymax)),
                }
                pushLog(step, `  Zone de test : L93 [${Math.round(xmin)}, ${Math.round(ymin)}, ${Math.round(xmax)}, ${Math.round(ymax)}]`)
              }
            } catch (_) {}

          // Réinitialise le buffer de logs pour cette étape
          logBuffers.set(step, [])
          pushLog(step, `▶ Lancement : python ${script}`)
          pushLog(step, `  Répertoire : ${PROJECT_ROOT}`)
          pushLog(step, '─'.repeat(60))

          const proc = spawn(PYTHON_BIN, [script], {
            cwd: PROJECT_ROOT,
            env: { ...process.env, PYTHONUNBUFFERED: '1', ...testEnv },
          })

          running.set(step, proc)
          broadcastEvent(step, 'start', { step })

          proc.stdout.on('data', chunk => {
            String(chunk).split('\n').filter(Boolean).forEach(l => pushLog(step, l))
          })
          proc.stderr.on('data', chunk => {
            String(chunk).split('\n').filter(Boolean).forEach(l => pushLog(step, `⚠ ${l}`))
          })
          proc.on('close', code => {
            running.delete(step)
            const msg = code === 0
              ? `✓ Terminé avec succès (code ${code})`
              : `✗ Erreur (code ${code})`
            pushLog(step, '─'.repeat(60))
            pushLog(step, msg)
            broadcastEvent(step, 'done', { step, code })
            console.log(`[carte42] Étape ${step} terminée — code ${code}`)
          })
          proc.on('error', err => {
            running.delete(step)
            pushLog(step, `✗ Impossible de lancer Python : ${err.message}`)
            pushLog(step, `  → Exécutable utilisé : ${PYTHON_BIN}`)
            pushLog(step, '  → Créez un .venv ou vérifiez que python est dans le PATH')
            broadcastEvent(step, 'done', { step, code: -1 })
          })

          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ ok: true, step, script }))
          }) // end req.on('end')
        })

        // ── POST /api/stop/:step — Arrête un script en cours ─────────────
        server.middlewares.use('/api/stop', (req, res) => {
          if (req.method !== 'POST') { res.statusCode = 405; res.end(); return }

          const step = req.url.replace(/^\//, '')
          const proc = running.get(step)

          if (!proc) {
            res.statusCode = 404
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ error: `Aucun processus en cours pour l'étape ${step}` }))
            return
          }

          pushLog(step, '─'.repeat(60))
          pushLog(step, '⚠ Arrêt demandé par l\'utilisateur…')

          // Sur Windows, kill() envoie SIGTERM mais ne termine pas toujours les
          // sous-processus. On force avec taskkill /F /T (termine l'arbre complet).
          if (process.platform === 'win32') {
            spawn('taskkill', ['/pid', String(proc.pid), '/f', '/t'])
          } else {
            proc.kill('SIGTERM')
          }

          running.delete(step)
          broadcastEvent(step, 'done', { step, code: -2 })

          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ ok: true, step }))
        })

        // ── GET /api/logs/:step — SSE stream des logs ─────────────────────
        server.middlewares.use('/api/logs', (req, res) => {
          const step = req.url.replace(/^\//, '')

          res.setHeader('Content-Type',  'text/event-stream')
          res.setHeader('Cache-Control', 'no-cache')
          res.setHeader('Connection',    'keep-alive')
          res.setHeader('Access-Control-Allow-Origin', '*')
          res.flushHeaders?.()

          // Rejoue le buffer existant pour les late joiners
          const buf = logBuffers.get(step) ?? []
          for (const line of buf) {
            res.write(`data: ${JSON.stringify(line)}\n\n`)
          }

          // Si le script est encore en cours, indique l'état
          if (running.has(step)) {
            res.write(`event: start\ndata: ${JSON.stringify({ step })}\n\n`)
          }

          if (!subscribers.has(step)) subscribers.set(step, new Set())
          subscribers.get(step).add(res)

          req.on('close', () => {
            subscribers.get(step)?.delete(res)
          })
        })

        // ── GET /api/running — Étapes en cours ───────────────────────────
        server.middlewares.use('/api/running', (req, res) => {
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ running: [...running.keys()] }))
        })

        // Diagnostic : affiche les chemins résolus au démarrage

        // ── GET /api/s2/layers — liste des années disponibles ────────────
        server.middlewares.use('/api/s2/layers', (req, res) => {
          const ndviDir = path.resolve(__dirname, '../data/processed/s2_ndvi')
          let years = []
          try {
            years = fs.readdirSync(ndviDir)
              .filter(f => /^\d{4}_composite\.png$/.test(f))
              .map(f => f.slice(0, 4))
              .sort()
          } catch (_) {}
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          res.end(JSON.stringify({ years }))
        })

        // ── GET /api/s2/composite/:year — PNG colorisé NDVI annuel ────────
        server.middlewares.use('/api/s2/composite', (req, res) => {
          const year     = req.url.replace(/^\//, '')
          const filePath = path.resolve(__dirname, `../data/processed/s2_ndvi/${year}_composite.png`)
          if (fs.existsSync(filePath)) {
            res.setHeader('Content-Type', 'image/png')
            res.setHeader('Cache-Control', 'no-cache')
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end()
          }
        })

        // ── GET /api/pc-logements — Permis de construire logements (points géocodés) ─
        server.middlewares.use('/api/pc-logements', (req, res) => {
          const filePath = path.resolve(__dirname,
            '../data/registre_permis_amenager/pc_logements.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez geocode_pc_logements.py' }))
          }
        })

        // ── GET /api/permis-demolir ───────────────────────────────────────────
        server.middlewares.use('/api/permis-demolir', (req, res) => {
          const filePath = path.resolve(__dirname,
            '../data/registre_permis_amenager/permis_demolir.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez geocode_autres_permis.py' }))
          }
        })

        // ── GET /api/locaux-non-resid ─────────────────────────────────────────
        server.middlewares.use('/api/locaux-non-resid', (req, res) => {
          const filePath = path.resolve(__dirname,
            '../data/registre_permis_amenager/locaux_non_resid.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez geocode_autres_permis.py' }))
          }
        })

        // ── GET /api/osm-roads — Nouvelles voies OSM 2020-2026 ───────────────────
        server.middlewares.use('/api/osm-roads', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/nouvelles_voies_osm.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez fetch_osm_roads.py' }))
          }
        })

        // ── GET /api/osm-chantiers-termines — Chantiers terminés depuis 2021 ─────
        server.middlewares.use('/api/osm-chantiers-termines', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/chantiers_termines_osm.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez fetch_osm_construction_history.py' }))
          }
        })

        // ── GET /api/osm-construction — Voies OSM en construction ───────────────
        server.middlewares.use('/api/osm-construction', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/voies_construction_osm.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez fetch_osm_roads.py' }))
          }
        })

        // ── GET /api/osm-existantes — Réseau OSM existant (avant 2020) ──────────
        server.middlewares.use('/api/osm-existantes', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/voies_existantes_osm.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez fetch_osm_roads.py' }))
          }
        })

        // ── GET /api/lotissements — Polygones lotissements détectés ─────────────
        server.middlewares.use('/api/lotissements', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/lotissements_detectes.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez detect_lotissements.py' }))
          }
        })

        // ── GET /api/osm-pieton — Nouveaux trottoirs/pistes cyclables OSM 2020+ ─
        server.middlewares.use('/api/osm-pieton', (req, res) => {
          const filePath = path.resolve(__dirname, '../data/osm/nouvelles_voies_pieton_osm.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez fetch_osm_roads.py' }))
          }
        })

        // ── GET /api/permis-pa — Permis d'aménager Châteaugiron (points géocodés) ─
        server.middlewares.use('/api/permis-pa', (req, res) => {
          const filePath = path.resolve(__dirname,
            '../data/registre_permis_amenager/permis_chateaugiron.geojson')
          res.setHeader('Content-Type', 'application/json')
          res.setHeader('Cache-Control', 'no-cache')
          if (fs.existsSync(filePath)) {
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.end(JSON.stringify({ error: 'Lancez geocode_permis.py' }))
          }
        })

        server.middlewares.use('/api/emprise/zone', serveShapefile(
          path.join(EMPRISE_DIR, 'emprise_zone.shp'),
          path.join(EMPRISE_DIR, 'emprise_zone.dbf'),
        ))

        server.middlewares.use('/api/emprise/voies', serveShapefile(
          path.join(EMPRISE_DIR, 'emprise_voies.shp'),
          path.join(EMPRISE_DIR, 'emprise_voies.dbf'),
        ))

        server.middlewares.use('/api/geojson', (req, res) => {
          const filePath = path.resolve(__dirname, '../output/vectors/changements_detectes.geojson')
          if (fs.existsSync(filePath)) {
            res.setHeader('Content-Type', 'application/json')
            res.setHeader('Cache-Control', 'no-cache')
            res.end(fs.readFileSync(filePath))
          } else {
            res.statusCode = 404
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify({ error: "GeoJSON introuvable. Lancez 03_change_detection.py d'abord." }))
          }
        })

        server.middlewares.use('/api/status', (req, res) => {
          // Compte les images Sentinel-2 téléchargées
          const s2Dir = path.resolve(__dirname, '../data/raw/sentinel2')
          let s2Count = 0
          try {
            s2Count = fs.readdirSync(s2Dir).filter(d =>
              fs.statSync(path.join(s2Dir, d)).isDirectory()
            ).length
          } catch (_) {}

          // Compte les NDVI calculés
          const ndviDir = path.resolve(__dirname, '../data/processed/s2_ndvi')
          let ndviCount = 0
          try { ndviCount = fs.readdirSync(ndviDir).filter(f => f.endsWith('_ndvi.tif')).length } catch (_) {}

          const files = {
            s2_images:  s2Count > 0
              ? { ok: true,  size_kb: s2Count, label: `${s2Count} dates` }
              : { ok: false },
            s2_ndvi:    ndviCount > 0
              ? { ok: true,  size_kb: ndviCount, label: `${ndviCount} NDVI` }
              : { ok: false },
            s2_change:  path.resolve(__dirname, '../data/processed/s2_change_mask.tif'),
            geojson:    path.resolve(__dirname, '../output/vectors/changements_detectes.geojson'),
            carte_html: path.resolve(__dirname, '../output/map/carte_changements.html'),
          }
          const status = {}
          for (const [key, val] of Object.entries(files)) {
            if (typeof val === 'object' && 'ok' in val) {
              status[key] = val   // déjà résolu (s2_images, s2_ndvi)
            } else {
              status[key] = fs.existsSync(val)
                ? { ok: true, size_kb: Math.round(fs.statSync(val).size / 1024) }
                : { ok: false }
            }
          }
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify(status))
        })
      }
    }
  ]
})
