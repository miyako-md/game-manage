import iconCatalog from './endfield-icon-catalog.js'
import { shipReport } from './endfield-ship.js'
import { parseBeijingTime } from './calendar.js'
import { newestFirst } from './role-order.js'

// Display helpers. Report calculations belong to the shared backend projection.
export const rows = value => Array.isArray(value) ? value : []
export const displayValue = value => value == null || value === '' || typeof value === 'number' && !Number.isFinite(value) ? '未知' : String(value)
export const sourceName = value => typeof value === 'object' && value !== null ? displayValue(value.name ?? value.value ?? value.key) : displayValue(value)

export function profileReport(payload) {
  if (payload?.report?.schema_version === 1) return { ...payload.report,
    honor: categorizedHonor(payload.report.honor, payload), regions: labeledRegions(payload.report.regions),
    ship: shipReport(payload.report.ship, payload.report.training?.items || payload.operators) }
  // Previously saved profiles remain readable until their next normal refresh.
  return {
    observed_at: payload?.observed_at,
    overview: { base: payload?.base, stamina: payload?.stamina, progress: rows(payload?.progress), todos: null },
    training: { items: rows(payload?.operators), summary: { listed_count: rows(payload?.operators).length || null } },
    regions: labeledRegions({ items: rows(payload?.regions), summary: { region_count: rows(payload?.regions).length || null } }),
    ship: shipReport({ rooms: rows(payload?.ship), available: payload?.availability?.ship ?? (rows(payload?.ship).length ? true : null),
      summary: { room_count: payload?.availability?.ship === false ? null : payload?.availability?.ship === true || rows(payload?.ship).length ? rows(payload?.ship).length : null } }, payload?.operators),
    honor: honorReport(payload),
  }
}

const areaNames = {map01_lv001:'枢纽区',map01_lv002:'谷地通道',map01_lv003:'阿伯莉采石场',
  map01_lv005:'源石研究园',map01_lv006:'矿脉源区',map01_lv007:'供能高地',
  map02_lv001:'景玉谷',map02_lv002:'武陵城',map02_lv003:'清波寨'}

function labeledRegions(report) {
  if (!report) return report
  return {...report,items:rows(report.items).map(region=>{
    const levels=rows(region.levels), collections=rows(region.collections)
    const areas=Array.isArray(region.areas) ? region.areas : [...levels,...collections
      .filter(item=>!levels.some(level=>level.id===item.level_id)).map(item=>({id:item.level_id,name:item.name,
        chests:{count:item.chest_count},puzzles:{count:item.puzzle_count},blackboxes:{count:item.blackbox_count},
        equipment_chests:{count:item.equipment_chest_count},pieces:{count:item.piece_count}}))]
    return {...region,money:region.money ? {...region.money,count:region.money.count ?? region.money.conut} : region.money,areas:areas.map(area=>({...area,name:
      levels.find(level=>level.id===area.id)?.name || collections.find(item=>item.level_id===area.id)?.name ||
      area.name || areaNames[area.id] || area.id}))}
  })}
}

// Older stored profiles predate the honor projection. Only the explicitly
// observed medal fields are lifted; an empty legacy array cannot prove zero.
function honorReport(payload) {
  const number = value => value == null || typeof value === 'boolean' || value === '' || !Number.isFinite(Number(value)) || Number(value) < 0 ? null : Number(value)
  const medals = rows(payload?.achievements?.medals).filter(item => item && typeof item === 'object' && !Array.isArray(item))
  const flag = payload?.availability?.honor
  const available = typeof flag === 'boolean' ? flag : medals.length ? true : null
  return { available, summary: { declared_count: number(payload?.achievements?.count), listed_count: available === true ? medals.length : null },
    items: medals.map(item => {
      const data = item.achievementData || {}, level = number(item.level), plated = typeof item.isPlated === 'boolean' ? item.isPlated : null
      let icon = data.initIcon
      if (level >= 2 && data.reforge2Icon) icon = data.reforge2Icon
      if (level >= 3 && data.reforge3Icon) icon = data.reforge3Icon
      if (plated === true && data.platedIcon) icon = data.platedIcon
      const timestamp = number(item.obtainTs), date = timestamp ? new Date(timestamp * 1000) : null
      return { id:data.id, name:data.name, category:categoryName(data.cateName), level, is_plated:plated,
        obtained_at:date && Number.isFinite(date.getTime()) ? date.toISOString() : null, icon_url:typeof icon === 'string' ? icon : null }
    }) }
}

const categoryName = value => typeof value === 'string' && value.trim() ? value.trim() : null
function categorizedHonor(report, payload) {
  if (!report) return honorReport(payload)
  const legacy = honorReport(payload).items
  return {...report,items:rows(report.items).map(item=>{
    if (Object.prototype.hasOwnProperty.call(item,'category')) return {...item,category:categoryName(item.category)}
    const matches = item.id == null ? [] : legacy.filter(raw=>raw.id != null && String(raw.id) === String(item.id))
    return {...item,category:matches.length === 1 ? matches[0].category : null}
  })}
}

export function selectMedals(items, {search='',category=undefined,sort='recent'}={}) {
  const term=search.trim().toLocaleLowerCase('zh-CN')
  return rows(items).filter(item=>(!term || String(item.name ?? '').toLocaleLowerCase('zh-CN').includes(term))
    && (category === undefined || categoryName(item.category) === category))
    .map((item,index)=>({item,index,time:parseBeijingTime(item.obtained_at)})).sort((a,b)=>{
      if (sort==='source') return a.index-b.index
      if (a.time == null || b.time == null) return a.time == null && b.time == null ? a.index-b.index : a.time == null ? 1 : -1
      return (sort==='oldest' ? a.time-b.time : b.time-a.time) || a.index-b.index
    }).map(({item})=>item)
}

// Card rosters key operators by an instance hash in `id`; the chr_NNNN_* template ID, when present, is in `char_id`.
const byNewest = newestFirst('endfield')
const templateId = item => [item.char_id, item.id].find(value => /^chr_\d+_/.test(String(value ?? '')))
const recencyKey = item => ({ id: templateId(item), name: item.name })

export function selectOperators(items, { search = '', rarity = '', profession = '', sort = 'level' } = {}) {
  const term = search.trim().toLocaleLowerCase('zh-CN')
  const numeric = (item, key) => typeof item[key] === 'number' && Number.isFinite(item[key]) ? item[key] : null
  return rows(items).filter(item => (!term || [item.name, item.id].some(value => String(value ?? '').toLocaleLowerCase('zh-CN').includes(term)))
    && (!rarity || String(item.rarity) === String(rarity))
    && (!profession || sourceName(item.profession) === profession))
    .map((item, index) => ({ item, index })).sort((a, b) => {
      if (sort === 'newest') return byNewest(recencyKey(a.item), recencyKey(b.item)) || a.index - b.index
      if (sort === 'name') return sourceName(a.item.name).localeCompare(sourceName(b.item.name), 'zh-CN') || a.index - b.index
      const left = numeric(a.item, sort), right = numeric(b.item, sort)
      if (left === null || right === null) return left === right ? a.index - b.index : left === null ? 1 : -1
      return right - left || a.index - b.index
    }).map(({ item }) => item)
}

// Only reviewed public artwork hosts; profile URLs never become arbitrary requests.
export function operatorImage(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.port || url.search || url.hash) return null
    return ['bbs.hycdn.cn', 'web.hycdn.cn'].includes(url.hostname) && /\.(png|jpe?g|webp)$/i.test(url.pathname) ? url.href : null
  } catch { return null }
}

export function operatorArtwork(operator, { portrait = false } = {}) {
  if (portrait) {
    for (const key of [operator?.char_id, operator?.id]) {
      const url = key && operatorImage(iconCatalog.roles[key]?.portrait)
      if (url) return url
    }
    const portraits = Object.values(iconCatalog.roles).filter(item => item.name === operator?.name)
    if (portraits.length === 1) {
      const url = operatorImage(portraits[0].portrait)
      if (url) return url
    }
  }
  const supplied = operatorImage(operator?.avatar_url || operator?.icon_url)
  if (supplied) return supplied
  // Official website keys are deliberately not guessed from game-ID suffixes.
  for (const key of [operator?.char_id, operator?.id]) {
    if (key && iconCatalog.roles[key]) return operatorImage(iconCatalog.roles[key].icon)
  }
  const matches = Object.values(iconCatalog.roles).filter(item => item.name === operator?.name)
  return matches.length === 1 ? operatorImage(matches[0].icon) : null
}

// Gacha pool identity distinguishes operators from weapons. Official wiki IDs
// are not game item IDs, so weapon fallback uses only an exact, unique name.
export function gachaArtwork(item, kind) {
  if (kind === 'character') return operatorArtwork(item)
  if (kind !== 'weapon') return null
  const matches = Object.values(iconCatalog.weapons || {}).filter(weapon => weapon.name === item?.name)
  return matches.length === 1 ? operatorImage(matches[0].icon) : null
}

// ── Distributions for the charts. Keys are the numeric values the source reported, as strings. ──
const countOf = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
function countParts(counts, label, direction) {
  return Object.entries(counts && typeof counts === 'object' && !Array.isArray(counts) ? counts : {})
    .map(([key, value]) => ({ key, rank: Number(key), label: label(key), value: countOf(value) }))
    .filter(part => Number.isFinite(part.rank) && part.value != null)
    .sort((a, b) => direction * (a.rank - b.rank))
    .map(({ rank, ...part }) => part)
}
/** Operator rarity tiers present in `rarity_counts`, highest first. */
export const rarityParts = counts => countParts(counts, key => `${key}★`, -1)
/** Elite phases present in `phase_counts`, lowest first. */
export const phaseParts = counts => countParts(counts, key => `精英阶段 ${key}`, 1)

/** Medal categories by count, the long tail folded into one part so a donut stays readable. */
export function medalCategoryParts(items, limit = 5) {
  const counts = new Map()
  for (const item of rows(items)) {
    const key = categoryName(item.category)
    counts.set(key, (counts.get(key) ?? 0) + 1)
  }
  const parts = [...counts].map(([key, value]) => ({ key, label: key ?? '未提供分类', value }))
    .sort((a, b) => b.value - a.value || (a.key == null) - (b.key == null) || String(a.key).localeCompare(String(b.key), 'zh-CN'))
  if (parts.length <= limit) return parts
  const rest = parts.slice(limit - 1)
  return [...parts.slice(0, limit - 1), { key: '__rest', label: '其他分类', value: rest.reduce((sum, part) => sum + part.value, 0) }]
}

/** The medals with a usable acquisition time, newest first. */
export function recentMedals(items, limit = 8) {
  return selectMedals(items, { sort: 'recent' }).filter(item => parseBeijingTime(item.obtained_at) != null).slice(0, limit)
}

/** Plated medals among the listed ones; `known` counts those whose plating was reported at all. */
export function platedSummary(items) {
  const list = rows(items)
  return { plated: list.filter(item => item.is_plated === true).length, known: list.filter(item => typeof item.is_plated === 'boolean').length, listed: list.length }
}

/** Collection totals across a region's areas, one row per collection kind. Only areas that
 *  report both a count and a total are summed; `partial` marks a sum that left some out. */
export function collectionTotals(areas) {
  const kinds = new Map()
  for (const list of rows(areas)) for (const item of rows(list)) {
    if (!kinds.has(item.key)) kinds.set(item.key, { key: item.key, label: item.label, items: [] })
    kinds.get(item.key).items.push(item)
  }
  const finite = value => typeof value === 'number' && Number.isFinite(value)
  return [...kinds.values()].map(({ items, ...kind }) => {
    const known = items.filter(item => finite(item.current) && finite(item.total))
    const current = known.length ? known.reduce((sum, item) => sum + item.current, 0) : null
    const total = known.length ? known.reduce((sum, item) => sum + item.total, 0) : null
    return { ...kind, current, total, partial: known.length > 0 && known.length < items.length,
      percent: total > 0 ? Math.round(Math.min(1, current / total) * 100) : null }
  })
}
