<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { lazyPage } from '../lazy-page.js'
import { subscribeSessionInvalidation } from '../http-client.js'
import AppIcon from './AppIcon.vue'
const props = defineProps({ allowed: { type: Boolean, default: false } })
const SystemUpdateDialog = lazyPage(() => import('./SystemUpdateDialog.vue'))
const opened = ref(false)
watch(() => props.allowed, allowed => { if (!allowed) opened.value = false })
const unsubscribe = subscribeSessionInvalidation(() => { opened.value = false })
onBeforeUnmount(unsubscribe)
</script>
<template>
  <template v-if="allowed">
    <button class="icon-button system-update-trigger" type="button" aria-label="系统更新" title="系统更新" aria-haspopup="dialog" :aria-expanded="opened" @click="opened = true"><AppIcon name="download" :size="16" /></button>
    <SystemUpdateDialog v-if="opened" @close="opened = false" />
  </template>
</template>
<style scoped>
.system-update-trigger { min-width:44px; min-height:44px; }
</style>
