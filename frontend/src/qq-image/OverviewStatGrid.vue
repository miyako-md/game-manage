<script setup>
import { computed } from 'vue'
const props = defineProps({
  stats: { type: Array, default: () => [] },
  columns: { type: Number, default: 6 },
})
const colCount = computed(() => {
  if (props.columns && props.columns > 0) return props.columns
  return Math.min(6, Math.max(1, props.stats.length))
})
</script>
<template>
  <div class="ao-stat-grid ov-stat-grid" :class="`ov-cols-${colCount}`">
    <div
      v-for="(stat, idx) in stats"
      :key="`${stat.label}-${idx}`"
      class="ao-stat-cell"
      :class="{ 'is-accent': stat.accent, [`is-tone-${stat.tone}`]: !!stat.tone }"
    >
      <strong class="ao-stat-val">{{ stat.value }}</strong>
      <span class="ao-stat-lbl">{{ stat.label }}</span>
      <span v-if="stat.sub" class="ov-stat-sub">{{ stat.sub }}</span>
    </div>
  </div>
</template>
