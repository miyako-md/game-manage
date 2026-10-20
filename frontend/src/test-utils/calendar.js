import { calendarDaysRange, parseBeijingTime } from '../calendar.js'

// Explicit Beijing display bounds for event geometry fixtures.
export const beijingRange = (start, end) => calendarDaysRange(parseBeijingTime(start), parseBeijingTime(end))
