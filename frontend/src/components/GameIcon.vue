<script setup>
import { computed, ref, watch } from 'vue'
import { gameStyle } from '../dashboard.js'
import { theme } from '../theme.js'

const props = defineProps({ gameId: { type: String, required: true }, name: { type: String, default: '' } })
const failed = ref(false)
const style = computed(() => gameStyle(props.gameId))
const icon = computed(() => theme.value === 'light' && style.value.iconLight || style.value.icon)
watch(() => props.gameId, () => { failed.value = false })
</script>

<template>
  <span class="game-icon" :style="{ color: style.color }">
    <img v-if="icon && !failed" :src="icon" :alt="`${name || gameId}图标`" decoding="async" @error="failed = true" />
    <span v-else aria-hidden="true">{{ style.mark }}</span>
  </span>
</template>

<style scoped>
.game-icon { display: inline-grid; place-items: center; flex-shrink: 0; overflow: hidden; vertical-align: middle; }
.game-icon img { display: block; width: 100%; height: 100%; object-fit: cover; }
</style>
