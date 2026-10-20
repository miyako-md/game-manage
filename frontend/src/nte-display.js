import catalog from './nte-icon-catalog.js'

export function displayNteText(value) {
  if (value == null || value === '') return '未提供'
  const text = String(value)
  if (/\{\d+\}/.test(text)) return '效果数值待核验'
  if (/^Effect\d+$/i.test(text.trim())) return '效果说明待核验'
  return text.replace(/\\r\\n|\\n|\\r/g, '\n')
    .replace(/<\/>|<\/?(?:Color|RichText|Font|b|i)(?:\s[^>]*)?>/gi, '')
    .replace(/([。！？，：；）」])(?:rn|n)+(?=[\p{Script=Han}「（·])/gu, '$1\n')
}

const namesById = new Map()
for (const bucket of [catalog.roles, catalog.weapons]) for (const [name, item] of Object.entries(bucket || {})) {
  const id = String(item.id)
  if (!namesById.has(id)) namesById.set(id, [])
  namesById.get(id).push(name)
}
export function nteItemLabel(id, suppliedName) {
  const names = namesById.get(String(id))
  const name = String(suppliedName || '').trim()
  const raw = !name || name === String(id) || /^角色\/弧盘\s/.test(name) || /\bfork_[a-z0-9_]+|^CHARACTER_|^char_/i.test(name)
  if (names) return raw ? names[0] : names.includes(name) ? name : '名称待核验'
  return raw ? '名称待核验' : displayNteText(name)
}

export function displayVehicleStat(stat) {
  if (stat?.value == null || stat.value === '') return '未知'
  return Number(stat.value) < 0 ? '来源未说明' : String(stat.value)
}

// Vehicle decorations arrive as internal slot keys plus an internal model ID.
// Only the tyre slot has been observed; other keys read as a generic decoration.
const VEHICLE_DECORATION_TYPES = { evmt_tyre: '轮胎' }
export function vehicleDecorationType(type) {
  return VEHICLE_DECORATION_TYPES[String(type ?? '').trim()] || '装饰'
}

// The bot image lists each official team once (主角·零 has a male and a female
// entry under one name). Teams carry no role IDs, so ownership is matched by
// role names in the team name: a team naming only unowned roles is dropped,
// while a name with no known role at all (a composite title) is kept. Without
// an owned roster nothing is filtered.
export function imageTeams(entries, ownedNames = [], knownNames = []) {
  const seen = new Set(), owned = ownedNames.filter(Boolean), known = [...new Set([...knownNames, ...owned].filter(Boolean))]
  return entries.filter(entry => {
    const name = String(entry?.name ?? '')
    if (name) { if (seen.has(name)) return false; seen.add(name) }
    if (!owned.length || !known.some(role => name.includes(role))) return true
    return owned.some(role => name.includes(role))
  })
}
