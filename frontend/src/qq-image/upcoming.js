import {DAY_MS,beijingDayStart,formatBeijingDateTime,parseBeijingTime} from '../calendar.js'

// Mirrors qq/event_views.py recent_window: the server selects the rows, the image groups them.
export const RECENT_HOURS=72
const HOUR_MS=3600000
const timed=value=>typeof value==='string'&&/[T ]\d{2}:\d{2}/.test(value)

/** Explicit instants as given; day precision spans the whole Beijing day; vague times stay unknown. */
export function windowEndpoint(event,side){
 const precision=event[side+'_precision'],raw=event[side+'_at']
 if([undefined,null,'minute','version_end'].includes(precision)&&timed(raw))return parseBeijingTime(raw)
 if(![undefined,null,'day'].includes(precision))return null
 const text=raw||event[side+'_date'],day=typeof text==='string'?parseBeijingTime(text.slice(0,10)):null
 return day===null?null:side==='end'?day+DAY_MS-1000:day
}

function duration(ms){
 const minutes=Math.floor(ms/60000),days=Math.floor(minutes/1440),hours=Math.floor(minutes%1440/60)
 return days?`${days} 天${hours?` ${hours} 小时`:''}`:hours?`${hours} 小时`:`${minutes} 分钟`
}
function countdown(side,at,dayOnly,now){
 if(dayOnly){
  const days=Math.round((beijingDayStart(at)-beijingDayStart(now))/DAY_MS),when=['今天','明天','后天'][days]||`${days} 天后`
  return when+(side==='start'?'开始':'结束')
 }
 if(at-now<60000)return side==='start'?'即将开始':'即将结束'
 return side==='start'?duration(at-now)+'后开始':'还剩 '+duration(at-now)
}
function timeLabel(at,dayOnly){
 const text=formatBeijingDateTime(at),weekday='日一二三四五六'[new Date(at+8*HOUR_MS).getUTCDay()]
 return `${text.slice(5,10)} 周${weekday} ${dayOnly?'当天':text.slice(11,16)}`
}

// A vague boundary may still fall in the window unless its source date rules that out.
function unconfirmed(event,side,now,limit){
 if(windowEndpoint(event,side)!==null||!(event[side+'_text']||event[side+'_date']||event[side+'_at']||['relative','dependent','unknown'].includes(event[side+'_precision'])))return false
 const text=event[side+'_at']||event[side+'_date'],day=typeof text==='string'?parseBeijingTime(text.slice(0,10)):null
 return day===null||day>=beijingDayStart(now)&&day<=limit
}

/** Events that start / end within [now, now+72h], plus the count still lacking a confirmed time. */
export function upcomingSections(events,now){
 const limit=now+RECENT_HOURS*HOUR_MS,starting=[],ending=[]
 let pending=0
 for(const event of events){
  const first=windowEndpoint(event,'start'),last=windowEndpoint(event,'end')
  const invalid=first!==null&&last!==null&&last<first
  let listed=false
  for(const [side,at,bucket] of [['start',first,starting],['end',last,ending]]){
   if(invalid||at===null||at<now||at>limit)continue
   const dayOnly=!timed(event[side+'_at'])||event[side+'_precision']==='day'
   bucket.push({...event,side,at,time:timeLabel(at,dayOnly),countdown:countdown(side,at,dayOnly,now),urgent:at-now<=24*HOUR_MS});listed=true
  }
  const unresolved=invalid||['start','end'].some(side=>unconfirmed(event,side,now,limit))
  if(!listed&&unresolved&&!(last!==null&&last<now)&&!(first!==null&&first>limit))pending++
 }
 const order=(a,b)=>a.at-b.at
 return {starting:starting.sort(order),ending:ending.sort(order),pending}
}
