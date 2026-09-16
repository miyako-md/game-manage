export const roleId = role => role?.id === null || role?.id === undefined ? '' : String(role.id).trim()
export const displayRoleValue = value => value === null || value === undefined || value === '' || (typeof value === 'number' && !Number.isFinite(value)) ? '未提供' : value
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null

export function filterRoles(entries, { search = '', quality = '', element = '', favoritesOnly = false, favorites = [], sort = 'level', direction = 'desc' } = {}) {
  const favoriteIds = new Set(favorites), query = search.trim().toLocaleLowerCase()
  const field = ['level', 'awaken_level', 'mix_level', 'name'].includes(sort) ? sort : 'level'
  return (Array.isArray(entries) ? entries : []).filter(role => role && typeof role === 'object')
    .filter(role => (!query || String(role.name ?? '').toLocaleLowerCase().includes(query)) && (!quality || role.quality === quality) && (!element || role.element === element) && (!favoritesOnly || favoriteIds.has(roleId(role))))
    .sort((a, b) => {
      const x = field === 'name' ? (a.name || null) : numeric(a[field])
      const y = field === 'name' ? (b.name || null) : numeric(b[field])
      if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1
      const order = field === 'name' ? String(x).localeCompare(String(y), 'zh-CN') : x - y
      return direction === 'asc' ? order : -order
    })
}

export function favoritesKey(accountId) {
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
