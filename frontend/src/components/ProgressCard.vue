<script setup>
import { displayBeijing, resetLabel } from '../time.js'
import { computed } from 'vue'
import SummaryMetrics from './SummaryMetrics.vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

function toLocal(value) {
  if (!value) return null
  return displayBeijing(value)
}

// refresh_at 重置提示：负数=已可重置，同日=今日重置，否则 X天后重置
function refreshText(value) {
  return resetLabel(value)
}

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map(it => ({ label:it.name || '未命名项目',
    ...(it.total > 0 ? {current:it.cur,total:it.total} : {value:it.cur}),
    icon:'calendar',note:refreshText(it.refresh_at),
  }))
})

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      周期进度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <SummaryMetrics v-else rows :metrics="rows" />

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.progress-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 13px;
}

.row-name {
  font-weight: 500;
}

.row-value {
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.row-refresh {
  margin-left: 6px;
  font-size: 12px;
}

.progress-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--border);
  overflow: hidden;
}

/* total=0（如终焉矩阵"暂无挑战记录"）：进度条置满但用灰色弱化 */
.progress-bar.no-total .progress-fill {
  background: var(--border);
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.3s ease;
}
</style>
