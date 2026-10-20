const id = value => typeof value === 'string' || typeof value === 'number' ? String(value).trim() : ''
const blocked = value => ['expired', 'auth_expired', 'revoked', 'unconfigured', 'disabled'].includes(value)
const expired = snapshot => blocked(snapshot?.state) || blocked(snapshot?.poll_status?.state)

// The passport ledger retains its own authorization even on a combined role page.
// The cloud envelope proves that grant; payload role IDs prove its ledger owner.
export function gachaView({ snaps = {}, cloudAccount, cloudRole, configured, authAccount } = {}) {
  const unavailable = message => ({ account: null, snapshot: null, accountId: '', message })
  if (cloudAccount) {
    if (cloudAccount.provider !== 'hypergryph') return unavailable('此角色尚未连接鹰角寻访，请到「账号与授权」登录。')
    if (cloudAccount.state !== 'active' || !cloudAccount.roles?.some(role => id(role.role_id) === id(cloudRole))) return unavailable('当前鹰角授权或角色不可用，请重新授权。')
  } else if (configured === false || authAccount?.configured === false || blocked(authAccount?.state)) {
    return unavailable('请登录有效的鹰角通行证后刷新寻访数据。')
  }
  const account = snaps.account, snapshot = snaps.gacha
  if (expired(account) || expired(snapshot)) return unavailable('鹰角身份已失效，请重新登录并刷新。')
  const role = id(account?.payload?.role_id)
  if (!role) return unavailable('尚未读取鹰角通行证角色，请刷新数据。')
  if (cloudAccount && (id(account.account_id) !== id(cloudAccount.account_id) || id(account.role_id) !== id(cloudRole))) return unavailable('当前授权与账号快照不一致，请重新读取。')
  const identity = { account: account.payload, accountId: cloudAccount ? `${cloudAccount.account_id}:${cloudRole}` : role }
  if (!snapshot) return { ...identity, snapshot: null, message: '尚未同步该鹰角角色的寻访记录。' }
  if (id(snapshot.payload?.role_id) !== role || (snapshot.payload?.report?.role_id != null && id(snapshot.payload.report.role_id) !== role) || cloudAccount && (id(snapshot.account_id) !== id(cloudAccount.account_id) || id(snapshot.role_id) !== id(cloudRole))) {
    return { ...identity, snapshot: null, accountId: '', message: '寻访快照与当前鹰角身份不一致，请刷新后查看。' }
  }
  return { ...identity, snapshot, message: '' }
}

const number = value => (typeof value === 'number' || typeof value === 'string' && value.trim() !== '') && Number.isFinite(Number(value)) && Number(value) >= 0 ? Number(value) : null
const rows = value => Array.isArray(value) ? value.filter(item=>item && typeof item==='object' && !Array.isArray(item)) : []
export const isGachaGift = row => String(row?.record_kind || row?.kind || '').startsWith('gift')
export function gachaPools(summary) {
  const values = summary?.report?.schema_version === 1 && Array.isArray(summary.report.pools) ? summary.report.pools : summary?.pools
  return rows(values).map(pool => {
    const unverified = number(pool.unverified_records) ?? 0
    const history = rows(pool.history).filter(item => !isGachaGift(item)), available = history.length
    const declared = number(pool.history_total) ?? number(pool.six_star)
    const total = declared != null && declared >= available ? declared : null
    return { ...pool, gifts: number(pool.gifts) ?? 0, unverified_records: unverified,
      history, banners: rows(pool.banners), history_available: available, history_total: total,
      history_truncated: total == null ? null : total > available,
      history_limit: number(pool.history_limit), four_star:number(pool.four_star), unknown_rarity:number(pool.unknown_rarity) }
  })
}

// How many pulls a 6★ took, in the wording the ledger can prove: exact, a known minimum, or unknown (null).
export function sixPullsParts(item) {
  if (item?.pulls == null || (item.status !== 'exact' && item.status !== 'lower_bound')) return null
  return { prefix: item.status === 'exact' ? '' : '≥', count: item.pulls, unit: '抽' }
}
export const sixPullsText = item => { const parts = sixPullsParts(item); return parts ? `${parts.prefix}${parts.count} ${parts.unit}` : '未知' }

// 6★ across all pools, newest first. An unknown time sorts last; equal times keep their pool order.
export function recentSixStars(pools, limit = Infinity) {
  const items = []
  for (const pool of rows(pools)) for (const item of rows(pool.history)) items.push({ ...item, pool_key: pool.key, pool_label: pool.label, pool_kind: pool.kind })
  return items
    .map((item, index) => ({ item, index, at: Number.isFinite(item.obtained_at) ? item.obtained_at : null }))
    .sort((a, b) => (a.at == null) - (b.at == null) || (b.at ?? 0) - (a.at ?? 0) || a.index - b.index)
    .slice(0, limit).map(({ item }) => item)
}

// One count summed over every pool. A single pool without it makes the whole total unknown, never a partial sum.
export function poolTotal(pools, field) {
  const values = rows(pools).map(pool => number(pool[field]))
  return values.length && values.every(value => value != null) ? values.reduce((sum, value) => sum + value, 0) : null
}

const isWeapon = pool => pool?.kind === 'weapon'

// Operator and weapon pulls are different currencies with different odds, so they are never added together.
export function kindSummary(pools, kind) {
  const list = rows(pools).filter(pool => isWeapon(pool) === (kind === 'weapon'))
  if (!list.length) return null
  return { kind, label: kind === 'weapon' ? '武器申领' : '干员寻访', total: poolTotal(list, 'total'), six_star: poolTotal(list, 'six_star'),
    five_star: poolTotal(list, 'five_star'), gifts: list.reduce((sum, pool) => sum + (number(pool.gifts) ?? 0), 0),
    unverified_records: list.reduce((sum, pool) => sum + (number(pool.unverified_records) ?? 0), 0), pace: poolPace({ history: list.flatMap(pool => rows(pool.history)) }) }
}

// What the page lets you pick: each operator pool type on its own (pity runs through a type),
// and every weapon banner together under 武器申领 (each keeps its own pity).
export function poolCategories(pools) {
  const list = rows(pools), weapons = list.filter(isWeapon)
  const categories = list.filter(pool => !isWeapon(pool)).map(pool => ({ key: pool.key, label: pool.label, kind: 'character', pools: [pool], ...pool }))
  if (weapons.length) {
    // 当期已垫 follows the banner drawn most recently; a pool holding only gifts has no draws to lead with.
    const drawn = weapons.filter(pool => number(pool.total) !== 0)
    const latest = (drawn.length ? drawn : weapons).reduce((best, pool) => (number(pool.newest_at) ?? -1) > (number(best.newest_at) ?? -1) ? pool : best)
    const times = field => weapons.map(pool => number(pool[field])).filter(value => value != null)
    categories.push({ key: 'weapon', label: '武器申领', kind: 'weapon', pools: weapons, latest,
      ...Object.fromEntries(['total', 'six_star', 'five_star', 'four_star', 'unknown_rarity', 'free', 'gaps'].map(field => [field, poolTotal(weapons, field)])),
      gifts: weapons.reduce((sum, pool) => sum + (number(pool.gifts) ?? 0), 0), unverified_records: weapons.reduce((sum, pool) => sum + (number(pool.unverified_records) ?? 0), 0),
      pending: weapons.some(pool => pool.pending === true) ? true : weapons.every(pool => pool.pending === false) ? false : null,
      newest_at: times('newest_at').length ? Math.max(...times('newest_at')) : null, oldest_at: times('oldest_at').length ? Math.min(...times('oldest_at')) : null,
      history: weapons.flatMap(pool => rows(pool.history)).sort((a, b) => (number(b.obtained_at) ?? 0) - (number(a.obtained_at) ?? 0)) })
  }
  return categories
}

// A category's banners, newest first, each with only its own 6★. Operator banners come from the
// ledger's per-banner counts (older snapshots: from the 6★ themselves, counts unknown); a weapon
// banner is its own ledger pool and carries its own pity.
export function bannerGroups(category) {
  if (category?.kind === 'weapon') return rows(category.pools).map(pool => ({ ...pool, key: pool.key, name: pool.label, pity: pool.since_last_six }))
    .sort((a, b) => (number(b.newest_at) ?? 0) - (number(a.newest_at) ?? 0))
  const history = rows(category?.history), banners = rows(category?.banners)
  const id = item => item.pool_id || item.pool_name || ''
  if (!banners.length) {
    const names = [...new Set(history.map(id))]
    return names.map(key => ({ key, name: history.find(item => id(item) === key).pool_name || null, total: null, six_star: null, five_star: null, history: history.filter(item => id(item) === key) }))
  }
  return banners.map(banner => ({ ...banner, key: id(banner), name: banner.name || null,
    history: history.filter(item => item.pool_id ? item.pool_id === banner.pool_id : item.pool_name === banner.name) }))
}

// A pool's 6★ pace from the exact intervals in its shown history only; a lower bound is never averaged in.
// The fastest and slowest need two intervals to compare, otherwise they stay null.
export function poolPace(pool) {
  const exact = rows(pool?.history).filter(item => !isGachaGift(item) && item.status === 'exact' && number(item.pulls) != null)
  if (!exact.length) return { count: 0, average: null, fastest: null, slowest: null }
  const pulls = exact.map(item => number(item.pulls))
  const pick = target => exact[pulls.indexOf(target)]
  const pair = exact.length > 1 && Math.min(...pulls) !== Math.max(...pulls)
  return { count: exact.length, average: Math.round(pulls.reduce((sum, value) => sum + value, 0) / pulls.length * 10) / 10,
    fastest: pair ? pick(Math.min(...pulls)) : null, slowest: pair ? pick(Math.max(...pulls)) : null }
}

// One bar ruler for every pool of a kind, so bars compare across pools: the longest recorded 6★ rounded up to ten.
// No pity rule is assumed; null when no 6★ of that kind states its pulls.
export function pullRuler(pools, kind) {
  const values = rows(pools).filter(pool => (pool.kind === 'weapon') === (kind === 'weapon'))
    .flatMap(pool => rows(pool.history)).filter(item => item.status === 'exact' || item.status === 'lower_bound')
    .map(item => number(item.pulls)).filter(value => value != null)
  return values.length ? Math.max(10, Math.ceil(Math.max(...values) / 10) * 10) : null
}

// Each rarity's count and share of the pool. An unstated count stays unknown and takes no share.
const RARITIES = [['six_star', '6★'], ['five_star', '5★'], ['four_star', '4★'], ['unknown_rarity', '未知 / 其他']]
export function rarityShares(pool) {
  const total = number(pool?.total)
  return RARITIES.map(([field, label]) => {
    const count = number(pool?.[field])
    return { field, label, count, share: count != null && total ? count / total : null }
  })
}

// The ledger's sync state in one label: unfinished first, then a proven complete scan, else unknown.
export function syncStatus(summary, report) {
  if (summary?.complete === false || report?.pending === true) return { tone: 'warn', label: '部分待同步' }
  if (summary?.complete === true) return { tone: 'done', label: '同步完成' }
  return { tone: 'unknown', label: '完整性未知' }
}
