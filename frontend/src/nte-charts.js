import { parseBeijingTime } from './calendar.js'
import { nteAssetImage } from './nte-artwork.js'
import { displayVehicleStat } from './nte-display.js'
// View-models behind the NTE cards and charts. Pure functions (no DOM), so the
// tests can pin how unknown values, zero and over-target counts are drawn.
import { percentOf } from './dashboard.js'
import catalog from './nte-icon-catalog.js'

const rows = value => (Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : [])
const label = value => (typeof value === 'string' && value.trim() ? value.trim() : '')
const known = value => typeof value === 'number' && Number.isFinite(value)

/** One gauge reading. `pct` is 0-100 and null unless both counts are known and the total is positive. */
export function gauge(current, total) {
  const pct = percentOf(current, total)
  return { current, total, pct, known: pct != null, over: pct != null && Number(current) > Number(total) }
}

/** Exploration areas with their detail lines, each as a gauge. */
export function areaViews(areas) {
  return rows(areas).map((area, index) => ({
    key: area.id ?? index, name: label(area.name), ...gauge(area.current, area.total),
    details: rows(area.details).map((entry, i) => ({ key: entry.id ?? i, name: label(entry.name), ...gauge(entry.current, entry.total) })),
  }))
}

/** Achievement ring, the three medal tiers and one gauge per category. */
export function progressView(payload) {
  const p = payload || {}
  return {
    ring: gauge(p.completed, p.total),
    medals: [['gold', '金', p.gold], ['silver', '银', p.silver], ['bronze', '铜', p.bronze]].map(([key, name, value]) => ({ key, label: name, value: known(value) ? value : null })),
    categories: rows(p.categories).map((entry, index) => ({ key: entry.id ?? index, name: label(entry.name), ...gauge(entry.current, entry.total) })),
  }
}

const QUALITY_ORDER = ['S', 'A', 'B', 'C']
const qualityRank = value => { const at = QUALITY_ORDER.indexOf(value); return at < 0 ? QUALITY_ORDER.length : at }
const byZh = (a, b) => a.localeCompare(b, 'zh-CN')

/** Roster counts by quality and by element, plus the level range of the roles that report one. */
export function roleBreakdown(entries) {
  const list = rows(entries)
  const tally = field => {
    const counts = new Map()
    for (const role of list) { const key = label(role[field]); if (key) counts.set(key, (counts.get(key) || 0) + 1) }
    return [...counts].map(([name, value]) => ({ label: name, value }))
  }
  const levels = list.map(role => role.level).filter(known)
  return {
    total: list.length,
    quality: tally('quality').sort((a, b) => qualityRank(a.label) - qualityRank(b.label) || byZh(a.label, b.label)),
    element: tally('element').sort((a, b) => b.value - a.value || byZh(a.label, b.label)),
    averageLevel: levels.length ? Math.round(levels.reduce((sum, level) => sum + level, 0) / levels.length) : null,
    maxLevel: levels.length ? Math.max(...levels) : null,
  }
}

/** Strongest first: S before A, then level, roles without a level last, then name. A copy; the source is untouched. */
export function rosterOrder(entries) {
  return rows(entries).map((role, index) => ({ role, index })).sort((a, b) => {
    const rank = qualityRank(a.role.quality) - qualityRank(b.role.quality)
    if (rank) return rank
    const x = known(a.role.level) ? a.role.level : null, y = known(b.role.level) ? b.role.level : null
    if (x !== y) return x === null ? 1 : y === null ? -1 : y - x
    return byZh(label(a.role.name), label(b.role.name)) || a.index - b.index
  }).map(item => item.role)
}

// The rating hues follow the Tajiduo community page: 1-2 lucky, 4 unlucky, 0 and 3 in between.
const TONES = { 0: 'medium', 1: 'short', 2: 'short', 3: 'medium', 4: 'long' }
const RATINGS = { 1: '超欧', 2: '欧', 3: '非', 4: '超非' }
export const gachaTone = entry => TONES[entry?.lucky_type] || 'unknown'
export const gachaRating = entry => RATINGS[entry?.lucky_type] || ''
/** The account-level luck title carries its own 1-15 code. */
export const luckTone = code => (code >= 1 && code <= 5 ? 'short' : code >= 6 && code <= 10 ? 'medium' : code >= 11 && code <= 15 ? 'long' : 'unknown')

const CDN = 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character'
/** Official art for a pull: roles by numeric id (tall portrait), arcs by `fork_` id. */
export function officialPullIcon(itemId) {
  const id = String(itemId || '')
  return /^fork_[a-zA-Z0-9_-]+$/.test(id) ? `${CDN}/fork/${id}.png` : /^\d+$/.test(id) ? `${CDN}/tall/${id}.PNG` : null
}

/** Milliseconds for a pull time; no zone means Beijing, like every time the community card shows. */
export function pullTime(value) {
  return typeof value === 'string' && value.trim() ? parseBeijingTime(value) : null
}

/** Pools, the luck split of every S pull and the newest S pulls across pools, newest first. */
export function gachaView(payload, limit = 12) {
  const p = payload || {}
  const pools = rows(p.pools).map((pool, index) => {
    const guarantee = known(pool.guarantee) && pool.guarantee > 0 ? pool.guarantee : null
    const average = known(pool.average) && pool.average >= 0 ? pool.average : null
    return {
      key: index, name: label(pool.name) || '未命名卡池', draws: known(pool.total_draws) && pool.total_draws >= 0 ? pool.total_draws : null,
      sCount: known(pool.s_count) && pool.s_count >= 0 ? pool.s_count : null, average, guarantee,
      reach: average !== null && guarantee ? gauge(average, guarantee) : null,
      entries: rows(pool.details),
    }
  })
  const tones = { short: 0, medium: 0, long: 0, unknown: 0 }
  const recent = []
  for (const pool of pools) for (const entry of pool.entries) {
    const tone = gachaTone(entry)
    tones[tone]++
    recent.push({ key: `${pool.key}:${recent.length}`, pool: pool.name, entry, tone, rating: gachaRating(entry), guarantee: pool.guarantee, time: pullTime(entry.obtained_at), order: recent.length })
  }
  recent.sort((a, b) => (b.time ?? -Infinity) - (a.time ?? -Infinity) || a.order - b.order)
  const drawsSum = pools.reduce((sum, pool) => sum + (pool.draws ?? 0), 0)
  const sSum = pools.reduce((sum, pool) => sum + (pool.sCount ?? 0), 0)
  return {
    title: typeof p.luck_title === 'string' ? p.luck_title : '', titleTone: luckTone(p.luck_type),
    totalDraws: known(p.total_draws) ? p.total_draws : pools.some(pool => pool.draws !== null) ? drawsSum : null,
    totalS: known(p.total_s) ? p.total_s : pools.some(pool => pool.sCount !== null) ? sSum : null,
    pools, tones, recent: recent.slice(0, limit), pulls: recent.length,
  }
}

const owned = value => (value === true ? true : value === false ? false : null)

/** A house card: ownership, resident ids and how much of the furniture is owned. */
export function houseView(entry) {
  const furniture = rows(entry?.furniture)
  return {
    name: label(entry?.name), owned: owned(entry?.owned), image: nteAssetImage('realestate',entry?.id),
    residents: (Array.isArray(entry?.resident_ids) ? entry.resident_ids : []).map(String),
    furnitureOwned: furniture.filter(item => item.owned === true).length, furnitureTotal: furniture.length,
  }
}

/** A vehicle card: base stats as the source wrote them, advanced stats as gauges, and whether it is the showcased one. */
export function vehicleView(entry, showId) {
  return {
    name: label(entry?.name), owned: owned(entry?.owned), image: nteAssetImage('vehicles',entry?.id),
    showcase: showId != null && showId !== '' && String(entry?.id) === String(showId),
    base: rows(entry?.base).map(stat => ({ name: label(stat.name) || '未命名属性', value: displayVehicleStat(stat) })),
    advanced: rows(entry?.advanced).map(stat => ({ name: label(stat.name) || '未命名属性', value: stat.value, maximum: stat.maximum, ...gauge(stat.value, stat.maximum) })),
    models: rows(entry?.models).length,
  }
}

let catalogById = null
/** Name and art of a catalog role by its numeric id; houses list their residents by id only. The first name per id is the canonical one. */
export function catalogRole(id) {
  catalogById ??= new Map()
  if (!catalogById.size) for (const [name, role] of Object.entries(catalog.roles)) if (!catalogById.has(String(role.id))) catalogById.set(String(role.id), { name, icon: role.icon })
  return catalogById.get(String(id)) || null
}

// Original line art (24-unit boxes, stroked) for the cover tiles of houses and vehicles.
export const GLYPHS = {
  house: 'M3.5 11.2 12 4l8.5 7.2 M5.5 9.8V20h13V9.8 M10 20v-5.2h4V20',
  car: 'M4 16.5h16 M3 16.5v-3.2l2-4.3A2 2 0 0 1 6.8 8h10.4A2 2 0 0 1 19 9l2 4.3v3.2 M7 16.5v2 M17 16.5v2 M3.5 12.5h17 M7.2 14.6h.01 M16.8 14.6h.01',
}
