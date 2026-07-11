// Construit une archive ZIP (méthode STORE, sans compression) côté navigateur.
// Les PDF sont déjà compressés : STORE évite un coût CPU/mémoire inutile et
// reste 100 % compatible (testé avec `unzip -t` + comparaison octet à octet).
//
// files : [{ name, data }]  où data est un Uint8Array (ou ArrayBuffer).
// Retourne un Blob `application/zip`.

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c >>> 0
  }
  return t
})()

function crc32(bytes) {
  let c = 0xffffffff
  for (let i = 0; i < bytes.length; i++) c = CRC_TABLE[(c ^ bytes[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

const u16 = n => new Uint8Array([n & 0xff, (n >>> 8) & 0xff])
const u32 = n => new Uint8Array([n & 0xff, (n >>> 8) & 0xff, (n >>> 16) & 0xff, (n >>> 24) & 0xff])

function concat(arrs) {
  let len = 0
  for (const a of arrs) len += a.length
  const out = new Uint8Array(len)
  let p = 0
  for (const a of arrs) { out.set(a, p); p += a.length }
  return out
}

export function buildZip(files) {
  const enc = new TextEncoder()
  const parts = []      // flux ZIP (en-têtes locaux + données)
  const central = []    // enregistrements du répertoire central
  let offset = 0        // position courante dans le flux
  const FLAG = 0x0800   // noms de fichiers en UTF-8
  const TIME = 0x0000
  const DATE = 0x0021   // 1980-01-01

  for (const f of files) {
    const data = f.data instanceof Uint8Array ? f.data : new Uint8Array(f.data)
    const name = enc.encode(f.name)
    const crc = crc32(data)
    const size = data.length

    const local = concat([
      u32(0x04034b50), u16(20), u16(FLAG), u16(0), u16(TIME), u16(DATE),
      u32(crc), u32(size), u32(size), u16(name.length), u16(0), name,
    ])
    parts.push(local, data)

    central.push(concat([
      u32(0x02014b50), u16(20), u16(20), u16(FLAG), u16(0), u16(TIME), u16(DATE),
      u32(crc), u32(size), u32(size), u16(name.length), u16(0), u16(0),
      u16(0), u16(0), u32(0), u32(offset), name,
    ]))
    offset += local.length + size
  }

  const cd = concat(central)
  const eocd = concat([
    u32(0x06054b50), u16(0), u16(0), u16(files.length), u16(files.length),
    u32(cd.length), u32(offset), u16(0),
  ])
  return new Blob([...parts, cd, eocd], { type: 'application/zip' })
}
