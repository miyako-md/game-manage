// Account roles come from the authenticated account listing. Display names are
// deliberately absent from identity matching: equal names do not prove ownership.
const providers = ['hypergryph', 'skland']
const isEndfield = account => account && (account.game == null || account.game === 'endfield') && providers.includes(account.provider)
const roles = account => (Array.isArray(account?.roles) ? account.roles : []).filter(role => typeof role.role_id === 'string' && role.role_id)
const knownChannel = channel => ['official', 'bilibili'].includes(channel)
const uid = role => role?.game_uid == null ? '' : String(role.game_uid)
const sameOwner = (a, b) => !a.user_id || !b.user_id || a.user_id === b.user_id
const identity = (a, ar, b, br) => {
  if (!sameOwner(a, b) || !knownChannel(a.channel) || a.channel !== b.channel || !a.server || a.server !== b.server) return false
  if (uid(ar) && uid(br)) return uid(ar) === uid(br)
  const h = a.provider === 'hypergryph' ? a : b, hr = a.provider === 'hypergryph' ? ar : br
  const s = a.provider === 'skland' ? a : b
  return s.authorization_source === 'passport' && roles(s).length === 1 && s.parent_account_id === h.account_id && s.parent_role_id === hr.role_id
}
const active = accounts => accounts.filter(a => isEndfield(a) && a.state === 'active').flatMap(account => roles(account).map(role => ({ account, role })))
const opposite = (entries, entry) => entries.filter(other => other.account.provider !== entry.account.provider && identity(entry.account, entry.role, other.account, other.role))
export function resolveEndfieldSources(accounts, account, roleId) {
  const entries = active(Array.isArray(accounts) ? accounts : [])
  const selected = entries.find(entry => entry.account.account_id === account?.account_id && entry.account.provider === account?.provider && entry.role.role_id === roleId)
  if (!selected) return {}
  const result = { [selected.account.provider]: { account: selected.account, role: selected.role.role_id } }
  const candidates = opposite(entries, selected)
  if (candidates.length === 1 && opposite(entries, candidates[0]).length === 1) {
    const other = candidates[0]; result[other.account.provider] = { account: other.account, role: other.role.role_id }
  }
  return result
}
export function endfieldRoleChoices(accounts) {
  const choices = [], seen = new Set()
  for (const account of (Array.isArray(accounts) ? accounts : []).filter(isEndfield)) for (const role of roles(account)) {
    const physicalKey = `${account.account_id}:${role.role_id}`
    if (seen.has(physicalKey)) continue
    const sources = resolveEndfieldSources(accounts, account, role.role_id)
    const canonical = sources.hypergryph || sources.skland || { account, role: role.role_id }
    for (const source of Object.values(sources)) seen.add(`${source.account.account_id}:${source.role}`)
    seen.add(physicalKey)
    choices.push({ key: `${canonical.account.account_id}:${canonical.role}`, ...canonical, sources })
  }
  return choices
}
// A choice lacking one provider may borrow that provider's pages from another single-provider choice.
// It is never paired: merged choices belong to their own character, and a known different owner,
// channel, server or UID proves another character, so neither is offered.
const sourceRole = source => roles(source.account).find(role => role.role_id === source.role)
const provenDifferent = (a, b) => !sameOwner(a.account, b.account) || (knownChannel(a.account.channel) && knownChannel(b.account.channel) && a.account.channel !== b.account.channel) ||
  (a.account.server && b.account.server && a.account.server !== b.account.server) || (uid(sourceRole(a)) && uid(sourceRole(b)) && uid(sourceRole(a)) !== uid(sourceRole(b)))
export function endfieldFallbackCandidates(choices, current, provider) {
  const own = Object.values(current?.sources || {})
  if (!providers.includes(provider) || own.length !== 1 || current.sources[provider]) return []
  return (Array.isArray(choices) ? choices : []).filter(choice => Object.keys(choice?.sources || {}).length === 1 && choice.sources[provider] && !provenDifferent(own[0], choice.sources[provider]))
}
export function endfieldFallback(choices, current, provider) {
  const candidates = endfieldFallbackCandidates(choices, current, provider)
  return candidates.length === 1 ? candidates[0] : null
}
// The selected character's sources plus, for a missing provider, the unique fallback flagged as such.
export function endfieldPageSources(accounts, account, roleId) {
  const sources = resolveEndfieldSources(accounts, account, roleId), choices = endfieldRoleChoices(accounts)
  for (const provider of providers) {
    const other = endfieldFallback(choices, { sources }, provider)
    if (other) sources[provider] = { ...other.sources[provider], fallback: true }
  }
  return sources
}
export const endfieldProviderLabel = provider => ({ hypergryph: '鹰角寻访', skland: '森空岛档案' })[provider] || ''
export const endfieldChannelLabel = channel => ({ official: '官服', bilibili: 'B 服' })[channel] || '渠道未提供'
export const endfieldSourceLabel = source => `${sourceRole(source)?.display_name || '未命名角色'} · ${endfieldChannelLabel(source.account.channel)}`
