<script setup>
import { displayBeijing } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
  capability: { type: String, required: true },
})

const titles = { account: '账号概览', stamina: '体力与日常', roles: '角色练度', progress: '成就进度', exploration: '探索进度', gacha: '抽卡统计', record: '社区名片' }
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => legacy.value ? {} : payload.value ?? {})
const list = (value) => Array.isArray(value) ? value : []
const display = (value) => value === null || value === undefined || value === '' || (typeof value === 'number' && !Number.isFinite(value)) ? '未知' : value
const ratio = (current, total) => `${display(current)} / ${display(total)}`
const measurable = (current, total) => Number.isFinite(current) && current >= 0 && Number.isFinite(total) && total > 0
const percent = (current, total) => measurable(current, total) ? `${Math.min(100, Math.round(current / total * 100))}%` : null
const exceedsTarget = (current, total) => measurable(current, total) && current > total

function safeUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null
  try {
    const url = new URL(value)
    return ['http:', 'https:'].includes(url.protocol) && !url.username && !url.password ? url.href : null
  } catch { return null }
}

const fetchedAt = computed(() => {
  const readAt = props.capability === 'stamina' ? data.value.updated_at || props.snap?.fetched_at : props.snap?.fetched_at
  return readAt ? displayBeijing(readAt) : null
})
const accountStats = computed(() => [
  ['等级', display(data.value.level)], ['世界等级', display(data.value.world_level)],
  ['大亨等级', display(data.value.tycoon_level)], ['活跃天数', display(data.value.active_days)],
  ['角色数', display(data.value.character_count)],
  ['成就', ratio(data.value.achievement_count, data.value.achievement_total)],
  ['房产', ratio(data.value.house_count, data.value.house_total)],
  ['载具', ratio(data.value.vehicle_count, data.value.vehicle_total)],
])
const staminaRows = computed(() => [
  { name: '本性像素', current: data.value.current, total: data.value.maximum },
  { name: '都市活力', current: data.value.city_current, total: data.value.city_maximum },
  { name: '日常活跃', current: data.value.daily_activity, total: 100 },
])
</script>

<template>
  <section class="cap-card nte-card">
    <div class="cap-title">
      {{ titles[capability] || '异环数据' }}
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
    </div>

    <p v-if="payload === null" class="empty">暂无数据，请登录后刷新</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>

    <template v-else-if="capability === 'account'">
      <div class="identity">
        <strong>{{ display(data.nickname) }}</strong>
        <span>{{ display(data.server_name) }} · UID {{ display(data.role_id) }}</span>
      </div>
      <dl class="metric-grid">
        <div v-for="[name, value] in accountStats" :key="name" class="metric">
          <dt>{{ name }}</dt><dd>{{ value }}</dd>
        </div>
      </dl>
    </template>

    <template v-else-if="capability === 'stamina'">
      <p class="muted">来源：塔吉多角色面板。社区数据可能延迟，请以游戏内体力为准。</p>
      <ul class="rows">
        <li v-for="row in staminaRows" :key="row.name">
          <div class="row-head"><span>{{ row.name }}</span><strong>{{ ratio(row.current, row.total) }}</strong></div>
          <progress v-if="measurable(row.current, row.total)" :value="row.current" :max="row.total" :aria-label="row.name" />
        </li>
        <li class="row-head"><span>周本剩余</span><strong>{{ data.weekly_remaining == null ? '未提供' : display(data.weekly_remaining) }}</strong></li>
      </ul>
    </template>

    <template v-else-if="capability === 'progress'">
      <div class="row-head"><span>已达成</span><strong>{{ ratio(data.completed, data.total) }}</strong></div>
      <progress v-if="measurable(data.completed, data.total)" :value="data.completed" :max="data.total" aria-label="成就总进度" />
      <p class="medals">铜 {{ display(data.bronze) }} · 银 {{ display(data.silver) }} · 金 {{ display(data.gold) }}</p>
      <ul class="rows">
        <li v-for="(category, i) in list(data.categories)" :key="category.id ?? i">
          <div class="row-head"><span>{{ display(category.name) }}</span><span>{{ ratio(category.current, category.total) }}</span></div>
          <progress v-if="measurable(category.current, category.total)" :value="category.current" :max="category.total" :aria-label="category.name || '成就分类'" />
        </li>
      </ul>
    </template>

    <template v-else-if="capability === 'exploration'">
      <p v-if="!list(data.areas).length" class="empty">暂无数据</p>
      <ul v-else class="rows">
        <li v-for="(area, i) in data.areas" :key="area.id ?? i" class="area">
          <div class="row-head"><strong>{{ display(area.name) }}</strong><span>{{ ratio(area.current, area.total) }}<template v-if="percent(area.current, area.total)"> · {{ percent(area.current, area.total) }}</template><span v-if="exceedsTarget(area.current, area.total)" class="target-met"> · 已达目标</span></span></div>
          <progress v-if="measurable(area.current, area.total)" :value="area.current" :max="area.total" :aria-label="area.name || '区域探索'" />
          <ul class="area-details">
            <li v-for="(entry, index) in list(area.details)" :key="entry.id ?? index" class="row-head muted">
              <span>{{ display(entry.name) }}</span><span>{{ ratio(entry.current, entry.total) }}<template v-if="percent(entry.current, entry.total)"> · {{ percent(entry.current, entry.total) }}</template><span v-if="exceedsTarget(entry.current, entry.total)" class="target-met"> · 已达目标</span></span>
            </li>
          </ul>
        </li>
      </ul>
    </template>

    <template v-else-if="capability === 'record'">
      <p v-if="!list(data.cards).length" class="empty">暂无社区名片</p>
      <ul v-else class="rows">
        <li v-for="(entry, i) in data.cards" :key="i" class="community-card">
          <span class="muted">{{ entry.game_name || '异环' }}</span>
          <div class="row-head"><strong>{{ display(entry.nickname) }}</strong><span>Lv{{ display(entry.level) }}</span></div>
          <p class="muted">{{ display(entry.server_name) }} · UID {{ display(entry.role_id) }}</p>
          <a v-if="safeUrl(entry.url)" :href="safeUrl(entry.url)" target="_blank" rel="noopener noreferrer">查看社区名片 ↗</a>
        </li>
      </ul>
    </template>

    <p v-if="fetchedAt" class="fetched-at">{{ capability === 'stamina' ? '读取于' : '更新于' }} {{ fetchedAt }}</p>
  </section>
</template>

<style scoped>
.nte-card { min-width: 0; overflow-wrap: anywhere; }
.identity { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 12px; margin-bottom: 12px; }
.identity > strong { font-size: 17px; }
.identity > span, .muted { color: var(--text-muted); font-size: 12px; }
.metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; margin: 0; }
.metric { background: var(--bg); border-radius: 6px; padding: 8px 10px; min-width: 0; }
dt { color: var(--text-muted); font-size: 12px; }
dd { margin: 4px 0 0; font-weight: 600; font-variant-numeric: tabular-nums; }
.rows { display: flex; flex-direction: column; gap: 12px; }
.row-head { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 4px 10px; font-size: 13px; }
.row-head > :last-child { font-variant-numeric: tabular-nums; }
progress { display: block; appearance: none; width: 100%; height: 6px; margin-top: 6px; border: none; border-radius: 99px; overflow: hidden; background: var(--border); accent-color: var(--accent); }
progress::-webkit-progress-bar { background: var(--border); border-radius: 99px; }
progress::-webkit-progress-value { background: var(--accent); border-radius: 99px; }
progress::-moz-progress-bar { background: var(--accent); border-radius: 99px; }
.role-grid { margin-top: 10px; display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 10px; align-items: start; }
.role-card { border: 1px solid var(--border); border-radius: 8px; padding: 10px; min-width: 0; }
.role-overview { display: flex; align-items: center; gap: 10px; }
.avatar { width: 48px; height: 48px; border-radius: 8px; object-fit: cover; background: var(--bg); flex-shrink: 0; }
.avatar-empty { display: grid; place-items: center; color: var(--text-muted); font-size: 20px; }
.role-heading { display: flex; flex-direction: column; gap: 5px; }
.role-heading > span { color: var(--text-muted); font-size: 12px; }
.role-meta { font-size: 13px; margin: 8px 0 4px; }
details { margin-top: 10px; border-top: 1px solid var(--border); }
summary { color: var(--accent); cursor: pointer; padding: 8px 0 2px; font-size: 13px; }
summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 3px; }
.detail-body h4, .pool h4 { margin: 12px 0 6px; font-size: 13px; }
.detail-rows { margin: 0; }
.detail-rows > div { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 3px 0; }
.detail-rows dd { margin: 0; font-size: 12px; }
.medals { margin: 10px 0 14px; color: var(--text-muted); font-size: 13px; }
.area + .area { border-top: 1px solid var(--border); padding-top: 12px; }
.area-details { margin-top: 8px; display: grid; gap: 5px; }
.target-met { color: var(--text-muted); font-size: 12px; }
.notice { background: var(--bg); color: var(--text-muted); padding: 10px; border-radius: 6px; font-size: 12px; line-height: 1.7; margin-bottom: 10px; }
.pool { margin-top: 14px; border-top: 1px solid var(--border); padding-top: 2px; }
.compact { grid-template-columns: repeat(auto-fit, minmax(105px, 1fr)); }
.draw-list { display: grid; gap: 10px; padding-top: 10px; }
.draw-list .muted { margin-top: 3px; }
.community-card { display: grid; gap: 5px; }
a { color: var(--accent); font-size: 12px; width: fit-content; margin-top: 3px; }
@media (max-width: 420px) { .metric-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
