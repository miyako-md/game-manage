<script setup>
import { ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'

// Caveats and how-to notes live behind an ⓘ instead of as prose in the card.
// The text stays in the DOM (screen readers get it through aria-describedby).
const props = defineProps({ text: { type: String, required: true }, label: { type: String, default: '说明' }, align: { type: String, default: 'auto' } })
const id = useId()
// 'auto' opens the tip towards the roomier side of the screen.
const side = ref(props.align === 'end' ? 'end' : 'start')
// Hover and keyboard focus show the tip through CSS; a tap toggles it, since
// touch focus does not match :focus-visible.
const open = ref(false)
function place(event) {
  if (props.align !== 'auto' || typeof window === 'undefined') return
  const box = event.currentTarget?.getBoundingClientRect?.()
  if (box) side.value = box.left > window.innerWidth / 2 ? 'end' : 'start'
}
</script>

<template>
  <span class="info-hint" :class="[`align-${side}`, { 'is-open': open }]" @pointerenter="place" @focusin="place">
    <button type="button" class="info-hint-trigger" :aria-label="label" :aria-describedby="id" @click="open = !open" @blur="open = false" @keydown.esc="open = false"><AppIcon name="info" :size="14" /></button>
    <span :id="id" role="tooltip" class="info-hint-tip">{{ text }}</span>
  </span>
</template>
