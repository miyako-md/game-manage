<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '../calendar.js'
import { asset } from './models.js'

const props = defineProps({
  src: { type: String, default: '' },
  name: { type: String, default: '' },
  size: { type: Number, default: 20 },
})

const failed = ref(false)
const url = computed(() => asset(safeUrl(props.src)))
watch(url, () => { failed.value = false }, { flush: 'sync' })

const kind = computed(() => {
  const s = String(props.name || '')
  if (/生命/.test(s)) return 'hp'
  if (/攻击/.test(s)) return 'atk'
  if (/防御/.test(s)) return 'def'
  if (/效率|充能/.test(s)) return 'er'
  if (/暴击伤害|暴伤/.test(s)) return 'cdmg'
  if (/暴击/.test(s)) return 'cr'
  if (/治疗/.test(s)) return 'heal'
  if (/环合|精通|异常/.test(s)) return 'anomaly'
  if (/伤害|加成|属性/.test(s)) return 'elem'
  return 'default'
})
</script>
<template>
  <span class="rd-stat-icon" :style="{ width: size + 'px', height: size + 'px' }" aria-hidden="true">
    <img v-if="url && !failed" :src="url" alt="" class="rd-stat-img" :style="{ width: size + 'px', height: size + 'px' }" @error="failed = true" />
    <svg v-else viewBox="0 0 24 24" class="rd-stat-svg" :style="{ width: size + 'px', height: size + 'px' }">
      <!-- HP: heart -->
      <path v-if="kind === 'hp'" d="M12 20.4l-1.45-1.32C5.4 14.36 2 11.28 2 7.5 2 4.42 4.42 2 7.5 2c1.74 0 3.41.81 4.5 2.09C13.09 2.81 14.76 2 16.5 2 19.58 2 22 4.42 22 7.5c0 3.78-3.4 6.86-8.55 11.58L12 20.4z" fill="currentColor" />
      <!-- ATK: crossed blades / sword -->
      <path v-else-if="kind === 'atk'" d="M19.5 3.5L13 10l-1.5-1.5L18 2h3v3l-6.5 6.5L13 10l6.5-6.5zM4.5 3.5L11 10l1.5-1.5L6 2H3v3l6.5 6.5L11 10 4.5 3.5zM8.5 12.5L4 17l-2-1.5L1.5 17 5 20.5 6.5 20 5 18l4.5-4.5-1-1zm7 0l-1 1L19 18l-1.5 2 1.5.5 3.5-3.5-.5-1.5-2 1.5-4.5-4.5z" fill="currentColor" />
      <!-- DEF: shield -->
      <path v-else-if="kind === 'def'" d="M12 2L4 5.4v6.1c0 5.1 3.4 9.7 8 10.9 4.6-1.2 8-5.8 8-10.9V5.4L12 2zm0 2.5l5.8 2.5v4.5c0 3.9-2.4 7.5-5.8 8.7V4.5z" fill="currentColor" />
      <!-- ER / Charge: orbit ring + bolt -->
      <template v-else-if="kind === 'er'">
        <path d="M12 3a9 9 0 1 0 8.5 6h-2.2A7 7 0 1 1 12 5V2l4 3.5L12 9V6.8" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" />
        <path d="M13 8l-3.5 5h3l-1 4 3.5-5h-3L13 8z" fill="currentColor" />
      </template>
      <!-- Crit Damage: 8-point starburst -->
      <path v-else-if="kind === 'cdmg'" d="M12 2l2.1 5.9L20 6l-1.9 5.9L22 14l-5.9 2.1L18 22l-5.9-1.9L10 22l-.1-5.9L4 18l1.9-5.9L2 10l5.9-2.1L6 2l5.9 1.9L12 2z" fill="currentColor" />
      <!-- Crit Rate: 4-point cross-spark + center reticle -->
      <template v-else-if="kind === 'cr'">
        <path d="M12 2l2.2 7.8L22 12l-7.8 2.2L12 22l-2.2-7.8L2 12l7.8-2.2L12 2z" fill="currentColor" />
      </template>
      <!-- Heal: medical cross inside circle -->
      <path v-else-if="kind === 'heal'" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm4 11h-3v3h-2v-3H8v-2h3V8h2v3h3z" fill="currentColor" />
      <!-- Anomaly / Harmony: hexagon node -->
      <path v-else-if="kind === 'anomaly'" d="M12 2.5L20 7v10l-8 4.5L4 17V7l8-4.5zm0 3.2L7 8.5v7l5 2.8 5-2.8v-7l-5-2.8z" fill="currentColor" />
      <!-- Elemental / Damage Bonus: flame/crystal -->
      <path v-else-if="kind === 'elem'" d="M13.2 2.2c.5 3.1 4.8 5.4 4.8 10.1A6 6 0 1 1 6 12.6c0-2.6 1.5-5 3.1-6.5.2 2.1 1.4 3.2 2.5 3.4-.5-2.6.5-5.3 1.6-7.3z" fill="currentColor" />
      <!-- Default: diamond emblem -->
      <path v-else d="M12 3l8 9-8 9-8-9 8-9z" fill="currentColor" />
    </svg>
  </span>
</template>
