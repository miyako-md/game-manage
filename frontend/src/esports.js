import { formatBeijingDateTime, safeUrl } from './calendar.js'
export const ESPORTS_FAMILIES = { lpl: 'LPL', first_stand: '全球先锋赛', msi: 'MSI', worlds: '全球总决赛', ewc: '电竞世界杯', asian_games: '亚运会 LOL' }
export const ESPORTS_STATUS = { scheduled: '未开始', live: '进行中', completed: '已结束', postponed: '延期', cancelled: '取消', unknown: '状态待确认' }
export const createEsportsBrowseState = () => ({ section: 'overview', view: 'schedule', family: '', date: '', filterTeamId: '', page: 1, teamId: '', playerId: '', matchId: '', returnTo: [] })
export const esportsTime = value => value ? formatBeijingDateTime(value) : '未提供'
export function selectEsportsMatches(payload, filters = {}) {
  const tournaments = new Map((payload?.tournaments || []).map(t => [t.id, t]))
  return (payload?.matches || []).filter(m => (!filters.family || tournaments.get(m.tournament_id)?.family === filters.family)
    && (!filters.date || (m.start_at && esportsTime(m.start_at).slice(0, 10) === filters.date))
    && (!(filters.filterTeamId || filters.teamId) || [m.team_a_id, m.team_b_id].includes(filters.filterTeamId || filters.teamId)))
    .slice().sort((a, b) => (Date.parse(a.start_at) || Infinity) - (Date.parse(b.start_at) || Infinity) || a.id.localeCompare(b.id))
}
export function esportsOutcome(match, side) {
  const winner = match.winner_team_id
  if (match.status !== 'completed' || !winner || !match.team_a_id || !match.team_b_id
    || match.team_a_id === match.team_b_id || ![match.team_a_id, match.team_b_id].includes(winner)) return ''
  return match[`team_${side}_id`] === winner ? '胜' : '负'
}
export function esportsSections(payload, filters = {}, pageSize = 20) {
  const matches = selectEsportsMatches(payload, filters)
  const definitions = filters.view === 'results' ? [['completed', '赛果']] : [
    ['live', '进行中'], ['scheduled', '未来比赛'], ['completed', '近期赛果'], ['other', '延期 / 取消 / 状态待确认'],
  ]
  return definitions.map(([key, label]) => {
    let rows = matches.filter(m => key === 'other' ? !['live', 'scheduled', 'completed'].includes(m.status) : m.status === key)
    if (key === 'completed') rows.sort((a, b) => {
      const aTime = Date.parse(a.start_at), bTime = Date.parse(b.start_at)
      if (!Number.isFinite(aTime)) return Number.isFinite(bTime) ? 1 : a.id.localeCompare(b.id)
      if (!Number.isFinite(bTime)) return -1
      return bTime - aTime || a.id.localeCompare(b.id)
    })
    const total = rows.length, pages = Math.max(1, Math.ceil(total / pageSize))
    const page = key === 'completed' ? Math.max(1, Math.min(pages, Math.trunc(Number(filters.page) || 1))) : 1
    if (key === 'completed') rows = rows.slice((page - 1) * pageSize, page * pageSize)
    const groups = []
    for (const match of rows) {
      const date = Number.isFinite(Date.parse(match.start_at)) ? esportsTime(match.start_at).slice(0, 10) : '时间待公布'
      let group = groups.find(g => g.date === date)
      if (!group) { group = { date, matches: [] }; groups.push(group) }
      group.matches.push(match)
    }
    return { key, label, groups, total, pages, page }
  })
}
export function esportsGroupLabel(meta) {
  if (!meta?.last_success_at) return '资料暂缺 · 尚未成功采集'
  return `本机采集 ${esportsTime(meta.last_success_at)} · 来源更新 ${esportsTime(meta.source_updated_at)}${meta.source_lagging ? ' · 来源阵容可能滞后' : ''}${meta.stale ? ' · 缓存可能过期' : ''}${meta.coverage !== 'complete' ? ' · 完整性未确认' : ''}`
}
export function officialEsportsUrl(value) {
  const safe = safeUrl(value)
  try {
    const url = new URL(safe)
    return url.protocol === 'https:' && url.hostname === 'lpl.qq.com' && !url.username && !url.password
      && (!url.port || url.port === '443') && /^\/web202301\/(live\.html|video_detail\.shtml|team-detail\.html|player-detail\.html)$/.test(url.pathname) ? safe : ''
  } catch { return '' }
}
export function esportsImage(value) {
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && ['img.crawler.qq.com', 'game.gtimg.cn', 'img1.gtimg.com', 'img2.gtimg.com', 'img.lol.qq.com', 'ossweb-img.qq.com'].includes(url.hostname) && !url.username && !url.password ? url.href : ''
  } catch { return '' }
}
