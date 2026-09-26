<script setup>
import { onBeforeUnmount, ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'

// Caveats and how-to notes live behind an ⓘ instead of as prose in the card.
// The text stays in the DOM (screen readers get it through aria-describedby).
// The tip is fixed-positioned from the trigger, so a clipping <details> or a
// scrolled page never hides it. Hover and keyboard focus show it, a tap
// toggles it (touch focus does not match :focus-visible), Escape dismisses it.
const props = defineProps({ text: { type: String, required: true }, label: { type: String, default: '说明' }, align: { type: String, default: 'auto' } })
const id = useId()
const open = ref(false)
const dismissed = ref(false)
const tipStyle = ref({})

function place(event) {
  dismissed.value = false
  const box = event.currentTarget?.getBoundingClientRect?.()
  if (!box || typeof window === 'undefined') return
  // Phones: a full-width tip below the icon, or above it when the icon sits low on the screen.
  if (innerWidth <= 600) {
    const edge = box.top > innerHeight * 0.6 ? { bottom: `${innerHeight - box.top + 8}px` } : { top: `${box.bottom + 8}px` }
    tipStyle.value = { ...edge, left: '16px', right: '16px', width: 'auto', maxWidth: 'none' }
    return
  }
  // 'auto' opens towards the roomier side; the tip goes above unless the icon is near the top.
  const end = props.align === 'end' || (props.align === 'auto' && box.left > innerWidth / 2)
  const style = end ? { right: `${Math.max(12, innerWidth - box.right - 6)}px` } : { left: `${Math.max(12, box.left - 6)}px` }
  if (box.top > 140) style.bottom = `${innerHeight - box.top + 6}px`
  else style.top = `${box.bottom + 6}px`
  tipStyle.value = style
}
function listen(on) {
  if (typeof window !== 'undefined') window[on ? 'addEventListener' : 'removeEventListener']('scroll', close, true)
}
function close() {
  if (!open.value) return
  open.value = false
  listen(false)
}
function toggle() {
  dismissed.value = false
  open.value = !open.value
  listen(open.value)
}
function onKeydown(event) {
  if (event.key !== 'Escape') return
  dismissed.value = true
  close()
}
onBeforeUnmount(() => listen(false))
</script>

<template>
  <span class="info-hint" :class="{ 'is-open': open, 'is-dismissed': dismissed }" @pointerenter="place" @focusin="place" @pointerleave="dismissed = false">
    <button type="button" class="info-hint-trigger" :aria-label="label" :aria-describedby="id" @click="toggle" @blur="close" @keydown="onKeydown"><AppIcon name="info" :size="14" /></button>
    <span :id="id" role="tooltip" class="info-hint-tip" :style="tipStyle">{{ text }}</span>
  </span>
</template>
