// Motion directives guard against non-DOM renderers (the component tests
// mount components into plain objects), so they are no-ops there.

const ACTIVE = '[aria-current="page"], [aria-pressed="true"], [aria-selected="true"], .active'

function domReady(el) {
  return typeof window !== 'undefined' && typeof el?.querySelector === 'function'
}

const FINE_POINTER = '(hover: hover) and (pointer: fine)'

function placeSlip(slip, item) {
  if (!item?.offsetWidth) { slip.style.opacity = '0'; return }
  const first = slip.style.opacity !== '1'
  if (first) slip.style.transition = 'none'
  slip.style.width = `${item.offsetWidth}px`
  slip.style.height = `${item.offsetHeight}px`
  slip.style.transform = `translate(${item.offsetLeft}px, ${item.offsetTop}px)`
  slip.style.opacity = '1'
  if (first) { void slip.offsetWidth; slip.style.transition = '' }
}

/** Follow hovered controls without sliding in from the container origin. */
function hoverSlip(el) {
  if (typeof matchMedia !== 'function' || !matchMedia(FINE_POINTER).matches) return null
  const slip = document.createElement('span')
  slip.className = 't-glide-hover'
  slip.setAttribute('aria-hidden', 'true')
  el.prepend(slip)
  let hovered = null
  const measure = () => placeSlip(slip, hovered?.parentElement === el && !hovered.matches(ACTIVE) ? hovered : null)
  const hide = () => { hovered = null; measure() }
  const over = (event) => {
    if (event.pointerType === 'touch') return
    const item = event.target.closest?.('a, button')
    if (!item || item.parentElement !== el) return
    hovered = item
    measure()
  }
  el.addEventListener('pointerover', over)
  el.addEventListener('pointerleave', hide)
  return { measure, destroy() { el.removeEventListener('pointerover', over); el.removeEventListener('pointerleave', hide); slip.remove() } }
}

/** v-glide: keeps a sliding slip under the active child of a tab list.
 *  Modifier `hover` adds a second, fainter slip that tracks the pointer. */
export const vGlide = {
  mounted(el, binding) {
    if (!domReady(el)) return
    const pill = document.createElement('span')
    pill.className = 't-glide'
    pill.setAttribute('aria-hidden', 'true')
    // Vue replaces a bound class on updates; keep directive-owned styling separate.
    el.setAttribute('data-glide', '')
    el.prepend(pill)
    const hover = binding?.modifiers?.hover ? hoverSlip(el) : null
    let frame = 0
    const observed = new Set()
    const measure = () => {
      const controls = [...el.children].filter(child => child.matches('a, button'))
      placeSlip(pill, controls.find(child => child.matches(ACTIVE)))
      hover?.measure()
      for (const child of observed) {
        if (!controls.includes(child)) { resizer?.unobserve(child); observed.delete(child) }
      }
      for (const child of controls) {
        if (!observed.has(child)) { resizer?.observe(child); observed.add(child) }
      }
    }
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; measure() })
    }
    const observer = new MutationObserver(schedule)
    observer.observe(el, { attributes: true, subtree: true, childList: true, attributeFilter: ['aria-current', 'aria-pressed', 'aria-selected', 'class'] })
    const resizer = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null
    resizer?.observe(el)
    measure()
    el.__glide = { measure: schedule, destroy() {
      observer.disconnect()
      resizer?.disconnect()
      cancelAnimationFrame(frame)
      hover?.destroy()
      pill.remove()
      el.removeAttribute('data-glide')
    } }
  },
  updated(el) { el.__glide?.measure() },
  unmounted(el) { el.__glide?.destroy(); delete el.__glide },
}

/** Pointer-following light on overview cards; keyboard focus uses a fixed light. */
export const vSpotlight = {
  mounted(el) {
    if (!domReady(el) || typeof matchMedia !== 'function') return
    const media = matchMedia(`${FINE_POINTER} and (prefers-reduced-motion: no-preference)`)
    let frame = 0, x = 0, y = 0
    const reset = () => {
      cancelAnimationFrame(frame)
      frame = 0
      el.removeAttribute('data-spotlight-active')
      el.style.removeProperty('--spotlight-x')
      el.style.removeProperty('--spotlight-y')
    }
    const move = event => {
      if (!media.matches || event.pointerType === 'touch') return
      x = event.clientX; y = event.clientY
      if (!frame) frame = requestAnimationFrame(() => {
        frame = 0
        const box = el.getBoundingClientRect()
        el.style.setProperty('--spotlight-x', `${x - box.left}px`)
        el.style.setProperty('--spotlight-y', `${y - box.top}px`)
        el.setAttribute('data-spotlight-active', '')
      })
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', reset)
    media.addEventListener('change', reset)
    el.__spotlight = () => {
      reset()
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', reset)
      media.removeEventListener('change', reset)
    }
  },
  unmounted(el) { el.__spotlight?.(); delete el.__spotlight },
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
