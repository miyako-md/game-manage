import { upcomingEvents } from './dashboard.js'

// The tabs each game page opens on from #/game/<id>?tab=<id>, in page order.
// They repeat the tab lists inside the game pages; search-index.test.js reads
// those pages and fails when the two drift. NTE groups appear only when the
// game has one of their capabilities, as on its page.
export const GAME_SECTIONS = {
  wuthering_waves: [['profile', '档案'], ['roles', '角色'], ['combat', '挑战'], ['activities', '玩法'], ['resources', '资源简报'], ['gacha', '抽卡历史'], ['history', '成长记录'], ['news', '公告与资讯']],
  nte: [['overview', '概览', ['account', 'stamina', 'progress', 'record']], ['characters', '角色', ['roles', 'calabash']], ['assets', '房产、载具与探索', ['realestate', 'vehicles', 'exploration']], ['teams', '官方配队', ['teams']], ['gacha', '抽卡统计', ['gacha']], ['news', '公告与资讯', ['announcement', 'news']]],
  league_of_legends: [['overview', '个人总览'], ['history', '对局记录'], ['hex', '海克斯'], ['news', '公告与资讯'], ['esports', '职业赛事']],
  endfield: [['overview', '概览'], ['operators', '全员练度'], ['regions', '地区建设'], ['ship', '帝江号'], ['gacha', '抽卡统计'], ['honor', '光荣之路'], ['challenges', '挑战记录'], ['news', '公告与资讯'], ['map', '地图与图鉴'], ['blueprints', '蓝图收藏']],
}
// Where a game lists its roles; a role result opens that tab.
const ROLE_TABS = { wuthering_waves: 'roles', nte: 'characters' }
const KIND_ORDER = ['page', 'game', 'section', 'role', 'event']
export const KIND_LABELS = { page: '页面', game: '游戏', section: '栏目', role: '角色', event: '活动' }

export const gameHref = (id, tab = '') => `#/game/${encodeURIComponent(id)}${tab ? `?tab=${encodeURIComponent(tab)}` : ''}`

export function sectionsFor(game) {
  const caps = game.capabilities || []
  // Guides live inside the role module; old deep links are handled by GameCard.
  return (GAME_SECTIONS[game.game_id] || []).filter(([id, , needs]) => !needs || needs.some(cap => cap !== 'events' && caps.includes(cap)))
}

function rolesOf(snapshot) {
  const payload = snapshot?.roles?.payload
  const list = Array.isArray(payload) ? payload : Array.isArray(payload?.entries) ? payload.entries : []
  const names = list.map(role => typeof role?.name === 'string' ? role.name.trim() : '').filter(Boolean)
  return [...new Set(names)]
}

/** Every place search can jump to: pages, games, their tabs, current events and known roles. */
export function buildSearchIndex({ pages = [], games = [], snapshots = {}, now = Date.now() }) {
  const items = pages.map(page => ({ key: `page:${page.href}`, kind: 'page', title: page.label, hint: page.hint || '', href: page.href, icon: page.icon }))
  for (const game of games) {
    const id = game.game_id, name = game.display_name
    items.push({ key: `game:${id}`, kind: 'game', title: name, hint: '游戏档案', href: gameHref(id), gameId: id })
    for (const [tab, label] of sectionsFor(game)) items.push({ key: `section:${id}:${tab}`, kind: 'section', title: label, hint: name, game: name, href: gameHref(id, tab), gameId: id })
    if (ROLE_TABS[id]) for (const role of rolesOf(snapshots[id])) items.push({ key: `role:${id}:${role}`, kind: 'role', title: role, hint: `${name} · 角色列表`, game: name, href: gameHref(id, ROLE_TABS[id]), gameId: id })
  }
  const seen = new Set()
  for (const event of upcomingEvents(games, snapshots, now)) {
    const key = `event:${event.gameId}:${event.name}`
    if (typeof event.name !== 'string' || !event.name.trim() || seen.has(key)) continue
    seen.add(key)
    items.push({ key, kind: 'event', title: event.name.trim(), hint: `${event.gameName} · ${event.upcoming ? '即将开始' : `${event.remainingDays} 天后结束`}`, game: event.gameName, href: `#/calendar?game=${encodeURIComponent(event.gameId)}`, gameId: event.gameId })
  }
  return items
}

const fold = text => text.toLocaleLowerCase('zh-CN').replace(/\s+/g, '')

/** Matches for a query, best first: a title that starts with it, then one that
    contains it, then the game name and title together (「鸣潮抽卡」, 「角色 异环」). */
export function searchItems(items, query, limit = 40) {
  const q = fold(query || '')
  const rank = item => KIND_ORDER.indexOf(item.kind)
  if (!q) return items.filter(item => item.kind === 'page' || item.kind === 'game').sort((a, b) => rank(a) - rank(b))
  const scored = items.flatMap(item => {
    const title = fold(item.title), game = fold(item.game || '')
    const score = title.startsWith(q) ? 0 : title.includes(q) ? 1 : game && (`${game}${title}`.includes(q) || `${title}${game}`.includes(q)) ? 2 : -1
    return score < 0 ? [] : [{ item, score }]
  })
  return scored.sort((a, b) => a.score - b.score || rank(a.item) - rank(b.item)).slice(0, limit).map(entry => entry.item)
}

/** Results in display groups, in kind order, each with its label. */
export function groupResults(results) {
  return KIND_ORDER.map(kind => ({ kind, label: KIND_LABELS[kind], items: results.filter(item => item.kind === kind) })).filter(group => group.items.length)
}
