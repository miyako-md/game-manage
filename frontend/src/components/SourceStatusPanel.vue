<script setup>
import { computed } from 'vue'
import { capabilityLabel, describeSource } from '../source-status.js'
import { displayBeijing } from '../time.js'
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
</script>
<template>
  <details class="source-panel" :open="faults > 0">
    <summary><span>采集状态 <small>{{ rows.length }} 项能力</small></span><span :class="{ warning: faults > 0 }">{{ summary }}</span></summary>
    <div class="source-table" role="region" aria-label="各项能力采集状态">
      <div v-for="row in rows" :key="row.capability" class="source-row">
        <div class="source-kind"><strong>{{ row.name }}</strong><span class="source-badge" :class="row.tone">{{ row.label }}</span><small v-if="row.retained">保留旧数据</small></div>
        <div class="source-times"><p>最后成功 <time>{{ row.last_success_at ? displayBeijing(row.last_success_at) : '暂无成功记录' }}</time></p><p>最后尝试 <time>{{ row.last_attempt_at ? displayBeijing(row.last_attempt_at) : '尚未尝试' }}</time></p></div>
        <div class="source-error"><span v-if="row.consecutive_failures > 0">连续失败 {{ row.consecutive_failures }} 次</span><p v-if="row.error">{{ row.error }}</p><p v-else-if="row.state === 'ok'">最近采集成功</p></div>
      </div>
    </div>
    <p class="source-note">北京时间 · 状态来自后台采集记录，页面读取快照不会重置成功时间。</p>
  </details>
</template>
<style scoped>
.source-panel { border:1px solid var(--border); border-radius:8px; background:#151f29; margin-bottom:22px; }
summary { display:flex; gap:12px; align-items:center; justify-content:space-between; padding:12px 15px; cursor:pointer; color:var(--text-muted); font-size:11px; }
summary>span:first-child { color:var(--text); }summary small { font-size:10px; color:var(--text-muted); margin-left:8px; }summary:after { content:'⌄'; color:var(--accent); }summary>span:nth-child(2) { margin-left:auto; }summary .warning { color:var(--stale-text); }
.source-table { border-top:1px solid var(--border); padding:0 15px; }.source-row { display:grid; grid-template-columns:1fr 1.35fr 1.15fr; gap:18px; padding:14px 0; border-bottom:1px solid var(--border); font-size:11px; }.source-row:last-child { border:0; }.source-kind strong { font-size:12px; font-weight:500; margin-right:8px; }.source-kind>small { display:block; margin-top:5px; color:var(--stale-text); font-size:10px; }.source-badge { font-size:10px; }.source-badge.good { color:var(--success); }.source-badge.danger,.source-error>span { color:var(--danger); }.source-badge.muted { color:var(--text-muted); }.source-times { color:var(--text-muted); line-height:1.9; font-size:10px; }.source-times time { margin-left:7px; color:var(--text); }.source-error { overflow-wrap:anywhere; font-size:10px; color:var(--text-muted); line-height:1.8; }.source-note { border-top:1px solid var(--border); padding:10px 15px; color:var(--text-muted); font-size:10px; }
@media(max-width:850px) { .source-row { grid-template-columns:1fr 1.5fr; gap:8px 13px; }.source-error { grid-column:1/-1; } }
@media(max-width:500px) { .source-row { grid-template-columns:1fr; gap:8px; }.source-times { font-size:10px; }summary { flex-wrap:wrap; } }
</style>
