<script setup>
import { fetchedLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

// 残象探寻汇总：已收录总数 + 按级计数（{"轻波级": n, ...}，按实测顺序渲染）
const detections = computed(() => payload.value?.detections ?? null)
const detectionText = computed(() => {
  const d = detections.value
  if (!d || d.total == null) return null
  const parts = Object.entries(d.by_level || {}).map(([k, v]) => `${k} ${v}`)
  return parts.length > 0 ? `（${parts.join(' / ')}）` : null
})

// 国家分组（实测 4 组）：组名 + countryProgress% 进度条 + 组内地区小字
const groups = computed(() => {
  const list = payload.value?.country_groups
  return (Array.isArray(list) ? list : []).map((g) => {
    const progress = g.progress ?? null
    const areas = Array.isArray(g.areas) ? g.areas : []
    const areaText = areas
      .map((a) => `${a.name || '-'} ${a.progress == null ? '-' : `${a.progress}%`}`)
      .join(' · ')
    return {
      name: g.name || '-',
      progress,
      pctText: progress == null ? '-' : `${progress}%`,
      barWidth: progress == null ? 0 : Math.min(100, progress),
      areaText,
    }
  })
})

const hasData = computed(() =>
  groups.value.length > 0 || (detections.value && detections.value.total != null))

const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      探索度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="!hasData" class="empty">暂无数据</p>
    <template v-else>
      <p v-if="detections?.total != null" class="detection">
        残象已收录 {{ detections.total }} 只 {{ detectionText }}
      </p>

      <ul v-if="groups.length > 0" class="group-list">
        <li v-for="(g, i) in groups" :key="i" class="group-item">
          <div class="group-head">
            <span class="group-name">{{ g.name }}</span>
            <span class="group-progress">{{ g.pctText }}</span>
          </div>
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: g.barWidth + '%' }"></div>
          </div>
          <p v-if="g.areaText" class="area-items">{{ g.areaText }}</p>
        </li>
      </ul>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.detection {
  font-size: 13px;
  color: var(--text-muted);
}

.group-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  justify-content: space-between;
  margin-bottom: 4px;
  font-size: 13px;
}

.group-name {
  font-weight: 500;
}

.group-progress {
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.progress-bar {
  height: 6px;
  border-radius: 999px;
  background: var(--border);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--accent);
  transition: width 0.3s ease;
}

.area-items {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
}
</style>
