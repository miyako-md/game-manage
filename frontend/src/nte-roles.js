import { isCloudMode } from './http-client.js'
import { finiteValue } from './dashboard.js'
import { normalizeSearch, searchCharacters } from './character-search.js'
import { roleRecency } from './role-order.js'

export const roleId = role => role?.id === null || role?.id === undefined ? '' : String(role.id).trim()
export const displayRoleValue = (value, missing = '未提供') => {
  const badNumber = typeof value === 'number' && !Number.isFinite(value)
  return value === null || value === undefined || value === '' || badNumber ? missing : value
}

export function filterRoles(entries, { search = '', quality = '', element = '', favoritesOnly = false, favorites = [], sort = 'level', direction = 'desc' } = {}) {
  const favoriteIds = new Set(favorites), query = normalizeSearch(search)
  const eligible = (Array.isArray(entries) ? entries : []).filter(role => role && typeof role === 'object')
    .filter(role => (!quality || role.quality === quality) && (!element || role.element === element) && (!favoritesOnly || favoriteIds.has(roleId(role))))
  const matches = new Map(searchCharacters('nte', search, eligible).map(item => [item.entry, item.score]))
  const field = ['newest', 'level', 'awaken_level', 'mix_level', 'name'].includes(sort) ? sort : 'level'
  // 'newest' is the shared newest-first proxy (role id); unplaced roles stay last and ties go by name.
  const read = role => field === 'name' ? (role.name || null) : field === 'newest' ? roleRecency('nte', role) : finiteValue(role[field])
  return eligible.filter(role => !query || matches.has(role))
    .sort((a, b) => {
      if (query && matches.get(a) !== matches.get(b)) return matches.get(a) - matches.get(b)
      const x = read(a), y = read(b)
      if (x === null || y === null) return x === y ? (field === 'newest' ? String(a.name ?? '').localeCompare(String(b.name ?? ''), 'zh-CN') : 0) : x === null ? 1 : -1
      const order = field === 'name' ? String(x).localeCompare(String(y), 'zh-CN') : x - y
      if (!order && field === 'newest') return String(a.name ?? '').localeCompare(String(b.name ?? ''), 'zh-CN')
      return direction === 'asc' ? order : -order
    })
}

export function favoritesKey(accountId) {
  if (isCloudMode()) {
    const keys = ['user_id','account_id','role_id']
    if (!accountId || typeof accountId !== 'object' || keys.some(key => typeof accountId[key] !== 'string' || !accountId[key].trim())) return null
    return `game-manage:cloud:nte:${keys.map(key => encodeURIComponent(accountId[key])).join(':')}:favorites:v1`
  }
  return typeof accountId === 'string' && accountId.trim() ? `game-manage:nte:${encodeURIComponent(accountId.trim())}:favorites:v1` : null
}
export function loadFavorites(accountId, storage) {
  const key = favoritesKey(accountId)
  if (!key) return { ids: [], error: null }
  try {
    const source = storage ?? globalThis.localStorage
    if (!source) throw Error('Storage unavailable')
    const raw = source.getItem(key)
    if (raw === null) return { ids: [], error: null }
    const ids = JSON.parse(raw)
    if (!Array.isArray(ids) || ids.some(id => typeof id !== 'string')) throw Error('Invalid favorites')
    return { ids: [...new Set(ids)], error: null }
  } catch { return { ids: [], error: '收藏读取失败，当前收藏仅在本次页面保留。' } }
}
export function saveFavorites(accountId, ids, storage) {
  const key = favoritesKey(accountId)
  if (!key) return { error: null }
  try {
    const source = storage ?? globalThis.localStorage
    if (!source) throw Error('Storage unavailable')
    source.setItem(key, JSON.stringify([...new Set(ids)]))
    return { error: null }
  } catch { return { error: '收藏保存失败，当前收藏仅在本次页面保留。' } }
}

export function comparisonGroups(roles) {
  const fixed = (name, fields, read) => ({ name, rows: fields.map(([label, key]) => ({ name: label, values: roles.map(role => displayRoleValue(read(role)?.[key])) })) })
  const groups = [
    fixed('基础', [['品质', 'quality'], ['元素', 'element'], ['等级', 'level'], ['觉醒', 'awaken_level'], ['混频', 'mix_level'], ['羁遇累计经验', 'affinity_exp']], role => role),
    fixed('弧盘', [['名称', 'name'], ['品质', 'quality'], ['等级', 'level'], ['混频', 'mix_level']], role => role.weapon),
  ]
  for (const [name, key, value] of [['属性', 'properties', 'value'], ['战技', 'skills', 'level'], ['城区技能', 'city_skills', 'level']]) {
    // Match repeated field names by their occurrence, retaining every source row.
    const names = new Map()
    const maps = roles.map(role => {
      const seen = new Map(), fields = new Map()
      for (const entry of Array.isArray(role[key]) ? role[key] : []) {
        if (!entry || typeof entry !== 'object') continue
        const label = String(displayRoleValue(entry.name)), count = (seen.get(label) ?? 0) + 1
        seen.set(label, count)
        const id = JSON.stringify([label, count])
        names.set(id, count > 1 ? `${label}（${count}）` : label)
        fields.set(id, displayRoleValue(entry[value]))
      }
      return fields
    })
    groups.push({ name, rows: [...names].map(([id, label]) => ({ name: label, values: maps.map(fields => fields.get(id) ?? '未提供') })) })
  }
  return groups
}
