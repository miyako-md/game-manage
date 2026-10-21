<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import GameIcon from './GameIcon.vue'
import ArtworkImage from './ArtworkImage.vue'
import { eventArtwork } from '../event-artwork.js'
import { beijingDayStart, eventGeometry, eventStatus, browserDayStart, browserEventGeometry, browserEventStatus, browserCalendarPosition } from '../calendar.js'
import { presentationGroups, activityBoundaryDays } from '../calendar-presentation.js'
import { useCalendarPan } from '../calendar-pan.js'
import { createCalendarDefaultPosition } from '../calendar-position.js'
import { gameVars } from '../dashboard.js'
const props = defineProps({ events:{type:Array,default:()=>[]}, snapshots:{type:Object,default:()=>({})}, range:{type:Object,default:null}, asOf:{type:Number,required:true}, rangeMode:{type:String,default:'rolling'}, mode:{type:String,default:'screen'}, selectedId:{type:String,default:null}, emptyTitle:{type:String,default:'暂无活动数据'}, showUnplaced:{type:Boolean,default:true} })
const emit = defineEmits(['select'])
const viewport = ref(null)
const pan = useCalendarPan(viewport, () => props.mode !== 'image')
let defaultPosition
onMounted(() => { defaultPosition = createCalendarDefaultPosition(viewport.value, () => props.mode !== 'image') })
onBeforeUnmount(() => defaultPosition?.destroy())
// A different game or date window places today in the left third. Refreshing the same data
// and the minute clock preserve the position the reader has chosen.
watch([
  () => props.range?.start, () => props.range?.end, () => props.rangeMode, () => props.mode,
  () => [...new Set(props.events.map(event => event.gameId || event.game_id || ''))].sort().join(':'),
], () => {
  pan.reset()
  defaultPosition?.reset()
}, { flush:'post' })
const dayStart = value => props.mode === 'image' ? beijingDayStart(value) : browserDayStart(value)
const position = time => props.mode === 'image' ? (time-props.range.start)/(props.range.end-props.range.start)*100 : browserCalendarPosition(time,props.range)
const today = computed(() => dayStart(props.asOf))
const todayPosition = computed(() => props.range ? position(props.asOf) : 0)
const todayVisible = computed(() => props.range && props.asOf>=props.range.start && props.asOf<props.range.end)
const events = computed(() => props.events.map(event => {
  const geometry = (props.mode === 'image' ? eventGeometry : browserEventGeometry)(event, props.range || {start:props.asOf,end:props.asOf+86400000})
  const status = (props.mode === 'image' ? eventStatus : browserEventStatus)(event,props.asOf)
  let elapsed=null, remainingDays=null
  if (geometry.kind==='range' && status==='进行中' && props.range) {
    const start=Math.max(geometry.start,props.range.start), end=Math.min(geometry.end,props.range.end)
    if (end>start) elapsed=Math.min(100,Math.max(0,(position(props.asOf)-position(start))/(position(end)-position(start))*100))
    remainingDays=Math.max(0,Math.ceil((geometry.end-props.asOf)/86400000))
  }
  return {...event,geometry,status,elapsed,remainingDays}
}))
const groups = computed(() => presentationGroups(events.value.filter(event => event.geometry.visible), props.mode))
const boundaryDays = computed(() => props.mode === 'image' ? new Set() : activityBoundaryDays(events.value,dayStart))
const undated = computed(() => props.showUnplaced ? events.value.filter(event => event.geometry.kind==='undated') : [])
const invalid = computed(() => props.showUnplaced ? events.value.filter(event => event.geometry.kind==='invalid') : [])
const groupVars = id => gameVars(id==='lol' ? 'league_of_legends' : id)
const barStyle = event => ({left:event.geometry.left+'%',width:event.geometry.kind==='range' ? event.geometry.width+'%' : undefined})
function stateLabel(event) {
  const state=event.status==='更新后开放' && event.start_precision!=='relative' ? '时刻待定' : event.status
  return state + (event.start_estimated ? ' · 预计' : event.geometry.approximateStart && ['未开始','进行中'].includes(state) ? ' · 时刻未知' : '')
}
const eventDescription = event => [event.name||'未命名活动',event.gameName,event.category,stateLabel(event),event.remainingDays != null ? `剩 ${event.remainingDays} 天` : ''].filter(Boolean).join(' · ')
function selectEvent(event, interaction) { if (props.mode!=='image') emit('select',event,interaction) }
</script>
<template>
  <div ref="viewport" class="calendar-content" :class="{ 'image-mode': mode === 'image' }">
<div v-if="range" class="timeline-scroll" :tabindex="mode === 'image' ? undefined : 0" role="region" aria-label="活动日期横轴，可横向和纵向滚动" :style="{ '--day-count': range.days.length, '--timeline-min': `calc(var(--timeline-label-width) + ${range.days.length * (rangeMode === 'fortnight' ? 44 : 40)}px)` }">
        <div :key="range.start" class="timeline-canvas t-panel">
          <div class="timeline-header" data-render-block>
            <div class="timeline-label header-label"><span>游戏</span><small v-if="mode === 'image'">{{ rangeMode === 'month' ? '当月时间轴' : rangeMode === 'rolling' ? '近 30 天时间轴' : rangeMode === 'version' ? '版本活动时间轴' : '14 天时间轴' }}</small></div>
            <div class="date-track">
              <div v-for="(day, index) in range.days" :key="day.timestamp" class="date-cell" :class="{ weekend: day.weekend, 'is-today': day.timestamp === today, 'is-month-start': day.day === 1, 'is-boundary': boundaryDays.has(day.timestamp) }" :title="`${day.month} 月 ${day.day} 日`">
                <span v-if="mode !== 'image' && (index === 0 || day.day === 1)" class="day-month">{{ day.month }}月</span>
                <small class="day-weekday">{{ day.weekday }}</small>
                <strong><template v-if="day.day===1 && mode==='image'">{{ day.month }}/<br>1</template><template v-else>{{ day.day }}</template></strong>
                <span v-if="day.timestamp === today" class="day-today">今天</span>
              </div>
            </div>
          </div>
          <template v-if="groups.length">
            <div v-for="group in groups" :key="group.key" class="timeline-group" data-render-block :style="groupVars(group.gameId)">
              <div class="timeline-label group-label"><GameIcon class="game-monogram" :game-id="group.gameId" :name="group.gameName" /><div><strong>{{ group.gameName }}</strong><span v-if="group.categoryLabel" class="group-category">{{ group.categoryLabel }}</span><small>{{ group.events.length }} 项活动</small></div></div>
              <div class="group-track">
                <div class="grid-backdrop" aria-hidden="true"><div v-for="day in range.days" :key="day.timestamp" :class="{ weekend: day.weekend, 'today-column': day.timestamp === today }" /></div>
                <div v-if="todayVisible" class="today-line" :style="{ left: `${todayPosition}%` }" aria-hidden="true" />
                <div v-for="event in group.events" :key="event.id" class="event-lane" data-render-block>
                  <component :is="mode === 'image' ? 'article' : 'button'" :type="mode === 'image' ? undefined : 'button'" class="timeline-event" :class="{ 'is-point': event.geometry.kind === 'point', 'is-short': event.geometry.kind === 'range' && event.geometry.width < 30, 'label-left': event.geometry.left >= 50, 'is-ended': event.status === '已结束', 'clipped-start': event.geometry.clippedStart, 'clipped-end': event.geometry.clippedEnd, 'is-selected': selectedId === event.id }" :style="barStyle(event)" :title="eventDescription(event)" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" :aria-pressed="mode === 'image' ? undefined : selectedId === event.id" @click="selectEvent(event, $event)">
                    <ArtworkImage v-if="mode !== 'image' && event.geometry.kind === 'range'" class="event-artwork" :candidates="eventArtwork(event, snapshots)" :retry-key="snapshots[event.gameId]?.events" decorative /><template v-if="event.geometry.kind === 'range'"><i v-if="event.elapsed != null" class="event-elapsed" :style="{width:`${event.elapsed}%`}" aria-hidden="true" /><span class="event-summary"><span class="event-heading"><span class="event-bar-title">{{ event.geometry.clippedStart ? '‹ ' : '' }}{{ event.name || '未命名活动' }}{{ event.geometry.clippedEnd ? ' ›' : '' }}</span><small class="event-category">{{ event.category }}</small><small class="event-status">{{ stateLabel(event) }}</small><small v-if="event.remainingDays != null" class="event-remaining" :class="{urgent:event.remainingDays<=3}">剩 {{ event.remainingDays }} 天</small></span></span></template>
                    <template v-else><span class="point-diamond" aria-hidden="true" /><span class="point-label" :class="{ 'point-label-left': event.geometry.left >= 50 }"><ArtworkImage v-if="mode !== 'image'" class="point-artwork" :candidates="eventArtwork(event, snapshots)" :retry-key="snapshots[event.gameId]?.events" decorative /><span class="event-heading"><strong>{{ event.name || '未命名活动' }}</strong><small class="event-category">{{ event.category }}</small><small class="event-status">{{ stateLabel(event) }}</small></span></span></template>
                  </component>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="calendar-empty timeline-empty"><strong>{{ events.length ? '当前范围没有可定位的活动' : emptyTitle }}</strong></div>
        </div>
      </div>
    <p v-if="!range && !events.length" class="calendar-empty">{{ emptyTitle }}</p>
<section v-if="undated.length || invalid.length" class="calendar-unplaced" aria-label="待确认的时间"><div class="unplaced-heading"><h2>待确认的时间</h2></div><div class="unplaced-grid"><div v-for="bucket in [{ title: '日期未提供', events: undated }, { title: '日期异常', events: invalid }]" v-show="bucket.events.length" :key="bucket.title" class="unplaced-bucket"><h3>{{ bucket.title }} <span>{{ bucket.events.length }}</span></h3><component :is="mode === 'image' ? 'article' : 'button'" v-for="event in bucket.events" :key="event.id" data-render-block :type="mode === 'image' ? undefined : 'button'" class="unplaced-event" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" @click="selectEvent(event, $event)"><ArtworkImage v-if="mode !== 'image'" class="unplaced-artwork" :candidates="eventArtwork(event, snapshots)" :retry-key="snapshots[event.gameId]?.events" decorative /><span><strong>{{ event.name || '未命名活动' }}</strong><small>{{ event.category }} · {{ stateLabel(event) }}</small></span></component></div></div></section>
  </div>
</template>
<style scoped>
.timeline-scroll { overflow:visible; flex:none; min-height:140px; scrollbar-color: var(--scrollbar) var(--bg); scrollbar-width: thin; }
.timeline-canvas { min-width: var(--timeline-min); }
.timeline-header, .timeline-group { display: grid; grid-template-columns: var(--timeline-label-width) minmax(0, 1fr); }
/* The date header stays put over the bars that scroll beneath it. */
.timeline-header { position: sticky; top: 0; z-index: 5; background: var(--card-bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.timeline-label { position: sticky; left: 0; z-index: 3; background: var(--card-bg); border-right: 1px solid var(--border); }
.header-label { display: flex; flex-direction: column; justify-content: center; gap: 4px; padding: 18px 20px; color: var(--text-muted); font-size: 12px; font-weight: 500; }
.header-label small { color: var(--text-faint); font-size: 12px; font-weight: 400; }
.date-track, .grid-backdrop { display: grid; grid-template-columns: repeat(var(--day-count), minmax(0, 1fr)); }
.date-cell { min-width:0; min-height: 78px; display: grid; grid-template-rows: 14px 26px 14px; justify-items: center; align-content: center; gap: 3px; padding: 8px 0; border-right: 1px solid var(--overlay-1); font-family: var(--font-sans); }
.date-cell small { font-size: 12px; line-height: 16px; color: var(--text-faint); }
.date-cell strong { display: grid; place-items: center; min-width: 28px; height: 26px; padding: 0 4px; border-radius: 8px; font-variant-numeric: tabular-nums; font-size: 14px; font-weight: 500; line-height: 1; }
.date-cell.is-month-start strong { font-size: 12px; }
.date-cell.weekend { background: var(--overlay-1); }
.date-cell.is-today { color: var(--accent); background: color-mix(in srgb, var(--accent) 5%, transparent); }
.date-cell.is-today strong { background: var(--accent-fill); color: var(--accent-ink); }
.day-today { font-size: 11px; font-weight: 500; line-height: 14px; white-space: nowrap; color: var(--accent); }
/* Keep each badge inside the same daily column used by the activity bars.
   Months get their own row instead of widening the first day's number. */
.calendar-content:not(.image-mode) .date-cell { min-height:108px; grid-template-rows:14px 16px 30px 16px; gap:4px; padding:10px 0; }
.day-month { grid-row:1; font-size:11px; line-height:14px; white-space:nowrap; color:var(--text-muted); }
.calendar-content:not(.image-mode) .day-weekday { grid-row:2; }
.calendar-content:not(.image-mode) .date-cell strong { grid-row:3; min-width:0; width:min(32px,calc(100% - 8px)); height:30px; padding:0; font-size:16px; white-space:nowrap; }
.calendar-content:not(.image-mode) .date-cell.is-month-start strong { font-size:16px; }
.calendar-content:not(.image-mode) .day-today { grid-row:4; }
.timeline-group { border-bottom: 1px solid var(--border); }
.timeline-group:last-child { border-bottom: 0; }
.group-label { display:flex; align-items:flex-start; gap:10px; padding:18px 16px; }
.game-monogram { width: 32px; height: 32px; background: var(--game-tone, var(--control-track)); border-radius: 10px; font-size: 15px; box-shadow: inset 0 0 0 1px var(--card-border); }
.group-label strong { display: block; font-size: 14px; font-weight: 500; line-height: 20px; }
.group-label small { display: block; color: var(--text-faint); font-size: 12px; line-height: 18px; }
.group-track { position:relative; overflow:hidden; container-type:inline-size; }
.grid-backdrop { position: absolute; inset: 0; pointer-events: none; }
.grid-backdrop > div { border-right: 1px solid var(--overlay-2); }
.grid-backdrop .weekend { background: var(--overlay-1); }
.grid-backdrop .today-column { background: color-mix(in srgb, var(--accent) 3%, transparent); }
.today-line { position: absolute; top: 0; bottom: 0; width: 2px; margin-left: -1px; border-radius: 2px; background: var(--accent-fill); z-index: 2; pointer-events: none; }
.event-lane { min-height:34px; padding-bottom:2px; position:relative; }
/* Bars: the game's pale tone with a uniform hairline; the elapsed part is deeper. */
.timeline-event { position:relative; top:0; min-height:32px; min-width:0; border:0; box-shadow:inset 0 0 0 1px color-mix(in srgb, var(--game-vivid, var(--game-accent)) 26%, transparent); border-radius:8px; color:var(--text); background:var(--game-tone, var(--control-track)); padding:4px 10px; display:block; text-align:left; overflow:hidden; transition:filter var(--duration-quick) var(--ease-smooth-out), transform var(--duration-quick) var(--ease-smooth-out); }
@media (hover: hover) and (pointer: fine) { .timeline-event:hover { box-shadow: inset 0 0 0 1px var(--game-vivid, var(--game-accent)); } }
.timeline-event:not(.is-point):active { transform: translateY(1px); }
.timeline-event.is-ended { opacity: .7; }
.event-artwork { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; border-radius:inherit; }
.event-summary { display:grid; gap:2px; min-width:0; width:100%; position:relative; }
.event-heading { display:flex; flex-wrap:wrap; align-items:center; gap:2px 6px; min-width:0; }

.event-summary,.point-label {font-family:inherit;line-height:1.4;text-shadow:0 1px 3px var(--bg),0 0 6px var(--card-bg)}
.event-elapsed{position:absolute;inset:0 auto 0 0;background:color-mix(in srgb,var(--game-vivid,var(--game-accent)) 24%,transparent);border-right:1px solid color-mix(in srgb,var(--game-vivid,var(--game-accent)) 70%,transparent);pointer-events:none}
.event-remaining{flex-shrink:0;font-size:12px;color:var(--text-muted);border-radius:var(--radius-chip);padding:0 7px;background:var(--card-bg)}
.event-remaining.urgent{color:var(--stale-text);background:var(--stale-bg)}
.timeline-event.is-short { overflow:visible; padding:4px 0; }
.is-short .event-summary { position:relative; left:10px; width:min(420px,45cqw); background:color-mix(in srgb,var(--card-bg) 92%,transparent); padding:0 5px; border-radius:3px; }
.is-short.label-left .event-summary { left:100%; transform:translateX(-100%); }
.timeline-event.is-short::after { content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 1px; background: var(--game-vivid, var(--game-accent)); opacity: .6; }
.event-bar-title { display:block; flex:1 1 80px; font-size:12px; font-weight:500; min-width:0; white-space:normal; overflow-wrap:anywhere; line-height:16px; }
.event-category, .event-status { flex-shrink: 0; font-size: 12px; white-space: nowrap; }
.event-category { color: var(--text-muted); }
.event-status { color: var(--game-accent); }
.timeline-event.clipped-start { border-top-left-radius: 0; border-bottom-left-radius: 0; }
.timeline-event.clipped-end { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.timeline-event.clipped-end::after { content: ''; position: absolute; inset: 0 0 0 auto; width: 2px; background: repeating-linear-gradient(to bottom, var(--game-vivid, var(--game-accent)) 0 3px, transparent 3px 6px); }
.timeline-event.is-selected { outline: 2px solid var(--accent); outline-offset: 2px; z-index: 2; }
.timeline-event.is-point { width: 16px; transform: translateX(-50%); padding: 0; background: transparent; border: 0; box-shadow: none; overflow: visible; justify-content: center; }
.point-diamond { position:absolute; left:3px; top:16px; display:block; height:10px; width:10px; border-radius:2px; background:var(--game-vivid, var(--game-accent)); transform:translateY(-50%) rotate(45deg); border:2px solid var(--card-bg); box-shadow:0 0 0 1px var(--game-vivid, var(--game-accent)); }
.point-label { position:relative; left:20px; width:min(420px,45cqw); display:grid; gap:2px; min-height:32px; color:var(--text); padding:4px 7px; background:color-mix(in srgb,var(--card-bg) 92%,transparent); }
.point-artwork { width:42px; height:28px; border-radius:4px; flex-shrink:0; }
.point-label:has(.point-artwork) { display:flex; align-items:center; gap:7px; }
.point-label strong { flex:1 1 80px; min-width:0; font-size:12px; font-weight:500; white-space:normal; overflow-wrap:anywhere; line-height:16px; }
.point-label-left { left:0; transform:translateX(calc(-100% - 20px)); }
.calendar-empty { padding: 42px 24px; text-align: center; color: var(--text-muted); font-size: 13px; }
.timeline-empty { display: grid; gap: 13px; justify-items: center; min-height: 245px; align-content: center; }
.timeline-empty strong { color: var(--text); font-size: 14px; font-weight: 500; }
.calendar-unplaced { padding: 20px; border-radius: var(--radius-tile); background: var(--surface-soft); }
.unplaced-heading { display: flex; gap: 16px; align-items: baseline; margin-bottom: 20px; flex-wrap: wrap; }
.unplaced-heading h2 { font-size: 16px; font-weight: 600; }
.unplaced-heading p { font-size: 13px; color: var(--text-muted); }
.unplaced-grid { display: grid; gap: 24px; }
.unplaced-bucket h3 { font-size: 12px; color: var(--text-muted); margin: 0 0 10px; font-weight: 500; }
.unplaced-bucket h3 span { margin-left: 6px; color: var(--text); }
.unplaced-event { transition:background-color var(--duration-quick) var(--ease-smooth-out); display:flex; justify-content:space-between; gap:20px; align-items:center; padding:8px 0; width:100%; border:0; border-top:1px solid var(--overlay-3); color:var(--text); background:transparent; text-align:left; }
.unplaced-event > span { display:flex; flex-wrap:wrap; align-items:center; gap:3px 8px; }
.calendar-content:not(.image-mode) .unplaced-event > span { min-width:0; overflow-wrap:anywhere; }
.unplaced-artwork { width:64px; height:48px; flex:none; border-radius:8px; }
.unplaced-event:has(.unplaced-artwork) { justify-content:flex-start; gap:10px; min-height:64px; }
.unplaced-event strong { font-weight: 500; font-size: 13px; }
.unplaced-event small { color: var(--text-muted); font-size: 12px; }

.calendar-content { --timeline-label-width:184px; min-width:0; display:flex; flex-direction:column; flex:1; min-height:0; }
.calendar-content:not(.image-mode) { overflow:auto; }
@media (hover:hover) and (pointer:fine) {
  .calendar-content:not(.image-mode) .timeline-scroll { cursor:grab; }
  .calendar-content.is-panning,.calendar-content.is-panning :deep(*) { cursor:grabbing !important; user-select:none; }
}
.calendar-unplaced { margin:12px 16px; }
.calendar-content button { cursor:pointer; font-family:inherit; }
.calendar-content button:focus-visible,.timeline-scroll:focus-visible { outline:2px solid var(--accent); outline-offset:3px; }
.sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
.image-mode .timeline-scroll { overflow:visible; flex:none; }
.image-mode .timeline-canvas { min-width:0; }
.image-mode .timeline-header,.image-mode .timeline-label { position:static; }
.image-mode .date-cell strong { min-width:0; padding:0; font-size:9px; white-space:nowrap; }
.image-mode .date-cell.is-month-start strong { font-size:8px; }
.image-mode .date-cell small,.image-mode .day-today { font-size:8px; }
.image-mode .timeline-event { cursor:default; }
.image-mode .event-lane { min-height:36px; }
.image-mode .timeline-event,.image-mode .point-label { min-height:34px; }
.image-mode .event-bar-title,.image-mode .point-label strong { font-size:13px; line-height:18px; }
.image-mode .event-category,.image-mode .event-status,.image-mode .event-remaining { font-size:11px; }
.image-mode .point-diamond { top:17px; }
.image-mode .calendar-unplaced { margin:12px 0; }

/* Screen banners retain their real date width; the left shade protects labels over any artwork. */
.calendar-content:not(.image-mode) .group-track { overflow:clip; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-short):not(.is-point) { overflow:clip; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-short) .event-summary { position:sticky; left:calc(var(--timeline-label-width) + 8px); max-width:min(300px,calc(var(--calendar-width,100vw) - var(--timeline-label-width) - 34px)); }
.calendar-content:not(.image-mode) .timeline-event:not(.is-short):not(.is-point) .event-summary { padding:3px 5px; border-radius:5px; background:rgba(7,13,22,.64); }
.calendar-content:not(.image-mode) .group-label > .game-monogram,.calendar-content:not(.image-mode) .group-label > div { position:sticky; top:108px; }
.calendar-content:not(.image-mode) .calendar-unplaced { position:sticky; left:16px; flex:none; }
.calendar-content:not(.image-mode) .timeline-group { border-top:8px solid var(--surface-soft); }
.calendar-content:not(.image-mode) .group-track { padding:8px 0; }
.group-category { display:block; margin-top:7px; color:var(--game-accent); font-size:12px; font-weight:600; line-height:1.5; }
.calendar-content:not(.image-mode) .event-lane { min-height:80px; padding-bottom:8px; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) { height:72px; min-height:72px; padding:10px 13px; color:#fff; background:color-mix(in srgb,var(--game-accent) 28%,#18212b); }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point)::before { content:''; position:absolute; inset:0; width:auto; border-radius:inherit; background:linear-gradient(90deg,rgba(7,13,22,.78) 0%,rgba(7,13,22,.58) 28%,rgba(7,13,22,.18) 60%,rgba(7,13,22,.04) 100%); z-index:1; pointer-events:none; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-artwork { object-position:center 38%; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-summary { width:max-content; max-width:min(300px,calc(100% - 14px)); z-index:2; text-shadow:0 1px 3px #000; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-heading { gap:5px; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-bar-title { flex-basis:100%; display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:1; overflow:hidden; font-size:13px; font-weight:600; line-height:18px; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-category,
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-status,
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-remaining { color:#fff; background:rgba(5,12,22,.8); border:1px solid rgba(255,255,255,.24); border-radius:4px; padding:1px 5px; font-size:11px; white-space:normal; }
.calendar-content:not(.image-mode) .timeline-event:not(.is-point) .event-elapsed { opacity:.2; }
.calendar-content:not(.image-mode) .timeline-event.is-short:not(.is-point) { padding-inline:0; }
.calendar-content:not(.image-mode) .timeline-event.is-short:not(.is-point) .event-summary { width:min(280px,42cqw); background:rgba(11,19,30,.35); border-radius:5px; padding:5px 7px; left:4px; }
.calendar-content:not(.image-mode) .timeline-event.is-short.label-left:not(.is-point) .event-summary { left:100%; transform:translateX(-100%); }
.calendar-content:not(.image-mode) .timeline-event.is-ended:not(.is-point) { opacity:.88; }

@media(max-width:760px) {
  .calendar-content { --timeline-label-width:142px; }
  .calendar-content:not(.image-mode) { --timeline-label-width:124px; }
  .header-label { padding:15px; }
  .group-label { padding:0 10px; gap:7px; }
  .game-monogram { width:24px; height:24px; font-size:12px; }
  .group-label strong { font-size:12px; }
  .calendar-unplaced { padding:18px; }
  .unplaced-event { gap:10px; align-items:start; }
  .calendar-content:not(.image-mode) .event-lane { min-height:108px; }
  .calendar-content:not(.image-mode) .timeline-event:not(.is-point) { height:100px; min-height:100px; }
  .calendar-content:not(.image-mode) .timeline-event:not(.is-point) :is(.event-category,.event-status,.event-remaining) { font-size:12px; }
}
@media(prefers-reduced-motion:reduce) { .timeline-event { transition:none; } }
</style>
