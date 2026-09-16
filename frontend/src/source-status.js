const STATUS = {
  never: ['尚未采集', 'muted'], ok: ['最近成功', 'good'], offline: ['客户端离线', 'muted'],
  unconfigured: ['未配置', 'muted'], auth_expired: ['登录失效', 'danger'], error: ['采集异常', 'danger'],
}
const PRIORITY = { auth_expired: 6, error: 5, offline: 4, unconfigured: 3, never: 2, ok: 1 }
export function describeSource(row) {
  const [label, tone] = STATUS[row?.state || 'never'] || ['状态未知', 'muted']
  return { ...row, label, tone, retained: !!row?.last_success_at && row.state !== 'ok' }
}
export function sourceForGame(gameId, rows = []) {
  const selected = rows.filter(row => row.game_id === gameId && row.scope !== 'public_source')
    .sort((a, b) => (PRIORITY[b.state] || 0) - (PRIORITY[a.state] || 0))[0]
  return selected ? describeSource(selected) : null
}
export function capabilityLabel(capability, gameId = '') {
  if (capability === 'progress') return gameId === 'nte' ? '成就进度' : '周期进度'
  return ({ account: '账号', stamina: '体力', roles: '角色练度', exploration: '探索', calabash: '数据坞',
    events: '活动日历', announcement: '公告', news: '资讯', match: '近期对局', stats: '近期对局统计',
    gacha: '抽卡统计', record: '社区名片', realestate: '房产', vehicles: '载具', teams: '官方配队',
    combat: '挑战战报', activities: '玩法进度', resources: '资源简报' })[capability] || capability
}
