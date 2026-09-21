export const DAY_MS = 86400000
const BEIJING_OFFSET = 8 * 3600000
const missing = (value) => value == null || value === ''

/** ISO timestamps without an offset are interpreted in Beijing, never the device timezone. */
export function parseBeijingTime(value) {
  if (missing(value)) return null
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (value instanceof Date) return Number.isFinite(value.getTime()) ? value.getTime() : null
  if (typeof value !== 'string') return null
  const raw = value.trim()
  const match = raw.match(/^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?)?$/i)
  if (!match) return null
  const [, year, month, day, hour = '00', minute = '00', second = '00', offset] = match
  const date = new Date(Date.UTC(+year, +month - 1, +day))
  if (date.getUTCFullYear() !== +year || date.getUTCMonth() !== +month - 1 || date.getUTCDate() !== +day || +hour > 23 || +minute > 59 || +second > 59) return null
  const timestamp = Date.parse(match[4] ? raw.replace(' ', 'T') + (offset ? '' : '+08:00') : `${raw}T00:00:00+08:00`)
  return Number.isFinite(timestamp) ? timestamp : null
}

export function formatBeijingDateTime(value) {
  const time = parseBeijingTime(value)
  if (time === null) return '未知'
  return new Date(time + BEIJING_OFFSET).toISOString().slice(0, 16).replace('T', ' ')
}

export function beijingDayStart(value = Date.now()) {
  const time = parseBeijingTime(value)
  return time === null ? null : Math.floor((time + BEIJING_OFFSET) / DAY_MS) * DAY_MS - BEIJING_OFFSET
}

export function calendarRange(anchor = Date.now(), mode = 'month') {
  const day = beijingDayStart(anchor) ?? beijingDayStart()
  const local = new Date(day + BEIJING_OFFSET)
  const start = mode === 'month' ? Date.UTC(local.getUTCFullYear(), local.getUTCMonth(), 1) - BEIJING_OFFSET : mode === 'rolling' ? day - 3 * DAY_MS : day
  const end = mode === 'month' ? Date.UTC(local.getUTCFullYear(), local.getUTCMonth() + 1, 1) - BEIJING_OFFSET : start + (mode === 'rolling' ? 30 : 14) * DAY_MS
  const days = Array.from({ length: Math.round((end - start) / DAY_MS) }, (_, index) => {
    const timestamp = start + index * DAY_MS
    const date = new Date(timestamp + BEIJING_OFFSET)
    return { timestamp, day: date.getUTCDate(), month: date.getUTCMonth() + 1, weekday: '日一二三四五六'[date.getUTCDay()], weekend: [0, 6].includes(date.getUTCDay()) }
  })
  return { start, end, days }
}

export function shiftCalendarAnchor(anchor, mode, direction) {
  if (mode === 'rolling') return beijingDayStart(anchor) + direction * 30 * DAY_MS
  const range = calendarRange(anchor, mode)
  if (mode !== 'month') return range.start + direction * 14 * DAY_MS
  const local = new Date(range.start + BEIJING_OFFSET)
  return Date.UTC(local.getUTCFullYear(), local.getUTCMonth() + direction, 1) - BEIJING_OFFSET
}

export function eventGeometry(event, range) {
  const start = parseBeijingTime(event.start_at || event.start_date)
  const end = parseBeijingTime(event.end_at)
  const base = { start, end, approximateStart: !event.start_at && !!event.start_date, left: 0, width: 0, visible: false, clippedStart: false, clippedEnd: false }
  if ((!missing(event.start_at) && start === null) || (!missing(event.end_at) && end === null)) return { ...base, kind: 'invalid', reason: '日期无法解析' }
  if (start !== null && end !== null && end < start) return { ...base, kind: 'invalid', reason: '截止早于开始' }
  if (start === null && end === null) return { ...base, kind: 'undated', reason: '起止时间均未知' }
  const span = range.end - range.start
  if (start === null || end === null || start === end) {
    const time = start ?? end
    return { ...base, kind: 'point', endpoint: start === null ? 'end' : end === null ? 'start' : 'instant', reason: start === null ? '开始时间未知' : end === null ? '截止时间未知' : '同一时点', visible: time >= range.start && time < range.end, left: (time - range.start) / span * 100 }
  }
  return { ...base, kind: 'range', reason: '', visible: end > range.start && start < range.end,
    left: Math.max(0, (start - range.start) / span * 100), width: Math.max(0, (Math.min(end, range.end) - Math.max(start, range.start)) / span * 100),
    clippedStart: start < range.start, clippedEnd: end > range.end }
}

export function eventStatus(event, now = Date.now()) {
  const geometry = eventGeometry(event, { start: now, end: now + DAY_MS })
  if (geometry.kind === 'invalid') return '日期异常'
  if (geometry.end !== null && geometry.end <= now) return '已结束'
  if (geometry.start !== null && geometry.start > now) return '未开始'
  if (geometry.approximateStart && beijingDayStart(now) === geometry.start) return '更新后开放'
  if (geometry.end === null) return geometry.start === null ? '时间待定' : '截止未知'
  if (geometry.start === null) return '开始未知'
  return '进行中'
}

export function collectCalendarEvents(games = [], snapshots = {}, gameId = '') {
  return games.filter((game) => !gameId || gameId === 'all' || game.game_id === gameId).flatMap((game) => {
    const snap = snapshots[game.game_id]?.events
    if (!Array.isArray(snap?.payload)) return []
    return snap.payload.filter((event) => event && typeof event === 'object').map((event, index) => ({
      ...event, id: `${game.game_id}:${index}:${event.source_post_id ?? ''}:${event.name ?? ''}`,
      gameId: game.game_id, gameName: game.display_name || game.game_id, category: event.category || '其他活动',
      fetchedAt: event.fetched_at || snap.fetched_at, stale: Boolean(snap.stale || event.source_stale),
    }))
  })
}

export function groupCalendarEvents(events) {
  const groups = new Map()
  for (const event of events) {
    const key = event.gameId
    if (!groups.has(key)) groups.set(key, { key, gameId: event.gameId, gameName: event.gameName, events: [] })
    groups.get(key).events.push(event)
  }
  return [...groups.values()]
}

export function safeUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value) || /[\s\\\u0000-\u001f]/.test(value)) return null
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch {
    return null
  }
}

