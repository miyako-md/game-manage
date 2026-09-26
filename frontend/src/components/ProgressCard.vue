<script setup>
import { fetchedLabel, resetLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => {
    const total = it.total ?? 0
    const hasTotal = total > 0
    const pct = hasTotal
      ? Math.min(100, Math.round(((it.cur ?? 0) / total) * 100))
      : 100
    return {
      ...it,
      hasTotal,
      pct,
      curText: hasTotal ? `${it.cur ?? 0}/${total}` : `${it.cur ?? 0}`,
      pctText: hasTotal ? `${pct}%` : null,
      refresh: resetLabel(it.refresh_at),
    }
  })
})

const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
// Sibling bars in one card cycle through the chart series so neighbours never share a hue.
// total=0 (e.g. 终焉矩阵 with no record yet): the bar stays full but in the track grey.
const series = (it, n) => (it.hasTotal ? `var(--chart-${n % 6 + 1})` : 'var(--track)')
</script>

<template>
  <div class="cap-card wuwa-cq">
    <div class="cap-title">
      周期进度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="bar-list wuwa-bars with-note">
      <li v-for="(it, i) in rows" :key="i" class="bar-row has-note">
        <span class="k" :title="it.name || undefined">{{ it.name || '-' }}</span>
        <span class="meter"><i :style="{ '--pct': it.pct + '%', '--series': series(it, i) }"></i></span>
        <span class="v">{{ it.curText }}<small v-if="it.pctText"> {{ it.pctText }}</small></span>
        <span class="note">{{ it.refresh || '' }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.bar-row > .v small {
  display: inline-block;
  min-width: 3.4em;
  text-align: right;
}
</style>
