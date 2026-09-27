<script setup>
import { ref } from 'vue'
import WuwaRoleDialog from './WuwaRoleDialog.vue'
import WuwaStatus from './WuwaStatus.vue'
import SummaryMetrics from './SummaryMetrics.vue'
defineProps({ title: { type: String, required: true }, description: { type: String, default: '' }, metrics: { type: Array, default: () => [] }, snap: { default: null }, buttonLabel: { type: String, default: '' }, inline: Boolean })
const opened = ref(false)
</script>
<template>
  <section class="wuwa-panel wuwa-module-card">
    <header class="cap-title wuwa-module-heading"><h2>{{ title }}</h2><button v-if="!inline" type="button" class="ui-button small-button" @click="opened = true">{{ buttonLabel || `查看${title}` }}</button></header>
    <p v-if="description" class="wuwa-muted">{{ description }}</p>
    <SummaryMetrics v-if="metrics.length" :metrics="metrics" />
    <div v-if="inline" class="inline-content"><slot /></div>
    <slot name="preview" />
    <WuwaStatus v-if="snap" :snap="snap" />
    <WuwaRoleDialog v-if="!inline && opened" :title="title" @close="opened = false"><slot /></WuwaRoleDialog>
  </section>
</template>
<style scoped>
.wuwa-module-card { min-width: 0; }
.wuwa-module-card > .wuwa-muted { margin-top: 12px; }
.wuwa-module-card .cap-title { margin-bottom: 0; }
.wuwa-module-card > .wuwa-status { margin-top: 12px; }
.inline-content :deep(.cap-card){padding:0;border:0;background:none;box-shadow:none;margin-top:16px}
.inline-content :deep(.cap-title),.inline-content :deep(.fetched-at){display:none}
</style>
