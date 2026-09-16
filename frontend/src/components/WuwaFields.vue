<script setup>
import { computed } from 'vue'
import { fieldLabels, value } from '../wuwa-display.js'
const props = defineProps({
  data: { default: null },
  exclude: { type: Array, default: () => [] },
})
const entries = computed(() =>
  props.data && typeof props.data === 'object' && !Array.isArray(props.data)
    ? Object.entries(props.data).filter(
        ([k]) =>
          !props.exclude.includes(k) &&
          !/(?:icon|pic|image|_url|^sort$|^provenance$)/.test(k),
      )
    : [],
)
const known = computed(() => entries.value.filter(([k]) => fieldLabels[k]))
const other = computed(() => entries.value.filter(([k]) => !fieldLabels[k]))
</script>
<template>
  <span v-if="data == null">未知</span>
  <div v-else-if="Array.isArray(data)" class="wuwa-stack">
    <p v-if="!data.length" class="wuwa-muted">暂无条目</p>
    <WuwaFields v-for="(entry, i) in data" :key="i" :data="entry" />
  </div>
  <span v-else-if="typeof data !== 'object'">{{ value(data) }}</span>
  <div v-else class="wuwa-fields">
    <div v-for="[key, item] in known" :key="key" class="wuwa-field">
      <span class="wuwa-muted">{{ fieldLabels[key] }}</span
      ><WuwaFields :data="item" />
    </div>
    <details v-if="other.length" class="wuwa-supplement">
      <summary>来源补充字段（{{ other.length }}）</summary>
      <div v-for="[key, item] in other" :key="key" class="wuwa-field">
        <span class="wuwa-muted">{{ key }}</span
        ><WuwaFields :data="item" />
      </div>
    </details>
  </div>
</template>
