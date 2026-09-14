<script setup>
import { computed } from 'vue'
const props = defineProps({ name: { type: String, default: 'grid' }, size: { type: Number, default: 18 } })
const paths = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  calendar: 'M5 5h14a2 2 0 0 1 2 2v13H3V7a2 2 0 0 1 2-2 M7 2v6 M17 2v6 M3 11h18',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0 M4 21v-2a8 8 0 0 1 16 0v2',
  bell: 'M5 16V9a7 7 0 0 1 14 0v7l2 2H3z M9 21h6',
  arrow: 'M5 12h14 M14 7l5 5-5 5',
  refresh: 'M20 7v5h-5 M4 17v-5h5 M5.5 7a7.5 7.5 0 0 1 13-1L20 9 M4 15l1.5 3a7.5 7.5 0 0 0 13-1',
  close: 'M6 6l12 12 M6 18 18 6',
  spark: 'M12 2l3 7 7 3-7 3-3 7-3-7-7-3 7-3z',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  chart: 'M4 20V10 M11 20V4 M18 20v-8',
  menu: 'M4 6h16 M4 12h16 M4 18h16',
  shield: 'm12 2 8 3v7c0 5-8 10-8 10S4 17 4 12V5z m-4 10 3 3 5-6',
}
const path = computed(() => paths[props.name] || paths.grid)
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="path" /></svg></template>
<style scoped>svg { flex-shrink: 0; display: block; }</style>
