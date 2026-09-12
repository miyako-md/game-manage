<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

function toLocal(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString()
}

const expectedFullAt = computed(() => toLocal(payload.value?.expected_full_at))
const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      体力
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div class="stamina-big">
        {{ payload.current ?? '-' }}<span class="sep">/</span>{{ payload.maximum ?? '-' }}
      </div>
      <p v-if="expectedFullAt" class="stamina-eta">
        预计 {{ expectedFullAt }} 恢复满
      </p>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.stamina-big {
  font-size: 34px;
  font-weight: 700;
  line-height: 1.2;
  font-variant-numeric: tabular-nums;
}

.sep {
  margin: 0 4px;
  color: var(--text-muted);
}

.stamina-eta {
  margin-top: 4px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
