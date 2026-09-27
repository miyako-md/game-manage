<script setup>
import { computed, ref, watch } from 'vue'
import { gameStyle } from '../dashboard.js'
import { theme } from '../theme.js'

const props = defineProps({ gameId: { type: String, required: true }, name: { type: String, default: '' } })
const failed = ref(0)
const style = computed(() => gameStyle(props.gameId))
const icons = computed(() => [...new Set([
  typeof __LOCAL_GAME_ICONS__ !== 'undefined' ? __LOCAL_GAME_ICONS__[props.gameId] : null,
  theme.value === 'light' && style.value.iconLight || style.value.icon,
].filter(Boolean))])
watch([() => props.gameId, theme], () => { failed.value = 0 })
</script>

<template>
  <span class="game-icon" :style="{ color: style.color }">
    <img v-if="icons[failed]" :src="icons[failed]" :alt="`${name || gameId}图标`" decoding="async" @error="failed++" />
    <span v-else aria-hidden="true">{{ style.mark }}</span>
  </span>
</template>

<style scoped>
.game-icon { display: inline-grid; place-items: center; flex-shrink: 0; overflow: hidden; vertical-align: middle; }
.game-icon img { display: block; width: 100%; height: 100%; object-fit: cover; }
</style>
