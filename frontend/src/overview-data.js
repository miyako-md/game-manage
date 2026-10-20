import { DAY_MS, parseBeijingTime } from './calendar.js'
import { ENDFIELD_SPECIAL_POOL } from './dashboard.js'
import { collectionState } from './snapshot-state.js'
import { gachaPools, gachaView as endfieldGachaView, kindSummary, poolTotal, recentSixStars, sixPullsText } from './endfield-gacha-summary.js'

// Data for the overview's cards, read from snapshots the page already has. Nothing here fetches.
const count = value => typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
const rows = value => Array.isArray(value) ? value.filter(row => row && typeof row === 'object' && !Array.isArray(row)) : []
const versioned = (snapshots, cap) => { const p = snapshots?.[cap]?.payload; return p && typeof p === 'object' && !Array.isArray(p) && p.schema_version === 1 ? p : null }
const beijingDay = time => Math.floor((time + 8 * 3600000) / DAY_MS)
const weekday = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', weekday: 'short' })
const clock = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
const monthDay = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric' })

// NTE's 日常活跃 and Endfield's 每日活跃 carry no reset time. Both reset daily at
// 04:00 Beijing time, so a value belongs to the cycle ending at the first 04:00
// after it was read. Weekly items keep no boundary: their reset is unconfirmed.
const DAILY_RESET_MS = 4 * 3600000 - 8 * 3600000
const dailyReset = snapshot => {
  const fetchedAt = parseBeijingTime(snapshot?.fetched_at)
  return fetchedAt == null ? null : (Math.floor((fetchedAt - DAILY_RESET_MS) / DAY_MS) + 1) * DAY_MS + DAILY_RESET_MS
}

/** When a progress item next resets, in words: 今天/明天/周X and the time, or N 天后. */
export function resetLabel(at, now) {
  if (at == null || at <= now) return ''
  const days = beijingDay(at) - beijingDay(now)
  const day = days === 0 ? '今天' : days === 1 ? '明天' : days < 7 ? weekday.format(at) : `${days} 天后`
  return days < 7 ? `${day} ${clock.format(at)} 重置` : `${day}重置`
}

/**
 * Daily and weekly progress the games report, read-only, daily first and then
 * by reset time. Wuwa's widget items count when they reset within a week (its
 * 活跃度 is the daily one); NTE gives 日常活跃 out of 100 and the weekly
 * attempts left; Endfield's Skland card gives 每日活跃 and 每周任务. A game
 * without such data adds nothing.
 */
export function dailyTasks(games, snapshots = {}, now = Date.now()) {
  const tasks = games.flatMap(game => {
    const id = game.game_id, snaps = snapshots[id] || {}
    const task = (snapshot, key, name, current, total, daily, resetAt = null, unit = '') => {
      const retained = snapshot?.stale === true || collectionState(snapshot) === 'failed' || !!snapshot?.readError
      const fetchedAt = parseBeijingTime(snapshot?.fetched_at)
      // A retained value can still prove completion before its recorded next
      // reset. Without that boundary, its current cycle cannot be established.
      const sameCycle = resetAt != null && resetAt > now && fetchedAt != null && fetchedAt <= now && fetchedAt < resetAt
      const pending = resetAt != null && resetAt <= now || retained && !sameCycle
      return {
        key: `${id}:${key}`, gameId: id, gameName: game.display_name, name, current, total, unit, daily, pending, retained,
        done: !pending && (total == null ? current === 0 : current >= total), resetAt, reset: resetLabel(resetAt, now),
      }
    }
    if (id === 'wuthering_waves') {
      const items = rows(snaps.progress?.payload)
      return items.flatMap((item, index) => {
        const current = count(item.cur), total = count(item.total), resetAt = parseBeijingTime(item.refresh_at)
        const daily = item.name === '活跃度'
        if (current == null || !total || typeof item.name !== 'string') return []
        if (!daily && (resetAt == null || resetAt <= now || resetAt - now > 7 * DAY_MS)) return []
        return [task(snaps.progress, `p${index}`,  item.name, current, total, daily, resetAt)]
      })
    }
    if (id === 'nte') {
      const stamina = versioned(snaps, 'stamina')
      const activity = count(stamina?.daily_activity), weekly = count(stamina?.weekly_remaining)
      return [
        ...(activity == null ? [] : [task(snaps.stamina, 'daily', '日常活跃', activity, 100, true, dailyReset(snaps.stamina))]),
        ...(weekly == null ? [] : [task(snaps.stamina, 'weekly', '周本剩余', weekly, null, false, null, '次')]),
      ]
    }
    if (id === 'endfield') {
      return rows(versioned(snaps, 'progress')?.items).flatMap(item => {
        const current = count(item.cur), total = count(item.total)
        return ['daily', 'weekly'].includes(item.id) && current != null && total ? [task(snaps.progress, item.id, item.name || (item.id === 'daily' ? '每日活跃' : '每周任务'), current, total, item.id === 'daily', item.id === 'daily' ? dailyReset(snaps.progress) : null)] : []
      })
    }
    return []
  })
  return tasks.sort((a, b) => b.daily - a.daily || (a.resetAt ?? Infinity) - (b.resetAt ?? Infinity))
}

/**
 * Deadlines per Beijing calendar day for the next `days` days, today first.
 * Each day says which games end something then, for the bar's tooltip.
 */
export function deadlineDays(events, now, days = 7) {
  const today = beijingDay(now)
  return Array.from({ length: days }, (_, i) => {
    const time = now + i * DAY_MS, ending = events.filter(event => beijingDay(event.endTime) === today + i)
    const label = days <= 7 ? (i === 0 ? '今天' : i === 1 ? '明天' : weekday.format(time)) : i === 0 ? '今天' : monthDay.format(time)
    const games = [...new Set(ending.map(event => event.gameName))].map(name => `${name} ${ending.filter(event => event.gameName === name).length}`)
    // A month of bars only labels every fifth day under the axis; each bar still names its day.
    return { label, tick: days <= 7 || i % 5 === 0 ? label : '', value: ending.length, note: games.join(' · ') }
  })
}

function endfieldDigest(game, snaps, account) {
  // A combined role page may use Skland for its visible nickname and level.
  // The ledger still checks the original passport identity, never that projection.
  const passportSnaps = Object.hasOwn(snaps, 'passport_account') ? { ...snaps, account: snaps.passport_account } : snaps
  const view = endfieldGachaView({ snaps: passportSnaps, configured: game.credentials_configured, authAccount: account })
  const payload = view.snapshot?.payload
  if (!payload) return null
  const pools = gachaPools(payload), report = payload.report?.schema_version === 1 ? payload.report : null
  // Weapon requisition is a different currency: once a ledger has weapon pools, the card counts operators only.
  const operators = kindSummary(pools, 'character'), weapons = kindSummary(pools, 'weapon')
  const total = weapons ? operators?.total : count(report?.total) ?? poolTotal(pools, 'total')
  if (total == null) return null
  const special = pools.find(pool => pool.key === ENDFIELD_SPECIAL_POOL)?.since_last_six
  const average = operators ? operators.pace.average : count(report?.known_exact_intervals) ? count(report.average_exact_pulls) : null
  const latest = recentSixStars(pools.filter(pool => pool.kind !== 'weapon'), 1)[0]
  return {
    gameId: game.game_id, gameName: game.display_name, total, tab: 'gacha', scope: '干员寻访',
    stats: [
      { label: '6★', value: weapons ? operators?.six_star : count(report?.six_star) ?? poolTotal(pools, 'six_star') },
      { label: '平均出 6★', value: average == null ? null : `${Math.round(average)} 抽` },
      { label: '特许距上次 6★', value: count(special?.count) == null ? null : `${special.status === 'exact' ? '' : '≥'}${special.count} 抽` },
    ],
    latest: latest ? { name: latest.name, detail: `${latest.pool_name || latest.pool_label || '寻访'} · ${sixPullsText(latest)}`, time: count(latest.obtained_at) } : null,
  }
}

function nteDigest(game, snaps) {
  const payload = versioned(snaps, 'gacha')
  const total = count(payload?.total_draws)
  if (total == null) return null
  const pulls = rows(payload.pools).flatMap(pool => rows(pool.details).map(entry => ({ ...entry, pool: pool.name, time: parseBeijingTime(entry.obtained_at) })))
  const pities = pulls.map(entry => count(entry.pity)).filter(value => value != null)
  const latest = pulls.filter(entry => entry.time != null).sort((a, b) => b.time - a.time)[0]
  return {
    gameId: game.game_id, gameName: game.display_name, total, tab: 'gacha',
    stats: [
      { label: 'S 级', value: count(payload.total_s) },
      { label: '平均出 S', value: pities.length ? `${Math.round(pities.reduce((sum, value) => sum + value, 0) / pities.length)} 抽` : null },
      { label: '欧气称号', value: typeof payload.luck_title === 'string' && payload.luck_title.trim() ? payload.luck_title.trim() : null },
    ],
    latest: latest && typeof latest.name === 'string' ? { name: latest.name, detail: `${latest.pool || '棋盘'} · ${count(latest.pity) == null ? '抽数未知' : `${latest.pity} 抽`}`, time: latest.time } : null,
  }
}

/** One headline per game that has pull records in its snapshots (Endfield's ledger, NTE's community card). */
export function gachaDigests(games, snapshots = {}, accounts = {}) {
  return games.flatMap(game => {
    const digest = game.game_id === 'endfield' ? endfieldDigest(game, snapshots.endfield || {}, accounts.endfield)
      : game.game_id === 'nte' ? nteDigest(game, snapshots.nte || {}) : null
    return digest ? [digest] : []
  })
}
