// "Newest first" without release dates (no catalog has them), one proxy per game:
// Wuwa = official wiki catalogue order (listed newest first; role ids are grouped by
// element, not by date), NTE = numeric role id, Endfield = the number in chr_NNNN_*.
// Roles a proxy cannot place go last; ties fall back to the name.
import wuwaCatalog from './wuwa-icon-catalog.js'

const wuwaNames = Object.keys(wuwaCatalog.roles)
const wuwaRank = new Map(wuwaNames.map((name, index) => [name, wuwaNames.length - index]))
const number = value => /^\d+$/.test(String(value ?? '')) ? Number(value) : null

export function roleRecency(game, role) {
  if (!role || typeof role !== 'object') return null
  if (game === 'wuthering_waves') return wuwaRank.get(role.name) ?? null
  if (game === 'nte') return number(role.id)
  if (game === 'endfield') { const match = /^chr_(\d+)_/.exec(String(role.id ?? role.char_id ?? '')); return match ? Number(match[1]) : null }
  return null
}

export const newestFirst = game => (a, b) => {
  const x = roleRecency(game, a), y = roleRecency(game, b)
  if (x !== y) return x == null ? 1 : y == null ? -1 : y - x
  return String(a?.name ?? '').localeCompare(String(b?.name ?? ''), 'zh-CN')
}
