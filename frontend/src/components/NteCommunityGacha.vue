<script setup>
import { nteItemLabel } from '../nte-display.js'
import { computed, reactive, ref, watch } from 'vue'
import { displayBeijing } from '../time.js'
import { safeUrl } from '../calendar.js'
import { finiteValue } from '../dashboard.js'
import { vGlide } from '../motion.js'
import { gachaRating, gachaTone, luckTone, officialPullIcon, pullTime } from '../nte-charts.js'
import InfoHint from './InfoHint.vue'
import { nteRewardIcon } from '../nte-icons.js'

const props = defineProps({ snap: { type: Object, default: null }, roles: { type: Array, default: () => [] }, imageMode:{type:Boolean,default:false} })
const legacy = computed(() => props.snap?.payload && props.snap.payload.schema_version !== 1)
const pools = computed(() => !legacy.value && Array.isArray(props.snap?.payload?.pools) ? props.snap.payload.pools : [])
const selected = ref(0), failedImages = reactive(new Set())
watch(pools, value => { if (!value[selected.value]) selected.value = 0 })
const current = computed(() => pools.value[selected.value])
const historyGroups = computed(() => (props.imageMode ? pools.value : current.value ? [current.value] : [])
  .map(pool => ({pool,entries:Array.isArray(pool.details) ? pool.details : []})))
const known = value => finiteValue(value) !== null && value >= 0
const show = value => known(value) ? value : '未知'
const average = value => known(value) ? Number(value.toFixed(1)) : '未知'
const scale = pool => known(pool?.guarantee) && pool.guarantee > 0 ? pool.guarantee : null
const officialTitle = computed(() => !legacy.value && typeof props.snap?.payload?.luck_title === 'string' ? props.snap.payload.luck_title : '')
const titleTone = computed(() => luckTone(props.snap?.payload?.luck_type))
const fetched = computed(() => props.snap?.fetched_at ? displayBeijing(props.snap.fetched_at) : '未提供')
const roleIcons = computed(() => new Map(props.roles.map(role => [String(role.id), role.icon_url])))
function icon(entry) {
  const id = String(entry.item_id || '')
  for (const raw of [roleIcons.value.get(id), nteRewardIcon({ id, name: entry.name }), officialPullIcon(id)]) {
    const url = safeUrl(raw)
    if (url && !failedImages.has(raw) && !failedImages.has(url)) return url
  }
  return null
}
function imageFailed(entry) { failedImages.add(icon(entry)) }
function barStyle(entry, pool) {
  const limit = scale(pool)
  if (!known(entry.pity) || !limit) return { width: '0%' }
  return { width: `${Math.min(100, entry.pity / limit * 100)}%` }
}
// Verified against Tajiduo scard/main.149e4946.js: no local rarity thresholds.
const obtained = value => pullTime(value) || '时间未提供'
</script>

<template>
  <section class="community-stats cap-card" aria-label="社区抽卡统计">
    <header class="cap-title stats-header">
      <h2>近期抽卡记录</h2>
      <span class="source-tag">社区统计</span>
      <InfoHint v-if="snap?.payload && !legacy" text="来源：塔吉多社区，仅含近期统计。" />
      <span v-if="officialTitle" class="luck-title" :class="titleTone"><small>近期评价</small><strong>{{ officialTitle }}</strong></span>
      <span class="cap-meta read-time">更新于 <time>{{ fetched }}</time><span v-if="snap?.stale" class="badge badge-stale">待更新</span></span>
    </header>
    <p v-if="!snap?.payload" class="empty">暂无抽卡数据，请刷新后查看。</p>
    <p v-else-if="legacy" class="empty">抽卡数据格式已升级，请刷新后查看。</p>
    <template v-else>
      <p v-if="!pools.length" class="empty">暂无卡池统计。</p>
      <div v-else class="pool-overview">
        <article v-for="(pool, index) in pools" :key="index" class="pool-stat t-item" :style="{ '--i': index }" :class="{ active: !imageMode && selected === index }">
          <h3>{{ pool.name || '未命名卡池' }}</h3>
          <p class="draw-total"><strong>{{ show(pool.total_draws) }}</strong><span>抽</span></p>
          <dl><div><dt>出 S 数量</dt><dd>{{ show(pool.s_count) }}</dd></div><div><dt>S 级平均</dt><dd>{{ average(pool.average) }}</dd></div></dl>
        </article>
      </div>
      <section v-for="(group, groupIndex) in historyGroups" :key="groupIndex" class="history-panel" :aria-label="`${group.pool.name || '未命名卡池'}已出 S 明细`">
        <div class="history-bar">
          <nav v-if="!imageMode" v-glide class="pool-tabs segmented" aria-label="选择抽卡统计卡池"><button v-for="(pool, index) in pools" :key="index" type="button" :aria-pressed="selected === index" @click="selected = index">{{ pool.name || '未命名卡池' }}</button></nav>
          <h3><template v-if="imageMode">{{ group.pool.name || '未命名卡池' }} · </template>已出 S 记录 <span>{{ group.entries.length }} 条</span></h3>
          <InfoHint align="end" text="仅展示已抽出的 S 级条目与本次出 S 抽数，不展示当前垫抽。" />
        </div>
        <p v-if="!group.entries.length" class="empty">该卡池暂无已出 S 明细。</p>
        <ol v-else class="pull-list">
          <li v-for="(entry, index) in group.entries" :key="`${groupIndex}-${entry.item_id}-${index}`" class="pull-row">
            <div class="reward-icon"><img v-if="icon(entry)" :src="icon(entry)" :alt="nteItemLabel(entry.item_id,entry.name)" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(entry)" /><span v-else aria-hidden="true">{{ nteItemLabel(entry.item_id,entry.name).slice(0, 2) }}</span></div>
            <strong class="pull-name" :title="entry.name || entry.item_id">{{ nteItemLabel(entry.item_id,entry.name) }}</strong>
            <div class="bar-track" :aria-label="known(entry.pity) ? `本次出 S：${entry.pity} 抽` : '本次抽数未提供'"><div class="pull-bar" :class="gachaTone(entry)" :style="barStyle(entry, group.pool)" /><div class="bar-values"><template v-if="known(entry.pity)"><strong>{{ entry.pity }}</strong><span>抽</span></template><span v-else>本次抽数未提供</span><span v-if="gachaRating(entry)" class="rating" :class="gachaTone(entry)" title="塔吉多社区评价">{{ gachaRating(entry) }}</span></div></div>
            <time class="pull-time">{{ obtained(entry.obtained_at) }}</time>
          </li>
        </ol>
        <footer v-if="group.entries.length" class="bar-legend"><span><i class="short" />欧 / 超欧</span><span><i class="medium" />普通 / 非</span><span><i class="long" />超非</span><span v-if="scale(group.pool)">本池标尺 {{ scale(group.pool) }} 抽</span><InfoHint align="end" text="评价与配色沿用塔吉多；横条表示这次出 S 的抽数，不表示当前垫抽。未提供评价时显示灰色，未提供标尺时不绘制比例。" /></footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
/* The rating hues follow the Tajiduo community page. Bars are tints of the
   series colours on the card colour, so the text on a bar stays readable in
   both themes; the rating words take the text-safe status colours. */
.community-stats { --bar-short:color-mix(in srgb,var(--chart-3) 40%,var(--card-bg)); --bar-medium:color-mix(in srgb,var(--chart-4) 42%,var(--card-bg)); --bar-long:color-mix(in srgb,var(--chart-8) 36%,var(--card-bg)); min-width:0; color:var(--text); }

/* Header: title, source tag and the official rating on one line, read time right. */
.stats-header { position:relative; }
.stats-header h2 { font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.01em; }
.source-tag { padding:0 8px; border-radius:var(--radius-chip); background:var(--control-track); color:var(--text-body); font-size:12px; font-weight:400; line-height:20px; }
.luck-title { display:inline-flex; align-items:baseline; gap:6px; padding:1px 10px; border-radius:var(--radius-chip); color:var(--text); line-height:20px; }
.luck-title small { font-size:12px; font-weight:400; }
.luck-title strong { font-size:13px; font-weight:600; }
.luck-title.unknown { color:var(--text-muted); }
.read-time time { color:var(--text-muted); font-variant-numeric:tabular-nums; }

/* Pool totals: a soft tile per pool, the count large on the left, S stats stacked right; the chosen pool is filled with the tone. */
.pool-overview { display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 240px), 1fr)); gap:12px; }
.pool-stat { display:grid; grid-template-columns:1fr auto; grid-template-areas:"name name" "total stats"; align-items:end; gap:4px 12px; min-width:0; padding:16px 18px; border-radius:var(--radius-tile); background:var(--surface-soft); box-shadow:inset 0 0 0 1px var(--overlay-2); }
.pool-stat.active { background:var(--game-tone); box-shadow:none; }
.pool-stat.active :is(h3, dt, .draw-total > span) { color:var(--game-accent); }
.pool-stat h3 { grid-area:name; overflow:hidden; color:var(--text-muted); font-size:12px; font-weight:500; line-height:18px; text-overflow:ellipsis; white-space:nowrap; }
.draw-total { grid-area:total; display:flex; align-items:baseline; gap:4px; }
.draw-total strong { font-size:32px; line-height:38px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
.draw-total > span { color:var(--text-muted); font-size:14px; }
.pool-stat dl { grid-area:stats; display:grid; gap:1px; margin:0 0 4px; }
.pool-stat dl > div { display:flex; align-items:baseline; justify-content:flex-end; gap:8px; }
.pool-stat dt { color:var(--text-muted); font-size:12px; line-height:18px; }
.pool-stat dd { min-width:2.5em; margin:0; color:var(--text); font-size:13px; font-weight:600; line-height:18px; text-align:right; font-variant-numeric:tabular-nums; }

/* S history: tabs and heading share one line; each pull is one ~36px row. */
.history-panel { margin-top:22px; }
.history-bar { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px; margin-bottom:14px; }
.history-bar h3 { margin-left:auto; font-size:14px; font-weight:600; white-space:nowrap; }
.history-bar h3 span { margin-left:4px; color:var(--text-muted); font-size:12px; font-weight:400; }
.pull-list { display:grid; gap:8px; margin:0; padding:0; list-style:none; }
.pull-row { display:grid; grid-template-columns:36px minmax(72px, 128px) minmax(0, 1fr) auto; align-items:center; gap:12px; min-width:0; min-height:36px; }
.reward-icon { display:grid; place-items:center; width:36px; height:36px; overflow:hidden; border-radius:30%; background:var(--game-tone); }
.reward-icon img { width:100%; height:100%; object-fit:cover; }
.reward-icon > span { color:var(--game-accent); font-size:12px; font-weight:600; }
/* A picture the bot could not fetch is swapped for its name; keep that readable in the tile. */
.reward-icon :deep(.render-missing-image) { display:-webkit-box; padding:0 3px; overflow:hidden; color:var(--game-accent); font-size:11px; line-height:1.2; text-align:center; overflow-wrap:anywhere; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.pull-name { min-width:0; overflow:hidden; color:var(--text); font-size:14px; font-weight:500; text-overflow:ellipsis; white-space:nowrap; }
.pull-time { color:var(--text-muted); font-size:12px; font-variant-numeric:tabular-nums; white-space:nowrap; }
.bar-track { position:relative; height:30px; min-width:0; border-radius:var(--radius-control); background:var(--track); }
.pull-bar { position:absolute; inset:0 auto 0 0; height:100%; max-width:100%; border-radius:var(--radius-control); box-sizing:border-box; transition:width var(--duration-slow) var(--ease-smooth-out); }
.bar-values { position:relative; display:flex; align-items:center; gap:4px; height:100%; padding:0 12px; color:var(--text); }
.bar-values strong { font-size:15px; font-weight:600; line-height:1; font-variant-numeric:tabular-nums; }
.bar-values > span { font-size:12px; white-space:nowrap; }
.bar-values .rating { margin-left:6px; padding:0 8px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--text); font-size:12px; font-weight:500; line-height:20px; }
.rating.short { color:var(--success); }.rating.long { color:var(--danger); }.rating.medium { color:var(--stale-text); }
.short { background-color:var(--bar-short); }.medium { background-color:var(--bar-medium); }.long { background-color:var(--bar-long); }.unknown { color:var(--text-muted); background-color:var(--overlay-2); }
.bar-legend { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:4px 14px; margin-top:14px; color:var(--text-muted); font-size:12px; }
.bar-legend > span { display:flex; align-items:center; gap:6px; }
.bar-legend i { width:8px; height:8px; border-radius:3px; }
.empty { padding:18px 0; color:var(--text-muted); font-size:13px; line-height:1.7; text-align:center; }
@media (max-width:560px) {
  .pool-overview { grid-template-columns:repeat(auto-fit, minmax(96px, 1fr)); gap:8px; }
  .pool-stat { grid-template-columns:minmax(0, 1fr); grid-template-areas:"name" "total" "stats"; padding:12px 10px; }
  .draw-total strong { font-size:26px; line-height:32px; }
  .pool-stat dl > div { justify-content:space-between; gap:4px; }
  .pool-stat dt { white-space:nowrap; }
  .pool-stat dd { min-width:0; }
  .history-bar h3 { margin-left:0; }
  .pull-row { grid-template-columns:36px minmax(0, 1fr) auto; grid-template-areas:"icon name time" "icon bar bar"; gap:2px 10px; }
  .reward-icon { grid-area:icon; align-self:start; margin-top:2px; }
  .pull-name { grid-area:name; }
  .pull-time { grid-area:time; }
  .bar-track { grid-area:bar; height:28px; }
}
</style>
