<script setup>
import { stamp } from '../wuwa-display.js'
import { computed } from 'vue'
import { collectionState } from '../snapshot-state.js'
const props = defineProps({ snap: { default: null } })
const failed = computed(()=>collectionState(props.snap)==='failed')
</script>
<template>
  <!-- Header meta: sits on a card's title line (margin-left:auto in wuwa.css). -->
  <span class="wuwa-status">
    <span v-if="snap?.stale || snap?.state === 'stale'" class="badge badge-stale"
      >旧数据</span
    ><span v-if="snap?.fetched_at"
      >来源采集 {{ stamp(snap.fetched_at) }}（北京时间）</span
    ><span v-else>尚无成功采集时间</span
    ><span v-if="failed" class="badge badge-danger wuwa-status-error" role="status">来源读取异常</span>
  </span>
</template>
