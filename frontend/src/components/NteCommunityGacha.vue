<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { displayBeijing } from '../time.js'
import { safeUrl } from '../calendar.js'
import { finiteValue } from '../dashboard.js'
import { vGlide } from '../motion.js'
import InfoHint from './InfoHint.vue'

const props = defineProps({ snap: { type: Object, default: null }, roles: { type: Array, default: () => [] } })
const legacy = computed(() => props.snap?.payload && props.snap.payload.schema_version !== 1)
const pools = computed(() => !legacy.value && Array.isArray(props.snap?.payload?.pools) ? props.snap.payload.pools : [])
const selected = ref(0), failedImages = reactive(new Set())
watch(pools, value => { if (!value[selected.value]) selected.value = 0 })
const current = computed(() => pools.value[selected.value])
const entries = computed(() => Array.isArray(current.value?.details) ? current.value.details : [])
const known = value => finiteValue(value) !== null && value >= 0
const show = value => known(value) ? value : '未知'
const average = value => known(value) ? Number(value.toFixed(1)) : '未知'
const scale = computed(() => known(current.value?.guarantee) && current.value.guarantee > 0 ? current.value.guarantee : null)
const officialTitle = computed(() => !legacy.value && typeof props.snap?.payload?.luck_title === 'string' ? props.snap.payload.luck_title : '')
const titleTone = computed(() => { const code = props.snap?.payload?.luck_type; return code >= 1 && code <= 5 ? 'short' : code >= 6 && code <= 10 ? 'medium' : code >= 11 && code <= 15 ? 'long' : 'unknown' })
const fetched = computed(() => props.snap?.fetched_at ? displayBeijing(props.snap.fetched_at) : '未提供')
const roleIcons = computed(() => new Map(props.roles.map(role => [String(role.id), role.icon_url])))
function icon(entry) {
  const id = String(entry.item_id || '')
  const cdn = 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character'
  const official = /^fork_[a-zA-Z0-9_-]+$/.test(id) ? `${cdn}/fork/${id}.png` : /^\d+$/.test(id) ? `${cdn}/tall/${id}.PNG` : null
  for (const raw of [roleIcons.value.get(id), official]) {
    const url = safeUrl(raw)
    if (url && !failedImages.has(raw) && !failedImages.has(url)) return url
  }
  return null
}
function imageFailed(entry) { failedImages.add(icon(entry)) }
function barStyle(entry) {
  if (!known(entry.pity) || !scale.value) return { width: '0%' }
  return { width: `${Math.min(100, entry.pity / scale.value * 100)}%` }
}
// Verified against Tajiduo scard/main.149e4946.js: no local rarity thresholds.
const rating = entry => ({ 1: '超欧', 2: '欧', 3: '非', 4: '超非' })[entry.lucky_type] || ''
function tone(entry) {
  return ({ 0: 'medium', 1: 'short', 2: 'short', 3: 'medium', 4: 'long' })[entry.lucky_type] || 'unknown'
}
function obtained(value) {
  if (typeof value !== 'string' || !value.trim()) return '时间未提供'
  const normalized = value.replace(' ', 'T')
  const source = /(?:Z|[+-]\d{2}:\d{2})$/i.test(normalized) ? normalized : `${normalized}+08:00`
  return Number.isNaN(new Date(source).getTime()) ? '时间未提供' : displayBeijing(source)
}
</script>

<template>
  <section class="community-stats cap-card" aria-label="社区抽卡统计">
    <header class="cap-title stats-header">
      <h2>近期抽卡记录</h2>
      <span class="source-tag">社区统计</span>
      <InfoHint v-if="snap?.payload && !legacy" text="来源：塔吉多社区 · 统计窗口内数据，可能存在同步延迟" />
      <span v-if="officialTitle" class="luck-title" :class="titleTone"><small>近期评价</small><strong>{{ officialTitle }}</strong></span>
      <span class="cap-meta read-time">最近读取 <time>{{ fetched }}</time><span v-if="snap?.stale" class="badge badge-stale">旧快照 · 等待更新</span></span>
    </header>
    <p v-if="!snap?.payload" class="empty">暂无社区抽卡数据，请登录后刷新。</p>
    <p v-else-if="legacy" class="empty">抽卡数据格式已升级，请刷新后查看。</p>
    <template v-else>
      <p v-if="!pools.length" class="empty">暂无卡池统计。</p>
      <div v-else class="pool-overview">
        <article v-for="(pool, index) in pools" :key="index" class="pool-stat t-item" :style="{ '--i': index }" :class="{ active: selected === index }">
          <h3>{{ pool.name || '未命名卡池' }}</h3>
          <p class="draw-total"><strong>{{ show(pool.total_draws) }}</strong><span>抽</span></p>
          <dl><div><dt>出 S 数量</dt><dd>{{ show(pool.s_count) }}</dd></div><div><dt>S 级平均</dt><dd>{{ average(pool.average) }}</dd></div></dl>
        </article>
      </div>
      <section v-if="pools.length" class="history-panel" aria-label="已出 S 明细">
        <div class="history-bar">
          <nav v-glide class="pool-tabs segmented" aria-label="选择抽卡统计卡池"><button v-for="(pool, index) in pools" :key="index" type="button" :aria-pressed="selected === index" @click="selected = index">{{ pool.name || '未命名卡池' }}</button></nav>
          <h3>已出 S 记录 <span>{{ entries.length }} 条</span></h3>
          <InfoHint align="end" text="仅展示已抽出的 S 级条目与本次出 S 抽数，不展示当前垫抽。" />
        </div>
        <p v-if="!entries.length" class="empty">该卡池暂无已出 S 明细。</p>
        <ol v-else class="pull-list">
          <li v-for="(entry, index) in entries" :key="`${selected}-${entry.item_id}-${index}`" class="pull-row">
            <div class="reward-icon"><img v-if="icon(entry)" :src="icon(entry)" :alt="entry.name || entry.item_id" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(entry)" /><span v-else aria-hidden="true">{{ String(entry.name || entry.item_id || '?').slice(0, 2) }}</span></div>
            <strong class="pull-name" :title="entry.name || entry.item_id">{{ entry.name || entry.item_id || '未知条目' }}</strong>
            <div class="bar-track" :aria-label="known(entry.pity) ? `本次出 S：${entry.pity} 抽` : '本次抽数未提供'"><div class="pull-bar" :class="tone(entry)" :style="barStyle(entry)" /><div class="bar-values"><template v-if="known(entry.pity)"><strong>{{ entry.pity }}</strong><span>抽</span></template><span v-else>本次抽数未提供</span><span v-if="rating(entry)" class="rating" :class="tone(entry)" title="塔吉多社区评价">{{ rating(entry) }}</span></div></div>
            <time class="pull-time">{{ obtained(entry.obtained_at) }}</time>
          </li>
        </ol>
        <footer v-if="entries.length" class="bar-legend"><span><i class="short" />欧 / 超欧</span><span><i class="medium" />普通 / 非</span><span><i class="long" />超非</span><span v-if="scale">本池标尺 {{ scale }} 抽</span><InfoHint align="end" text="评价与配色沿用塔吉多；横条表示这次出 S 的抽数，不表示当前垫抽。未提供评价时显示灰色，未提供标尺时不绘制比例。" /></footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
.community-stats { --mint:#04c8a3; --mint-ink:#062e28; --bar-green:#04c8a3; --bar-yellow:#edbc49; --bar-red:#e55961; --rating-bg:#101820e8; --rating-short:#3aebc0; --rating-long:#ff7c86; --rating-medium:#f5d46e; --bar-text-shadow:0 1px 3px #0009; --badge-ink:#17201f; min-width:0; color:var(--text); }
/* Day theme: bars turn into light tints under dark text; the mint used as text darkens. */
:root[data-theme="light"] .community-stats { --mint:#06755e; --mint-ink:#ffffff; --bar-green:#8fdcc7; --bar-yellow:#f3cf73; --bar-red:#f2a1a7; --rating-bg:#ffffffe6; --rating-short:#0b7d61; --rating-long:#c23c48; --rating-medium:#836000; --bar-text-shadow:none; }

/* Header: title, source tag and the official rating on one line, read time right. */
.stats-header { position:relative; }
.stats-header h2 { font-size:18px; line-height:24px; font-weight:600; letter-spacing:-.01em; }
.source-tag { padding:0 6px; border-radius:4px; background:var(--mint); color:var(--mint-ink); font-size:11px; font-weight:600; line-height:18px; }
.luck-title { display:inline-flex; align-items:baseline; gap:6px; padding:1px 8px; border-radius:5px; color:var(--badge-ink); line-height:20px; }
.luck-title small { font-size:10px; font-weight:500; }
.luck-title strong { font-size:13px; font-weight:700; }
.luck-title.unknown { color:var(--text-muted); }
.read-time time { color:var(--text-muted); font-variant-numeric:tabular-nums; }

/* Pool totals: three compact tiles, count on the left, S stats stacked right. */
.pool-overview { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap:8px; }
.pool-stat { display:grid; grid-template-columns:1fr auto; grid-template-areas:"name name" "total stats"; align-items:end; gap:2px 12px; min-width:0; padding:10px 12px; border:1px solid var(--border); border-radius:9px; background:var(--overlay-2); }
.pool-stat.active { border-color:color-mix(in srgb,var(--accent) 35%,transparent); background:linear-gradient(150deg,color-mix(in srgb,var(--accent) 5%,transparent),var(--overlay-2)); }
.pool-stat h3 { grid-area:name; overflow:hidden; color:var(--text-muted); font-size:12px; font-weight:500; line-height:16px; text-overflow:ellipsis; white-space:nowrap; }
.draw-total { grid-area:total; display:flex; align-items:baseline; gap:4px; }
.draw-total strong { font-size:26px; line-height:30px; font-weight:600; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.draw-total > span { color:var(--text-muted); font-size:12px; }
.pool-stat dl { grid-area:stats; display:grid; gap:1px; margin:0 0 3px; }
.pool-stat dl > div { display:flex; align-items:baseline; justify-content:flex-end; gap:8px; }
.pool-stat dt { color:var(--text-muted); font-size:11px; line-height:16px; }
.pool-stat dd { min-width:2.5em; margin:0; color:var(--text); font-size:13px; font-weight:600; line-height:16px; text-align:right; font-variant-numeric:tabular-nums; }

/* S history: tabs and heading share one line; each pull is one ~34px row. */
.history-panel { margin-top:12px; padding-top:12px; border-top:1px solid var(--border); }
.history-bar { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px; margin-bottom:10px; }
.history-bar h3 { margin-left:auto; font-size:13px; font-weight:600; white-space:nowrap; }
.history-bar h3 span { margin-left:4px; color:var(--text-muted); font-size:11px; font-weight:400; }
.pull-list { display:grid; gap:6px; margin:0; padding:0; list-style:none; }
.pull-row { display:grid; grid-template-columns:28px minmax(72px, 112px) minmax(0, 1fr) auto; align-items:center; gap:10px; min-width:0; min-height:32px; }
.reward-icon { display:grid; place-items:center; width:28px; height:28px; overflow:hidden; border:1px solid color-mix(in srgb,var(--game-nte) 22%,transparent); border-radius:6px; background:linear-gradient(140deg,color-mix(in srgb,var(--game-nte) 16%,transparent),var(--overlay-1)); }
.reward-icon img { width:100%; height:100%; object-fit:cover; }
.reward-icon > span { color:var(--game-nte); font-size:11px; }
.pull-name { min-width:0; overflow:hidden; color:var(--text); font-size:12px; font-weight:500; text-overflow:ellipsis; white-space:nowrap; }
.pull-time { color:var(--text-muted); font-size:11px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.bar-track { position:relative; height:26px; min-width:0; border-radius:5px; background:var(--overlay-2); }
.pull-bar { position:absolute; inset:0 auto 0 0; height:100%; max-width:100%; border-radius:5px; box-sizing:border-box; transition:width var(--duration-slow) var(--ease-smooth-out); background-image:repeating-linear-gradient(110deg,transparent 0,transparent 22px,#ffffff15 22px,#ffffff15 40px); }
.bar-values { position:relative; display:flex; align-items:center; gap:4px; height:100%; padding:0 10px; color:var(--text); text-shadow:var(--bar-text-shadow); }
.bar-values strong { font-size:15px; font-weight:700; line-height:1; font-variant-numeric:tabular-nums; }
.bar-values > span { font-size:11px; white-space:nowrap; }
.bar-values .rating { margin-left:6px; padding:1px 5px; border-radius:3px; background:var(--rating-bg); color:var(--text); font-size:10.5px; line-height:15px; text-shadow:none; }
.rating.short { color:var(--rating-short); }.rating.long { color:var(--rating-long); }.rating.medium { color:var(--rating-medium); }
.short { background-color:var(--bar-green); }.medium { background-color:var(--bar-yellow); }.long { background-color:var(--bar-red); }.unknown { color:var(--text-muted); background-color:var(--overlay-2); background-image:none; }
.bar-legend { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:4px 12px; margin-top:10px; padding-top:8px; border-top:1px solid var(--border); color:var(--text-muted); font-size:11px; }
.bar-legend > span { display:flex; align-items:center; gap:5px; }
.bar-legend i { width:7px; height:7px; border-radius:2px; }
.empty { padding:18px 0; color:var(--text-muted); font-size:13px; line-height:1.7; text-align:center; }
@media (max-width:560px) {
  .pool-overview { grid-template-columns:repeat(auto-fit, minmax(96px, 1fr)); gap:6px; }
  .pool-stat { grid-template-columns:minmax(0, 1fr); grid-template-areas:"name" "total" "stats"; padding:8px; }
  .draw-total strong { font-size:22px; line-height:26px; }
  .pool-stat dl > div { justify-content:space-between; gap:4px; }
  .pool-stat dt { font-size:10.5px; white-space:nowrap; }
  .pool-stat dd { min-width:0; }
  .history-bar h3 { margin-left:0; }
  .pull-row { grid-template-columns:28px minmax(0, 1fr) auto; grid-template-areas:"icon name time" "icon bar bar"; gap:2px 10px; }
  .reward-icon { grid-area:icon; align-self:start; margin-top:2px; }
  .pull-name { grid-area:name; }
  .pull-time { grid-area:time; font-size:10.5px; }
  .bar-track { grid-area:bar; height:24px; }
}
</style>
