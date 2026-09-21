<script setup>
import { fetchedLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

// 简表行：null 显示 "—"；base_catch 自带 "%"，原样展示
const rows = computed(() => {
  const p = payload.value
  return [
    { label: '数据坞等级', value: p?.level ?? null },
    { label: '基础捕获率', value: p?.base_catch ?? null },
    { label: '捕获品质', value: p?.catch_quality ?? null },
    { label: '声骸经验', value: p?.cur_exp ?? null },
    { label: '收集数', value: p?.max_count ?? null },
  ]
})

const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      数据坞
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <ul v-else class="dock-list">
      <li v-for="r in rows" :key="r.label" class="dock-row">
        <span class="dock-label">{{ r.label }}</span>
        <span class="dock-value">{{ r.value ?? '—' }}</span>
      </li>
    </ul>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.dock-list {
  display: flex;
  flex-direction: column;
}

.dock-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.dock-row:last-child {
  border-bottom: none;
}

.dock-label {
  color: var(--text-muted);
}

.dock-value {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}
</style>
