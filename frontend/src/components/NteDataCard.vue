<script setup>
import { fetchedLabel } from '../time.js'
import { percentOf } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
import { displayRoleValue } from '../nte-roles.js'
import { computed } from 'vue'
import { vPop } from '../motion.js'
import InfoHint from './InfoHint.vue'
import RingGauge from './RingGauge.vue'
import DonutChart from './DonutChart.vue'

const props = defineProps({
  snap: { type: Object, default: null },
  capability: { type: String, required: true },
  imageMode: Boolean,
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
// RingGauge draws only from counts it knows; the centre says so when it cannot.
const ring = (current, total) => measurable(current, total) ? { value: Number(current), max: Number(total) } : { value: null, max: null }
const centre = (current, total) => percent(current, total) ?? '—'
const initial = (value) => String(value || '异').slice(0, 1)

const fetchedAt = computed(() => {
  const readAt = props.capability === 'stamina' ? data.value.updated_at || props.snap?.fetched_at : props.snap?.fetched_at
  return fetchedLabel(readAt)
})
const accountStats = computed(() => [
  { name: '等级', value: data.value.level }, { name: '世界等级', value: data.value.world_level },
  { name: '大亨等级', value: data.value.tycoon_level }, { name: '活跃天数', value: data.value.active_days },
  { name: '角色数', value: data.value.character_count },
])
// Three different counts, so they take the first three series colours in order.
const accountRings = computed(() => [
  { name: '成就', value: data.value.achievement_count, total: data.value.achievement_total, series: 'var(--game-vivid, var(--game-nte-vivid))' },
  { name: '房产', value: data.value.house_count, total: data.value.house_total, series: 'var(--game-vivid, var(--game-nte-vivid))' },
  { name: '载具', value: data.value.vehicle_count, total: data.value.vehicle_total, series: 'var(--game-vivid, var(--game-nte-vivid))' },
])
const staminaRows = computed(() => [
  { name: '本性像素', current: data.value.current, total: data.value.maximum, series: 'var(--game-vivid, var(--game-nte-vivid))' },
  { name: '都市活力', current: data.value.city_current, total: data.value.city_maximum, series: 'var(--game-vivid, var(--game-nte-vivid))' },
  { name: '日常活跃', current: data.value.daily_activity, total: 100, series: 'var(--game-vivid, var(--game-nte-vivid))' },
])
// Medals are tiers rather than a series: gold, a pale silver and bronze.
const medals = computed(() => [
  { name: '金', value: data.value.gold, color: 'var(--chart-4)' },
  { name: '银', value: data.value.silver, color: 'color-mix(in srgb, var(--text-faint) 62%, var(--card-bg))' },
  { name: '铜', value: data.value.bronze, color: 'var(--chart-2)' },
].map(medal => ({ ...medal, value: Number.isFinite(medal.value) ? medal.value : null })))
</script>

<template>
  <section class="cap-card nte-card">
    <div class="cap-title">
      {{ titles[capability] || '异环数据' }}
      <InfoHint v-if="capability === 'stamina' && payload !== null && !legacy" text="体力可能有更新延迟，可在游戏内确认。" />
      <span v-if="snap?.stale && !imageMode" class="badge badge-stale">数据可能过期</span>
      <span v-if="fetchedAt" class="cap-meta">{{ capability === 'stamina' ? '读取于' : '更新于' }} {{ fetchedAt }}</span>
    </div>

    <p v-if="payload === null" class="empty">暂无数据，请刷新后查看</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>

    <template v-else-if="capability === 'account'">
      <div class="identity">
        <span class="identity-avatar" aria-hidden="true">{{ initial(data.nickname) }}</span>
        <div class="identity-copy">
          <strong>{{ display(data.nickname) }}</strong>
          <span class="chip-list"><span class="chip">{{ display(data.server_name) }}</span><span v-if="!imageMode" class="chip mono">UID {{ display(data.role_id) }}</span></span>
        </div>
      </div>
      <dl class="kv-grid tiles account-grid">
        <div v-for="stat in accountStats" :key="stat.name"><dt>{{ stat.name }}</dt><dd>{{ display(stat.value) }}</dd></div>
      </dl>
      <dl class="ring-stats">
        <div v-for="stat in accountRings" :key="stat.name" class="ring-stat">
          <dt>{{ stat.name }}</dt>
          <dd>{{ display(stat.value) }}<small>/ {{ display(stat.total) }}</small></dd>
          <span aria-hidden="true"><RingGauge v-bind="ring(stat.value, stat.total)" :label="stat.name" :size="64" :stroke="7" :color="stat.series"><b class="ring-pct">{{ centre(stat.value, stat.total) }}</b></RingGauge></span>
        </div>
      </dl>
    </template>

    <div v-else-if="capability === 'stamina'" class="stamina-grid">
      <div v-for="row in staminaRows" :key="row.name" class="ring-tile">
        <span class="k">{{ row.name }}</span>
        <!-- The ring is the picture; a native progress element stays for assistive tech and the tests. -->
        <progress v-if="measurable(row.current, row.total)" class="sr-only" :value="row.current" :max="row.total" :aria-label="row.name" />
        <span aria-hidden="true"><RingGauge v-bind="ring(row.current, row.total)" :label="row.name" :size="88" :stroke="9" :color="row.series"><b class="ring-pct">{{ centre(row.current, row.total) }}</b></RingGauge></span>
        <span v-pop class="v">{{ display(row.current) }}<small> / {{ display(row.total) }}</small></span>
      </div>
      <div class="ring-tile weekly"><span class="k">周本剩余</span><span class="v big">{{ data.weekly_remaining == null ? '未提供' : display(data.weekly_remaining) }}</span></div>
    </div>

    <template v-else-if="capability === 'progress'">
      <div class="progress-top">
        <span aria-hidden="true"><RingGauge v-bind="ring(data.completed, data.total)" label="成就总进度" :size="120" :stroke="12" color="var(--game-vivid)"><b class="ring-pct large">{{ centre(data.completed, data.total) }}</b></RingGauge></span>
        <div class="progress-copy">
          <span class="k">已达成</span>
          <progress v-if="measurable(data.completed, data.total)" class="sr-only" :value="data.completed" :max="data.total" aria-label="成就总进度" />
          <span class="v big">{{ display(data.completed) }}<small> / {{ display(data.total) }}<template v-if="percent(data.completed, data.total)"> · {{ percent(data.completed, data.total) }}</template></small></span>
        </div>
        <DonutChart class="medals" :segments="medals.map(({ name, value, color }) => ({ label: name, value, color }))" label="奖章分布" unit=" 枚" :size="104" :stroke="14" />
      </div>
      <ul v-if="list(data.categories).length" class="bar-list gauges categories">
        <li v-for="(category, i) in list(data.categories)" :key="category.id ?? i" class="bar-row">
          <span class="k" :title="category.name">{{ display(category.name) }}</span>
          <progress v-if="measurable(category.current, category.total)" :value="category.current" :max="category.total" :aria-label="category.name || '成就分类'" />
          <span v-else class="meter-none" aria-hidden="true" />
          <span class="v">{{ display(category.current) }}<small> / {{ display(category.total) }}</small><span v-if="exceedsTarget(category.current, category.total)" class="target-met">已达目标</span></span>
        </li>
      </ul>
    </template>

    <template v-else-if="capability === 'exploration'">
      <p v-if="!list(data.areas).length" class="empty">暂无数据</p>
      <ul v-else class="area-grid">
        <li v-for="(area, i) in data.areas" :key="area.id ?? i" class="area">
          <div class="area-head">
            <span aria-hidden="true"><RingGauge v-bind="ring(area.current, area.total)" :label="area.name || '区域探索'" :size="72" :stroke="8" color="var(--game-vivid)"><b class="ring-pct">{{ centre(area.current, area.total) }}</b></RingGauge></span>
            <div class="area-row">
              <strong class="k" :title="area.name">{{ display(area.name) }}</strong>
              <progress v-if="measurable(area.current, area.total)" class="sr-only" :value="area.current" :max="area.total" :aria-label="area.name || '区域探索'" />
              <span class="v">{{ display(area.current) }}<small> / {{ display(area.total) }}<template v-if="percent(area.current, area.total)"> · {{ percent(area.current, area.total) }}</template></small><span v-if="exceedsTarget(area.current, area.total)" class="target-met">已达目标</span></span>
            </div>
          </div>
          <ul v-if="list(area.details).length" class="area-details">
            <li v-for="(entry, index) in list(area.details)" :key="entry.id ?? index">
              <span class="k" :title="entry.name">{{ display(entry.name) }}</span>
              <span v-if="measurable(entry.current, entry.total)" class="meter" aria-hidden="true"><i :style="{ '--pct': `${percentOf(entry.current, entry.total)}%` }" /></span>
              <span v-else class="meter-none" aria-hidden="true" />
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
          <span class="record-avatar" aria-hidden="true">{{ initial(entry.nickname) }}</span>
          <div class="record-main">
            <p class="record-name">
              <span class="chip game">{{ entry.game_name || '异环' }}</span>
              <strong>{{ display(entry.nickname) }}</strong>
              <span class="level">Lv{{ display(entry.level) }}</span>
            </p>
            <p class="chip-list">
              <span class="chip">{{ display(entry.server_name) }}</span>
              <span v-if="!imageMode" class="chip mono">UID {{ display(entry.role_id) }}</span>
            </p>
          </div>
          <a v-if="safeUrl(entry.url)" class="ui-button small-button record-link" :href="safeUrl(entry.url)" target="_blank" rel="noopener noreferrer">查看社区名片 ↗</a>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.nte-card { min-width: 0; overflow-wrap: anywhere; }
.cap-title { position: relative; font-size: 16px; line-height: 24px; }
.mono { font-family: var(--font-mono); font-size: 12px; }
.k { min-width: 0; color: var(--text-body); }
.ring-pct { color: var(--text); font-size: 14px; font-weight: 600; letter-spacing: -.01em; }
.ring-pct.large { font-size: 22px; letter-spacing: -.02em; }
.big { font-weight: 550; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }
.big small { margin-left: 4px; color: var(--text-muted); font-size: 13px; font-weight: 400; letter-spacing: 0; }

/* Account: the name on the game's tone, plain levels as soft tiles, owned counts as rings. */
.identity { display: flex; align-items: center; gap: 14px; margin-bottom: 16px; }
.identity-avatar { display: grid; place-items: center; flex-shrink: 0; width: 56px; height: 56px; border-radius: 30%; color: var(--game-accent); font-size: 24px; font-weight: 600; background: var(--game-tone); }
.identity-copy { display: grid; justify-items: start; gap: 6px; min-width: 0; }
.identity-copy > strong { color: var(--text); font-size: 22px; line-height: 28px; font-weight: 600; letter-spacing: -.02em; }
.account-grid { --kv-min: 120px; grid-template-columns: repeat(auto-fit, minmax(var(--kv-min), 1fr)); gap: 10px; }
.account-grid > div { padding: 14px 16px; border-radius: var(--radius-tile); }
.account-grid dd { margin-top: 2px; font-size: 26px; line-height: 32px; font-weight: 550; letter-spacing: -.04em; font-variant-numeric: tabular-nums; }
.ring-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 10px; margin: 10px 0 0; }
.ring-stat { display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "dt ring" "dd ring"; align-items: center; gap: 2px 12px; padding: 14px 16px; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.ring-stat dt { grid-area: dt; align-self: end; color: var(--text-muted); font-size: 12px; line-height: 18px; }
.ring-stat dd { grid-area: dd; align-self: start; margin: 0; color: var(--text); font-size: 20px; line-height: 26px; font-weight: 550; letter-spacing: -.03em; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ring-stat dd small { margin-left: 4px; color: var(--text-muted); font-size: 13px; font-weight: 400; letter-spacing: 0; }
.ring-stat > span { grid-area: ring; }

/* Stamina: one ring per resource, and the weekly attempts beside them. */
.stamina-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 150px), 1fr)); gap: 10px; }
.ring-tile { position: relative; display: grid; justify-items: center; align-content: center; gap: 10px; min-width: 0; padding: 16px 8px 14px; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.ring-tile .k { color: var(--text-muted); font-size: 12px; line-height: 18px; font-weight: 500; }
.ring-tile .v { color: var(--text); font-size: 19px; line-height: 24px; font-weight: 550; letter-spacing: -.03em; font-variant-numeric: tabular-nums; white-space: nowrap; }
.ring-tile .v small { color: var(--text-muted); font-size: 12px; font-weight: 400; letter-spacing: 0; }
.ring-tile.weekly .v { font-size: 32px; line-height: 38px; letter-spacing: -.04em; }

/* Achievements: the ring and its total, the medal split beside them, then one bar per category. */
.progress-top { display: flex; flex-wrap: wrap; align-items: center; gap: 16px 28px; }
.progress-copy { display: grid; gap: 2px; min-width: 120px; }
.progress-copy .big { font-size: 34px; line-height: 40px; }
.medals { margin-left: auto; padding: 14px 18px; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.categories { margin-top: 18px; }
.gauges > .bar-row { grid-template-columns: 76px minmax(60px, 1fr) minmax(76px, auto); min-height: 30px; }
.bar-row > .v { font-variant-numeric: tabular-nums; }
.bar-row > .v small { font-size: 12px; }
/* <progress> keeps the native semantics (the tests read value/max) and takes the meter look: a thin track with a solid fill. */
progress { display: block; appearance: none; width: 100%; height: 6px; border: none; border-radius: 6px; overflow: hidden; background: var(--track); }
progress::-webkit-progress-bar { background: var(--track); border-radius: 6px; }
progress::-webkit-progress-value { background: var(--game-vivid); border-radius: 6px; }
progress::-moz-progress-bar { background: var(--game-vivid); border-radius: 6px; }
progress.sr-only { position: absolute; width: 1px; height: 1px; }
/* Unknown counts draw no bar at all: a dashed hairline instead of a 0% track. */
.meter-none { display: block; height: 0; border-top: 1px dashed var(--border-strong); }

/* Exploration: a tile per area, the detail kinds as thin bars below. */
.area-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); gap: 12px; margin: 0; padding: 0; list-style: none; }
.area { display: grid; align-content: start; gap: 10px; min-width: 0; padding: 16px; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.area-head { display: flex; align-items: center; gap: 14px; min-width: 0; }
.area-row { display: grid; gap: 2px; min-width: 0; }
.area-row > .k { overflow: hidden; color: var(--text); font-size: 15px; line-height: 22px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.area-row > .v { color: var(--text-body); font-size: 15px; font-weight: 600; font-variant-numeric: tabular-nums; }
.area-row > .v small { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.area-details { display: grid; gap: 2px; margin: 0; padding: 8px 0 0; border-top: 1px solid var(--border); list-style: none; font-size: 12px; line-height: 20px; }
.area-details > li { display: grid; grid-template-columns: 64px minmax(40px, 1fr) auto; align-items: center; gap: 10px; min-width: 0; }
.area-details .k { overflow: hidden; color: var(--text-muted); text-overflow: ellipsis; white-space: nowrap; }
.area-details .meter { height: 6px; --series: var(--game-vivid); }
.area-details .v { color: var(--text-body); text-align: right; font-variant-numeric: tabular-nums; }
.area-details .v small { color: var(--text-faint); font-size: 12px; white-space: nowrap; }
.target-met { display: inline-block; margin-left: 6px; padding: 0 8px; border-radius: var(--radius-chip); background: var(--success-bg); color: var(--success); font-size: 12px; font-weight: 500; line-height: 18px; }

/* Community card: a letter tile, the name and chips, the link as a button. */
.record-list { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.record { display: flex; flex-wrap: wrap; align-items: center; gap: 10px 16px; }
.record-avatar { display: grid; place-items: center; flex-shrink: 0; width: 48px; height: 48px; border-radius: 30%; color: var(--game-accent); font-size: 20px; font-weight: 600; background: var(--game-tone); }
.record-main { display: grid; gap: 6px; min-width: 0; flex: 1 1 220px; }
.record-name { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
.record-name > strong { color: var(--text); font-size: 16px; line-height: 22px; font-weight: 600; }
.record .chip.game { --game-color: var(--game-vivid); }
.record-link { margin-left: auto; color: var(--accent); }
.level { color: var(--text-muted); font-size: 12px; font-variant-numeric: tabular-nums; }

@media (max-width: 480px) {
  .account-grid { --kv-min: 96px; }
  .medals { margin-left: 0; width: 100%; }
  .stamina-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
