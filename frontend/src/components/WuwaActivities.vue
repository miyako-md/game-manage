<script setup>
import { computed } from 'vue'
import WuwaFields from './WuwaFields.vue'
import WuwaStatus from './WuwaStatus.vue'
import WuwaModuleCard from './WuwaModuleCard.vue'
const props = defineProps({ snap: { default: null } })
const sections = computed(() =>
  Object.entries(props.snap?.payload?.sections || {}).sort(
    (a, b) => (a[1]?.sort ?? 999) - (b[1]?.sort ?? 999),
  ),
)
</script>
<template>
  <section class="wuwa-panel">
    <p class="wuwa-kicker">ACTIVITIES</p>
    <h2>玩法进度</h2>
    <p class="wuwa-muted">按当前来源返回的玩法展示，名称与内容随版本变化。</p>
    <div class="wuwa-grid">
      <WuwaModuleCard v-for="[key, section] in sections" :key="key" class="activity-card" :title="section.title || '未命名玩法'" button-label="查看详情">
        <WuwaFields :data="section" :exclude="['title']" />
        <WuwaStatus :snap="snap" />
      </WuwaModuleCard>
    </div>
    <p v-if="!sections.length" class="wuwa-muted">尚未获得玩法数据</p>
    <WuwaStatus :snap="snap" />
  </section>
</template>
<style scoped>
.activity-card :deep(.wuwa-heading) { flex-direction: column; align-items: flex-start; gap: 16px; }
.activity-card :deep(.wuwa-heading h2) { margin: 0; line-height: 1.5; }
</style>
