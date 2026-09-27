<script setup>
import { computed, ref, watch } from 'vue'
import { safeWuwaIcon } from '../wuwa-icons.js'
const props = defineProps({ src: { type: String, default: '' }, name: { type: String, default: '' }, size: { type: String, default: 'normal' } })
const failed = ref(false)
const url = computed(() => safeWuwaIcon(props.src))
watch(url, () => { failed.value = false }, { flush: 'sync' })
</script>
<template>
  <span class="wuwa-item-icon" :class="`icon-${size}`" :title="name" aria-hidden="true">
    <img v-if="url && !failed" :src="url" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer" @error="failed = true" />
    <span v-else class="icon-fallback">{{ name?.slice(0, 1) || '·' }}</span>
  </span>
</template>
<style scoped>
.wuwa-item-icon { width: 48px; height: 48px; display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; border: 1px solid var(--border-strong); border-radius: 10px; background: linear-gradient(150deg, var(--surface-soft), var(--bg)); overflow: hidden; vertical-align: middle; }
.wuwa-item-icon img { width: 100%; height: 100%; object-fit: contain; }
.icon-fallback { color: var(--text-muted); font-size: 16px; }
.icon-small { width: 28px; height: 28px; border-radius: 6px; }
.icon-large { width: 76px; height: 76px; border-radius: 14px; }
</style>
