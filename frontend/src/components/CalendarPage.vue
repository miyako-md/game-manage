<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import GameIcon from './GameIcon.vue'
import { gameStyle } from '../dashboard.js'
import { beijingDayStart, calendarRange, collectCalendarEvents, eventGeometry, eventStatus, formatBeijingDateTime, groupCalendarEvents, safeSourceUrl, shiftCalendarAnchor } from '../calendar.js'

const props = defineProps({
  games: { type: Array, default: () => [] },
  snapshots: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  initialGameId: { type: String, default: '' },
  readErrors: { type: Object, default: () => ({}) },
})
const now = ref(Date.now())
const anchor = ref(now.value)
const mode = ref('rolling')
const filter = ref(props.initialGameId === 'all' ? '' : props.initialGameId)
const selectedId = ref(null)
const detailElement = ref(null)
const boardElement = ref(null)
const boardTop = ref(240)
let layoutObserver
function fitWindow() {
  if (typeof window === 'undefined' || !boardElement.value?.getBoundingClientRect) return
  boardTop.value = Math.round(boardElement.value.getBoundingClientRect().top + window.scrollY)
}
let timer
onMounted(() => {
  timer = setInterval(() => { now.value = Date.now() }, 60000)
  fitWindow()
  if (typeof window !== 'undefined') window.addEventListener('resize', fitWindow)
  if (typeof ResizeObserver !== 'undefined' && boardElement.value?.parentElement) {
    layoutObserver = new ResizeObserver(fitWindow)
    layoutObserver.observe(boardElement.value.parentElement)
  }
})
onUnmounted(() => {
  clearInterval(timer)
  if (typeof window !== 'undefined') window.removeEventListener('resize', fitWindow)
  layoutObserver?.disconnect()
})
watch(() => props.initialGameId, (id) => { filter.value = id === 'all' ? '' : id })
watch(filter, () => { selectedId.value = null })

const range = computed(() => calendarRange(anchor.value, mode.value))
const today = computed(() => beijingDayStart(now.value))
const todayPosition = computed(() => (now.value - range.value.start) / (range.value.end - range.value.start) * 100)
const todayVisible = computed(() => now.value >= range.value.start && now.value < range.value.end)
const rangeTitle = computed(() => mode.value === 'month'
  ? formatBeijingDateTime(range.value.start).slice(0, 7).replace('-', ' 年 ') + ' 月'
  : `${formatBeijingDateTime(range.value.start).slice(5, 10)} — ${formatBeijingDateTime(range.value.end - 1).slice(5, 10)}`)
const events = computed(() => collectCalendarEvents(props.games, props.snapshots, filter.value).map(event => {
  const geometry = eventGeometry(event, range.value)
  const status = eventStatus(event, now.value)
  let elapsed = null, remainingDays = null
  if (geometry.kind === 'range' && status === '进行中') {
    const visStart = Math.max(geometry.start, range.value.start)
    const visEnd = Math.min(geometry.end, range.value.end)
    if (visEnd > visStart) elapsed = Math.min(100, Math.max(3, (now.value - visStart) / (visEnd - visStart) * 100))
    remainingDays = Math.max(0, Math.ceil((geometry.end - now.value) / 86400000))
  }
  return { ...event, geometry, status, elapsed, remainingDays }
}))
const visibleEvents = computed(() => events.value.filter(event => event.geometry.visible))
const groups = computed(() => groupCalendarEvents(visibleEvents.value))
const undated = computed(() => events.value.filter(event => event.geometry.kind === 'undated'))
const invalid = computed(() => events.value.filter(event => event.geometry.kind === 'invalid'))
const selected = computed(() => events.value.find(event => event.id === selectedId.value))
const sourceUrl = computed(() => safeSourceUrl(selected.value?.source_url ?? selected.value?.source_post_id))
const filteredGames = computed(() => props.games.filter(game => !filter.value || game.game_id === filter.value))
const staleGames = computed(() => filteredGames.value.filter(game => props.snapshots[game.game_id]?.events?.stale).map(game => game.display_name))
const missingGames = computed(() => filteredGames.value.filter(game => (!Array.isArray(game.capabilities) || game.capabilities.includes('events')) && !Array.isArray(props.snapshots[game.game_id]?.events?.payload)).map(game => game.display_name))
const failedReads = computed(() => filteredGames.value.filter(game => props.readErrors[game.game_id]).map(game => ({
  id: game.game_id, name: game.display_name, error: props.readErrors[game.game_id], retained: Array.isArray(props.snapshots[game.game_id]?.events?.payload),
})))
function gameAccent(id) { return gameStyle(id).color }
function shift(direction) { anchor.value = shiftCalendarAnchor(anchor.value, mode.value, direction) }
function goToday() { now.value = Date.now(); anchor.value = now.value }
function setMode(value) { mode.value = value }
function barStyle(event) {
  return { left: `${event.geometry.left}%`, width: event.geometry.kind === 'range' ? `${event.geometry.width}%` : undefined }
}
function eventDescription(event) {
  return `${event.name || '未命名活动'} · ${event.gameName} · ${event.category} · ${formatBeijingDateTime(event.start_at)} 至 ${formatBeijingDateTime(event.end_at)} · ${event.status}${event.geometry.reason ? ' · ' + event.geometry.reason : ''}`
}
async function selectEvent(event) {
  selectedId.value = event.id
  await nextTick()
  detailElement.value?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
  detailElement.value?.focus?.({ preventScroll: true })
}
</script>

<template>
  <div class="calendar-page">
    <header class="calendar-heading">
      <div><p class="calendar-eyebrow">VERSION CALENDAR</p><h1>活动日历<span class="heading-dot">.</span></h1><p class="calendar-subtitle">把握每一段旅程，让值得期待的事有迹可循。</p></div>
      <div class="calendar-timezone"><span aria-hidden="true">◷</span> 北京时间 <strong>UTC+8</strong></div>
    </header>

    <section ref="boardElement" class="calendar-board" aria-label="游戏活动时间轴" :aria-busy="loading" :style="{ '--calendar-top': `${boardTop}px` }">
      <div class="calendar-toolbar">
        <div class="calendar-navigation">
          <div class="calendar-arrows"><button type="button" aria-label="上一时间范围" @click="shift(-1)">‹</button><button type="button" aria-label="下一时间范围" @click="shift(1)">›</button></div>
          <h2 aria-live="polite">{{ rangeTitle }}</h2>
          <button class="today-button" type="button" @click="goToday">今天</button>
        </div>
        <div class="calendar-filters">
          <div class="range-toggle" aria-label="显示范围"><button type="button" :aria-pressed="mode === 'rolling'" @click="setMode('rolling')">近 30 天</button><button type="button" :aria-pressed="mode === 'month'" @click="setMode('month')">整月</button><button type="button" :aria-pressed="mode === 'fortnight'" @click="setMode('fortnight')">14 天</button></div>
          <label class="game-filter"><span class="sr-only">筛选游戏</span><select v-model="filter" aria-label="筛选游戏"><option value="">全部游戏</option><option v-for="game in games" :key="game.game_id" :value="game.game_id">{{ game.display_name }}</option></select></label>
        </div>
      </div>
      <div class="calendar-meta"><span><strong>{{ visibleEvents.length }}</strong> 项活动位于当前范围<span v-if="events.length > visibleEvents.length"> · 共 {{ events.length }} 项</span></span><div class="calendar-legend"><span><i class="legend-elapsed" />已进行</span><span><i class="legend-range" />剩余区间</span><span><i class="legend-point" />日期标记</span><span><i class="legend-today" />现在</span></div></div>
      <p v-if="staleGames.length" class="calendar-stale" role="status">数据可能过期 · {{ staleGames.join('、') }}，活动安排请以原始公告为准。</p>
      <p v-for="failure in failedReads" :key="failure.id" class="calendar-read-error" role="status">{{ failure.name }} · 游戏数据读取或刷新异常：{{ failure.error }}。{{ failure.retained ? '保留上次成功快照，请留意活动更新时间。' : '尚无可显示的成功快照。' }}</p>
      <p v-if="missingGames.length && !loading" class="calendar-missing" role="status">{{ missingGames.join('、') }} · 尚未取得活动快照，请刷新后查看。</p>
      <p v-if="loading && !events.length" class="calendar-empty" role="status">正在读取活动快照…</p>

      <div v-else class="timeline-scroll" tabindex="0" role="region" aria-label="活动日期横轴，可横向和纵向滚动" :style="{ '--day-count': range.days.length, '--timeline-min': `${184 + range.days.length * (mode === 'fortnight' ? 39 : 26)}px` }">
        <div class="timeline-canvas">
          <div class="timeline-header"><div class="timeline-label header-label"><span>游戏</span><small>{{ mode === 'month' ? '当月时间轴' : mode === 'rolling' ? '近 30 天时间轴' : '14 天时间轴' }}</small></div><div class="date-track"><div v-for="day in range.days" :key="day.timestamp" class="date-cell" :class="{ weekend: day.weekend, 'is-today': day.timestamp === today }" :title="`${day.month} 月 ${day.day} 日`"><small>{{ day.weekday }}</small><strong>{{ day.day === 1 ? `${day.month}/1` : day.day }}</strong><span v-if="day.timestamp === today" class="day-today">今天</span></div></div></div>
          <template v-if="groups.length">
            <div v-for="group in groups" :key="group.key" class="timeline-group" :style="{ '--game-accent': gameAccent(group.gameId) }">
              <div class="timeline-label group-label"><GameIcon class="game-monogram" :game-id="group.gameId" :name="group.gameName" /><div><strong>{{ group.gameName }}</strong><small>{{ group.events.length }} 项活动</small></div></div>
              <div class="group-track">
                <div class="grid-backdrop" aria-hidden="true"><div v-for="day in range.days" :key="day.timestamp" :class="{ weekend: day.weekend, 'today-column': day.timestamp === today }" /></div>
                <div v-if="todayVisible" class="today-line" :style="{ left: `${todayPosition}%` }" aria-hidden="true" />
                <div v-for="event in group.events" :key="event.id" class="event-lane">
                  <button type="button" class="timeline-event" :class="{ 'is-point': event.geometry.kind === 'point', 'is-short': event.geometry.kind === 'range' && event.geometry.width < 30, 'label-left': event.geometry.left > 70, 'is-ended': event.status === '已结束', 'clipped-start': event.geometry.clippedStart, 'clipped-end': event.geometry.clippedEnd, 'is-selected': selectedId === event.id }" :style="barStyle(event)" :title="eventDescription(event)" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" @click="selectEvent(event)">
                    <template v-if="event.geometry.kind === 'range'"><i v-if="event.elapsed != null" class="event-elapsed" :style="{ width: `${event.elapsed}%` }" aria-hidden="true" /><span class="event-summary"><span class="event-bar-title">{{ event.geometry.clippedStart ? '‹ ' : '' }}{{ event.name || '未命名活动' }}{{ event.geometry.clippedEnd ? ' ›' : '' }}</span><small class="event-category">{{ event.category }}</small><small class="event-status">{{ event.status }}{{ event.geometry.approximateStart ? ' · 更新后' : '' }}</small><small v-if="event.remainingDays != null" class="event-remaining" :class="{ urgent: event.remainingDays <= 3 }">剩 {{ event.remainingDays }} 天</small></span></template>
                    <template v-else><span class="point-diamond" aria-hidden="true" /><span class="point-label" :class="{ 'point-label-left': event.geometry.left > 70 }"><strong>{{ event.name || '未命名活动' }}</strong><small class="event-category">{{ event.category }}</small><small class="event-status">{{ event.status }}</small><span class="sr-only">{{ event.geometry.endpoint === 'end' ? '截止' : event.geometry.endpoint === 'start' ? '开始' : '时点' }} · {{ event.geometry.reason }}</span></span></template>
                  </button>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="calendar-empty timeline-empty"><span aria-hidden="true">◇</span><strong>{{ events.length ? '当前范围没有可定位的活动' : '暂无活动数据' }}</strong><p>{{ events.length ? '可切换时间范围，或查看下方未确定日期的活动。' : '采集到的活动公告将在这里按真实日期展示。' }}</p></div>
        </div>
      </div>
      <div class="calendar-footer"><span>日期按时间比例展示 · “更新后”仅表示开始日期，具体时刻见公告</span><span>↔ 可横向滚动</span></div>
    </section>

    <section v-if="undated.length || invalid.length" class="calendar-unplaced" aria-labelledby="unplaced-title"><div class="unplaced-heading"><h2 id="unplaced-title">待确认的时间</h2><p>原始数据未给出完整日期，或日期存在异常。</p></div><div class="unplaced-grid"><div v-for="bucket in [{ title: '日期未提供', events: undated }, { title: '日期异常', events: invalid }]" v-show="bucket.events.length" :key="bucket.title" class="unplaced-bucket"><h3>{{ bucket.title }} <span>{{ bucket.events.length }}</span></h3><button v-for="event in bucket.events" :key="event.id" type="button" class="unplaced-event" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" @click="selectEvent(event)"><span><strong>{{ event.name || '未命名活动' }}</strong><small>{{ event.gameName }} · {{ event.category }}</small></span><span class="unknown-reason">{{ event.geometry.reason }} <b aria-hidden="true">↗</b></span></button></div></div></section>

    <section v-if="selected" ref="detailElement" class="calendar-detail" aria-labelledby="calendar-detail-title" tabindex="-1" :style="{ '--game-accent': gameAccent(selected.gameId) }">
      <div class="detail-heading"><div><p class="calendar-eyebrow">{{ selected.gameName }} / {{ selected.category }}</p><h2 id="calendar-detail-title">{{ selected.name || '未命名活动' }}</h2></div><button type="button" class="detail-close" aria-label="关闭活动详情" @click="selectedId = null">×</button></div>
      <div class="detail-status"><span>{{ selected.status }}</span><span v-if="selected.geometry.reason">{{ selected.geometry.reason }}</span><span v-if="selected.stale" class="calendar-stale">数据可能过期</span></div>
      <dl><div><dt>开始时间 · 北京时间</dt><dd>{{ selected.start_at ? formatBeijingDateTime(selected.start_at) : selected.start_text || '未知' }}</dd><small v-if="selected.geometry.approximateStart">仅知开始日期 {{ selected.start_date }}，具体时刻未知</small><small v-if="selected.start_at && selected.geometry.start === null">原始值：{{ selected.start_at }}</small></div><div><dt>截止时间 · 北京时间</dt><dd>{{ formatBeijingDateTime(selected.end_at) }}</dd><small v-if="selected.end_at && selected.geometry.end === null">原始值：{{ selected.end_at }}</small></div><div><dt>来源标题</dt><dd>{{ selected.source_name ? selected.source_name + ' · ' : '' }}{{ selected.source_title || '未提供' }}</dd></div><div><dt>快照抓取时间 · 北京时间</dt><dd>{{ formatBeijingDateTime(selected.fetchedAt) }}</dd></div></dl>
      <p v-if="selected.time_text" class="source-id">日期依据：{{ selected.time_text }}</p>
      <p v-if="selected.source_note" class="source-id">{{ selected.source_note }}</p>
      <p v-if="selected.geometry.clippedStart || selected.geometry.clippedEnd" class="clipping-note">时间条已按当前显示范围裁剪{{ selected.geometry.clippedStart ? '左侧' : '' }}{{ selected.geometry.clippedStart && selected.geometry.clippedEnd ? '和' : '' }}{{ selected.geometry.clippedEnd ? '右侧' : '' }}；以上为完整起止时间。</p>
      <p v-if="selected.source_post_id" class="source-id">来源标识：{{ selected.source_post_id }}</p><a v-if="sourceUrl" :href="sourceUrl" target="_blank" rel="noopener noreferrer" class="source-link">查看原始公告 ↗</a>
    </section>
  </div>
</template>

<style scoped>
.calendar-page { min-width: 0; display: grid; gap: 24px; color: var(--text); }
.calendar-heading { display: flex; justify-content: space-between; gap: 24px; align-items: end; padding: 2px 0 7px; }
.calendar-eyebrow { font-family: var(--mono); font-size: 10px; letter-spacing: 2.8px; color: var(--accent); font-weight: 500; margin-bottom: 10px; text-transform: uppercase; }
.calendar-heading h1 { font-size: clamp(26px, 3vw, 36px); letter-spacing: -.04em; font-weight: 600; line-height: 1.3; }
.heading-dot { color: var(--accent); margin-left: 3px; }
.calendar-subtitle { margin-top: 10px; color: var(--text-muted); font-size: 13px; }
.calendar-timezone { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-muted); white-space: nowrap; padding-bottom: 3px; }
.calendar-timezone strong { color: var(--accent); font-size: 10px; font-weight: 500; font-family: var(--mono); letter-spacing: .8px; }
.calendar-board { background: linear-gradient(180deg, #211d16, var(--card-bg) 220px); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; min-width: 0; box-shadow: inset 0 1px 0 #ffffff08; display:flex; flex-direction:column; height:max(460px, calc(100dvh - var(--calendar-top) - 24px)); }
.calendar-board > :not(.timeline-scroll) { flex-shrink:0; }
.calendar-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap; padding: 24px 24px 18px; }
.calendar-navigation, .calendar-filters { display: flex; align-items: center; gap: 16px; }
.calendar-navigation h2 { font-family: var(--mono); font-size: 19px; font-weight: 500; letter-spacing: .5px; min-width: 141px; font-variant-numeric: tabular-nums; }
.calendar-arrows { display: flex; gap: 4px; }
.calendar-page button, .calendar-page select { cursor: pointer; font-family: inherit; }
.calendar-arrows button, .today-button, .detail-close { border: 1px solid var(--border-strong); background: transparent; color: var(--text-muted); border-radius: 7px; transition: color .233s, border-color .233s, background .233s; }
.calendar-arrows button { height: 32px; width: 29px; font-size: 22px; line-height: 24px; }
.calendar-arrows button:hover, .today-button:hover, .detail-close:hover { color: var(--accent); border-color: var(--accent); }
.today-button { padding: 6px 12px; font-size: 11px; font-family: var(--mono); letter-spacing: 1px; }
.range-toggle { display: flex; background: var(--bg-deep); border: 1px solid var(--border-soft); border-radius: 9px; padding: 4px; gap: 2px; }
.range-toggle button { border: 0; padding: 6px 13px; color: var(--text-muted); background: transparent; border-radius: 6px; font-size: 12px; transition: background .233s, color .233s; }
.range-toggle button[aria-pressed="true"] { background: var(--accent-dim); color: var(--accent); box-shadow: inset 0 0 0 1px #e9c46a38; }
.game-filter select { background: var(--bg-deep); border: 1px solid var(--border); color: var(--text); border-radius: 7px; padding: 8px 10px; font-size: 12px; max-width: 170px; }
.calendar-meta { display: flex; justify-content: space-between; gap: 12px; padding: 0 24px 18px; font-size: 11px; color: var(--text-muted); }
.calendar-meta strong { color: var(--text); font-size: 12px; font-weight: 500; font-family: var(--mono); }
.calendar-legend { display: flex; gap: 16px; }
.calendar-legend span { display: flex; align-items: center; gap: 6px; }
.calendar-legend i { display: inline-block; }
.legend-elapsed { width: 12px; height: 7px; border-radius: 2px 0 0 2px; background: #8a7a52; }
.legend-range { width: 12px; height: 7px; border-radius: 0 2px 2px 0; background: repeating-linear-gradient(115deg, #4a4130 0 3px, #322b1d 3px 6px); }
.legend-point { width: 6px; height: 6px; background: #b9ad93; transform: rotate(45deg); }
.legend-today { width: 2px; height: 10px; background: var(--accent); box-shadow: 0 0 5px var(--accent); }
.calendar-stale { color: var(--stale-text); font-size: 11px; }
.calendar-board > .calendar-stale { margin: 0 24px 16px; padding: 10px 12px; background: #f4a2610d; border-left: 2px solid #a97a44; }
.calendar-read-error, .calendar-missing { margin: 0 24px 16px; padding: 10px 12px; font-size: 11px; line-height: 1.6; }
.calendar-read-error { background: #ef8f7d0d; border-left: 2px solid #b06a54; color: var(--danger); }
.calendar-missing { color: var(--text-muted); border: 1px dashed var(--border-strong); border-radius: 6px; }
.timeline-scroll { overflow: auto; flex:1; min-height:140px; scrollbar-color: #4a4130 var(--bg-deep); scrollbar-width: thin; }
.timeline-canvas { min-width: var(--timeline-min); }
.timeline-header, .timeline-group { display: grid; grid-template-columns: 184px minmax(0, 1fr); }
.timeline-header { position: sticky; top: 0; z-index: 5; background: #221e16; border-top: 1px solid var(--border-soft); border-bottom: 1px solid var(--border); }
.timeline-label { position: sticky; left: 0; z-index: 3; background: #211d15; border-right: 1px solid var(--border); }
.header-label { display: flex; flex-direction: column; justify-content: center; gap: 5px; padding: 18px 20px; color: var(--text-muted); font-size: 11px; }
.header-label small { color: var(--text-faint); font-size: 9px; font-family: var(--mono); letter-spacing: .6px; }
.date-track, .grid-backdrop { display: grid; grid-template-columns: repeat(var(--day-count), minmax(0, 1fr)); }
.date-cell { position: relative; min-height: 78px; display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 12px 0 17px; border-right: 1px solid #e9c46a08; font-variant-numeric: tabular-nums; }
.date-cell small { font-size: 9px; color: var(--text-faint); letter-spacing: 1px; }
.date-cell strong { font-size: 14px; font-weight: 500; font-family: var(--mono); }
.date-cell.weekend { background: #e9c46a05; }
.date-cell.is-today { color: var(--accent); background: #e9c46a0f; }
.date-cell.is-today strong { border-radius: 50%; background: var(--accent); color: var(--accent-ink); width: 25px; height: 25px; line-height: 25px; margin-top: -3px; box-shadow: 0 0 10px #e9c46a55; }
.day-today { font-size: 8px; position: absolute; bottom: 5px; color: var(--accent); font-family: var(--mono); letter-spacing: 1px; }
.timeline-group { border-bottom: 1px solid var(--border); }
.timeline-group:last-child { border-bottom: 0; }
.group-label { display: flex; align-items: center; gap: 10px; padding: 0 16px; }
.game-monogram { width: 28px; height: 28px; background: color-mix(in srgb, var(--game-accent) 14%, transparent); border: 1px solid color-mix(in srgb, var(--game-accent) 30%, transparent); border-radius: 7px; font-size: 15px; }
.group-label strong { display: block; font-size: 12px; line-height: 17px; }
.group-label small { display: block; color: var(--text-faint); font-size: 9px; line-height: 13px; font-family: var(--mono); }
.group-track { position: relative; overflow: hidden; }
.grid-backdrop { position: absolute; inset: 0; pointer-events: none; }
.grid-backdrop > div { border-right: 1px solid #e9c46a07; }
.grid-backdrop .weekend { background: #e9c46a04; }
.grid-backdrop .today-column { background: #e9c46a09; }
.today-line { position: absolute; top: 0; bottom: 0; width: 1px; background: linear-gradient(180deg, var(--accent), #e9c46a66); box-shadow: 0 0 7px #e9c46a66; z-index: 2; pointer-events: none; }
.today-line:before { content: ''; position: absolute; top: 0; left: -3.5px; width: 8px; height: 8px; background: var(--accent); transform: rotate(45deg) scale(.8); transform-origin: top center; box-shadow: 0 0 6px var(--accent); }
.event-lane { height: 40px; position: relative; }
.event-lane:nth-child(odd of .event-lane) { background: #ffffff02; }
.timeline-event { position: absolute; top: 5px; height: 30px; min-width: 0; border: 1px solid color-mix(in srgb, var(--game-accent) 38%, transparent); box-shadow: inset 0 1px 0 #ffffff0a, inset 0 -1px 0 color-mix(in srgb, var(--game-accent) 18%, transparent); border-radius: 7px; color: var(--text); background: repeating-linear-gradient(115deg, transparent 0 10px, #ffffff05 10px 12px), linear-gradient(100deg, color-mix(in srgb, var(--game-accent) 22%, #1c1914), color-mix(in srgb, var(--game-accent) 7%, #1c1914)); padding: 0 10px 0 12px; display: flex; align-items: center; gap: 9px; text-align: left; overflow: hidden; transition: filter .233s, box-shadow .233s; }
.timeline-event:not(.is-point):before { content: ''; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--game-accent); box-shadow: 0 0 6px color-mix(in srgb, var(--game-accent) 60%, transparent); }
.event-elapsed { position: absolute; inset: 0 auto 0 0; background: color-mix(in srgb, var(--game-accent) 30%, transparent); border-right: 1px solid color-mix(in srgb, var(--game-accent) 85%, transparent); pointer-events: none; }
.timeline-event:hover { filter: brightness(1.18); box-shadow: inset 0 1px 0 #ffffff12, 0 4px 14px -6px var(--game-accent), 0 0 0 1px color-mix(in srgb, var(--game-accent) 45%, transparent); }
.timeline-event.is-ended { opacity: .5; filter: saturate(.6); }
.event-summary { display: flex; align-items: center; gap: 9px; min-width: 0; width: 100%; position: relative; }
.event-summary, .point-label { font-family:inherit; line-height:1.4; text-shadow:0 1px 3px #14110d, 0 0 8px #14110d; }
.timeline-event.is-short { overflow: visible; }
.is-short .event-summary { position: absolute; left: 11px; width: max-content; max-width: 330px; text-shadow: 0 1px 3px #14110d, 0 0 8px #14110d; }
.is-short.label-left .event-summary { left: auto; right: 11px; }
.timeline-event.is-short:after { content: ''; position: absolute; right: 0; top: 0; bottom: 0; width: 1px; background: var(--game-accent); opacity: .5; }
.event-bar-title { display: block; font-size: 11px; font-weight: 600; min-width: 24px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.event-category, .event-status { flex-shrink: 0; font-size: 10px; white-space: nowrap; }
.event-category { color: var(--text-muted); }
.event-status { color: var(--game-accent); font-family: var(--mono); letter-spacing: .3px; }
.event-remaining { flex-shrink: 0; font-family: var(--mono); font-size: 9px; letter-spacing: .4px; color: var(--text-muted); border: 1px solid var(--border-strong); border-radius: 4px; padding: 1px 5px; background: #14110d80; }
.event-remaining.urgent { color: var(--stale-text); border-color: #a97a44; background: #f4a26114; }
.timeline-event.clipped-start { border-top-left-radius: 0; border-bottom-left-radius: 0; }
.timeline-event.clipped-start:before { background: repeating-linear-gradient(to bottom, var(--game-accent) 0 3px, transparent 3px 6px); box-shadow: none; }
.timeline-event.clipped-end { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.timeline-event.clipped-end:after { content: ''; position: absolute; inset: 0 0 0 auto; width: 2px; background: repeating-linear-gradient(to bottom, var(--game-accent) 0 3px, transparent 3px 6px); }
.timeline-event.is-selected { outline: 2px solid var(--accent); outline-offset: 2px; z-index: 2; }
.timeline-event.is-point { width: 16px; top: 0; height: 40px; transform: translateX(-50%); padding: 0; background: transparent; border: 0; box-shadow: none; overflow: visible; justify-content: center; }
.point-diamond { display: block; height: 10px; width: 10px; background: var(--game-accent); transform: rotate(45deg); border: 2px solid #1c1914; box-shadow: 0 0 0 1px var(--game-accent), 0 0 8px color-mix(in srgb, var(--game-accent) 55%, transparent); }
.point-label { position: absolute; left: 20px; max-width: 330px; display: flex; align-items: center; gap: 9px; height: 30px; color: var(--text); padding: 0 8px; background: #1c1914f0; border: 1px solid var(--border-soft); border-radius: 6px; }
.point-label strong { min-width: 24px; font-size: 11px; font-weight: 600; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.point-label-left { left: auto; right: 20px; text-align: right; }
.calendar-empty { padding: 42px 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
.timeline-empty { display: grid; gap: 13px; justify-items: center; min-height: 245px; align-content: center; }
.timeline-empty > span { font-size: 27px; color: var(--accent); opacity: .7; }
.timeline-empty strong { color: var(--text); font-size: 14px; font-weight: 500; }
.calendar-footer { padding: 14px 24px; display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid var(--border-soft); font-size: 10px; color: var(--text-faint); font-family: var(--mono); letter-spacing: .3px; }
.calendar-unplaced { border: 1px solid var(--border); padding: 23px; border-radius: 14px; background: var(--bg-deep); box-shadow: inset 0 1px 0 #ffffff06; }
.unplaced-heading { display: flex; gap: 16px; align-items: baseline; margin-bottom: 20px; flex-wrap: wrap; }
.unplaced-heading h2 { font-size: 15px; font-weight: 600; }
.unplaced-heading p { font-size: 11px; color: var(--text-muted); }
.unplaced-grid { display: grid; gap: 24px; }
.unplaced-bucket h3 { font-size: 11px; color: var(--text-muted); margin: 0 0 10px; font-weight: 500; font-family: var(--mono); letter-spacing: .8px; }
.unplaced-bucket h3 span { margin-left: 7px; color: var(--accent); }
.unplaced-event { display: flex; justify-content: space-between; gap: 20px; align-items: center; padding: 13px 0; width: 100%; border: 0; border-top: 1px solid var(--border-soft); color: var(--text); background: transparent; text-align: left; transition: padding-left .233s; }
.unplaced-event:hover { padding-left: 6px; }
.unplaced-event > span:first-child { display: grid; gap: 6px; }
.unplaced-event strong { font-weight: 500; font-size: 12px; }
.unplaced-event small, .unknown-reason { color: var(--text-muted); font-size: 10px; }
.unknown-reason b { margin-left: 18px; color: var(--accent); }
.calendar-detail { background: linear-gradient(180deg, #211d16, var(--card-bg) 200px); border: 1px solid color-mix(in srgb, var(--game-accent) 38%, var(--border)); border-radius: 14px; padding: 25px; scroll-margin: 22px; box-shadow: inset 0 1px 0 #ffffff08; }
.detail-heading { display: flex; align-items: start; justify-content: space-between; gap: 20px; }
.detail-heading h2 { font-size: 20px; font-weight: 600; line-height: 1.5; }
.detail-close { height: 30px; width: 30px; font-size: 20px; flex-shrink: 0; }
.detail-status { display: flex; gap: 10px; margin: 15px 0 22px; color: var(--game-accent); font-size: 11px; flex-wrap: wrap; }
.detail-status > span { background: color-mix(in srgb, var(--game-accent) 10%, transparent); border: 1px solid color-mix(in srgb, var(--game-accent) 22%, transparent); padding: 4px 9px; border-radius: 5px; font-family: var(--mono); letter-spacing: .4px; }
.calendar-detail dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; margin: 0; }
.calendar-detail dt { color: var(--text-faint); font-size: 10px; margin-bottom: 8px; font-family: var(--mono); letter-spacing: .6px; }
.calendar-detail dd { margin: 0; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.calendar-detail dl small { display: block; color: var(--text-muted); margin-top: 6px; }
.clipping-note { margin-top: 20px; padding: 12px; background: #e9c46a0a; border-left: 2px solid var(--accent); color: var(--accent); font-size: 11px; line-height: 1.6; }
.source-id { color: var(--text-muted); margin-top: 20px; font-size: 10px; overflow-wrap: anywhere; font-family: var(--mono); }
.source-link { display: inline-block; margin-top: 15px; color: var(--accent); font-size: 12px; }
.calendar-page button:focus-visible, .calendar-page select:focus-visible, .timeline-scroll:focus-visible, .calendar-detail:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.calendar-page button:hover { color: var(--text); }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 760px) {
  .calendar-heading { align-items: start; flex-direction: column; gap: 14px; }
  .calendar-toolbar { padding: 18px 16px; gap: 17px; }
  .calendar-navigation { gap: 10px; }
  .calendar-navigation h2 { font-size: 16px; min-width: 121px; }
  .calendar-filters { justify-content: space-between; width: 100%; }
  .calendar-meta { padding: 0 16px 16px; flex-direction: column; }
  .timeline-header, .timeline-group { grid-template-columns: 142px minmax(0, 1fr); }
  .header-label { padding: 15px; }
  .group-label { padding: 0 10px; gap: 7px; }
  .game-monogram { width: 24px; height: 24px; font-size: 12px; }
  .group-label strong { font-size: 11px; }
  .calendar-footer { padding: 12px 16px; flex-direction: column; }
  .calendar-unplaced, .calendar-detail { padding: 18px; }
  .calendar-detail dl { grid-template-columns: 1fr; }
  .unplaced-event { gap: 10px; align-items: start; }
  .unknown-reason { max-width: 100px; line-height: 1.6; flex-shrink: 0; }
}
@media (prefers-reduced-motion: reduce) { .timeline-event { transition: none; } }
</style>
