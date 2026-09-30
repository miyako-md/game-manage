import { onBeforeUnmount, onMounted, ref } from 'vue'
import { prefersReducedMotion } from './motion.js'

export function useDialog(onClose) {
  const dialog = ref(null)
  const closing = ref(false)
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
    onClose()
  }
  function requestClose() {
    if (closing.value || closed) return
    closing.value = true
    if (!dialog.value?.open || prefersReducedMotion()) { finishClose(); return }
    // Still release the modal if animation events are unavailable or interrupted.
    closeTimer = setTimeout(finishClose, 220)
  }
  function backdropDown(event) { pressedBackdrop = event.target === dialog.value }
  function backdropClick(event) {
    if (pressedBackdrop && event.target === dialog.value) requestClose()
    pressedBackdrop = false
  }
  function animationEnded(event) {
    if (event.target === dialog.value && event.animationName === 't-dialog-exit' && closing.value) finishClose()
  }

  return { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded }
}
