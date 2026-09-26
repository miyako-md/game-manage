<script setup>
import { fetchedLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)
// Sibling bars in one card cycle through the chart series so neighbours never share a hue.
const series = (n) => `var(--chart-${n % 6 + 1})`

// 残象探寻汇总：已收录总数 + 按级计数（{"轻波级": n, ...}，按实测顺序渲染）
const detections = computed(() => payload.value?.detections ?? null)
const levels = computed(() =>
  Object.entries(detections.value?.by_level || {}).map(([name, count], i) => ({
    name,
    count,
    size: typeof count === 'number' && count > 0 ? count : 0,
    series: series(i),
  })),
)
const hasSplit = computed(() => levels.value.some((l) => l.size > 0))

const groups = computed(() => {
  const list = payload.value?.country_groups
  return (Array.isArray(list) ? list : []).map((g) => {
    const progress = g.progress ?? null
    const areas = Array.isArray(g.areas) ? g.areas : []
    return {
      name: g.name || '-',
      pctText: progress == null ? '-' : `${progress}%`,
      barWidth: progress == null ? 0 : Math.min(100, progress),
      areas: areas.map((a) => ({
        name: a.name || '-',
        pctText: a.progress == null ? '-' : `${a.progress}%`,
      })),
    }
  })
})

const hasData = computed(() =>
  groups.value.length > 0 || (detections.value && detections.value.total != null))

const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card wuwa-cq">
    <div class="cap-title">
      探索度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="!hasData" class="empty">暂无数据</p>
    <template v-else>
      <ul v-if="groups.length > 0" class="bar-list wuwa-bars region-list">
        <li v-for="(g, i) in groups" :key="i" class="region">
          <div class="bar-row">
            <span class="k">{{ g.name }}</span>
            <span class="meter"><i :style="{ '--pct': g.barWidth + '%', '--series': series(i) }"></i></span>
            <span class="v">{{ g.pctText }}</span>
          </div>
          <ul v-if="g.areas.length" class="chip-list">
            <li v-for="(a, j) in g.areas" :key="j" class="chip">{{ a.name }} <b>{{ a.pctText }}</b></li>
          </ul>
        </li>
      </ul>

      <div v-if="detections?.total != null" class="detection">
        <p class="detection-head">
          <span class="detection-label">残象已收录</span>
          <b>{{ detections.total }}</b>
          <span class="detection-unit">只</span>
        </p>
        <template v-if="hasSplit">
          <div class="stack-bar" aria-hidden="true">
            <i v-for="l in levels" v-show="l.size" :key="l.name" :style="{ flex: l.size, '--series': l.series }"></i>
          </div>
          <ul class="legend">
            <li v-for="l in levels" :key="l.name" :style="{ '--series': l.series }">{{ l.name }} <b>{{ l.count }}</b></li>
          </ul>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.region-list {
  --bar-label: 20%;
  row-gap: 6px;
}

.region {
  display: grid;
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
}

.region > .bar-row {
  grid-column: 1 / -1;
  grid-template-columns: subgrid;
}

.region > .chip-list {
  grid-column: 1 / -1;
  margin-bottom: 2px;
}

.detection {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

.detection-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.detection-head b {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
  font-variant-numeric: tabular-nums;
}
</style>
