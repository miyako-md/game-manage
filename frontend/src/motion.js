// Motion directives guard against non-DOM renderers (the component tests
// mount components into plain objects), so they are no-ops there.

const ACTIVE = '[aria-current="page"], [aria-pressed="true"], [aria-selected="true"], .active'

function domReady(el) {
  return typeof window !== 'undefined' && typeof el?.querySelector === 'function'
}

const FINE_POINTER = '(hover: hover) and (pointer: fine)'

export const clamp = (value, min, max) => Math.max(min, Math.min(max, value))

const H = 1 / 240
export function stepSpringRk4(pos, vel, target, k, c, dt, wall = 0) {
  const steps = Math.max(1, Math.min(24, Math.round(dt / H)))
  const h = dt / steps
  let x = pos, v = vel
  const accel = (px, pv) => {
    const outside = wall ? px - clamp(px, 0, 1) : 0
    return (target - px) * k - pv * c - outside * wall
  }
  for (let i = 0; i < steps; i++) {
    const a1 = accel(x, v)
    const v2 = v + 0.5 * h * a1, a2 = accel(x + 0.5 * h * v, v2)
    const v3 = v + 0.5 * h * a2, a3 = accel(x + 0.5 * h * v2, v3)
    const v4 = v + h * a3, a4 = accel(x + h * v3, v4)
    x += (h / 6) * (v + 2 * v2 + 2 * v3 + v4)
    v += (h / 6) * (a1 + 2 * a2 + 2 * a3 + a4)
  }
  return [x, v]
}

export function prefersReducedMotion() {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
}

function revealControl(el, active, smooth) {
  if (!active || !el.clientWidth || el.scrollWidth <= el.clientWidth) return
  const left = active.offsetLeft, right = left + active.offsetWidth
  if (left >= el.scrollLeft && right <= el.scrollLeft + el.clientWidth) return
  el.scrollTo({
    left: Math.max(0, Math.min(el.scrollWidth - el.clientWidth, left - (el.clientWidth - active.offsetWidth) / 2)),
    behavior: smooth && !prefersReducedMotion() ? 'smooth' : 'auto',
  })
}

function placeSlip(slip, item) {
  if (!item?.offsetWidth) {
    if (slip.style.opacity !== '0') slip.style.opacity = '0'
    return
  }
  const width = `${item.offsetWidth}px`
  const height = `${item.offsetHeight}px`
  const transform = `translate(${item.offsetLeft}px, ${item.offsetTop}px)`
  const first = slip.style.opacity !== '1'
  if (!first && slip.__w === width && slip.__h === height && slip.__t === transform) return
  if (first) slip.style.transition = 'none'
  if (slip.__w !== width) { slip.style.width = width; slip.__w = width }
  if (slip.__h !== height) { slip.style.height = height; slip.__h = height }
  if (slip.__t !== transform) { slip.style.transform = transform; slip.__t = transform }
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
    let frame = 0, lastActive = null, lastWidth = 0
    const observed = new Set()
    const measure = (initial = false) => {
      const controls = [...el.children].filter(child => child.matches('a, button'))
      const active = controls.find(child => child.matches(ACTIVE))
      placeSlip(pill, active)
      // Scroll only the control strip, and leave a user's manual browsing alone.
      if (active !== lastActive || el.clientWidth !== lastWidth) revealControl(el, active, !initial && active !== lastActive)
      lastActive = active
      lastWidth = el.clientWidth
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
    const observer = new MutationObserver(records => {
      if (records.some(m => m.type === 'childList' || m.target === el || m.target.parentElement === el)) schedule()
    })
    observer.observe(el, { attributes: true, subtree: true, childList: true, attributeFilter: ['aria-current', 'aria-pressed', 'aria-selected', 'class'] })
    const resizer = typeof ResizeObserver === 'function' ? new ResizeObserver(schedule) : null
    resizer?.observe(el)
    measure(true)
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

/* v-reveal is default-visible. Only an element that starts below the fold of a
   live page is hidden until it is scrolled to; anything already on screen,
   rendered off-screen for a bot image, printed or under reduced motion shows
   at once, and no content waits on an observer that may never fire. */
const REVEAL_SETTLE = 700
let revealObserver = null
function showRevealed(entries) {
  let order = 0
  for (const entry of entries) {
    if (!entry.isIntersecting) continue
    const el = entry.target
    revealObserver.unobserve(el)
    // Cards that arrive together rise one after another.
    const delay = Math.min(order++, 6) * 60
    el.style.setProperty('--reveal-delay', `${delay}ms`)
    el.dataset.reveal = 'shown'
    // Afterwards the card's own hover and press transitions take over again.
    el.__revealSettle = setTimeout(() => settleReveal(el), REVEAL_SETTLE + delay)
  }
}
function settleReveal(el) {
  clearTimeout(el.__revealSettle)
  delete el.__revealSettle
  delete el.dataset.reveal
  el.style.removeProperty('--reveal-delay')
}

/** v-reveal: content below the fold rises in when it is scrolled to. */
export const vReveal = {
  mounted(el) {
    if (!domReady(el) || typeof IntersectionObserver !== 'function' || prefersReducedMotion() || el.closest('.render-image')) return
    const box = el.getBoundingClientRect()
    const height = window.innerHeight
    if (!box.height || box.top < height * 0.9 || box.right <= 0 || box.left >= window.innerWidth) return
    revealObserver ??= new IntersectionObserver(showRevealed, { rootMargin: '0px 0px -10% 0px' })
    el.dataset.reveal = 'pending'
    revealObserver.observe(el)
  },
  unmounted(el) {
    if (!el.dataset?.reveal) return
    revealObserver?.unobserve(el)
    settleReveal(el)
  },
}

/* v-parallax gives the bound element --plx, its distance from the middle of the
   viewport in viewport heights (−1 above … 1 below). Layers inside turn that
   into a transform with their own --plx-range, so one scroll handler drives
   every depth. */
const parallaxItems = new Set()
let parallaxFrame = 0
function moveParallax() {
  parallaxFrame = 0
  const height = window.innerHeight
  for (const el of parallaxItems) {
    const box = el.getBoundingClientRect()
    if (box.bottom < -height || box.top > height * 2) continue
    const offset = (box.top + box.height / 2 - height / 2) / height
    const next = clamp(offset, -1, 1).toFixed(4)
    if (el.__plx !== next) {
      el.__plx = next
      el.style.setProperty('--plx', next)
    }
  }
}
const scheduleParallax = () => { if (!parallaxFrame) parallaxFrame = requestAnimationFrame(moveParallax) }

/** v-parallax: background layers drift slower than the page as it scrolls. */
export const vParallax = {
  mounted(el) {
    if (!domReady(el) || prefersReducedMotion() || el.closest('.render-image')) return
    if (!parallaxItems.size) {
      window.addEventListener('scroll', scheduleParallax, { passive: true })
      window.addEventListener('resize', scheduleParallax)
    }
    parallaxItems.add(el)
    scheduleParallax()
  },
  unmounted(el) {
    if (!parallaxItems.delete(el)) return
    delete el.__plx
    el.style.removeProperty('--plx')
    if (parallaxItems.size) return
    window.removeEventListener('scroll', scheduleParallax)
    window.removeEventListener('resize', scheduleParallax)
    cancelAnimationFrame(parallaxFrame)
    parallaxFrame = 0
  },
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
