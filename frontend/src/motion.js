// Motion directives. Both guard against non-DOM renderers (the unit tests
// mount components into plain objects), so they are no-ops there.

const ACTIVE = '[aria-pressed="true"], [aria-selected="true"], .active'

function domReady(el) {
  return typeof window !== 'undefined' && typeof el?.querySelector === 'function'
}

/** v-glide: keeps a sliding indicator under the active child of a tab list.
 *  Modifier `underline` draws a 2px bar at the bottom instead of a pill. */
export const vGlide = {
  mounted(el, binding) {
    if (!domReady(el)) return
    const underline = !!binding.modifiers.underline
    const pill = document.createElement('span')
    pill.className = underline ? 't-glide t-glide-underline' : 't-glide t-glide-pill'
    pill.setAttribute('aria-hidden', 'true')
    el.classList.add('has-glide')
    el.prepend(pill)
    let ready = false
    const measure = () => {
      const active = el.querySelector(ACTIVE)
      if (!active || !active.offsetWidth) { pill.style.opacity = '0'; return }
      const height = underline ? 2 : active.offsetHeight
      const top = underline ? active.offsetTop + active.offsetHeight - height : active.offsetTop
      pill.style.opacity = '1'
      pill.style.width = `${active.offsetWidth}px`
      pill.style.height = `${height}px`
      pill.style.transform = `translate(${active.offsetLeft}px, ${top}px)`
      if (!ready) {
        // First position is written without a transition so the indicator
        // does not slide in from the origin.
        ready = true
        pill.style.transition = 'none'
        void pill.offsetWidth
        requestAnimationFrame(() => { pill.style.transition = '' })
      }
    }
    const observer = new MutationObserver(measure)
    observer.observe(el, { attributes: true, subtree: true, childList: true, attributeFilter: ['aria-pressed', 'aria-selected', 'class'] })
    const resizer = typeof ResizeObserver === 'function' ? new ResizeObserver(measure) : null
    resizer?.observe(el)
    measure()
    requestAnimationFrame(measure)
    el.__glide = { measure, destroy() { observer.disconnect(); resizer?.disconnect(); pill.remove() } }
  },
  updated(el) { el.__glide?.measure() },
  unmounted(el) { el.__glide?.destroy(); delete el.__glide },
}

/** v-pop: replays a short rise on an element whenever its text changes. */
export const vPop = {
  mounted(el) {
    if (!domReady(el) || typeof MutationObserver !== 'function') return
    const replay = () => {
      el.classList.remove('t-pop')
      void el.offsetWidth
      el.classList.add('t-pop')
    }
    const observer = new MutationObserver(replay)
    observer.observe(el, { childList: true, characterData: true, subtree: true })
    el.__pop = observer
  },
  unmounted(el) { el.__pop?.disconnect(); delete el.__pop },
}
