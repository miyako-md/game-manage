<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
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
const mode = ref('month')
const filter = ref(props.initialGameId === 'all' ? '' : props.initialGameId)
const selectedId = ref(null)
const detailElement = ref(null)
let timer
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 60000) })
onUnmounted(() => clearInterval(timer))
watch(() => props.initialGameId, (id) => { filter.value = id === 'all' ? '' : id })
watch(filter, () => { selectedId.value = null })

const range = computed(() => calendarRange(anchor.value, mode.value))
const today = computed(() => beijingDayStart(now.value))
const todayPosition = computed(() => (now.value - range.value.start) / (range.value.end - range.value.start) * 100)
const todayVisible = computed(() => now.value >= range.value.start && now.value < range.value.end)
const rangeTitle = computed(() => mode.value === 'month'
  ? formatBeijingDateTime(range.value.start).slice(0, 7).replace('-', ' 年 ') + ' 月'
  : `${formatBeijingDateTime(range.value.start).slice(5, 10)} — ${formatBeijingDateTime(range.value.end - 1).slice(5, 10)}`)
const events = computed(() => collectCalendarEvents(props.games, props.snapshots, filter.value).map(event => ({
  ...event, geometry: eventGeometry(event, range.value), status: eventStatus(event, now.value),
})))
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
const gameColors = { wuthering_waves: '#d8bb84', nte: '#b6a3d4', league_of_legends: '#87b9ce', lol: '#87b9ce' }
function gameAccent(id) { return gameColors[id] || '#d8bb84' }
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

    <section class="calendar-board" aria-label="游戏活动时间轴" :aria-busy="loading">
      <div class="calendar-toolbar">
        <div class="calendar-navigation">
          <div class="calendar-arrows"><button type="button" aria-label="上一时间范围" @click="shift(-1)">‹</button><button type="button" aria-label="下一时间范围" @click="shift(1)">›</button></div>
          <h2 aria-live="polite">{{ rangeTitle }}</h2>
          <button class="today-button" type="button" @click="goToday">今天</button>
        </div>
        <div class="calendar-filters">
          <div class="range-toggle" aria-label="显示范围"><button type="button" :aria-pressed="mode === 'month'" @click="setMode('month')">整月</button><button type="button" :aria-pressed="mode === 'fortnight'" @click="setMode('fortnight')">14 天</button></div>
          <label class="game-filter"><span class="sr-only">筛选游戏</span><select v-model="filter" aria-label="筛选游戏"><option value="">全部游戏</option><option v-for="game in games" :key="game.game_id" :value="game.game_id">{{ game.display_name }}</option></select></label>
        </div>
      </div>
      <div class="calendar-meta"><span><strong>{{ visibleEvents.length }}</strong> 项活动位于当前范围<span v-if="events.length > visibleEvents.length"> · 共 {{ events.length }} 项</span></span><div class="calendar-legend"><span><i class="legend-range" />已知区间</span><span><i class="legend-point" />日期标记</span><span><i class="legend-today" />现在</span></div></div>
      <p v-if="staleGames.length" class="calendar-stale" role="status">数据可能过期 · {{ staleGames.join('、') }}，活动安排请以原始公告为准。</p>
      <p v-for="failure in failedReads" :key="failure.id" class="calendar-read-error" role="status">{{ failure.name }} · 游戏数据读取或刷新异常：{{ failure.error }}。{{ failure.retained ? '保留上次成功快照，请留意活动更新时间。' : '尚无可显示的成功快照。' }}</p>
      <p v-if="missingGames.length && !loading" class="calendar-missing" role="status">{{ missingGames.join('、') }} · 尚未取得活动快照，请刷新后查看。</p>
      <p v-if="loading && !events.length" class="calendar-empty" role="status">正在读取活动快照…</p>

      <div v-else class="timeline-scroll" tabindex="0" role="region" aria-label="活动日期横轴，可横向和纵向滚动" :style="{ '--day-count': range.days.length, '--timeline-min': `${184 + range.days.length * (mode === 'month' ? 26 : 39)}px` }">
        <div class="timeline-canvas">
          <div class="timeline-header"><div class="timeline-label header-label"><span>游戏 / 活动类型</span><small>{{ mode === 'month' ? '当月时间轴' : '14 天时间轴' }}</small></div><div class="date-track"><div v-for="day in range.days" :key="day.timestamp" class="date-cell" :class="{ weekend: day.weekend, 'is-today': day.timestamp === today }"><small>{{ day.weekday }}</small><strong>{{ day.day }}</strong><span v-if="day.timestamp === today" class="day-today">今天</span></div></div></div>
          <template v-if="groups.length">
            <div v-for="group in groups" :key="group.key" class="timeline-group" :style="{ '--game-accent': gameAccent(group.gameId) }">
              <div class="timeline-label group-label"><span class="game-monogram" aria-hidden="true">{{ group.gameName.slice(0, 1) }}</span><div><strong>{{ group.gameName }}</strong><p>{{ group.category }}</p><small>{{ group.events.length }} 项活动</small></div></div>
              <div class="group-track">
                <div class="grid-backdrop" aria-hidden="true"><div v-for="day in range.days" :key="day.timestamp" :class="{ weekend: day.weekend, 'today-column': day.timestamp === today }" /></div>
                <div v-if="todayVisible" class="today-line" :style="{ left: `${todayPosition}%` }" aria-hidden="true" />
                <div v-for="event in group.events" :key="event.id" class="event-lane">
                  <button type="button" class="timeline-event" :class="{ 'is-point': event.geometry.kind === 'point', 'is-ended': event.status === '已结束', 'clipped-start': event.geometry.clippedStart, 'clipped-end': event.geometry.clippedEnd, 'is-selected': selectedId === event.id }" :style="barStyle(event)" :title="eventDescription(event)" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" @click="selectEvent(event)">
                    <template v-if="event.geometry.kind === 'range'"><span class="event-bar-title">{{ event.geometry.clippedStart ? '‹ ' : '' }}{{ event.name || '未命名活动' }}{{ event.geometry.clippedEnd ? ' ›' : '' }}</span><small>{{ event.status }}</small></template>
                    <template v-else><span class="point-diamond" aria-hidden="true" /><span class="point-label" :class="{ 'point-label-left': event.geometry.left > 70 }"><strong>{{ event.name || '未命名活动' }}</strong><small>{{ event.geometry.endpoint === 'end' ? '截止' : event.geometry.endpoint === 'start' ? '开始' : '时点' }} · {{ event.geometry.reason }}</small></span></template>
                  </button>
                </div>
              </div>
            </div>
          </template>
          <div v-else class="calendar-empty timeline-empty"><span aria-hidden="true">◇</span><strong>{{ events.length ? '当前范围没有可定位的活动' : '暂无活动数据' }}</strong><p>{{ events.length ? '可切换时间范围，或查看下方未确定日期的活动。' : '采集到的活动公告将在这里按真实日期展示。' }}</p></div>
        </div>
      </div>
      <div class="calendar-footer"><span>日期按实际时刻比例展示 · 点击活动查看完整时间与来源</span><span>↔ 可横向滚动</span></div>
    </section>

    <section v-if="undated.length || invalid.length" class="calendar-unplaced" aria-labelledby="unplaced-title"><div class="unplaced-heading"><h2 id="unplaced-title">待确认的时间</h2><p>原始数据未给出完整日期，或日期存在异常。</p></div><div class="unplaced-grid"><div v-for="bucket in [{ title: '日期未提供', events: undated }, { title: '日期异常', events: invalid }]" v-show="bucket.events.length" :key="bucket.title" class="unplaced-bucket"><h3>{{ bucket.title }} <span>{{ bucket.events.length }}</span></h3><button v-for="event in bucket.events" :key="event.id" type="button" class="unplaced-event" :aria-label="`查看活动详情：${event.name || '未命名活动'}`" @click="selectEvent(event)"><span><strong>{{ event.name || '未命名活动' }}</strong><small>{{ event.gameName }} · {{ event.category }}</small></span><span class="unknown-reason">{{ event.geometry.reason }} <b aria-hidden="true">↗</b></span></button></div></div></section>

    <section v-if="selected" ref="detailElement" class="calendar-detail" aria-labelledby="calendar-detail-title" tabindex="-1" :style="{ '--game-accent': gameAccent(selected.gameId) }">
      <div class="detail-heading"><div><p class="calendar-eyebrow">{{ selected.gameName }} / {{ selected.category }}</p><h2 id="calendar-detail-title">{{ selected.name || '未命名活动' }}</h2></div><button type="button" class="detail-close" aria-label="关闭活动详情" @click="selectedId = null">×</button></div>
      <div class="detail-status"><span>{{ selected.status }}</span><span v-if="selected.geometry.reason">{{ selected.geometry.reason }}</span><span v-if="selected.stale" class="calendar-stale">数据可能过期</span></div>
      <dl><div><dt>开始时间 · 北京时间</dt><dd>{{ formatBeijingDateTime(selected.start_at) }}</dd><small v-if="selected.start_at && selected.geometry.start === null">原始值：{{ selected.start_at }}</small></div><div><dt>截止时间 · 北京时间</dt><dd>{{ formatBeijingDateTime(selected.end_at) }}</dd><small v-if="selected.end_at && selected.geometry.end === null">原始值：{{ selected.end_at }}</small></div><div><dt>来源标题</dt><dd>{{ selected.source_title || '未提供' }}</dd></div><div><dt>快照抓取时间 · 北京时间</dt><dd>{{ formatBeijingDateTime(selected.fetchedAt) }}</dd></div></dl>
      <p v-if="selected.geometry.clippedStart || selected.geometry.clippedEnd" class="clipping-note">时间条已按当前显示范围裁剪{{ selected.geometry.clippedStart ? '左侧' : '' }}{{ selected.geometry.clippedStart && selected.geometry.clippedEnd ? '和' : '' }}{{ selected.geometry.clippedEnd ? '右侧' : '' }}；以上为完整起止时间。</p>
      <p v-if="selected.source_post_id" class="source-id">来源标识：{{ selected.source_post_id }}</p><a v-if="sourceUrl" :href="sourceUrl" target="_blank" rel="noopener noreferrer" class="source-link">查看原始公告 ↗</a>
    </section>
  </div>
</template>

<style scoped>
.calendar-page { min-width: 0; display: grid; gap: 24px; color: var(--text); }
.calendar-heading { display: flex; justify-content: space-between; gap: 24px; align-items: end; padding: 2px 0 7px; }
.calendar-eyebrow { font-size: 10px; letter-spacing: .18em; color: var(--accent); font-weight: 650; margin-bottom: 10px; }
.calendar-heading h1 { font-size: clamp(26px, 3vw, 36px); letter-spacing: -.04em; font-weight: 650; line-height: 1.3; }
.heading-dot { color: var(--accent); margin-left: 3px; }
.calendar-subtitle { margin-top: 10px; color: var(--text-muted); font-size: 13px; }
.calendar-timezone { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--text-muted); white-space: nowrap; padding-bottom: 3px; }
.calendar-timezone strong { color: var(--accent); font-size: 10px; font-weight: 550; }
.calendar-board { background: var(--card-bg); border: 1px solid var(--border); border-radius: 16px; overflow: hidden; min-width: 0; }
.calendar-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 18px; flex-wrap: wrap; padding: 24px 24px 18px; }
.calendar-navigation, .calendar-filters { display: flex; align-items: center; gap: 16px; }
.calendar-navigation h2 { font-size: 19px; font-weight: 600; letter-spacing: -.02em; min-width: 141px; }
.calendar-arrows { display: flex; gap: 2px; }
.calendar-page button, .calendar-page select { cursor: pointer; font-family: inherit; }
.calendar-arrows button, .today-button, .detail-close { border: 1px solid var(--border); background: transparent; color: var(--text-muted); border-radius: 7px; }
.calendar-arrows button { height: 32px; width: 29px; font-size: 22px; line-height: 24px; }
.today-button { padding: 6px 12px; font-size: 11px; }
.range-toggle { display: flex; background: var(--bg); border-radius: 8px; padding: 4px; }
.range-toggle button { border: 0; padding: 6px 13px; color: var(--text-muted); background: transparent; border-radius: 5px; font-size: 12px; }
.range-toggle button[aria-pressed="true"] { background: #35404b; color: var(--accent); }
.game-filter select { background: var(--bg); border: 1px solid var(--border); color: var(--text); border-radius: 7px; padding: 8px 10px; font-size: 12px; max-width: 170px; }
.calendar-meta { display: flex; justify-content: space-between; gap: 12px; padding: 0 24px 18px; font-size: 11px; color: var(--text-muted); }
.calendar-meta strong { color: var(--text); font-size: 12px; font-weight: 500; }
.calendar-legend { display: flex; gap: 16px; }
.calendar-legend span { display: flex; align-items: center; gap: 6px; }
.calendar-legend i { display: inline-block; }
.legend-range { width: 12px; height: 7px; border-radius: 2px; background: #677785; }
.legend-point { width: 6px; height: 6px; background: #a6b2c2; transform: rotate(45deg); }
.legend-today { width: 2px; height: 10px; background: var(--accent); }
.calendar-stale { color: #e2c38a; font-size: 11px; }
.calendar-board > .calendar-stale { margin: 0 24px 16px; padding: 10px 12px; background: #d8bb840a; border-left: 2px solid #ad925c; }
.calendar-read-error, .calendar-missing { margin: 0 24px 16px; padding: 10px 12px; font-size: 11px; line-height: 1.6; }
.calendar-read-error { background: #dfaa8a0a; border-left: 2px solid #c39a7c; color: #e3ba9a; }
.calendar-missing { color: var(--text-muted); border: 1px dashed var(--border); border-radius: 6px; }
.timeline-scroll { overflow: auto; max-height: min(68vh, 560px); scrollbar-color: #4b5a68 var(--bg); scrollbar-width: thin; }
.timeline-canvas { min-width: var(--timeline-min); }
.timeline-header, .timeline-group { display: grid; grid-template-columns: 184px minmax(0, 1fr); }
.timeline-header { position: sticky; top: 0; z-index: 5; background: var(--card-bg); border-top: 1px solid var(--border); border-bottom: 1px solid var(--border); }
.timeline-label { position: sticky; left: 0; z-index: 3; background: var(--card-bg); border-right: 1px solid var(--border); }
.header-label { display: flex; flex-direction: column; justify-content: center; gap: 5px; padding: 18px 20px; color: var(--text-muted); font-size: 11px; }
.header-label small { color: #8393a4; font-size: 9px; }
.date-track, .grid-backdrop { display: grid; grid-template-columns: repeat(var(--day-count), minmax(0, 1fr)); }
.date-cell { position: relative; min-height: 78px; display: flex; flex-direction: column; align-items: center; gap: 7px; padding: 12px 0 17px; border-right: 1px solid #ffffff05; font-variant-numeric: tabular-nums; }
.date-cell small { font-size: 9px; color: #8191a3; }
.date-cell strong { font-size: 14px; font-weight: 500; }
.date-cell.weekend { background: #ffffff03; }
.date-cell.is-today { color: var(--accent); background: #d8bb840c; }
.date-cell.is-today strong { border-radius: 50%; background: var(--accent); color: #1c242d; width: 25px; height: 25px; line-height: 25px; margin-top: -3px; }
.day-today { font-size: 8px; position: absolute; bottom: 5px; color: var(--accent); }
.timeline-group { border-bottom: 1px solid var(--border); min-height: 110px; }
.timeline-group:last-child { border-bottom: 0; }
.group-label { display: flex; align-items: flex-start; gap: 11px; padding: 21px 16px; }
.game-monogram { flex: 0 0 32px; height: 38px; background: color-mix(in srgb, var(--game-accent) 13%, transparent); color: var(--game-accent); border: 1px solid color-mix(in srgb, var(--game-accent) 24%, transparent); border-radius: 6px; text-align: center; line-height: 36px; font-size: 15px; font-family: serif; }
.group-label strong { display: block; font-size: 12px; margin-top: 2px; }
.group-label p { color: var(--game-accent); margin-top: 6px; font-size: 10px; }
.group-label small { display: block; color: #8292a4; margin-top: 8px; font-size: 9px; }
.group-track { position: relative; padding: 12px 0; overflow: hidden; }
.grid-backdrop { position: absolute; inset: 0; pointer-events: none; }
.grid-backdrop > div { border-right: 1px solid #ffffff05; }
.grid-backdrop .weekend { background: #ffffff02; }
.grid-backdrop .today-column { background: #d8bb8407; }
.today-line { position: absolute; top: 0; bottom: 0; width: 1px; background: #d8bb8475; z-index: 2; pointer-events: none; }
.event-lane { height: 61px; position: relative; }
.timeline-event { position: absolute; top: 5px; height: 48px; min-width: 0; border: 0; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--game-accent) 32%, transparent); border-radius: 5px; color: var(--text); background: repeating-linear-gradient(125deg, transparent, transparent 12px, #ffffff03 12px, #ffffff03 14px), linear-gradient(100deg, color-mix(in srgb, var(--game-accent) 26%, #19232e), color-mix(in srgb, var(--game-accent) 9%, #19232e)); padding: 7px 0; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 4px; text-align: left; overflow: hidden; transition: filter .15s; }
.timeline-event:not(.is-point)::before { content: ''; position: absolute; inset: 0 auto 0 0; width: 3px; background: var(--game-accent); }
.timeline-event:hover { filter: brightness(1.2); }
.timeline-event.is-ended { opacity: .56; }
.event-bar-title { display: block; font-size: 11px; font-weight: 550; width: 100%; padding: 0 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.timeline-event > small { font-size: 9px; color: var(--game-accent); white-space: nowrap; padding-left: 11px; }
.timeline-event.clipped-start { border-top-left-radius: 0; border-bottom-left-radius: 0; }
.timeline-event.clipped-start::before { background: repeating-linear-gradient(to bottom, var(--game-accent) 0 3px, transparent 3px 6px); }
.timeline-event.clipped-end { border-top-right-radius: 0; border-bottom-right-radius: 0; }
.timeline-event.clipped-end::after { content: ''; position: absolute; inset: 0 0 0 auto; width: 2px; background: repeating-linear-gradient(to bottom, var(--game-accent) 0 3px, transparent 3px 6px); }
.timeline-event.is-selected { outline: 2px solid var(--accent); outline-offset: 2px; z-index: 2; }
.timeline-event.is-point { height: 38px; width: 16px; transform: translateX(-50%); top: 10px; padding: 0; background: transparent; border: 0; box-shadow: none; overflow: visible; align-items: center; }
.point-diamond { display: block; height: 9px; width: 9px; background: var(--game-accent); transform: rotate(45deg); border: 2px solid var(--card-bg); box-shadow: 0 0 0 1px var(--game-accent); }
.point-label { position: absolute; left: 20px; width: 230px; max-width: 230px; display: grid; gap: 5px; color: var(--text); padding: 4px 7px; border-radius: 4px; background: #19232eeb; }
.point-label strong { font-size: 11px; font-weight: 500; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.point-label small { font-size: 9px; color: var(--text-muted); }
.point-label-left { left: auto; right: 20px; text-align: right; }
.calendar-empty { padding: 42px 24px; text-align: center; color: var(--text-muted); font-size: 12px; }
.timeline-empty { display: grid; gap: 13px; justify-items: center; min-height: 245px; align-content: center; }
.timeline-empty > span { font-size: 27px; color: var(--accent); opacity: .7; }
.timeline-empty strong { color: var(--text); font-size: 14px; font-weight: 500; }
.calendar-footer { padding: 14px 24px; display: flex; justify-content: space-between; gap: 12px; border-top: 1px solid var(--border); font-size: 10px; color: #93a1b1; }
.calendar-unplaced { border: 1px solid var(--border); padding: 23px; border-radius: 14px; background: #151e28; }
.unplaced-heading { display: flex; gap: 16px; align-items: baseline; margin-bottom: 20px; flex-wrap: wrap; }
.unplaced-heading h2 { font-size: 15px; font-weight: 550; }
.unplaced-heading p { font-size: 11px; color: var(--text-muted); }
.unplaced-grid { display: grid; gap: 24px; }
.unplaced-bucket h3 { font-size: 11px; color: #a4b0bf; margin: 0 0 10px; font-weight: 500; }
.unplaced-bucket h3 span { margin-left: 7px; color: var(--accent); }
.unplaced-event { display: flex; justify-content: space-between; gap: 20px; align-items: center; padding: 13px 0; width: 100%; border: 0; border-top: 1px solid #ffffff08; color: var(--text); background: transparent; text-align: left; }
.unplaced-event > span:first-child { display: grid; gap: 6px; }
.unplaced-event strong { font-weight: 500; font-size: 12px; }
.unplaced-event small, .unknown-reason { color: var(--text-muted); font-size: 10px; }
.unknown-reason b { margin-left: 18px; color: var(--accent); }
.calendar-detail { background: var(--card-bg); border: 1px solid color-mix(in srgb, var(--game-accent) 38%, var(--border)); border-radius: 14px; padding: 25px; scroll-margin: 22px; }
.detail-heading { display: flex; align-items: start; justify-content: space-between; gap: 20px; }
.detail-heading h2 { font-size: 20px; font-weight: 550; line-height: 1.5; }
.detail-close { height: 30px; width: 30px; font-size: 20px; flex-shrink: 0; }
.detail-status { display: flex; gap: 10px; margin: 15px 0 22px; color: var(--game-accent); font-size: 11px; flex-wrap: wrap; }
.detail-status > span { background: #ffffff06; padding: 4px 8px; border-radius: 4px; }
.calendar-detail dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px; margin: 0; }
.calendar-detail dt { color: var(--text-muted); font-size: 10px; margin-bottom: 8px; }
.calendar-detail dd { margin: 0; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.calendar-detail dl small { display: block; color: var(--text-muted); margin-top: 6px; }
.clipping-note { margin-top: 20px; padding: 12px; background: #d8bb8409; color: var(--accent); font-size: 11px; line-height: 1.6; }
.source-id { color: var(--text-muted); margin-top: 20px; font-size: 10px; overflow-wrap: anywhere; }
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
  .group-label { padding: 20px 10px; gap: 7px; }
  .game-monogram { flex-basis: 24px; height: 30px; line-height: 28px; font-size: 12px; }
  .group-label strong { font-size: 11px; }
  .calendar-footer { padding: 12px 16px; flex-direction: column; }
  .calendar-unplaced, .calendar-detail { padding: 18px; }
  .calendar-detail dl { grid-template-columns: 1fr; }
  .unplaced-event { gap: 10px; align-items: start; }
  .unknown-reason { max-width: 100px; line-height: 1.6; flex-shrink: 0; }
}
@media (prefers-reduced-motion: reduce) { .timeline-event { transition: none; } }
</style>
