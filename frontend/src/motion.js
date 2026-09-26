// Motion directives. Both guard against non-DOM renderers (the unit tests
// mount components into plain objects), so they are no-ops there.

const ACTIVE = '[aria-pressed="true"], [aria-selected="true"], .active'

function domReady(el) {
  return typeof window !== 'undefined' && typeof el?.querySelector === 'function'
}

const FINE_POINTER = '(hover: hover) and (pointer: fine)'

/** Hover slip (beUI shared-layout background): follows the hovered item and
 *  fades out when the pointer leaves; the first appearance only fades in. */
function hoverSlip(el) {
  if (typeof matchMedia !== 'function' || !matchMedia(FINE_POINTER).matches) return null
  const slip = document.createElement('span')
  slip.className = 't-glide-hover'
  slip.setAttribute('aria-hidden', 'true')
  el.prepend(slip)
  let shown = false
  const hide = () => { shown = false; slip.style.opacity = '0' }
  const over = (event) => {
    const item = event.target.closest?.('a, button')
    if (!item || item.parentElement !== el) return
    if (item.matches(ACTIVE)) { hide(); return }
    if (!shown) slip.style.transition = 'opacity var(--duration-quick) var(--ease-out)'
    slip.style.width = `${item.offsetWidth}px`
    slip.style.height = `${item.offsetHeight}px`
    slip.style.transform = `translate(${item.offsetLeft}px, ${item.offsetTop}px)`
    slip.style.opacity = '1'
    if (!shown) { shown = true; void slip.offsetWidth; slip.style.transition = '' }
  }
  el.addEventListener('pointerover', over)
  el.addEventListener('pointerleave', hide)
  return () => { el.removeEventListener('pointerover', over); el.removeEventListener('pointerleave', hide); slip.remove() }
}

/** v-glide: keeps a sliding slip under the active child of a tab list.
 *  Modifier `hover` adds a second, fainter slip that tracks the pointer. */
export const vGlide = {
  mounted(el, binding) {
    if (!domReady(el)) return
    const pill = document.createElement('span')
    pill.className = 't-glide'
    pill.setAttribute('aria-hidden', 'true')
    el.classList.add('has-glide')
    el.prepend(pill)
    const dropHover = binding?.modifiers?.hover ? hoverSlip(el) : null
    let ready = false
    const measure = () => {
      const active = el.querySelector(ACTIVE)
      if (!active || !active.offsetWidth) { pill.style.opacity = '0'; return }
      pill.style.opacity = '1'
      pill.style.width = `${active.offsetWidth}px`
      pill.style.height = `${active.offsetHeight}px`
      pill.style.transform = `translate(${active.offsetLeft}px, ${active.offsetTop}px)`
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
    el.__glide = { measure, destroy() { observer.disconnect(); resizer?.disconnect(); dropHover?.(); pill.remove() } }
  },
  updated(el) { el.__glide?.measure() },
  unmounted(el) { el.__glide?.destroy(); delete el.__glide },
}

/** v-pop: replays a short rise on an element whenever its text changes. */
export const vPop = {
  mounted(el) { if (domReady(el)) el.__popText = el.textContent },
  updated(el) {
    if (el.__popText === undefined || el.textContent === el.__popText) return
    el.__popText = el.textContent
    el.classList.remove('t-pop')
    void el.offsetWidth
    el.classList.add('t-pop')
  },
}
