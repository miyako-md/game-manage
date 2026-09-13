<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

function toLocal(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString()
}

// refresh_at 重置提示：负数=已可重置，同日=今日重置，否则 X天后重置
function refreshText(value) {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.ceil((d.getTime() - Date.now()) / 86400000)
  if (days < 0) return '已可重置'
  if (days === 0) return '今日重置'
  return `${days}天后重置`
}

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
      refresh: refreshText(it.refresh_at),
    }
  })
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
    <ul v-else class="progress-list">
      <li v-for="(it, i) in rows" :key="i" class="progress-row">
        <div class="row-head">
          <span class="row-name">{{ it.name || '-' }}</span>
          <span class="row-value">
            {{ it.curText }}<template v-if="it.pctText">（{{ it.pctText }}）</template>
            <span v-if="it.refresh" class="row-refresh">{{ it.refresh }}</span>
          </span>
        </div>
        <div class="progress-bar" :class="{ 'no-total': !it.hasTotal }">
          <div class="progress-fill" :style="{ width: it.pct + '%' }"></div>
        </div>
      </li>
    </ul>

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
