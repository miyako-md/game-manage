import { DAY_MS, eventGeometry, eventStatus, formatBeijingDateTime, parseBeijingTime } from './calendar.js'

// Match qq/event_views.py: a date is not an instant, even if a source puts
// midnight in its *_at field. A resolved version_end is an explicit instant.
export function eventEndpoint(event, side) {
  const raw = event[`${side}_at`], precision = event[`${side}_precision`]
  if (![undefined, null, 'minute', 'version_end'].includes(precision) || typeof raw !== 'string' || !/[T ]\d{2}:\d{2}/.test(raw)) return null
  return parseBeijingTime(raw)
}
const datePart = value => typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value) && parseBeijingTime(value.slice(0,10)) !== null ? value.slice(0,10) : null
const explicitUncertainty = (event, side) => eventEndpoint(event,side) === null && (event[`${side}_text`] || event[`${side}_date`] || ['relative','day','dependent','unknown'].includes(event[`${side}_precision`]))

export function eventBoundaryText(event, side) {
  const instant = eventEndpoint(event,side), precision = event[`${side}_precision`], description = event[`${side}_text`]
  if (instant !== null) return formatBeijingDateTime(instant) + (precision === 'version_end' ? ` · ${description || '维护前'}` : '')
  const date = datePart(event[`${side}_at`] || event[`${side}_date`])
  if (precision === 'relative') return (date ? `${date} · ` : '') + (description || '相对时间，时刻待确认')
  return date ? `${date} · 时刻未确认${description ? ` · ${description}` : ''}` : description || '未知'
}

export function normalizeQqEvents(payload) {
  const source = Array.isArray(payload) ? payload : Array.isArray(payload?.events) ? payload.events : []
  const seen = new Set(), output = []
  for (const original of source.filter(row=>row && typeof row === 'object' && !Array.isArray(row))) {
    const phases = Array.isArray(original.phases) ? original.phases.filter(row=>row && typeof row === 'object' && !Array.isArray(row)) : []
    const rows = phases.length ? phases : [original]
    rows.forEach((phase,index) => {
      const item = {...original,...phase}
      delete item.phases
      const title = item.name || item.title
      if (!title) return
      item.name = String(title) + (rows.length > 1 ? ` · 阶段 ${index+1}` : '')
      const key = JSON.stringify([item.name,item.category,item.start_at,item.start_date,item.end_at,item.end_date,item.start_text,item.end_text])
      if (!seen.has(key)) { seen.add(key); output.push(item) }
    })
  }
  return output
}

export function selectQqEvents(payload, command, now) {
  const windowEnd = now + 168*3600000
  return normalizeQqEvents(payload).filter(event => {
    if (command === 'calendar') return true
    const first = eventEndpoint(event,'start'), last = eventEndpoint(event,'end')
    const invalid = first !== null && last !== null && last <= first
    if (command === 'recent_events') return (!invalid && [first,last].some(instant=>instant !== null && now < instant && instant <= windowEnd)) || invalid || ['start','end'].some(side=>explicitUncertainty(event,side))
    if (command === 'events') {
      if (!invalid && first !== null && last !== null) return first <= now && now < last
      return !(last !== null && last <= now || first !== null && first > now)
    }
    return true
  })
}

export function qqEventGeometry(event, range, command) {
  const first = eventEndpoint(event,'start'), last = eventEndpoint(event,'end')
  const empty = eventGeometry({},range)
  if (first !== null && last !== null) {
    if (last <= first) return {...empty,kind:'invalid',reason:'截止不晚于开始，来源日期区间异常'}
    return eventGeometry({start_at:first,end_at:last},range)
  }
  const reason = `开始：${eventBoundaryText(event,'start')} · 截止：${eventBoundaryText(event,'end')}`
  if (command === 'calendar' && !['start','end'].some(side=>['relative','dependent','unknown'].includes(event[`${side}_precision`]))) {
    const startDate = datePart(event.start_at || event.start_date), endDate = datePart(event.end_at || event.end_date)
    const start = first ?? (startDate ? parseBeijingTime(startDate) : null)
    // A day-only end covers that whole Beijing day; exact midnight stays exclusive.
    const end = last ?? (endDate ? parseBeijingTime(endDate)+DAY_MS : null)
    if (start !== null && end !== null && end > start) return {...eventGeometry({start_at:start,end_at:end},range),timeUncertain:true,reason}
  }
  // An explicitly uncertain boundary remains visible below the original
  // timeline, including when its stated date lies outside the rolling window.
  if (command === 'events' || ['start','end'].some(side=>explicitUncertainty(event,side))) return {...empty,timeUncertain:true,reason}
  return {...eventGeometry({start_at:first,end_at:last},range),reason}
}

export function qqEventStatus(event, now, geometry) {
  if (geometry.kind === 'invalid') return '日期异常'
  if (geometry.timeUncertain) return '时间待确认'
  return eventStatus({start_at:eventEndpoint(event,'start'),end_at:eventEndpoint(event,'end')},now)
}
