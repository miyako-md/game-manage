<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { displayBeijing } from '../time.js'
import { safeUrl } from '../calendar.js'
import { finiteValue } from '../dashboard.js'
import { vGlide } from '../motion.js'

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
  <section class="community-stats" aria-label="社区抽卡统计">
    <header class="stats-header">
      <div><p class="eyebrow">RECENT PULLS</p><h2>近期抽卡记录 <span>社区统计</span></h2><p v-if="officialTitle" class="luck-title" :class="titleTone"><small>近期评价</small><strong>{{ officialTitle }}</strong></p></div>
      <p class="read-time">最近读取 <time>{{ fetched }}</time><span v-if="snap?.stale" class="stale">旧快照 · 等待更新</span></p>
    </header>
    <p v-if="!snap?.payload" class="empty">暂无社区抽卡数据，请登录后刷新。</p>
    <p v-else-if="legacy" class="empty">抽卡数据格式已升级，请刷新后查看。</p>
    <template v-else>
      <p v-if="!pools.length" class="empty">暂无卡池统计。</p>
      <div v-else class="pool-overview">
        <article v-for="(pool, index) in pools" :key="index" class="pool-stat t-item" :style="{ '--i': index }" :class="{ active: selected === index }">
          <h3>{{ pool.name || '未命名卡池' }}</h3>
          <p class="draw-total"><strong>{{ show(pool.total_draws) }}</strong><span>抽</span></p>
          <dl><div><dd>{{ show(pool.s_count) }}</dd><dt>出 S 数量</dt></div><div><dd>{{ average(pool.average) }}</dd><dt>S 级平均</dt></div></dl>
        </article>
      </div>
      <p class="source-note">来源：塔吉多社区 · 统计窗口内数据，可能存在同步延迟</p>
      <section v-if="pools.length" class="history-panel" aria-label="已出 S 明细">
        <nav v-glide.underline class="pool-tabs" aria-label="选择抽卡统计卡池"><button v-for="(pool, index) in pools" :key="index" :aria-pressed="selected === index" @click="selected = index">{{ pool.name || '未命名卡池' }}</button></nav>
        <div class="history-heading"><h3>已出 S 记录 <span>{{ entries.length }} 条</span></h3><p>仅展示已抽出的 S 级条目与本次出 S 抽数，不展示当前垫抽。</p></div>
        <p v-if="!entries.length" class="empty">该卡池暂无已出 S 明细。</p>
        <ol v-else class="pull-list">
          <li v-for="(entry, index) in entries" :key="`${selected}-${entry.item_id}-${index}`" class="pull-row t-item" :style="{ '--i': Math.min(index, 11) }">
            <div class="reward-icon"><img v-if="icon(entry)" :src="icon(entry)" :alt="entry.name || entry.item_id" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed(entry)" /><span v-else aria-hidden="true">{{ String(entry.name || entry.item_id || '?').slice(0, 2) }}</span><small>S</small></div>
            <div class="pull-content">
              <div class="pull-caption"><strong>{{ entry.name || entry.item_id || '未知条目' }}</strong><time>{{ obtained(entry.obtained_at) }}</time></div>
              <div class="bar-track" :aria-label="known(entry.pity) ? `本次出 S：${entry.pity} 抽` : '本次抽数未提供'"><div class="pull-bar" :class="tone(entry)" :style="barStyle(entry)" /><div class="bar-values"><template v-if="known(entry.pity)"><strong>{{ entry.pity }}</strong><span>抽</span></template><span v-else>本次抽数未提供</span><span v-if="rating(entry)" class="rating" :class="tone(entry)" title="塔吉多社区评价">{{ rating(entry) }}</span></div></div>
            </div>
          </li>
        </ol>
        <footer v-if="entries.length" class="bar-legend"><span><i class="short" />欧 / 超欧</span><span><i class="medium" />普通 / 非</span><span><i class="long" />超非</span><span v-if="scale">本池标尺 {{ scale }} 抽</span><p>评价与配色沿用塔吉多；横条表示这次出 S 的抽数，不表示当前垫抽。未提供评价时显示灰色，未提供标尺时不绘制比例。</p></footer>
      </section>
    </template>
  </section>
</template>

<style scoped>
.community-stats { --mint:#04c8a3; --bar-green:#04c8a3; --bar-yellow:#edbc49; --bar-red:#e55961; min-width:0; color:var(--text); }
.stats-header { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:26px 28px; border:1px solid var(--border); border-bottom:0; border-radius:14px 14px 0 0; background:linear-gradient(110deg,#04c8a314,transparent 65%),var(--surface,var(--bg)); }
.eyebrow { color:var(--mint); font-size:10px; letter-spacing:.2em; margin-bottom:8px; }.stats-header h2 { display:flex;align-items:center;gap:14px;font-size:23px;letter-spacing:.02em; }.stats-header h2 span { font-size:11px; font-weight:600; padding:5px 9px; background:var(--mint); color:#062e28; border-radius:3px; }
.read-time { display:grid;gap:5px;text-align:right;color:var(--text-muted);font-size:11px; }.read-time time { color:var(--text);font-variant-numeric:tabular-nums; }.stale { color:#e9bb68; }
.pool-overview { display:grid; grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:0 28px 26px;border:1px solid var(--border);border-top:0;border-radius:0 0 14px 14px; }
.pool-stat { background:#ffffff06;border:1px solid var(--border);border-radius:11px;padding:22px 24px; }.pool-stat.active { border-color:#04c8a34a; background:linear-gradient(150deg,#04c8a30c,#ffffff06); }.pool-stat h3 { font-size:14px;font-weight:500;color:var(--text-muted); }.draw-total { display:flex;align-items:baseline;gap:8px;margin:13px 0 20px; }.draw-total strong { font-size:clamp(30px,4vw,46px);line-height:1;font-weight:650;letter-spacing:-.035em;font-variant-numeric:tabular-nums; }.draw-total>span { font-size:13px;color:var(--text-muted); }
.pool-stat dl { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;border-top:1px solid var(--border);padding-top:16px; }.pool-stat dd { margin:0;font-size:21px;font-variant-numeric:tabular-nums; }.pool-stat dt { margin-top:5px;color:var(--text-muted);font-size:11px; }
.source-note { text-align:center;color:var(--text-muted);font-size:12px;padding:17px 10px;line-height:1.6; }
.history-panel { border:1px solid var(--border);border-radius:14px;background:#ffffff02;padding:0 28px 24px; }.pool-tabs { display:flex;gap:30px;border-bottom:1px solid var(--border);overflow-x:auto; }.pool-tabs button { position:relative;border:0;background:none;color:var(--text-muted);font:inherit;font-size:15px;white-space:nowrap;cursor:pointer;padding:22px 0 20px; }.pool-tabs button[aria-pressed=true] { color:var(--text);font-weight:600; }.pool-tabs :deep(.t-glide) { background:var(--mint);height:3px !important; }.pool-tabs button:focus-visible { outline:2px solid var(--mint);outline-offset:-3px; }
.history-heading { display:flex;align-items:center;justify-content:space-between;gap:15px;margin:21px 0 24px; }.history-heading h3 { font-size:13px;white-space:nowrap; }.history-heading h3 span { color:var(--text-muted);font-weight:400;margin-left:8px;font-size:11px; }.history-heading p { font-size:11px;line-height:1.7;color:var(--text-muted); }
.pull-list { list-style:none;padding:0;margin:0;display:grid;gap:22px; }.pull-row { display:flex;align-items:center;gap:15px;min-width:0; }.reward-icon { width:58px;height:64px;flex-shrink:0;border-radius:8px;position:relative;background:linear-gradient(140deg,#d8bb8429,#ffffff04);border:1px solid #d8bb8438;display:grid;place-items:center;overflow:hidden; }.reward-icon img { width:100%;height:100%;object-fit:cover; }.reward-icon>span { font-size:13px;color:var(--accent); }.reward-icon small { position:absolute;bottom:0;right:0;background:#d8bb84;color:#182028;font-size:9px;font-weight:700;padding:1px 5px;border-radius:4px 0 0 0; }
.pull-content { flex:1;min-width:0; }.pull-caption { display:flex;justify-content:space-between;align-items:baseline;gap:12px;margin-bottom:8px; }.pull-caption strong { font-size:12px;font-weight:500;overflow-wrap:anywhere; }.pull-caption time { font-size:10px;white-space:nowrap;color:var(--text-muted);font-variant-numeric:tabular-nums; }
.bar-track { position:relative;height:38px;min-width:0;background:#ffffff03;border-radius:5px; }.pull-bar { position:absolute;inset:0 auto 0 0;height:100%;max-width:100%;border-radius:5px;box-sizing:border-box;transition:width var(--duration-slow) var(--ease-smooth-out);background-image:repeating-linear-gradient(110deg,transparent 0,transparent 22px,#ffffff15 22px,#ffffff15 40px); }.bar-values { position:relative;display:flex;align-items:center;gap:6px;height:100%;padding:0 12px;color:var(--text);text-shadow:0 1px 3px #0009; }.bar-values .rating { margin-left:8px;padding:3px 6px;border-radius:3px;background:#101820e8;color:var(--text);font-size:11px;text-shadow:none; }.rating.short { color:#3aebc0; }.rating.long { color:#ff7c86; }.rating.medium { color:#f5d46e; }.luck-title { display:inline-flex;align-items:center;gap:14px;padding:8px 14px;margin-top:16px;border-radius:4px;color:#17201f; }.luck-title small { font-size:10px; }.luck-title strong { font-size:17px; }.bar-values strong { font-size:23px;font-weight:750;line-height:1;font-variant-numeric:tabular-nums; }.bar-values>span { font-size:12px;white-space:nowrap; }.short { background-color:var(--bar-green); }.medium { background-color:var(--bar-yellow); }.long { background-color:var(--bar-red); }.unknown { color:var(--text-muted);background-color:#ffffff06;background-image:none; }
.bar-legend { display:flex;flex-wrap:wrap;align-items:center;gap:14px;font-size:10px;color:var(--text-muted);margin-top:26px;border-top:1px solid var(--border);padding-top:17px; }.bar-legend>span { display:flex;align-items:center;gap:5px; }.bar-legend i { width:7px;height:7px;border-radius:2px; }.bar-legend p { flex-basis:100%;line-height:1.7; }.empty { padding:28px;color:var(--text-muted);font-size:13px;line-height:1.7; }
@media(max-width:650px) { .stats-header { padding:20px 15px;align-items:flex-start;flex-direction:column;gap:14px; }.stats-header h2 { font-size:20px; }.read-time { text-align:left;display:flex;flex-wrap:wrap;gap:8px; }.pool-overview { padding:0 12px 16px;gap:7px; }.pool-stat { padding:15px 10px; }.pool-stat h3 { font-size:12px; }.draw-total { gap:4px;margin:14px 0; }.draw-total strong { font-size:30px; }.pool-stat dl { gap:5px;padding-top:12px; }.pool-stat dd { font-size:17px; }.pool-stat dt { font-size:9px;line-height:1.5; }.history-panel { padding:0 14px 18px; }.pool-tabs { gap:23px; }.pool-tabs button { font-size:14px;padding:19px 0; }.history-heading { display:grid;gap:9px;margin:18px 0; }.reward-icon { width:46px;height:55px; }.pull-row { gap:10px; }.pull-caption { align-items:flex-start;gap:5px;flex-direction:column; }.pull-caption time { font-size:9px; }.pull-list { gap:20px; }.bar-track { height:34px; }/* The duplicated block this replaces left the title dark on narrow screens even for the unknown tone; kept as-is. */.luck-title { color:#17201f; }.bar-values strong { font-size:21px; } }
</style>
