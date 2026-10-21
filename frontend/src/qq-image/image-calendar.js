import {DAY_MS,beijingDayStart,calendarDaysRange,eventGeometry,formatBeijingDateTime,versionCalendarRange} from '../calendar.js'

/** 活动 uses a 14-day window from two days ago; 日历 (full) spans every dated activity of the version. */
export function imageCalendarWindows(events,asOf,full=false){
 const start=beijingDayStart(asOf)-2*DAY_MS
 const range=full&&versionCalendarRange(events,asOf)||calendarDaysRange(start,start+14*DAY_MS)
 const visible=events.filter(event=>eventGeometry(event,range).visible)
 return [{range,events:visible,label:formatBeijingDateTime(range.start).slice(0,10)+' 至 '+formatBeijingDateTime(range.end-1).slice(0,10)}]
}
