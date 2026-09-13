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
const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))

const pct = (v) => (v == null ? '-' : `${v}%`)
const avg = (v) => (v == null ? '-' : String(v))

const topChampions = computed(() => {
  const list = payload.value?.top_champions ?? []
  return list.map((c) => ({
    ...c,
    winrate: c.games > 0 ? Math.round((c.wins / c.games) * 100) : null,
  }))
})

const records = computed(() => payload.value?.records ?? [])
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      生涯统计
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div class="overview">
        <div class="metric">
          <span class="metric-value">{{ payload.total_games }}</span>
          <span class="metric-label">近20场</span>
        </div>
        <div class="metric">
          <span class="metric-value">{{ pct(payload.winrate) }}</span>
          <span class="metric-label">胜率（{{ payload.wins }}胜）</span>
        </div>
        <div class="metric">
          <span class="metric-value">
            {{ avg(payload.avg_kills) }}/{{ avg(payload.avg_deaths) }}/{{ avg(payload.avg_assists) }}
          </span>
          <span class="metric-label">平均 KDA</span>
        </div>
      </div>

      <div v-if="topChampions.length > 0" class="block">
        <p class="block-title">常用英雄</p>
        <ul class="champ-list">
          <li v-for="c in topChampions" :key="c.champion_id" class="champ-row">
            <span class="champ-name">{{ c.champion_name || `英雄 #${c.champion_id}` }}</span>
            <span class="champ-stat">{{ c.games }}场 {{ c.winrate == null ? '-' : `${c.winrate}%` }}</span>
          </li>
        </ul>
      </div>

      <div v-if="records.length > 0" class="block">
        <p class="block-title">名场面</p>
        <ul class="record-list">
          <li v-for="r in records" :key="r.label" class="record-row">
            <span class="record-label">{{ r.label }}</span>
            <span class="record-value">{{ r.value }}</span>
          </li>
        </ul>
      </div>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  gap: 10px;
  margin-bottom: 10px;
}

.metric {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  background: var(--bg);
  border-radius: 8px;
  padding: 8px 4px;
}

.metric-value {
  font-size: 18px;
  font-weight: 600;
}

.metric-label {
  font-size: 11px;
  color: var(--text-muted);
}

.block {
  margin-top: 8px;
}

.block-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.champ-row,
.record-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 3px 0;
  font-size: 13px;
}

.record-value {
  font-weight: 600;
}
</style>
