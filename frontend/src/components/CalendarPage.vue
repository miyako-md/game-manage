<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import ArtworkImage from './ArtworkImage.vue'
import { eventArtwork } from '../event-artwork.js'
import CalendarTimelineContent from './CalendarTimelineContent.vue'
import VersionCalendarContent from './VersionCalendarContent.vue'
import VersionCalendarMetadata from './VersionCalendarMetadata.vue'
import AppIcon from './AppIcon.vue'
import MenuSelect from './MenuSelect.vue'
import DonutChart from './DonutChart.vue'
import { DAY_MS, browserTimeZone, browserCalendarRange, browserCalendarBoundary, collectCalendarEvents, collectVersionCalendars, browserEventGeometry, browserEventStatus, formatBrowserDateTime, browserVersionCalendarRange, safeUrl, shiftBrowserCalendarAnchor } from '../calendar.js'
import { gameStyle, gameVars as themeVars } from '../dashboard.js'
import { prefersReducedMotion, vGlide, vReveal } from '../motion.js'
import { collectionState, hasFreshPublicFallback } from '../snapshot-state.js'
import CloudSnapshotStatus from './CloudSnapshotStatus.vue'

const props = defineProps({
  games: { type: Array, default: () => [] },
  snapshots: { type: Object, default: () => ({}) },
  loading: { type: Boolean, default: false },
  initialGameId: { type: String, default: '' },
  readErrors: { type: Object, default: () => ({}) },
  showSourceStatus: { type:Boolean, default:false },
})
const formatSnapshotTime = value => {
  const formatted = formatBrowserDateTime(value)
  return formatted === '未知' ? '未提供' : formatted
}
const timeZone = browserTimeZone()
const now = ref(Date.now())
const anchor = ref(now.value)
const mode = ref('version')
const filter = ref(props.initialGameId === 'all' ? '' : props.initialGameId)
const gameOptions = computed(() => [{ value: '', label: '全部游戏' }, ...props.games.map(game => ({ value: game.game_id, label: game.display_name }))])
const selectedId = ref(null)
const detailElement = ref(null)
const agendaElement = ref(null)
let selectedTrigger = null
const boardElement = ref(null)
const boardTop = ref(240)
const boardWidth = ref(0)
let layoutObserver
function fitWindow() {
  if (typeof window === 'undefined' || !boardElement.value?.getBoundingClientRect) return
  const bounds = boardElement.value.getBoundingClientRect()
  boardTop.value = Math.round(bounds.top + window.scrollY)
  boardWidth.value = Math.round(bounds.width)
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

const versionCalendars = computed(() => collectVersionCalendars(props.games, props.snapshots, filter.value, now.value))
const range = computed(() => mode.value === 'version' ? browserVersionCalendarRange(versionCalendars.value.flatMap(c => c.events), now.value) || browserCalendarRange(anchor.value, 'rolling') : browserCalendarRange(anchor.value, mode.value))
const rangeTitle = computed(() => mode.value === 'version' ? '版本活动汇总' : mode.value === 'month'
  ? formatBrowserDateTime(range.value.start).slice(0, 7).replace('-', ' 年 ') + ' 月'
  : `${formatBrowserDateTime(range.value.start).slice(5, 10)} — ${formatBrowserDateTime(range.value.end - 1).slice(5, 10)}`)
const events = computed(() => (mode.value === 'version' ? versionCalendars.value.flatMap(c => c.events) : collectCalendarEvents(props.games, props.snapshots, filter.value)).map(event => {
  const geometry = browserEventGeometry(event, range.value)
  const status = browserEventStatus(event, now.value)
  return {...event, geometry, status}
}))
const visibleEvents = computed(() => mode.value === 'version' ? events.value : events.value.filter(event => event.geometry.visible))
const selected = computed(() => events.value.find(event => event.id === selectedId.value))
const sourceUrl = computed(() => safeUrl(selected.value?.source_url))
const filteredGames = computed(() => props.games.filter(game => !filter.value || game.game_id === filter.value))
const staleGames = computed(() => filteredGames.value.filter(game => props.snapshots[game.game_id]?.events?.stale).map(game => game.display_name))
const eventGames = computed(() => filteredGames.value.filter(game => !Array.isArray(game.capabilities) || game.capabilities.includes('events')))
const missingGames = computed(() => eventGames.value.filter(game => !collectionState(props.snapshots[game.game_id]?.events) && !Array.isArray(props.snapshots[game.game_id]?.events?.payload)).map(game => game.display_name))
const neverGames = computed(() => eventGames.value.filter(game => collectionState(props.snapshots[game.game_id]?.events) === 'never').map(game => game.display_name))
const failedCollections = computed(() => eventGames.value.filter(game => !props.readErrors[game.game_id] && collectionState(props.snapshots[game.game_id]?.events) === 'failed').map(game => ({ id: game.game_id, name: game.display_name, partial: hasFreshPublicFallback(props.snapshots[game.game_id]?.events), retained: Array.isArray(props.snapshots[game.game_id]?.events?.payload) })))
const failedCollectionAlerts = computed(() => failedCollections.value.filter(failure => !failure.partial))
const failedCollectionNames = computed(() => failedCollectionAlerts.value.map(failure => failure.name).join('、'))
const collectionRetainedMessage = computed(() => failedCollectionAlerts.value.every(failure => failure.retained) ? '正在显示已有活动。' : failedCollectionAlerts.value.some(failure => failure.retained) ? '部分游戏正在显示已有活动，其余暂无可显示活动。' : '暂无可显示活动。')
const partialCollections = computed(() => failedCollections.value.filter(failure => failure.partial))
const emptyTitle = computed(() => failedCollectionAlerts.value.length ? '活动更新暂不可用，等待更新' : neverGames.value.length ? '等待活动更新' : '暂无活动数据')
const failedReads = computed(() => filteredGames.value.filter(game => props.readErrors[game.game_id]).map(game => ({
  id: game.game_id, name: game.display_name, error: props.readErrors[game.game_id], retained: Array.isArray(props.snapshots[game.game_id]?.events?.payload),
})))
const failedReadNames = computed(() => failedReads.value.map(failure => failure.name).join('、'))
const readRetainedMessage = computed(() => failedReads.value.every(failure => failure.retained) ? '正在显示已有活动。' : failedReads.value.some(failure => failure.retained) ? '部分游戏正在显示已有活动，其余暂无可显示活动。' : '暂无可显示活动。')
const gameVars = id => themeVars(id === 'lol' ? 'league_of_legends' : id)
// Counts for the tiles above the board, over every event the current view collects.
const statusCounts = computed(() => ({
  ongoing: events.value.filter(event => event.status === '进行中').length,
  soon: events.value.filter(event => event.status === '进行中' && event.geometry.end !== null && event.geometry.end - now.value <= 3 * DAY_MS).length,
  upcoming: events.value.filter(event => event.status === '未开始').length,
}))
const gameSplit = computed(() => filteredGames.value.map(game => ({ label: game.display_name, value: events.value.filter(event => event.gameId === game.game_id).length, color: gameStyle(game.game_id).vivid2 })).filter(part => part.value))
// The side column's list while nothing is selected: what ends first in this view, then what starts next.
const agenda = computed(() => [
  ...visibleEvents.value.filter(event => event.status === '进行中' && event.geometry.end != null).sort((a, b) => a.geometry.end - b.geometry.end),
  ...visibleEvents.value.filter(event => event.status === '未开始').sort((a, b) => (a.geometry.start ?? Infinity) - (b.geometry.start ?? Infinity)),
].slice(0, 6))
function shift(direction) { anchor.value = shiftBrowserCalendarAnchor(anchor.value, mode.value, direction) }
function goToday() { now.value = Date.now(); anchor.value = now.value }
function setMode(value) { mode.value = value }
async function selectEvent(event, interaction) {
  selectedTrigger = interaction?.currentTarget ?? null
  selectedId.value = event.id
  await nextTick()
  detailElement.value?.scrollIntoView?.({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'nearest' })
  detailElement.value?.focus?.({ preventScroll: true })
}
async function closeDetail() {
  selectedId.value = null
  await nextTick()
  // A detail opened from the side list replaced that list; focus returns to its heading.
  if (selectedTrigger?.isConnected) selectedTrigger.focus()
  else agendaElement.value?.focus?.({ preventScroll: true })
  selectedTrigger = null
}
</script>

<template>
  <div class="calendar-page">
    <header class="page-heading">
      <div class="page-heading-copy"><h1>活动日历</h1></div>
      <div class="page-meta calendar-timezone"><AppIcon name="clock" :size="14" /> {{ timeZone }}</div>
    </header>

    <div class="calendar-layout">
      <section ref="boardElement" class="calendar-board" aria-label="游戏活动时间轴" :aria-busy="loading" :style="{'--calendar-top':`${boardTop}px`, '--calendar-width':boardWidth ? `${boardWidth}px` : undefined}">
        <div class="calendar-toolbar">
          <div class="calendar-navigation">
            <div v-if="mode !== 'version'" class="calendar-arrows"><button type="button" aria-label="上一时间范围" @click="shift(-1)"><AppIcon name="chevron" :size="15" class="previous-arrow" /></button><button type="button" aria-label="下一时间范围" @click="shift(1)"><AppIcon name="chevron" :size="15" class="next-arrow" /></button></div>
            <h2 aria-live="polite">{{ rangeTitle }}</h2>
            <button v-if="mode !== 'version'" class="today-button" type="button" @click="goToday">今天</button>
          </div>
          <div class="calendar-filters">
            <div v-glide class="range-toggle segmented" aria-label="显示范围"><button type="button" :aria-pressed="mode === 'version'" @click="setMode('version')">版本</button><button type="button" :aria-pressed="mode === 'rolling'" @click="setMode('rolling')">近 30 天</button><button type="button" :aria-pressed="mode === 'month'" @click="setMode('month')">整月</button><button type="button" :aria-pressed="mode === 'fortnight'" @click="setMode('fortnight')">14 天</button></div>
            <MenuSelect v-model="filter" label="筛选游戏" align="end" :options="gameOptions" />
          </div>
        </div>
        <div class="calendar-meta"><span><strong>{{ visibleEvents.length }}</strong> 项活动<span v-if="events.length > visibleEvents.length"> · 共 {{ events.length }} 项</span></span><div class="calendar-legend"><span><i class="legend-range" aria-hidden="true" />活动区间</span><span><i class="legend-point" aria-hidden="true" />日期标记</span><span><i class="legend-today" aria-hidden="true" />现在</span></div></div>
        <p v-if="failedCollectionAlerts.length" class="calendar-read-error" role="status">{{ failedCollectionNames }} · 活动更新暂不可用。{{ collectionRetainedMessage }}</p>
        <p v-if="failedReads.length" class="calendar-read-error" role="status">{{ failedReadNames }} · 活动读取失败。{{ readRetainedMessage }}</p>
        <p v-if="missingGames.length && !loading" class="calendar-missing" role="status">{{ missingGames.join('、') }} · 尚未取得活动，请稍后刷新。</p>
        <p v-if="neverGames.length && !loading" class="calendar-missing" role="status">{{ neverGames.join('、') }} · 等待活动更新。</p>
        <details v-if="showSourceStatus || staleGames.length || failedReads.length || partialCollections.length || versionCalendars.length" class="calendar-source-states"><summary>数据来源详情</summary><p v-if="staleGames.length" class="calendar-stale">数据可能过期 · {{ staleGames.join('、') }}</p><p v-for="failure in partialCollections" :key="failure.id">{{ failure.name }} · 部分来源不可用，显示可用来源数据。</p><p v-for="failure in failedReads" :key="failure.id">{{ failure.name }}：{{ failure.error }}</p><div v-if="showSourceStatus" v-for="game in filteredGames" :key="game.game_id"><strong>{{ game.display_name }}</strong><CloudSnapshotStatus :snapshots="snapshots[game.game_id] || {}" :capabilities="['events']" :format-time="formatSnapshotTime" /></div><VersionCalendarMetadata :calendars="versionCalendars" /></details>
        <p v-if="loading && !events.length" class="calendar-empty" role="status">加载中…</p>
        <VersionCalendarContent v-else-if="mode === 'version'" :calendars="versionCalendars" :snapshots="snapshots" :as-of="now" :selected-id="selectedId" :empty-title="emptyTitle" :show-source-details="false" @select="selectEvent" />
        <CalendarTimelineContent v-else :events="events" :snapshots="snapshots" :range="range" :as-of="now" :range-mode="mode" :selected-id="selectedId" :empty-title="emptyTitle" @select="selectEvent" />
      </section>
      <aside class="calendar-aside">
        <section v-if="selected" ref="detailElement" class="calendar-detail t-panel" aria-labelledby="calendar-detail-title" tabindex="-1" :style="gameVars(selected.gameId)" @keydown.esc.stop="closeDetail">
          <div class="detail-heading"><div><p class="eyebrow">{{ selected.gameName }} / {{ selected.category }}</p><h2 id="calendar-detail-title">{{ selected.name || '未命名活动' }}</h2></div><button type="button" class="detail-close" aria-label="关闭活动详情" @click="closeDetail"><AppIcon name="close" :size="16" /></button></div>
          <ArtworkImage class="detail-artwork" :candidates="eventArtwork(selected, snapshots)" :retry-key="snapshots[selected.gameId]?.events" :alt="`${selected.name || '活动'}配图`" /><div class="detail-status"><span>{{ selected.status }}</span><span v-if="selected.geometry.reason">{{ selected.geometry.reason }}</span><span v-if="selected.stale" class="calendar-stale">数据可能过期</span></div>
          <dl><div><dt>开始时间</dt><dd>{{ browserCalendarBoundary(selected, 'start') }}</dd><small v-if="selected.geometry.approximateStart">仅知开始日期 {{ selected.start_date }}，具体时刻未知</small></div><div><dt>截止时间</dt><dd>{{ browserCalendarBoundary(selected, 'end') }}</dd><small v-if="selected.end_at && selected.end_precision === 'version_end'">{{ selected.end_text }}，时刻取自下个版本的维护预告</small></div><div><dt>来源标题</dt><dd>{{ selected.source_name ? selected.source_name + ' · ' : '' }}{{ selected.source_title || '未提供' }}</dd></div><div><dt>数据更新时间</dt><dd>{{ formatBrowserDateTime(selected.fetchedAt) }}</dd></div></dl>
          <p v-if="selected.source_note" class="source-id">{{ selected.source_note }}</p>
          <a v-if="sourceUrl" :href="sourceUrl" target="_blank" rel="noopener noreferrer" class="source-link">查看原始公告 ↗</a>
        </section>
        <section v-else class="calendar-agenda" aria-labelledby="calendar-agenda-title">
          <h2 id="calendar-agenda-title" ref="agendaElement" tabindex="-1">即将截止</h2>
          <ul v-if="agenda.length" class="agenda-list">
            <li v-for="event in agenda" :key="event.id"><button type="button" class="agenda-item" :style="gameVars(event.gameId)" @click="selectEvent(event, $event)"><ArtworkImage class="agenda-artwork" :candidates="eventArtwork(event, snapshots)" :retry-key="snapshots[event.gameId]?.events" decorative /><span class="agenda-pill">{{ event.gameName }} · {{ event.status }}</span><strong>{{ event.name || '未命名活动' }}</strong><small>{{ event.status === '未开始' ? `${browserCalendarBoundary(event, 'start')} 开始` : `${browserCalendarBoundary(event, 'end')} 截止` }}</small><AppIcon name="arrow" :size="14" /></button></li>
          </ul>
          <p v-else class="agenda-empty">{{ loading ? '加载中…' : '当前范围内没有进行中或即将开始的活动。' }}</p>
        </section>
        <div v-if="events.length" class="calendar-stats">
          <article v-reveal class="calendar-stat"><span>进行中</span><p><b>{{ statusCounts.ongoing }}</b><small>项</small></p></article>
          <article v-reveal class="calendar-stat" :class="{ hot: statusCounts.soon }"><span>3 天内截止</span><p><b>{{ statusCounts.soon }}</b><small>项</small></p></article>
          <article v-reveal class="calendar-stat"><span>未开始</span><p><b>{{ statusCounts.upcoming }}</b><small>项</small></p></article>
          <article v-if="gameSplit.length" v-reveal class="calendar-split"><DonutChart :segments="gameSplit" label="各游戏的活动数" unit=" 项" :size="92" :stroke="12"><b class="split-total">{{ events.length }}</b><small class="split-unit">项</small></DonutChart></article>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.calendar-page { min-width: 0; display: grid; gap: 20px; color: var(--text); }
.calendar-page > .page-heading { margin-bottom: 0; }
:global(.workspace-main:has(.calendar-page)) { max-width:1800px; }
.calendar-timezone { gap: 6px; white-space: nowrap; }
/* Board on the left; on the right the selected event's detail, or what ends first, then the counts. */
.calendar-layout { display:grid; grid-template-columns:minmax(0, 1fr) minmax(260px, 280px); gap:20px; align-items:start; }
.calendar-aside { position:sticky; top:16px; display:grid; gap:16px; min-width:0; }
/* Counts under the side list, and the split by game. */
.calendar-stats { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
.calendar-stat, .calendar-split { min-width:0; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); box-shadow:var(--card-shadow); }
.calendar-stat { display:flex; flex-direction:column; justify-content:space-between; gap:6px; padding:14px 16px; border-radius:var(--radius-tile); }
.calendar-stat > span { color:var(--text-muted); font-size:12px; font-weight:500; }
.calendar-stat p { display:flex; align-items:baseline; gap:4px; }
.calendar-stat b { font-size:26px; line-height:30px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
.calendar-stat small, .split-unit { color:var(--text-muted); font-size:12px; }
.calendar-stat.hot { background:var(--stale-bg); border-color:var(--attention-border); }
.calendar-stat.hot b { color:var(--stale-text); }
.calendar-split { grid-column:1 / -1; padding:14px 18px; display:flex; align-items:center; border-radius:var(--radius-tile); }
.calendar-split :deep(.donut-chart) { width:100%; }
.split-total { font-size:22px; font-weight:600; letter-spacing:-.02em; }
.calendar-board { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius-card); box-shadow: var(--card-shadow); overflow: visible; min-width: 0; display:flex; flex-direction:column; min-height:max(760px,calc(100dvh - var(--calendar-top) - 24px)); }
.calendar-board > .version-calendars { flex:none; }
.calendar-board :deep(.calendar-content:not(.image-mode)) { flex:none; min-height:min(640px,80dvh); max-height:max(720px,calc(100dvh - 56px)); overflow:auto; }
.calendar-board > :not(.calendar-content):not(.version-calendars){flex-shrink:0}
.calendar-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; padding: 18px 20px 12px; }
.calendar-navigation, .calendar-filters { display: flex; align-items: center; gap: 12px; }
.calendar-navigation h2 { font-size: 17px; font-weight: 600; letter-spacing: -.01em; font-variant-numeric: tabular-nums; }
.calendar-arrows { display: flex; gap: 4px; }
.calendar-page button, .calendar-page select { cursor: pointer; font-family: inherit; }
.calendar-arrows button, .today-button, .detail-close { border: 1px solid var(--border); background: var(--card-bg); box-shadow: var(--btn-shadow); color: var(--text-body); border-radius: var(--radius-control); transition: color var(--duration-quick) var(--ease-smooth-out), border-color var(--duration-quick) var(--ease-smooth-out), background-color var(--duration-quick) var(--ease-smooth-out), transform var(--duration-quick) var(--ease-smooth-out); }
@media (hover: hover) and (pointer: fine) { .calendar-arrows button:hover, .today-button:hover, .detail-close:hover { background: var(--button-hover-bg); color: var(--text); } }
.calendar-arrows button:active, .today-button:active, .detail-close:active { transform: translateY(1px) scale(0.98); }
.calendar-arrows button { display: grid; place-items: center; height: var(--control-h, 40px); width: var(--control-h, 40px); padding: 0; }
.previous-arrow { transform: rotate(90deg); }
.next-arrow { transform: rotate(-90deg); }
.today-button { min-height: var(--control-h, 40px); padding: 6px 14px; font-size: var(--fs-body, 0.8125rem); font-weight: 500; }
.calendar-meta { display: flex; justify-content: space-between; gap: 12px; padding: 0 20px 14px; font-size: 12px; color: var(--text-muted); }
.calendar-meta strong { color: var(--text); font-size: 13px; font-weight: 500; }
.calendar-legend { display: flex; gap: 16px; }
.calendar-legend span { display: flex; align-items: center; gap: 6px; }
.calendar-legend i { display: inline-block; }
.legend-range { width: 16px; height: 8px; border-radius: 3px; background: color-mix(in srgb, var(--text-muted) 45%, var(--track)); }
.legend-point { width: 6px; height: 6px; background: var(--text-muted); transform: rotate(45deg); }
.legend-today { width: 2px; height: 12px; border-radius: 2px; background: var(--accent); }
.calendar-stale { color: var(--stale-text); font-size: 12px; }
.calendar-board > .calendar-stale { margin: 0 20px 16px; padding: 10px 12px; background: var(--stale-bg); border: 1px solid color-mix(in srgb, var(--stale-text) 22%, transparent); border-radius: var(--radius-well); font-size: 13px; }
.calendar-read-error, .calendar-missing { margin: 0 20px 10px; padding: 8px 12px; font-size: 13px; line-height: 1.6; border-radius: var(--radius-well); }
.calendar-source-states { margin:0 20px 12px; color:var(--text-muted); font-size:12px; }
.calendar-source-states > summary { cursor:pointer; }
.calendar-source-states > div { margin-top:10px; }
.calendar-read-error { background: var(--danger-bg); border: 1px solid var(--danger-border); color: var(--danger); }
.calendar-missing { color: var(--text-muted); background: var(--surface-soft); }
/* Detail: the event's game tone as a header panel inside a white card (mockup .event-detail). */
.calendar-detail { position: relative; overflow: hidden; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius-card); box-shadow: var(--card-shadow); padding: 7px 7px 22px; scroll-margin: 24px; }
.calendar-detail > :not(.detail-heading) { margin-left: 16px; margin-right: 16px; }
.detail-heading { display: flex; align-items: start; justify-content: space-between; gap: 16px; padding: 18px 16px 22px 18px; border-radius: calc(var(--radius-card) - 7px); background: var(--game-tone); }
.detail-heading .eyebrow { color: var(--game-accent); }
.detail-heading h2 { margin-top: 6px; font-size: 21px; font-weight: 600; letter-spacing: -.02em; line-height: 1.4; }
.detail-close { display: grid; place-items: center; height: 40px; width: 40px; padding: 0; flex-shrink: 0; border-color: transparent; background: color-mix(in srgb, var(--card-bg) 70%, transparent); }
.detail-artwork { width:calc(100% - 32px); height:150px; margin-top:14px; border-radius:var(--radius-well); }
.detail-status { display: flex; gap: 8px; margin-top: 16px; margin-bottom: 20px; color: var(--text-body); font-size: 12px; font-weight: 500; flex-wrap: wrap; }
.detail-status > span { background: var(--surface-soft); padding: 2px 10px; border-radius: var(--radius-chip); line-height: 20px; }
.detail-status > span:first-child { background: var(--game-tone); color: var(--game-accent); }
.calendar-detail dl { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
.calendar-detail dt { color: var(--text-muted); font-size: 12px; margin-bottom: 6px; }
.calendar-detail dd { margin: 0; font-size: 14px; line-height: 1.6; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.calendar-detail dl small { display: block; color: var(--text-muted); margin-top: 6px; }
.source-id { color: var(--text-muted); margin-top: 10px; font-size: 12px; overflow-wrap: anywhere; }
.source-link { display: inline-block; margin-top: 16px; color: var(--accent); font-size: var(--fs-body, 0.8125rem); font-weight: 500; text-decoration: underline; text-decoration-color: color-mix(in srgb, var(--accent) 42%, transparent); text-underline-offset: 3px; }
.calendar-page button:focus-visible, .calendar-page select:focus-visible, .calendar-detail:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (hover: hover) and (pointer: fine) { .source-link:hover { color: var(--accent-strong); text-decoration-color: currentColor; } }
/* Side list (mockup .agenda-card): a warm panel of white rows, each opening its event's detail. */
.calendar-agenda { padding:22px 20px 20px; border:1px solid var(--border); border-radius:var(--radius-card); background:var(--control-track); }
.calendar-agenda h2 { font-size:17px; font-weight:600; letter-spacing:-.02em; outline:none; }
.calendar-agenda h2:focus-visible { outline:2px solid var(--accent); outline-offset:3px; border-radius:6px; }
.agenda-list { display:grid; gap:10px; margin-top:16px; }
.agenda-item { position:relative; display:grid; justify-items:start; gap:6px; width:100%; min-height:84px; padding:14px 40px 14px 14px; overflow:hidden; border:1px solid var(--card-border); border-radius:16px; background:var(--card-bg); color:var(--text); text-align:left; }
.agenda-artwork { width:100%; height:100%; border-radius:inherit; position:absolute; inset:0; object-position:center 35%; }
.agenda-item:has(.agenda-artwork) { min-height:126px; color:#fff; background:color-mix(in srgb,var(--game-accent) 28%,#18212b); }
.agenda-item:has(.agenda-artwork)::before { content:''; position:absolute; inset:0; background:linear-gradient(90deg,rgba(7,13,22,.94),rgba(7,13,22,.8) 48%,rgba(7,13,22,.16)); z-index:1; }
.agenda-item > :not(.agenda-artwork):not(svg) { position:relative; z-index:2; }
.agenda-pill { max-width:100%; overflow:hidden; padding:2px 7px; border-radius:var(--radius-chip); background:var(--game-tone); color:var(--game-accent); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.agenda-item strong { max-width:88%; font-size:14px; font-weight:600; line-height:1.4; }
.agenda-item small { color:var(--text-muted); font-size:12px; font-variant-numeric:tabular-nums; }
.agenda-item > svg { position:absolute; right:14px; top:16px; z-index:2; color:var(--text-muted); transition:transform var(--duration-fast) var(--ease-smooth-out), color var(--duration-quick) var(--ease-smooth-out); }
.agenda-item:has(.agenda-artwork) strong { text-shadow:0 1px 3px #000; }
.agenda-item:has(.agenda-artwork) small { color:rgba(255,255,255,.92); text-shadow:0 1px 3px #000; }
.agenda-item:has(.agenda-artwork) .agenda-pill { color:#fff; border:1px solid rgba(255,255,255,.3); background:rgba(7,13,22,.78); }
.agenda-item:has(.agenda-artwork) > svg { color:rgba(255,255,255,.88); }
@media (hover: hover) and (pointer: fine) { .agenda-item:hover { border-color:var(--border-strong); } .agenda-item:hover > svg { color:var(--accent); transform:translateX(2px); } .agenda-item:has(.agenda-artwork):hover > svg { color:#fff; } }
.agenda-item:active { transform:translateY(1px); }
.agenda-empty { margin-top:16px; color:var(--text-muted); font-size:13px; line-height:1.8; }
@media (max-width: 1250px) { .calendar-layout { grid-template-columns:minmax(0, 1fr); } .calendar-aside { position:static; grid-template-columns:minmax(0, 1fr) minmax(0, 1fr); align-items:start; } .calendar-aside > .calendar-detail { grid-column:1 / -1; } }
@media (max-width: 760px) {
  .calendar-board { min-height:700px; }
  .calendar-board :deep(.calendar-content:not(.image-mode)) { min-height:min(560px,70dvh); max-height:max(620px,calc(100dvh - 80px)); }
  .calendar-aside { grid-template-columns:minmax(0, 1fr); }
  .calendar-stats { grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px; }
  .calendar-stat { padding:14px; }
  .calendar-stat b { font-size:24px; line-height:28px; }
  .calendar-toolbar { padding: 16px; gap: 14px; }
  .calendar-navigation { gap: 8px; width: 100%; }
  .calendar-navigation h2 { font-size: 15px; }
  .today-button { margin-left: auto; }
  .calendar-filters { justify-content: space-between; flex-wrap:wrap; width: 100%; }
  .range-toggle { flex:1 1 100%; }
  .range-toggle > button { flex:1; }
  .range-toggle > button,.calendar-arrows button,.today-button,.detail-close { min-height:44px; }
  .calendar-arrows button,.detail-close { min-width:44px; }
  .calendar-meta { padding: 0 16px 16px; flex-direction: column; }
  .calendar-detail { padding: 7px 7px 20px; }
  .calendar-detail dl { grid-template-columns: 1fr; }
}
@media (max-width: 400px) {
  .calendar-toolbar { padding: 12px; }
  .calendar-filters { gap: 6px; }
  .range-toggle > button { padding-left: 8px; padding-right: 8px; }
  .calendar-navigation h2 { font-size: 14px; }
  .calendar-arrows button { width: 26px; }
  .today-button { padding-left: 8px; padding-right: 8px; }
}

</style>
