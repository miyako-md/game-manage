<script setup>
defineProps({
  title: { type: String, required: true },
  en: { type: String, default: '' },
  index: { type: [String, Number], default: '' },
  meta: { type: String, default: '' },
})
const padIndex = v => (v === '' || v == null ? '' : String(v).padStart(2, '0'))
</script>
<template>
  <div class="ao-section-head ov-section-head" :class="{ 'has-meta': !!meta }">
    <span class="ao-head-line left" aria-hidden="true"></span>
    <h2 class="ao-section-title ov-section-title">
      <span v-if="padIndex(index)" class="ov-ef-num">{{ padIndex(index) }} /</span>
      <span class="ao-diamond" aria-hidden="true">◇</span>
      <span class="ov-title-text">{{ title }}</span>
      <span v-if="meta" class="ov-title-meta-inline">· {{ meta }}</span>
      <span class="ao-diamond" aria-hidden="true">◇</span>
      <span v-if="en" class="ov-ef-en">{{ en }}</span>
    </h2>
    <span v-if="meta" class="ov-head-meta">{{ meta }}</span>
    <span class="ao-head-line right" aria-hidden="true"></span>
  </div>
</template>
