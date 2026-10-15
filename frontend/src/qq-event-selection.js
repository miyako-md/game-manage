import { eventEndpoint, normalizeCalendarEvents } from './calendar.js'

const explicitUncertainty = (event, side) => eventEndpoint(event,side) === null && (event[`${side}_text`] || event[`${side}_date`] || ['relative','day','dependent','unknown'].includes(event[`${side}_precision`]))

export function selectQqEvents(payload, command, now) {
  const windowEnd = now + 168*3600000
  return normalizeCalendarEvents(payload).filter(event => {
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
