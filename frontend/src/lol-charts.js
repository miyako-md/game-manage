// Pure helpers behind the League of Legends visuals: no DOM, no network, no clock unless one is passed in.
import { DAY_MS, beijingDayStart, formatBeijingDateTime, parseBeijingTime } from './calendar.js'

const finite = value => typeof value === 'number' && Number.isFinite(value)
const BEIJING_OFFSET = 8 * 3600000

/** First visible character of a name, for the letter tiles that stand in for champion and team art. */
export function letterOf(name, fallback = '?') {
  const text = typeof name === 'string' ? name.trim() : ''
  return text ? [...text][0].toUpperCase() : fallback
}

/** Win, loss, unknown and remake counts in drawing order; a count that is missing draws nothing. */
export function resultParts(overview = {}) {
  const count = value => (finite(value) && value > 0 ? value : 0)
  return [
    { key: 'win', label: '胜利', value: count(overview.wins) },
    { key: 'loss', label: '失败', value: count(overview.losses) },
    { key: 'unknown', label: '胜负未知', value: count(overview.unknown_results) },
    { key: 'remake', label: '重开', value: count(overview.remakes) },
  ]
}

/** (K + A) / max(D, 1); unknown unless all three numbers are known. */
export function kdaRatio(kills, deaths, assists) {
  return finite(kills) && finite(deaths) && finite(assists) ? (kills + assists) / Math.max(deaths, 1) : null
}

/** Mean of a field over the rows that know it; null when none does. */
export function meanOf(rows, field) {
  const values = rows.map(row => row[field]).filter(finite)
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null
}

/** Shares of one game's kills, deaths and assists (0–1, summing to 1); null unless all three are known and not all zero. */
export function kdaSplit(kills, deaths, assists) {
  if (!finite(kills) || !finite(deaths) || !finite(assists)) return null
  const total = kills + deaths + assists
  return total > 0 ? { k: kills / total, d: deaths / total, a: assists / total } : null
}

const KDA_CAP = 10
/** Bar height (percent) for a KDA ratio on a scale that stops at 10; `clipped` marks a bar that hit the stop. */
export function kdaBar(ratio, cap = KDA_CAP) {
  if (!finite(ratio)) return null
  return { pct: Math.max(4, Math.min(1, ratio / cap) * 100), clipped: ratio > cap }
}

/** One letter for each way a game can end, so a result never rests on colour alone. */
export const FORM_LABELS = { win: '胜', loss: '负', remake: '重', unknown: '未' }

/**
 * The newest `limit` games as a strip that reads left to right like time (oldest first).
 * `rows` are newest first; `kindOf(row)` is 'win', 'loss', 'remake' or 'unknown'.
 */
export function formStrip(rows, kindOf, limit = 20) {
  return rows.slice(0, limit).map(row => {
    const kind = kindOf(row)
    return { row, kind, label: FORM_LABELS[kind] ?? FORM_LABELS.unknown }
  }).reverse()
}

/** Wins, losses and the win rate of a strip; remakes and unknown results are not decided games. */
export function formRecord(strip) {
  const wins = strip.filter(item => item.kind === 'win').length
  const losses = strip.filter(item => item.kind === 'loss').length
  return { wins, losses, rate: wins + losses ? Math.round(wins / (wins + losses) * 100) : null }
}

/** Ranked solo/duo entry from an account snapshot payload; null for an unranked or empty season. */
export function rankedSolo(payload) {
  const entry = payload?.extra?.ranked_solo
  if (!entry || typeof entry !== 'object' || !entry.tier) return null
  const rounded = value => (finite(value) ? value : null)
  return {
    tier: String(entry.tier), division: entry.division ? String(entry.division) : '',
    points: rounded(entry.league_points), wins: rounded(entry.wins), losses: rounded(entry.losses),
  }
}

/** Every Beijing date of the window, oldest first, with games and wins filled in (zero when the archive has none). */
export function heatmapDays(rows, count, now = Date.now()) {
  const end = beijingDayStart(now), start = end - (count - 1) * DAY_MS
  const byDate = new Map((rows || []).map(row => [row.date, row]))
  return Array.from({ length: count }, (_, index) => {
    const date = formatBeijingDateTime(start + index * DAY_MS).slice(0, 10), row = byDate.get(date)
    return { date, games: row?.games ?? 0, wins: row?.wins ?? 0 }
  })
}

// Monday = 0 … Sunday = 6 for a YYYY-MM-DD date.
const weekdayRow = date => (new Date(`${date}T00:00:00Z`).getUTCDay() + 6) % 7

/**
 * Layout of a calendar heat map. `days` is every date of the window, oldest first. Columns are weeks that
 * start on Monday, so `first` is the row the first date sits in; `level` is 0 for no games, 1–4 by share of
 * the busiest day. `months` labels the column where a new month begins, skipping labels that would crowd.
 */
export function heatmapLayout(days) {
  const list = days || []
  const first = list.length ? weekdayRow(list[0].date) : 0
  const max = Math.max(0, ...list.map(day => day.games))
  const cells = list.map(day => ({ ...day, level: day.games > 0 && max > 0 ? Math.min(4, Math.ceil((day.games / max) * 4)) : 0 }))
  const months = []
  list.forEach((day, index) => {
    const month = day.date.slice(5, 7)
    if (index > 0 && month === list[index - 1].date.slice(5, 7)) return
    const col = Math.floor((first + index) / 7)
    if (months.length && col - months.at(-1).col < 3) months.pop()
    months.push({ col, label: `${Number(month)}月` })
  })
  let run = 0, longest = 0
  for (const day of list) { run = day.games > 0 ? run + 1 : 0; longest = Math.max(longest, run) }
  const busiest = cells.reduce((best, day) => (day.games > (best?.games ?? 0) ? day : best), null)
  return {
    cells, first, weeks: Math.ceil((first + list.length) / 7), months, max,
    total: list.reduce((sum, day) => sum + day.games, 0), wins: list.reduce((sum, day) => sum + day.wins, 0),
    activeDays: list.filter(day => day.games > 0).length, longest, busiest,
  }
}

/** Items per Beijing week (weeks start on Monday) for the last `weeks` weeks, oldest first; dates that do not parse are skipped. */
export function weeklyCounts(dates, weeks = 8, now = Date.now()) {
  const today = beijingDayStart(now)
  const monday = today - ((new Date(today + BEIJING_OFFSET).getUTCDay() + 6) % 7) * DAY_MS
  const buckets = Array.from({ length: weeks }, (_, index) => ({ start: monday - (weeks - 1 - index) * 7 * DAY_MS, value: 0 }))
  for (const value of dates || []) {
    const time = parseBeijingTime(value)
    if (time == null) continue
    const index = Math.floor((beijingDayStart(time) - buckets[0].start) / (7 * DAY_MS))
    if (index >= 0 && index < weeks) buckets[index].value += 1
  }
  return buckets.map(bucket => ({ label: formatBeijingDateTime(bucket.start).slice(5, 10).replace('-', '/'), value: bucket.value }))
}

/** Games started in each Beijing hour of the day, 0–23; rows without a usable start time are skipped. */
export function hourCounts(rows) {
  const counts = Array(24).fill(0)
  for (const row of rows || []) {
    const time = parseBeijingTime(row.start_at)
    if (time != null) counts[new Date(time + BEIJING_OFFSET).getUTCHours()] += 1
  }
  return counts
}
