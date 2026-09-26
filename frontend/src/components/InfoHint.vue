<script setup>
import { onBeforeUnmount, ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'

// Caveats and how-to notes live behind an ⓘ instead of as prose in the card.
// The text stays in the DOM (screen readers get it through aria-describedby).
// The tip is fixed-positioned from the icon, so a clipping <details> never
// hides it, and it follows the icon while the page scrolls. A mouse over the
// icon or the tip, or keyboard focus, shows it; a tap or click toggles it, and
// a tapped tip closes on scroll or on a tap elsewhere. Escape dismisses it.
const props = defineProps({ text: { type: String, required: true }, label: { type: String, default: '说明' }, align: { type: String, default: 'auto' } })
const id = useId()
const root = ref(null)
const open = ref(false)
const hovered = ref(false)
const dismissed = ref(false)
const tipStyle = ref({})
const side = ref('above')
let focused = false
let leaveTimer = 0

function place() {
  const box = root.value?.getBoundingClientRect?.()
  if (!box) return
  // Phones: a full-width tip below the icon, or above it when the icon sits low on the screen.
  if (innerWidth <= 600) {
    side.value = box.top > innerHeight * 0.6 ? 'above' : 'below'
    const edge = side.value === 'above' ? { bottom: `${innerHeight - box.top + 8}px` } : { top: `${box.bottom + 8}px` }
    tipStyle.value = { ...edge, left: '16px', right: '16px', width: 'auto', maxWidth: 'none' }
    return
  }
  // 'auto' opens towards the roomier side; the tip goes above unless the icon is near the top.
  // Fixed offsets are measured without a classic (Windows) scrollbar, hence clientWidth.
  const width = document.documentElement.clientWidth
  const end = props.align === 'end' || (props.align === 'auto' && box.left > width / 2)
  const style = end ? { right: `${Math.max(12, width - box.right - 6)}px` } : { left: `${Math.max(12, box.left - 6)}px` }
  side.value = box.top > 140 ? 'above' : 'below'
  if (side.value === 'above') style.bottom = `${innerHeight - box.top + 6}px`
  else style.top = `${box.bottom + 6}px`
  tipStyle.value = style
}

function onScroll() {
  if (open.value) close()
  place()
}
function onOutside(event) {
  if (open.value && !root.value?.contains(event.target)) close()
}
function onEscape(event) {
  if (event.key !== 'Escape') return
  dismissed.value = true
  close()
}
// Listeners stay attached only while the tip can be showing.
function sync() {
  if (typeof document === 'undefined') return
  const method = hovered.value || focused || open.value ? 'addEventListener' : 'removeEventListener'
  window[method]('scroll', onScroll, true)
  document[method]('pointerdown', onOutside, true)
  document[method]('keydown', onEscape)
}
function close() {
  open.value = false
  sync()
}
// Hover is tracked for mouse and pen only: after a tap, :hover stays on the
// tapped element (touch laptops included), which would pin the tip open.
function enter(event) {
  if (event.pointerType === 'touch') return
  clearTimeout(leaveTimer)
  hovered.value = true
  dismissed.value = false
  place()
  sync()
}
// A short grace lets the pointer leave the icon sideways and still reach the tip.
function leave() {
  clearTimeout(leaveTimer)
  leaveTimer = setTimeout(() => {
    hovered.value = false
    dismissed.value = false
    sync()
  }, 150)
}
function focusIn() {
  focused = true
  dismissed.value = false
  place()
  sync()
}
function focusOut() {
  focused = false
  close()
}
function toggle() {
  dismissed.value = false
  open.value = !open.value
  if (open.value) place()
  sync()
}
onBeforeUnmount(() => {
  clearTimeout(leaveTimer)
  hovered.value = false
  focused = false
  close()
})
</script>

<template>
  <span ref="root" class="info-hint" :class="{ 'is-open': open, 'is-hovered': hovered, 'is-dismissed': dismissed }" @pointerenter="enter" @pointerleave="leave" @focusin="focusIn" @focusout="focusOut">
    <button type="button" class="info-hint-trigger" :aria-label="label" :aria-describedby="id" @click="toggle"><AppIcon name="info" :size="14" /></button>
    <span :id="id" role="tooltip" class="info-hint-tip" :data-side="side" :style="tipStyle">{{ text }}</span>
  </span>
</template>
