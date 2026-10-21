// Pure helpers that turn Wuwa payloads into chart input. Unknown stays unknown:
// a missing number never becomes a zero, and nothing here invents a maximum.
import { beijingDayStart, DAY_MS, parseBeijingTime } from './calendar.js'
import { stamp, starCount } from './wuwa-display.js'

const known = v => typeof v === 'number' && Number.isFinite(v)
const rows = v => (Array.isArray(v) ? v.filter(item => item != null) : [])

/** Experience toward the next level as { cur, max, pct }; null when the source gave neither side. */
export function expProgress(profile) {
  const cur = profile?.next_exp ?? null, max = profile?.exp_limit ?? null
  if (cur == null && max == null) return null
  const pct = known(cur) && known(max) && max > 0 ? Math.max(0, Math.min(100, Math.round((cur / max) * 100))) : 0
  return { cur, max, pct }
}

/** Whole days from today to a date, counted on Beijing calendar days; null for an unreadable date. */
export function daysUntil(value, now = Date.now()) {
  const time = parseBeijingTime(value)
  if (time == null) return null
  return Math.round((beijingDayStart(time) - beijingDayStart(now)) / DAY_MS)
}

/** "今日结束", "3 天后结束" and so on; null for an unreadable date. */
export function endLabel(value, now = Date.now()) {
  const time = parseBeijingTime(value)
  if (time == null) return null
  if (time <= now) return '已结束'
  const days = daysUntil(time, now)
  return days === 0 ? '今日结束' : days === 1 ? '明日结束' : `${days} 天后结束`
}

/** Roster counts: [{ label, value }] per attribute, most owned first; the tail beyond `limit` folds into 其他. */
export function attributeSplit(roles, limit = 6) {
  const counts = new Map()
  for (const role of rows(roles)) {
    const name = typeof role.attribute === 'string' ? role.attribute.trim() : ''
    if (name) counts.set(name, (counts.get(name) || 0) + 1)
  }
  const sorted = [...counts].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value)
  if (sorted.length <= limit) return sorted
  const rest = sorted.slice(limit - 1)
  return [...sorted.slice(0, limit - 1), { label: '其他', value: rest.reduce((sum, item) => sum + item.value, 0) }]
}

/** Roster levels in bands of ten, low to high, with empty bands between kept; unknown levels are left out. */
export function levelBands(roles) {
  const counts = new Map()
  for (const role of rows(roles)) {
    if (!known(role.level) || role.level < 0) continue
    const start = role.level >= 90 ? 90 : role.level >= 60 ? Math.floor(role.level / 10) * 10 : 0
    counts.set(start, (counts.get(start) || 0) + 1)
  }
  if (!counts.size) return []
  const label = start => (start === 0 ? '≤59' : start >= 90 ? '90+' : `${start}–${start + 9}`)
  const low = Math.min(...counts.keys()), high = Math.max(...counts.keys())
  const starts = [0, 60, 70, 80, 90].filter(start => start >= low && start <= high)
  return starts.map(start => ({ label: label(start), value: counts.get(start) || 0 }))
}

/** Headline numbers for the roster card. */
export function rosterSummary(roles) {
  const list = rows(roles)
  const stars = star => list.filter(role => starCount(role.star_level) === star).length
  return {
    total: list.length,
    five: stars(5),
    four: stars(4),
    maxLevel: list.filter(role => known(role.level) && role.level >= 90).length,
    fullChain: list.filter(role => known(role.chain) && role.chain >= 6).length,
  }
}

/** Stars over a list of tower areas: what was earned, the cap when every area states one, and whether anything is known. */
export function towerTotals(areas) {
  const list = rows(areas)
  const earned = list.filter(area => known(area.star))
  const capped = list.length > 0 && list.every(area => known(area.max_star))
  return {
    got: earned.length ? earned.reduce((sum, area) => sum + area.star, 0) : null,
    cap: capped ? list.reduce((sum, area) => sum + area.max_star, 0) : null,
  }
}

const roster = entry => rows(entry?.role_list || entry?.roles)
const isFull = (got, cap) => known(got) && known(cap) && cap > 0 && got >= cap

/** The deep zone (难度 3) of a tower's difficulty list. */
export const deepZone = difficulties => rows(difficulties).find(zone => String(zone.difficulty) === '3')

/**
 * Floors of a tower zone: how many are listed and how many are at full stars, or null when
 * it lists none. A floor is full when its own stars reach its cap, or its area is full; when
 * any floor cannot be told either way the full count is unknown (null), never a guess.
 */
export function towerFloors(zone) {
  const areas = rows(zone?.tower_area_list)
  let total = 0, full = 0, unknown = false
  for (const area of areas) {
    for (const floor of rows(area.floor_list)) {
      total++
      if (isFull(floor.star, floor.max_star) || isFull(area.star, area.max_star)) full++
      else if (!known(floor.star) || !known(floor.max_star)) unknown = true
    }
  }
  return total ? { full: unknown ? null : full, total } : null
}

/**
 * The team of the deepest floor that names one: the last area, then the highest floor
 * number, as { area, floor, roles } with at most `limit` roles; null when no floor has a team.
 */
export function towerTeam(zone, limit = 3) {
  let best = null
  rows(zone?.tower_area_list).forEach((area, a) => rows(area.floor_list).forEach((floor, i) => {
    const roles = roster(floor)
    const number = Number(floor.floor ?? floor.floor_index)
    const depth = [a, Number.isFinite(number) ? number : i]
    if (roles.length && (!best || depth[0] > best.depth[0] || (depth[0] === best.depth[0] && depth[1] >= best.depth[1])))
      best = { depth, area: area.area_name || `区域 ${a + 1}`, floor: floor.floor ?? floor.floor_index ?? null, roles: roles.slice(0, limit) }
  }))
  return best && { area: best.area, floor: best.floor, roles: best.roles }
}

/** Star totals of every zone but the deep one, in source order; zones without earned stars are left out. */
export function otherZoneStars(difficulties) {
  return rows(difficulties)
    .filter(zone => String(zone.difficulty) !== '3')
    .map(zone => ({ name: zone.difficulty_name || `分区 ${zone.difficulty ?? '未知'}`, ...towerTotals(zone.tower_area_list) }))
    .filter(zone => zone.got != null)
}

// Slash ranks from best to worst; a rank outside this list is unknown and never compared.
const RANKS = ['SSS', 'SS', 'S', 'A', 'B', 'C', 'D']

/** The best rank among a zone's challenges (SSS > SS > S > A > B > C > D); null when none is known. */
export function bestRank(challenges) {
  const found = rows(challenges)
    .map(challenge => RANKS.indexOf(typeof challenge.rank === 'string' ? challenge.rank.trim().toUpperCase() : ''))
    .filter(index => index >= 0)
  return found.length ? RANKS[Math.min(...found)] : null
}

/**
 * Sources of an income report as donut parts, largest first; a source without a number
 * reads as unknown. Beyond `limit` rows the smaller known sources fold into 其他, whose
 * total stays known (zero included), and the sources without a number keep one row of
 * their own, so none drops out of the legend.
 */
export function sourceShares(sources, limit = 6) {
  const parts = rows(sources).map(row => ({ label: row.type || '未知来源', value: known(row.num) ? row.num : null }))
  const counted = parts.filter(part => part.value != null).sort((a, b) => b.value - a.value)
  const unknown = parts.filter(part => part.value == null)
  if (parts.length <= limit) return [...counted, ...unknown]
  const unknownRows = unknown.length > 1 ? [{ label: `数量未知的来源（${unknown.length} 项）`, value: null }] : unknown
  const keep = counted.slice(0, Math.max(0, limit - unknownRows.length - 1))
  const rest = counted.slice(keep.length)
  const folded = rest.length ? [{ label: '其他', value: rest.reduce((sum, part) => sum + part.value, 0) }] : []
  return [...keep, ...folded, ...unknownRows]
}

/** Rarity counts over every pool, five stars first; empty buckets are left out. */
export function rarityTotals(pools) {
  const totals = new Map()
  for (const pool of rows(pools)) {
    for (const [rarity, count] of Object.entries(pool.rarity_distribution || {})) {
      if (known(count) && count > 0) totals.set(rarity, (totals.get(rarity) || 0) + count)
    }
  }
  const order = rarity => (rarity === 'unknown' ? -1 : Number(rarity))
  return [...totals].map(([rarity, value]) => ({ rarity, value })).sort((a, b) => order(b.rarity) - order(a.rarity))
}

/** Pulls per pool in the order the archive lists the pools; an unknown total keeps its slot. */
export function poolPulls(pools) {
  return rows(pools).map(pool => ({ label: pool.name || `卡池 ${pool.pool ?? '未知'}`, value: known(pool.total) ? pool.total : null }))
}

/**
 * The newest five-star records first, as many as `limit`. Times are compared as instants (a
 * time without an offset is Beijing time), so archives that keep different offsets still sort
 * by when the pull happened; an unreadable time sorts last and equal times keep their order.
 */
export function recentGold(records, limit = 12) {
  return rows(records)
    .map((row, index) => ({ row, index, at: parseBeijingTime(row.time) }))
    .sort((a, b) => (a.at == null) - (b.at == null) || (b.at ?? 0) - (a.at ?? 0) || a.index - b.index)
    .slice(0, limit)
    .map(item => item.row)
}

/** A pity ring only when the count is exact and the user's rule says how far the cap is. */
export function pityGauge(pity) {
  if (pity?.status !== 'exact' || !known(pity.count) || !known(pity.hard_pity_remaining)) return null
  return { value: pity.count, max: pity.count + pity.hard_pity_remaining }
}

const observed = item => parseBeijingTime(item?.observed_at)

/** The role a history record is about. */
export const historySubject = item => String(item?.subject ?? item?.payload?.role_id ?? '')

/**
 * Role level over time for every role seen at least twice: a Map from the role to
 * its points in time order and the id of its newest record (the one that carries
 * the chart). A single observation draws nothing.
 */
export function levelSeries(items) {
  const bySubject = new Map()
  for (const item of rows(items)) {
    const level = item.payload?.level ?? item.payload?.data?.role?.level ?? item.payload?.role?.level
    const at = observed(item)
    if (!known(level) || at == null) continue
    const key = historySubject(item)
    bySubject.set(key, [...(bySubject.get(key) || []), { at, id: item.id, label: stamp(item.observed_at), value: level }])
  }
  const series = new Map()
  for (const [key, points] of bySubject) {
    if (points.length < 2) continue
    points.sort((a, b) => a.at - b.at)
    series.set(key, { id: points.at(-1).id, points: points.map(({ label, value }) => ({ label, value })) })
  }
  return series
}

/** Stars in the deep zone per season, oldest first; seasons without a known total are left out. */
export function seasonStars(items) {
  return rows(items)
    .map(item => {
      const zone = rows(item.payload?.difficulty_list).find(z => String(z.difficulty) === '3')
      const { got } = towerTotals(zone?.tower_area_list)
      const at = parseBeijingTime(item.season)
      return got == null || at == null ? null : { at, label: stamp(item.season).slice(5, 10), value: got }
    })
    .filter(Boolean)
    .sort((a, b) => a.at - b.at)
    .map(({ label, value }) => ({ label, value }))
}
