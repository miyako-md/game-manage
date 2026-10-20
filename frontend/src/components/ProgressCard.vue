<script setup>
import { displayBeijing, resetLabel } from '../time.js'
import { computed } from 'vue'
import { share } from '../chart-math.js'
import RingGauge from './RingGauge.vue'

const props = defineProps({
  snap: { type: Object, default: null },
  imageMode: Boolean,
})

function toLocal(value) {
  if (!value) return null
  return displayBeijing(value)
}

const shown = v => (v == null || v === '' || (typeof v === 'number' && !Number.isFinite(v)) ? '未知' : v)
// A ring only where the source states a cap; the others stay plain values.
const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map(it => {
    const total = it.total > 0 ? it.total : null
    const ratio = total == null ? null : share(it.cur, total)
    return { label: it.name || '未命名项目', cur: it.cur, total, percent: ratio == null ? '—' : `${Math.round(ratio * 100)}%`, note: resetLabel(it.refresh_at) }
  })
})

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      周期进度
      <span v-if="snap?.stale && !imageMode" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="progress-grid">
      <li v-for="(row, i) in rows" :key="i" class="progress-item">
        <RingGauge v-if="row.total" :value="row.cur" :max="row.total" :label="row.label" :size="54" :stroke="6" color="var(--game-vivid, var(--accent))">
          <span class="ring-pct">{{ row.percent }}</span>
        </RingGauge>
        <div class="progress-copy">
          <span class="progress-label">{{ row.label }}</span>
          <strong>{{ shown(row.cur) }}<small v-if="row.total"> / {{ row.total }}</small></strong>
          <span v-if="row.note" class="progress-note">{{ row.note }}</span>
        </div>
      </li>
    </ul>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.cap-title {
  font-size: 16px;
  line-height: 24px;
}

.progress-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 232px), 1fr));
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.progress-item {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: var(--radius-tile);
  background: var(--surface-soft);
  box-shadow: inset 0 0 0 1px var(--overlay-2);
}

.ring-pct {
  color: var(--text);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: -0.01em;
}

.progress-copy {
  display: grid;
  flex: 1;
  min-width: 0;
}

.progress-label {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 12px;
  line-height: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-copy strong {
  color: var(--text);
  font-size: 20px;
  line-height: 26px;
  font-weight: 550;
  letter-spacing: -0.03em;
  font-variant-numeric: tabular-nums;
}

.progress-copy small {
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0;
}

.progress-note {
  color: var(--text-faint);
  font-size: 12px;
  line-height: 18px;
}

.fetched-at {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
