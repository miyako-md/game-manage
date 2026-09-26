<script setup>
import { computed } from 'vue'
import { fieldLabels, value, sourceDateTime } from '../wuwa-display.js'
const props = defineProps({
  data: { default: null },
  exclude: { type: Array, default: () => [] },
  // A handful of labelled scalars ({ count, total }) reads as one line of pairs.
  inline: { type: Boolean, default: false },
})
const HIDDEN = /(?:icon|pic|image|_url|^sort$|^provenance$)/
const isScalar = (v) => v == null || typeof v !== 'object'
const visible = (obj) => Object.entries(obj).filter(([k]) => !HIDDEN.test(k))
// Source date-times show as Beijing wall time, like every other timestamp here.
const shown = (v) => sourceDateTime(v) ?? value(v)
function small(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return false
  const rows = visible(v)
  return (
    rows.length > 0 &&
    rows.length <= 4 &&
    rows.every(([k, item]) => fieldLabels[k] && isScalar(item))
  )
}
const smallList = (v) =>
  Array.isArray(v) && v.length > 0 && v.every((e) => isScalar(e) || small(e))
const entries = computed(() =>
  props.data && typeof props.data === 'object' && !Array.isArray(props.data)
    ? visible(props.data).filter(([k]) => !props.exclude.includes(k))
    : [],
)
const known = computed(() => entries.value.filter(([k]) => fieldLabels[k]))
const flat = computed(() => known.value.filter(([, v]) => isScalar(v)))
const nested = computed(() => known.value.filter(([, v]) => !isScalar(v)))
const other = computed(() => entries.value.filter(([k]) => !fieldLabels[k]))
</script>
<template>
  <span v-if="data == null">未知</span>
  <div
    v-else-if="Array.isArray(data)"
    class="wuwa-fields-list"
    :class="{ 'is-scalars': data.length && data.every(isScalar) }"
  >
    <p v-if="!data.length" class="wuwa-muted">暂无条目</p>
    <WuwaFields
      v-for="(entry, i) in data"
      :key="i"
      :data="entry"
      :inline="small(entry)"
    />
  </div>
  <span v-else-if="typeof data !== 'object'">{{ shown(data) }}</span>
  <span v-else-if="inline" class="wuwa-inline"
    ><span v-for="[key, item] in flat" :key="key"
      ><span class="k">{{ fieldLabels[key] }}</span> <b>{{ shown(item) }}</b></span
    ></span
  >
  <div v-else class="wuwa-fields">
    <dl v-if="flat.length" class="wuwa-kv">
      <div v-for="[key, item] in flat" :key="key">
        <dt>{{ fieldLabels[key] }}</dt>
        <dd>{{ shown(item) }}</dd>
      </div>
    </dl>
    <div
      v-for="[key, item] in nested"
      :key="key"
      class="wuwa-field-group"
      :class="{ 'is-inline': small(item) || smallList(item) }"
    >
      <span class="wuwa-field-label">{{ fieldLabels[key] }}</span
      ><WuwaFields :data="item" :inline="small(item)" />
    </div>
    <details v-if="other.length" class="wuwa-supplement">
      <summary>来源补充字段（{{ other.length }}）</summary>
      <div class="wuwa-other">
        <div
          v-for="[key, item] in other"
          :key="key"
          class="wuwa-field"
          :class="{ 'is-wide': !isScalar(item) }"
        >
          <span class="wuwa-field-key">{{ key }}</span
          ><WuwaFields :data="item" :inline="small(item)" />
        </div>
      </div>
    </details>
  </div>
</template>
