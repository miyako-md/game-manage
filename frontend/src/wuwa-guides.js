import catalog from './wuwa-guides-catalog.js'

export const guideUpdatedAt = catalog.updatedAt
export const guideSections = {
  weapons: '武器推荐',
  teams: '配队推荐',
  echo_sets: '声骸配装',
  echo_stats: '声骸词条',
  skill_priority: '技能加点优先级',
}

// Character IDs identify forms; names alone must never select a guide.
export function getWuwaGuide(characterId) {
  const id = String(characterId ?? '')
  if (!/^\d{1,12}$/.test(id)) return null
  return catalog.guides.find(guide => guide.id === id) || null
}

// Source-matched reviewed updates replace the snapshot. Automatic drafts stay
// visible for new forms, or alongside existing reviewed recommendations.
export function displayWuwaGuide(characterId, update) {
  const original = getWuwaGuide(characterId)
  if (!update || String(update.id) !== String(characterId) || !Array.isArray(update.sections)) return original
  if (!original || update.sections.length === 5 && update.sections.every(s => s.status === 'reviewed')) return update
  return original
}

export function guideSourceUrl(url) {
  return typeof url === 'string' && /^https:\/\/www\.kurobbs\.com\/forum\/post\/\d+$/.test(url)
    ? url
    : null
}

export function guideVersion(source) {
  if (!source?.version) return '版本未确认'
  return `V${source.version}${source.kind === 'preview' ? ' · 前瞻' : ''}`
}
