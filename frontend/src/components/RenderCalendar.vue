<script setup>
import { computed } from 'vue'
import { calendarBoundary, eventGeometry, eventStatus, formatBeijingDateTime, parseBeijingTime } from '../calendar.js'
import { gameVars } from '../dashboard.js'
import ArtworkImage from './ArtworkImage.vue'
import { eventArtwork } from '../event-artwork.js'

const props = defineProps({
  calendars: { type: Array, default: () => [] },
  events: { type: Array, default: () => [] },
  asOf: { type: Number, required: true },
})
const groups = computed(() => {
  if (props.calendars.length) return props.calendars.map((calendar, index) => ({ ...calendar, key: calendar.key || `${calendar.gameId}:${index}`, version: calendar.version || {}, events: calendar.events || [] }))
  const buckets = new Map()
  for (const event of props.events) {
    const gameId = event.gameId || event.game_id || ''
    const key = JSON.stringify([gameId, event.version || ''])
    if (!buckets.has(key)) buckets.set(key, { key, gameId, gameName: event.gameName || gameId || '游戏活动', version: { id: event.version }, events: [] })
    buckets.get(key).events.push(event)
  }
  return [...buckets.values()]
})
// Repeated official notice artwork belongs in the group header, so each activity
// remains short and repeated page headings can retain the same visual context.
function sharedArtwork(calendar) {
  const counts = new Map()
  for (const event of calendar.events) {
    for (const url of eventArtwork(event)) counts.set(url, (counts.get(url) || 0) + 1)
  }
  const shared = [...counts].filter(([, count]) => count > 1).sort((a, b) => b[1] - a[1])[0]
  return shared ? [shared[0]] : []
}
function activityArtwork(calendar, event) {
  const shared = sharedArtwork(calendar)
  return eventArtwork(event).filter(url => !shared.includes(url))
}
const count = computed(() => groups.value.reduce((total, group) => total + group.events.length, 0))
const gameCount = computed(() => new Set(groups.value.map(group => group.gameId || group.gameName)).size)
const versionLabel = version => version.id ? `${version.id} 版本` : '已公布活动'
const status = event => eventStatus(event, props.asOf)
const statusClass = event => ({ '进行中': 'active', '常驻开放': 'active', '未开始': 'upcoming', '已结束': 'ended' }[status(event)] || 'uncertain')
function equivalentDateText(label, text) {
  const pureDate = /^\d{4}[-/]\d{2}[-/]\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?$/i
  if (typeof text !== 'string' || !pureDate.test(text.trim()) || !pureDate.test(label)) return false
  const time = parseBeijingTime(text.trim().replaceAll('/', '-'))
  return time !== null && time === parseBeijingTime(label)
}
function boundary(event, side) {
  const raw = event[`${side}_at`] || event[`${side}_date`]
  const geometry = eventGeometry(event, { start: props.asOf, end: props.asOf + 86400000 })
  if (geometry.kind === 'invalid' && raw) return String(raw) + '（待核对）'
  const label = calendarBoundary(event, side, true)
  const text = event[`${side}_text`]
  const exact = event[`${side}_at`]
  const precision = event[`${side}_precision`]
  const confirmedMinute = typeof exact === 'string' && /[T ]\d{2}:\d{2}/.test(exact) && parseBeijingTime(exact) !== null && !['day', 'relative', 'unknown', 'dependent'].includes(precision)
  const isDay = !confirmedMinute && (event[`${side}_date`] || precision === 'day')
  return [label, isDay ? '时刻未确认' : null, text && !label.includes(text) && !equivalentDateText(label, text) ? text : null].filter(Boolean).join(' · ')
}
function notes(calendar) {
  const version = calendar.version
  return [
    version.source_stale || calendar.events.some(event => event.stale) ? '来源快照可能过期' : null,
    version.coverage === 'partial' ? '部分来源不可用' : version.coverage === 'unverified' ? '活动覆盖范围待核验' : null,
    ...(version.diagnostics || []).map(text => text.replace('有界来源列表可能遗漏公告', '公告列表可能遗漏补充内容')),
  ].filter(Boolean)
}
function sources(calendar) {
  const entries = new Map()
  for (const event of calendar.events) {
    const label = [event.source_name, event.source_title].filter(Boolean).join(' · ') || '来源未提供'
    const key = JSON.stringify([label, event.source_url || '', event.stale || false, event.fetchedAt || event.fetched_at || ''])
    if (!entries.has(key)) entries.set(key, { key, label, stale: event.stale, fetchedAt: event.fetchedAt || event.fetched_at })
  }
  return [...entries.values()]
}
</script>

<template>
  <div class="qq-calendar" :data-calendar-count="count">
    <p v-if="gameCount > 1" class="qq-calendar-summary" data-render-block>{{ gameCount }} 款游戏 · 共 {{ count }} 项</p>
    <p v-if="!groups.length" class="qq-calendar-empty" data-render-block>暂无活动数据</p>
    <section v-for="calendar in groups" :key="calendar.key" class="qq-calendar-game" :style="gameVars(calendar.gameId === 'lol' ? 'league_of_legends' : calendar.gameId)" :data-calendar-game="calendar.gameId">
      <header class="qq-calendar-heading" data-render-block>
        <h2 data-render-heading>{{ calendar.gameName }} · {{ versionLabel(calendar.version) }}</h2>
        <p>{{ calendar.events.length }} 项活动</p>
        <ArtworkImage v-if="sharedArtwork(calendar).length" class="qq-calendar-cover" :candidates="sharedArtwork(calendar)" :alt="`${calendar.gameName}活动公告配图`" />
      </header>
      <p v-if="!calendar.events.length" class="qq-calendar-empty" data-render-block>暂无活动数据</p>
      <article v-for="(event, index) in calendar.events" :key="event.id || index" class="qq-calendar-event" data-render-block data-calendar-event :data-event-id="event.id || index">
        <ArtworkImage v-if="activityArtwork(calendar, event).length" class="qq-calendar-artwork" :candidates="activityArtwork(calendar, event)" :alt="`${event.name || '活动'}公告配图`" />
        <div class="qq-calendar-event-heading">
          <h3>{{ event.name || '未命名活动' }}</h3>
          <span class="qq-calendar-status" :class="statusClass(event)">{{ status(event) }}</span>
        </div>
        <div class="qq-calendar-event-detail">
          <p v-if="event.category || event.cross_version || (event.version && event.version !== calendar.version.id)" class="qq-calendar-category">{{ [event.category, event.cross_version ? '跨版本活动' : event.version && event.version !== calendar.version.id ? `${event.version} 版本` : null].filter(Boolean).join(' · ') }}</p>
          <p><span>开始</span>{{ boundary(event, 'start') }}</p>
          <p><span>结束</span>{{ boundary(event, 'end') }}</p>
          <p v-if="eventGeometry(event, { start: asOf, end: asOf + 86400000 }).kind === 'invalid'" class="qq-calendar-warning">{{ eventGeometry(event, { start: asOf, end: asOf + 86400000 }).reason }}</p>
        </div>
      </article>
      <aside v-if="notes(calendar).length || calendar.version.start_at || calendar.version.start_date || calendar.version.end_at || calendar.version.end_date" class="qq-calendar-notes" data-render-block>
        <h3>版本与覆盖说明</h3>
        <p v-if="calendar.version.start_at || calendar.version.start_date || calendar.version.end_at || calendar.version.end_date">版本开放：{{ boundary(calendar.version, 'start') }}；结束：{{ boundary(calendar.version, 'end') }}</p>
        <p v-for="note in notes(calendar)" :key="note">{{ note }}</p>
      </aside>
      <aside v-for="source in sources(calendar)" :key="source.key" class="qq-calendar-source" data-render-block>
        <p>来源：{{ source.label }}{{ source.stale ? ' · 陈旧快照' : '' }}</p>
        <p v-if="source.fetchedAt">读取：{{ formatBeijingDateTime(source.fetchedAt) }}</p>
      </aside>
    </section>
  </div>
</template>

<style scoped>
.qq-calendar { display:grid; gap:24px; min-width:0; color:var(--text); font-size:26px; line-height:1.5; }
.qq-calendar p,.qq-calendar h2,.qq-calendar h3 { margin:0; }
.qq-calendar-summary { font-size:22px; color:var(--text-muted); }
.qq-calendar-heading p { margin-top:8px; font-size:22px; color:var(--text-muted); }
.qq-calendar-game { display:grid; gap:14px; min-width:0; }
.qq-calendar-heading { padding:16px 18px; border-radius:18px; background:var(--game-tone,var(--surface-soft)); }
.qq-calendar-heading h2 { font-size:32px; font-weight:600; line-height:1.35; overflow-wrap:anywhere; }
.qq-calendar-event { padding:20px; background:var(--card-bg); border:1px solid var(--border); border-radius:18px; box-shadow:0 4px 14px #14213309; min-width:0; }
.qq-calendar-cover { width:100%; height:132px; margin-top:12px; border-radius:12px; object-position:center 38%; }
.qq-calendar-artwork { width:100%; height:116px; margin-bottom:14px; border-radius:12px; object-position:center 38%; }
.qq-calendar-event-heading { display:flex; align-items:flex-start; gap:10px; flex-wrap:wrap; }
.qq-calendar-event-heading h3 { flex:1 1 340px; font-size:28px; font-weight:600; line-height:1.4; overflow-wrap:anywhere; }
.qq-calendar-status { flex:none; padding:3px 10px; border-radius:10px; font-size:22px; font-weight:600; background:var(--surface-soft); color:var(--text-muted); }
.qq-calendar-status.active { color:var(--game-accent,var(--accent)); background:var(--game-tone,var(--surface-soft)); }
.qq-calendar-status.upcoming { color:var(--accent); background:var(--accent-soft,var(--surface-soft)); }
.qq-calendar-status.uncertain,.qq-calendar-warning { color:var(--stale-text,var(--text-muted)); }
.qq-calendar-event-detail { display:grid; gap:3px; margin-top:12px; font-size:22px; overflow-wrap:anywhere; color:var(--text-muted); }
.qq-calendar-event-detail p > span { display:inline-block; min-width:62px; color:var(--text-faint,var(--text-muted)); }
.qq-calendar-category { color:var(--game-accent,var(--accent)); }
.qq-calendar-notes,.qq-calendar-source { padding:14px 18px; border-radius:14px; background:var(--surface-soft); color:var(--text-muted); font-size:22px; overflow-wrap:anywhere; }
.qq-calendar-notes h3 { font-size:24px; font-weight:600; color:var(--text); margin-bottom:6px; }
.qq-calendar-empty { padding:24px 18px; border-radius:18px; font-size:26px; color:var(--text-muted); background:var(--surface-soft); }
</style>
