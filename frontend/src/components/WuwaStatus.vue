<script setup>
import { stamp } from '../wuwa-display.js'
defineProps({ snap: { default: null } })
</script>
<template>
  <!-- Header meta: sits on a card's title line (margin-left:auto in wuwa.css). -->
  <span class="wuwa-status">
    <span v-if="snap?.stale || snap?.state === 'stale'" class="badge badge-stale"
      >旧数据</span
    ><span v-if="snap?.fetched_at"
      >来源采集 {{ stamp(snap.fetched_at) }}（北京时间）</span
    ><span v-else>尚无成功采集时间</span
    ><span v-if="snap?.error" class="badge badge-danger wuwa-status-error" role="status">{{
      snap.error
    }}</span>
  </span>
</template>
