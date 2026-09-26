<script setup>
import { fetchedLabel } from '../time.js'
import { vPop } from '../motion.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

const expectedFullAt = computed(() => fetchedLabel(payload.value?.expected_full_at))
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
const pct = computed(() => {
  const { current, maximum } = payload.value || {}
  return typeof current === 'number' && typeof maximum === 'number' && maximum > 0
    ? Math.max(0, Math.min(100, (current / maximum) * 100))
    : null
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      体力
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div class="stamina-line">
        <span class="stamina-big" v-pop>
          {{ payload.current ?? '-' }}<span class="sep">/</span>{{ payload.maximum ?? '-' }}
        </span>
        <span v-if="expectedFullAt" class="stamina-eta">
          预计 {{ expectedFullAt }} 恢复满
        </span>
      </div>
      <span v-if="pct != null" class="meter stamina-meter"><i :style="{ '--pct': pct + '%' }"></i></span>
    </template>
  </div>
</template>

<style scoped>
.stamina-line {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 2px 12px;
}

.stamina-big {
  display: inline-block;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -.02em;
  line-height: 32px;
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.sep {
  margin: 0 3px;
  color: var(--text-faint);
  font-weight: 400;
}

.stamina-eta {
  font-size: 12px;
  color: var(--text-muted);
}

.stamina-meter {
  margin-top: 8px;
  --series: var(--game-wuwa);
}
</style>
