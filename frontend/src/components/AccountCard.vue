<script setup>
import { computed } from 'vue'
import { fetchedLabel } from '../time.js'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))

const rankedSolo = computed(() => {
  const rs = payload.value?.extra?.ranked_solo ?? null
  // 空赛季/未打排位时后端会给出 tier 为空串的数据，视同无段位
  return rs && rs.tier ? rs : null
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      账号
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <div v-else class="identity">
      <p class="identity-name">{{ payload.nickname || '未知' }}</p>
      <ul class="chip-list">
        <li class="chip">Lv{{ payload.level ?? '未知' }}</li>
        <li v-if="rankedSolo" class="chip"><b>{{ rankedSolo.tier }}</b>{{ rankedSolo.division ? ' ' + rankedSolo.division : '' }} · {{ rankedSolo.league_points }}LP</li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
/* Name and chips on one line; the card reads as an identity strip. */
.identity {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
}

.identity-name {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  line-height: 22px;
  color: var(--text);
}
</style>
