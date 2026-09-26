<script setup>
import { fetchedLabel } from '../time.js'
import { percentOf } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
import { displayRoleValue } from '../nte-roles.js'
import { computed } from 'vue'
import { vPop } from '../motion.js'
import InfoHint from './InfoHint.vue'

const props = defineProps({
  snap: { type: Object, default: null },
  capability: { type: String, required: true },
})

const titles = { account: '账号概览', stamina: '体力与日常', progress: '成就进度', exploration: '探索进度', record: '社区名片' }
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => legacy.value ? {} : payload.value ?? {})
const list = (value) => Array.isArray(value) ? value : []
const display = (value) => displayRoleValue(value, '未知')
const measurable = (current, total) => percentOf(current, total) != null
const percent = (current, total) => measurable(current, total) ? `${Math.round(percentOf(current, total))}%` : null
const exceedsTarget = (current, total) => measurable(current, total) && Number(current) > Number(total)

const fetchedAt = computed(() => {
  const readAt = props.capability === 'stamina' ? data.value.updated_at || props.snap?.fetched_at : props.snap?.fetched_at
  return fetchedLabel(readAt)
})
// Sibling progress bars in one card cycle through the chart series so
// neighbours never share a hue; the stamina rows carry a fixed colour instead
// since each one is a distinct, always-present metric rather than a list.
const series = (n) => `var(--chart-${n % 6 + 1})`
const accountStats = computed(() => [
  { name: '等级', value: data.value.level }, { name: '世界等级', value: data.value.world_level },
  { name: '大亨等级', value: data.value.tycoon_level }, { name: '活跃天数', value: data.value.active_days },
  { name: '角色数', value: data.value.character_count },
  { name: '成就', value: data.value.achievement_count, total: data.value.achievement_total, series: series(0) },
  { name: '房产', value: data.value.house_count, total: data.value.house_total, series: series(1) },
  { name: '载具', value: data.value.vehicle_count, total: data.value.vehicle_total, series: series(2) },
])
const staminaRows = computed(() => [
  { name: '本性像素', current: data.value.current, total: data.value.maximum, series: 'var(--game-nte)' },
  { name: '都市活力', current: data.value.city_current, total: data.value.city_maximum, series: 'var(--chart-2)' },
  { name: '日常活跃', current: data.value.daily_activity, total: 100, series: 'var(--chart-3)' },
])
const medals = computed(() => [
  { name: '铜', value: data.value.bronze, tone: 'bronze' },
  { name: '银', value: data.value.silver, tone: 'silver' },
  { name: '金', value: data.value.gold, tone: 'gold' },
])
</script>

<template>
  <section class="cap-card nte-card">
    <div class="cap-title">
      {{ titles[capability] || '异环数据' }}
      <template v-if="capability === 'stamina' && payload !== null && !legacy"><span class="delay-note">以游戏内为准</span><InfoHint text="来源：塔吉多角色面板。社区数据可能延迟，请以游戏内体力为准。" /></template>
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="fetchedAt" class="cap-meta">{{ capability === 'stamina' ? '读取于' : '更新于' }} {{ fetchedAt }}</span>
    </div>

    <p v-if="payload === null" class="empty">暂无数据，请登录后刷新</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>

    <template v-else-if="capability === 'account'">
      <div class="identity">
        <strong>{{ display(data.nickname) }}</strong>
        <span class="chip">{{ display(data.server_name) }}</span>
        <span class="chip mono">UID {{ display(data.role_id) }}</span>
      </div>
      <dl class="kv-grid tiles account-grid">
        <div v-for="stat in accountStats" :key="stat.name">
          <dt>{{ stat.name }}</dt>
          <dd>{{ display(stat.value) }}<small v-if="stat.series">/ {{ display(stat.total) }}</small><span v-if="stat.series && measurable(stat.value, stat.total)" class="meter tile-meter" :style="{ '--series': stat.series }"><i :style="{ '--pct': `${percentOf(stat.value, stat.total)}%` }" /></span></dd>
        </div>
      </dl>
    </template>

    <ul v-else-if="capability === 'stamina'" class="bar-list gauges">
      <li v-for="row in staminaRows" :key="row.name" class="bar-row" :style="{ '--series': row.series }">
        <span class="k">{{ row.name }}</span>
        <progress v-if="measurable(row.current, row.total)" :value="row.current" :max="row.total" :aria-label="row.name" />
        <span v-else class="meter-none" aria-hidden="true" />
        <span v-pop class="v">{{ display(row.current) }}<small> / {{ display(row.total) }}</small></span>
      </li>
      <li class="bar-row weekly"><span class="k">周本剩余</span><span class="v">{{ data.weekly_remaining == null ? '未提供' : display(data.weekly_remaining) }}</span></li>
    </ul>

    <template v-else-if="capability === 'progress'">
      <div class="bar-row total-row" :style="{ '--series': series(0) }">
        <span class="k">已达成</span>
        <progress v-if="measurable(data.completed, data.total)" :value="data.completed" :max="data.total" aria-label="成就总进度" />
        <span v-else class="meter-none" aria-hidden="true" />
        <span class="v">{{ display(data.completed) }}<small> / {{ display(data.total) }}<template v-if="percent(data.completed, data.total)"> · {{ percent(data.completed, data.total) }}</template></small></span>
      </div>
      <p class="chip-list medals">
        <span v-for="medal in medals" :key="medal.tone" class="chip medal" :class="medal.tone">{{ medal.name }} <b>{{ display(medal.value) }}</b></span>
      </p>
      <ul v-if="list(data.categories).length" class="bar-list gauges categories">
        <li v-for="(category, i) in list(data.categories)" :key="category.id ?? i" class="bar-row" :style="{ '--series': series(i + 1) }">
          <span class="k" :title="category.name">{{ display(category.name) }}</span>
          <progress v-if="measurable(category.current, category.total)" :value="category.current" :max="category.total" :aria-label="category.name || '成就分类'" />
          <span v-else class="meter-none" aria-hidden="true" />
          <span class="v">{{ display(category.current) }}<small> / {{ display(category.total) }}</small></span>
        </li>
      </ul>
    </template>

    <template v-else-if="capability === 'exploration'">
      <p v-if="!list(data.areas).length" class="empty">暂无数据</p>
      <ul v-else class="area-grid">
        <li v-for="(area, i) in data.areas" :key="area.id ?? i" class="area" :style="{ '--series': series(i) }">
          <div class="bar-row area-row">
            <strong class="k" :title="area.name">{{ display(area.name) }}</strong>
            <progress v-if="measurable(area.current, area.total)" :value="area.current" :max="area.total" :aria-label="area.name || '区域探索'" />
            <span v-else class="meter-none" aria-hidden="true" />
            <span class="v">{{ display(area.current) }}<small> / {{ display(area.total) }}<template v-if="percent(area.current, area.total)"> · {{ percent(area.current, area.total) }}</template></small><span v-if="exceedsTarget(area.current, area.total)" class="target-met">已达目标</span></span>
          </div>
          <ul v-if="list(area.details).length" class="area-details">
            <li v-for="(entry, index) in list(area.details)" :key="entry.id ?? index">
              <span class="k" :title="entry.name">{{ display(entry.name) }}</span>
              <span class="v">{{ display(entry.current) }}<small> / {{ display(entry.total) }}<template v-if="percent(entry.current, entry.total)"> · {{ percent(entry.current, entry.total) }}</template></small> <span v-if="exceedsTarget(entry.current, entry.total)" class="target-met">已达目标</span></span>
            </li>
          </ul>
        </li>
      </ul>
    </template>

    <template v-else-if="capability === 'record'">
      <p v-if="!list(data.cards).length" class="empty">暂无社区名片</p>
      <ul v-else class="record-list">
        <li v-for="(entry, i) in data.cards" :key="i" class="record">
          <div class="record-main">
            <p class="record-name">
              <span class="chip game">{{ entry.game_name || '异环' }}</span>
              <strong>{{ display(entry.nickname) }}</strong>
              <span class="level">Lv{{ display(entry.level) }}</span>
            </p>
            <p class="chip-list">
              <span class="chip">{{ display(entry.server_name) }}</span>
              <span class="chip mono">UID {{ display(entry.role_id) }}</span>
            </p>
          </div>
          <a v-if="safeUrl(entry.url)" class="text-link" :href="safeUrl(entry.url)" target="_blank" rel="noopener noreferrer">查看社区名片 ↗</a>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
/* Stamina comes from a community panel that can lag: the short note stays visible, the detail sits behind ⓘ. */
.delay-note { color: var(--text-faint); font-size: 11px; font-weight: 400; }
.nte-card { min-width: 0; overflow-wrap: anywhere; --medal-bronze: #c98a5a; --medal-silver: #a9b1bd; --medal-gold: #e2b340; }
:root[data-theme="light"] .nte-card { --medal-bronze: #9c5a2b; --medal-silver: #7c8698; --medal-gold: #ad7a00; }
.cap-title { position: relative; }
.mono { font-family: var(--font-mono); font-size: 10.5px; }

/* Account: name with server / UID chips, then eight compact tiles. */
.identity { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 6px; margin-bottom: 10px; }
.identity > strong { margin-right: 4px; font-size: 15px; line-height: 22px; font-weight: 600; color: var(--text); }
.account-grid { --kv-min: 104px; }
.account-grid dd { font-variant-numeric: tabular-nums; }
.tile-meter { height: 3px; margin-top: 4px; }

/* One-line gauges: label · bar · value. <progress> keeps the native semantics
   (the tests read value/max) but takes the .meter look. */
.gauges > .bar-row { grid-template-columns: 64px minmax(60px, 1fr) minmax(64px, auto); }
.bar-row > .v { font-variant-numeric: tabular-nums; }
progress { display: block; appearance: none; width: 100%; height: 6px; border: none; border-radius: 99px; overflow: hidden; background: var(--track); accent-color: var(--series, var(--accent)); }
progress::-webkit-progress-bar { background: var(--track); border-radius: 99px; }
progress::-webkit-progress-value { background: var(--series, var(--accent)); border-radius: 99px; }
progress::-moz-progress-bar { background: var(--series, var(--accent)); border-radius: 99px; }
/* Unknown counts draw no bar at all: a dashed hairline instead of a 0% track. */
.meter-none { display: block; height: 0; border-top: 1px dashed var(--border-strong); }
.weekly { margin-top: 2px; border-top: 1px solid var(--border); }
.weekly > .v { grid-column: 3; }

/* Achievements: total row, medal chips under the bar, then categories. */
.total-row > .v { font-size: 13px; }
/* Indented to start under the bar, so the medals read as part of the total. */
.medals { margin: 2px 0 0 74px; }
.medal::before { content: ''; width: 7px; height: 7px; border-radius: 50%; background: var(--medal); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--text) 12%, transparent); }
.medal.bronze { --medal: var(--medal-bronze); }
.medal.silver { --medal: var(--medal-silver); }
.medal.gold { --medal: var(--medal-gold); }
.categories { margin-top: 10px; padding-top: 6px; border-top: 1px solid var(--border); }
/* Total and categories share one value column, so every bar ends on one line. */
.total-row, .categories > .bar-row { grid-template-columns: 64px minmax(60px, 1fr) 104px; }

/* Exploration: one bar row per area, its details as a compact line below. */
.area-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 400px), 1fr)); gap: 10px 32px; margin: 0; padding: 0; list-style: none; }
.area { min-width: 0; }
.area-row { grid-template-columns: 104px minmax(60px, 1fr) minmax(92px, auto); }
.area-row > .k { color: var(--text); font-weight: 600; }
.area-details { display: grid; grid-template-columns: repeat(auto-fill, minmax(128px, 1fr)); gap: 0 14px; margin: 0 0 0 calc(104px + 10px); padding: 0; list-style: none; font-size: 12px; line-height: 20px; }
.area-details > li { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; min-width: 0; }
.area-details .k { flex: none; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted); }
/* The value may wrap its 已达目标 tag under the numbers in a narrow cell. */
.area-details .v { flex: 1 1 auto; min-width: 0; color: var(--text-body); text-align: right; font-variant-numeric: tabular-nums; }
.area-details .v small { color: var(--text-faint); font-size: 11px; white-space: nowrap; }
.area-details .target-met { display: inline-block; margin-left: 0; }
.area-details > li:only-child { grid-column: 1 / -1; justify-content: flex-start; }
.area-details > li:only-child > .v { flex: none; }
.target-met { margin-left: 6px; padding: 0 5px; border-radius: 4px; background: var(--success-bg); color: var(--success); font-size: 10.5px; font-weight: 500; line-height: 16px; }

/* Community card: one compact block, link on the right. */
.record-list { display: grid; gap: 8px; margin: 0; padding: 0; list-style: none; }
.record { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; }
.record + .record { padding-top: 8px; border-top: 1px solid var(--border); }
.record-main { display: grid; gap: 4px; min-width: 0; }
.record-name { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.record-name > strong { font-size: 14px; line-height: 20px; font-weight: 600; color: var(--text); }
.record .chip.game { --game-color: var(--game-nte); }
.level { color: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }

@media (max-width: 480px) {
  .account-grid { --kv-min: 88px; }
  /* Phones: the area name keeps its full width, the bar runs underneath. */
  .area-row { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "k v" "bar bar"; gap: 2px 10px; }
  .area-row > .k { grid-area: k; }
  .area-row > .v { grid-area: v; }
  .area-row > progress, .area-row > .meter-none { grid-area: bar; }
  .area-details { margin: 4px 0 0; grid-template-columns: repeat(auto-fill, minmax(118px, 1fr)); }
}
</style>
