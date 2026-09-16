<script setup>
import { stamp } from '../wuwa-display.js'
defineProps({ snap: { default: null } })
</script>
<template>
  <p class="wuwa-meta">
    <span v-if="snap?.stale || snap?.state === 'stale'" class="wuwa-warning"
      >旧数据 · </span
    ><span v-if="snap?.fetched_at"
      >来源采集 {{ stamp(snap.fetched_at) }}（北京时间）</span
    ><span v-else>尚无成功采集时间</span>
  </p>
  <p v-if="snap?.error" class="wuwa-error" role="status">{{ snap.error }}</p>
</template>
