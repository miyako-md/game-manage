<script setup>
import { fetchedLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

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
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <dl v-else class="kv-grid dock-grid">
      <div v-for="r in rows" :key="r.label">
        <dt>{{ r.label }}</dt>
        <dd>{{ r.value ?? '—' }}</dd>
      </div>
    </dl>
  </div>
</template>

<style scoped>
.dock-grid {
  --kv-min: 84px;
  grid-template-columns: repeat(auto-fit, minmax(var(--kv-min), 1fr));
}
</style>
