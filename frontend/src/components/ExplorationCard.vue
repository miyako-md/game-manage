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

const payload = computed(() => props.snap?.payload ?? null)

const areas = computed(() => {
  const list = payload.value?.areas
  return Array.isArray(list) ? list : []
})

// countryProgress 可能是 "85" 或 "85%"，统一带 % 展示
const countryText = computed(() => {
  const v = payload.value?.country_progress
  if (v == null || v === '') return null
  const s = String(v)
  return s.endsWith('%') ? s : `${s}%`
})

const detectionCount = computed(() => payload.value?.detection_count ?? 0)

function pctText(v) {
  return v == null ? null : `${v}%`
}

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      探索度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div v-if="countryText" class="country-row">
        <span class="country-label">全地区探索</span>
        <span class="country-value">{{ countryText }}</span>
      </div>

      <ul v-if="areas.length > 0" class="area-list">
        <li v-for="(a, i) in areas" :key="i" class="area-item">
          <div class="area-head">
            <span class="area-name">{{ a.name || '-' }}</span>
            <span class="area-progress">{{ pctText(a.progress) ?? '-' }}</span>
          </div>
          <p v-if="a.items && a.items.length > 0" class="area-items">
            {{ a.items.join(' · ') }}
          </p>
        </li>
      </ul>
      <p v-else-if="!countryText" class="empty">暂无数据</p>

      <p v-if="detectionCount > 0" class="detection">
        残象已收录 {{ detectionCount }} 只
      </p>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.country-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: space-between;
}

.country-label {
  font-size: 13px;
  color: var(--text-muted);
}

.country-value {
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
}

.area-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.area-item {
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
}

.area-item:last-child {
  border-bottom: none;
}

.area-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: space-between;
  font-size: 13px;
}

.area-name {
  font-weight: 500;
}

.area-progress {
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.area-items {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.detection {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
