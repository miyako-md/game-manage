<script setup>
import { onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { prefersReducedMotion } from '../motion.js'

defineProps({ title: { type: String, required: true }, eyebrow: { type: String, default: '' } })
const emit = defineEmits(['close'])
const dialog = ref(null)
const closing = ref(false)
const headingId = `game-dialog-${useId()}`
let previousFocus, previousOverflow, closeTimer, pressedBackdrop = false, closed = false

onMounted(() => {
  if (typeof document === 'undefined' || !dialog.value?.showModal) return
  previousFocus = document.activeElement
  previousOverflow = document.body.style.overflow
  dialog.value.showModal()
  document.body.style.overflow = 'hidden'
})
onBeforeUnmount(() => {
  closed = true
  clearTimeout(closeTimer)
  dialog.value?.close?.()
  if (typeof document !== 'undefined' && previousOverflow !== undefined) document.body.style.overflow = previousOverflow
  if (previousFocus?.isConnected) previousFocus.focus?.({ preventScroll: true })
})

function finishClose() {
  if (closed) return
  closed = true
  clearTimeout(closeTimer)
  emit('close')
}
function requestClose() {
  if (closing.value || closed) return
  closing.value = true
  if (!dialog.value?.open || prefersReducedMotion()) { finishClose(); return }
  // Still release the modal if animation events are unavailable or interrupted.
  closeTimer = setTimeout(finishClose, 220)
}
function backdropClick(event) {
  if (pressedBackdrop && event.target === dialog.value) requestClose()
  pressedBackdrop = false
}
function animationEnded(event) {
  if (event.target === dialog.value && event.animationName === 't-dialog-exit' && closing.value) finishClose()
}
</script>

<template>
  <dialog ref="dialog" class="game-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" :aria-labelledby="headingId" @cancel.prevent="requestClose" @pointerdown="pressedBackdrop = $event.target === dialog" @click="backdropClick" @animationend="animationEnded">
    <header class="game-dialog-heading">
      <div><p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p><h2 :id="headingId">{{ title }}</h2></div>
      <button type="button" class="ui-button small-button" autofocus @click="requestClose">关闭详情</button>
    </header>
    <div class="game-dialog-body"><slot /></div>
  </dialog>
</template>

<style scoped>
.game-dialog { position:fixed; inset:0; margin:auto; width:min(var(--dialog-width,1180px),calc(100vw - 48px)); max-width:none; max-height:calc(100dvh - 48px); padding:0; border:1px solid var(--border-strong); border-radius:18px; background:var(--card-bg); color:var(--text); box-shadow:var(--popover-shadow); }
.game-dialog[open] { display:flex; flex-direction:column; }
.game-dialog::backdrop { background:var(--scrim); backdrop-filter:blur(4px); }
.game-dialog-heading { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:20px 24px; border-bottom:1px solid var(--border); flex-shrink:0; background:linear-gradient(115deg,var(--accent-soft),transparent 70%); }
.game-dialog-heading .eyebrow { color:var(--accent); }
.game-dialog-heading h2 { font-size:20px; line-height:1.4; margin:4px 0 0; }
.game-dialog-body { overflow-y:auto; overscroll-behavior:contain; padding:22px 24px 28px; min-height:0; }
@media (max-width:640px) {
  .game-dialog { inset:auto 0 0; margin:0 auto; width:100%; max-height:calc(100dvh - 24px); border-radius:20px 20px 0 0; border-bottom:0; }
  .game-dialog-heading { padding:18px 16px; gap:12px; }
  .game-dialog-heading h2 { font-size:18px; }
  .game-dialog-body { padding:18px 16px max(24px,env(safe-area-inset-bottom)); }
}
</style>
