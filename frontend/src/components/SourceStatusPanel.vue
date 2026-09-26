<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { capabilityLabel, describeSource } from '../source-status.js'
import { displayBeijing } from '../time.js'
import AppIcon from './AppIcon.vue'
const props = defineProps({ game: { type: Object, required: true }, collection: { type: Array, default: () => [] } })
const rows = computed(() => props.game.capabilities.map(cap => {
  const row = props.collection.find(row => row.game_id === props.game.game_id && row.capability === cap)
  return { ...describeSource(row), capability: cap, name: capabilityLabel(cap, props.game.game_id) }
}))
const faults = computed(() => rows.value.filter(row => row.tone === 'danger').length)
const summary = computed(() => {
  if (faults.value) return `${faults.value} 项需要关注`
  const offline = rows.value.filter(row => row.state === 'offline')
  if (offline.length) return offline.some(row => row.retained) ? '客户端离线 · 保留旧数据' : '客户端离线 · 暂无成功快照'
  const pending = rows.value.filter(row => !row.state || row.state === 'never').length
  return pending ? `${pending} 项尚未采集` : '各项状态已更新'
})
const tone = computed(() => faults.value ? 'danger' : summary.value === '各项状态已更新' ? 'good' : 'warn')
// The details open as a popover under the header chip; a click outside or
// Escape closes them, like a menu.
const panel = ref(null)
function dismiss(event) {
  const el = panel.value
  if (!el?.open) return
  if (event.type === 'keydown' ? event.key === 'Escape' : !el.contains(event.target)) {
    el.open = false
    if (event.type === 'keydown') el.querySelector('summary')?.focus()
  }
}
onMounted(() => {
  if (typeof document === 'undefined' || !panel.value?.contains) return
  document.addEventListener('pointerdown', dismiss)
  document.addEventListener('keydown', dismiss)
})
onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.removeEventListener('pointerdown', dismiss)
  document.removeEventListener('keydown', dismiss)
})
</script>
<template>
  <details ref="panel" class="source-panel">
    <summary :class="tone"><i class="source-dot" aria-hidden="true"></i><span>采集状态<small>{{ rows.length }} 项能力</small></span><span class="source-summary">{{ summary }}</span><AppIcon class="source-chevron" name="chevron" :size="14" /></summary>
    <div class="source-body">
      <div class="source-table" role="region" aria-label="各项能力采集状态">
        <div v-for="row in rows" :key="row.capability" class="source-row">
          <div class="source-kind"><strong>{{ row.name }}</strong><span class="source-badge" :class="row.tone">{{ row.label }}</span><small v-if="row.retained">保留旧数据</small></div>
          <div class="source-times"><p>最后成功 <time>{{ row.last_success_at ? displayBeijing(row.last_success_at) : '暂无成功记录' }}</time></p><p>最后尝试 <time>{{ row.last_attempt_at ? displayBeijing(row.last_attempt_at) : '尚未尝试' }}</time></p></div>
          <div class="source-error"><span v-if="row.consecutive_failures > 0">连续失败 {{ row.consecutive_failures }} 次</span><p v-if="row.error">{{ row.error }}</p><p v-else-if="row.state === 'ok'">最近采集成功</p></div>
        </div>
      </div>
      <p class="source-note">北京时间 · 状态来自后台采集记录，页面读取快照不会重置成功时间。</p>
    </div>
  </details>
</template>
<style scoped>
.source-panel { position:relative; }
summary { display:flex; align-items:center; gap:8px; min-height:32px; padding:5px 10px; border:1px solid var(--border-strong); border-radius:7px; background:var(--card-bg); box-shadow:var(--btn-shadow); color:var(--text-body); font-size:12px; line-height:18px; cursor:pointer; list-style:none; white-space:nowrap; }
summary::-webkit-details-marker { display:none; }
summary small { margin-left:6px; color:var(--text-faint); font-size:11px; }
.source-summary { color:var(--text-muted); }
.source-dot { width:6px; height:6px; border-radius:50%; background:var(--success); box-shadow:0 0 0 3px color-mix(in srgb, var(--success) 18%, transparent); }
summary.warn .source-dot { background:var(--stale-text); box-shadow:0 0 0 3px color-mix(in srgb, var(--stale-text) 18%, transparent); }
summary.danger { border-color:var(--danger-border); background:var(--danger-bg); }
summary.danger .source-dot { background:var(--danger); box-shadow:0 0 0 3px color-mix(in srgb, var(--danger) 18%, transparent); }
summary.danger .source-summary { color:var(--danger); font-weight:500; }
summary.warn .source-summary { color:var(--stale-text); }
.source-chevron { color:var(--text-faint); transition:transform var(--duration-fast) var(--ease-smooth-out); }
.source-panel[open] .source-chevron { transform:rotate(180deg); }
@media(hover:hover) and (pointer:fine) { summary:hover { background:var(--button-hover-bg); color:var(--text); } summary.danger:hover { background:var(--danger-bg); } }
summary:active { transform:scale(var(--scale-medium)); }
/* Popover under the chip, right-aligned to it. */
.source-body { position:absolute; top:calc(100% + 6px); right:0; z-index:26; width:min(760px, calc(100vw - 32px)); max-height:min(70vh, 560px); overflow:auto; border:1px solid var(--border); border-radius:12px; background:var(--card-bg); box-shadow:var(--popover-shadow); }
.source-panel[open] .source-body { animation:t-rise var(--duration-fast) var(--ease-smooth-out) backwards; }
.source-table { padding:0 14px; }.source-row { display:grid; grid-template-columns:1fr 1.35fr 1.15fr; gap:14px; padding:10px 0; border-bottom:1px solid var(--border); font-size:12px; }.source-row:last-child { border:0; }.source-kind strong { font-size:12px; font-weight:600; margin-right:8px; }.source-kind>small { display:block; margin-top:3px; color:var(--stale-text); font-size:11px; }.source-badge { font-size:11px; }.source-badge.good { color:var(--success); }.source-badge.danger,.source-error>span { color:var(--danger); }.source-badge.muted { color:var(--text-muted); }.source-times { color:var(--text-muted); line-height:1.7; font-size:11px; }.source-times time { margin-left:6px; color:var(--text); }.source-error { overflow-wrap:anywhere; font-size:11px; color:var(--text-muted); line-height:1.7; }.source-note { border-top:1px solid var(--border); padding:8px 14px; color:var(--text-faint); font-size:11px; }
@media(max-width:850px) { .source-row { grid-template-columns:1fr 1.5fr; gap:6px 12px; }.source-error { grid-column:1/-1; } }
@media(max-width:600px) { summary small,summary:not(.danger) .source-summary { display:none; }.source-body { position:fixed; top:64px; left:16px; right:16px; width:auto; } }
@media(max-width:500px) { .source-row { grid-template-columns:1fr; gap:6px; } }
</style>
