import { DAY_MS, beijingDayStart, formatBeijingDateTime, parseBeijingTime } from './calendar.js'

export function displayBeijing(value) {
  const formatted = formatBeijingDateTime(value)
  return formatted === '未知' ? '未提供' : formatted
}
export function monthDay(value) {
  const parsed = parseBeijingTime(value)
  return parsed == null ? '' : formatBeijingDateTime(parsed).slice(5, 10)
}
export function resetLabel(value, now = Date.now()) {
  const time = parseBeijingTime(value)
  if (time == null) return null
  if (time <= now) return '已可重置'
  const days = Math.round((beijingDayStart(time) - beijingDayStart(now)) / DAY_MS)
  return days === 0 ? '今日重置' : days === 1 ? '明日重置' : `${days} 天后重置`
}
export function elapsedLabel(value, now = Date.now()) {
  const time = parseBeijingTime(value)
  if (time == null) return '尚未尝试'
  const mins = Math.max(0, Math.floor((now - time) / 60000))
  return mins === 0 ? '刚刚' : mins < 60 ? `${mins} 分钟前` : mins < 1440 ? `${Math.floor(mins / 60)} 小时前` : `${Math.floor(mins / 1440)} 天前`
}
