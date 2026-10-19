// Click feedback inspired by lucide-animated's icon-specific movement. This
// implementation uses browser animations and the app's existing SVG geometry.
const CONTROL = 'button, a[href], [role="button"], summary'
const BLOCKED = '[disabled], [aria-disabled="true"], [aria-busy="true"], [inert], [hidden], [data-icon-motion="off"], [data-busy="true"], .spinning, .is-spinning, .busy, .is-busy'
const EASE = 'cubic-bezier(.2,.7,.25,1)'

function motions(icon) {
  const name = icon.getAttribute('data-app-icon')
  const body = icon.querySelector('[data-icon-part="body"]')
  const move = (transforms, duration = 440) => [{ target: body, frames: transforms.map(transform => ({ transform })), duration }]
  if (name === 'refresh') return move(['rotate(0deg)', 'rotate(360deg)'], 1000)
  if (name === 'calendar') return [
    ...move(['rotate(0deg)', 'rotate(-8deg)', 'rotate(5deg)', 'rotate(0deg)'], 620),
    { target: icon.querySelector('[data-icon-part="cells"]'), frames: [{ opacity: 0 }, { opacity: 1, offset: .3 }, { opacity: 1, offset: .75 }, { opacity: 0 }], duration: 620 },
  ]
  if (name === 'search') return move(['translate(0px, 0px)', 'translate(1px, -2px)', 'translate(-2px, 1px)', 'translate(0px, 0px)'], 560)
  if (name === 'sun') return move(['rotate(0deg)', 'rotate(90deg)'], 650)
  if (name === 'moon') return move(['rotate(0deg)', 'rotate(-15deg)', 'rotate(8deg)', 'rotate(0deg)'], 620)
  if (name === 'auto') return [{ target: icon.querySelector('[data-icon-part="orbit"]'), frames: [{ transform: 'rotate(0deg)' }, { transform: 'rotate(180deg)' }], duration: 560 }]
  if (name === 'arrow') return move(['translateX(0px)', 'translateX(3px)', 'translateX(0px)'], 420)
  if (name === 'chevron') return move(['translateY(0px)', 'translateY(2px)', 'translateY(0px)'], 360)
  if (name === 'plus') return move(['rotate(0deg) scale(1)', 'rotate(90deg) scale(.86)', 'rotate(90deg) scale(1)'], 420)
  if (name === 'check') return [{ target: icon.querySelector('[data-icon-part="stroke"]'), frames: [{ strokeDasharray: '1', strokeDashoffset: '1' }, { strokeDasharray: '1', strokeDashoffset: '0' }], duration: 440 }]
  if (name === 'menu') return [...icon.querySelectorAll('[data-icon-part="line"]')].map((target, index) => ({ target, frames: [{ transform: 'translateX(0px)' }, { transform: `translateX(${index % 2 ? -2 : 2}px)` }, { transform: 'translateX(0px)' }], duration: 380, delay: index * 45 }))
  if (name === 'grid') return [...icon.querySelectorAll('[data-icon-part="tile"]')].map((target, index) => ({ target, frames: [{ opacity: 1, transform: 'scale(1)' }, { opacity: .45, transform: 'scale(.9)' }, { opacity: 1, transform: 'scale(1)' }], duration: 380, delay: index * 45 }))
  return move(['scale(1)', 'scale(.88)', 'scale(1)'], 340)
}

/** Install once in the interactive entry point, never in the image renderer. */
export function installIconMotion(document) {
  const win = document?.defaultView
  if (!win || typeof document.addEventListener !== 'function' || !document.documentElement) return { destroy() {} }
  const media = win.matchMedia?.('(prefers-reduced-motion: reduce)')
  const active = new Map()
  let destroyed = false, observing = false, lastClickUntil = -Infinity
  let recentClicks = new WeakMap()
  const CLICK_WINDOW = 1200
  const imageMode = () => Boolean(win.__RENDER_STATE__ || document.querySelector('.render-root, [data-image-mode="true"]'))
  const eligibleDom = (icon, control) => (
    icon.isConnected && control.isConnected && !icon.closest(BLOCKED) && icon.closest(CONTROL) === control &&
    icon.getAttribute('data-active') !== 'false' && !icon.closest('.render-root, [data-image-mode="true"]')
  )
  const eligible = (icon, control, checkStyle = true) => {
    if (!eligibleDom(icon, control)) return false
    if (!checkStyle) return true
    const style = win.getComputedStyle(icon)
    const alreadyAnimating = style.animationName?.split(',').some(name => name.trim() && name.trim() !== 'none')
    return style.display !== 'none' && style.visibility !== 'hidden' && !alreadyAnimating
  }
  const observer = win.MutationObserver ? new win.MutationObserver(records => {
    const now = win.performance.now()
    if (!active.size && now > lastClickUntil) {
      unobserve()
      return
    }
    for (const [icon, record] of active) {
      const styleTouched = records.some(m => m.type === 'attributes' && m.attributeName === 'class' && m.target?.contains?.(icon))
      if (imageMode() || !eligible(icon, record.control, styleTouched) || icon.getAttribute('data-app-icon') !== record.name) cancel(icon)
    }
    if (now > lastClickUntil) {
      if (!active.size) unobserve()
      return
    }
    // View Transitions may swap the theme icons in a later task. Only a recent
    // click on this control authorizes that newly active icon's feedback.
    for (const mutation of records) {
      if (mutation.type !== 'attributes' || !['data-active', 'data-app-icon'].includes(mutation.attributeName)) continue
      const icon = mutation.target
      if (!icon.matches?.('svg[data-app-icon]') || (mutation.attributeName === 'data-active' && icon.getAttribute('data-active') !== 'true')) continue
      const control = icon.closest(CONTROL)
      if (control) playForClick(icon, control, recentClicks.get(control))
    }
  }) : null
  function observe() {
    if (observing || !observer || destroyed) return
    observing = true
    observer.observe(document.documentElement, { subtree: true, childList: true, attributes: true,
      attributeFilter: ['disabled', 'aria-disabled', 'aria-busy', 'inert', 'hidden', 'data-icon-motion', 'data-busy', 'data-active', 'data-app-icon', 'class'] })
  }
  function unobserve() {
    if (!observing) return
    observing = false
    observer?.disconnect()
  }
  function cancel(icon) {
    const record = active.get(icon)
    if (!record) return
    active.delete(icon)
    for (const animation of record.animations) {
      animation.onfinish = null; animation.oncancel = null
      animation.cancel()
    }
    if (!active.size && win.performance.now() > lastClickUntil) unobserve()
  }
  function cancelAll() { for (const icon of [...active.keys()]) cancel(icon) }
  function play(icon, control) {
    cancel(icon)
    const record = { animations: [], control, name: icon.getAttribute('data-app-icon') }
    active.set(icon, record)
    observe()
    for (const { target, frames, duration, delay = 0 } of motions(icon)) {
      if (typeof target?.animate !== 'function') continue
      const animation = target.animate(frames, { duration, delay, easing: EASE, fill: 'none' })
      record.animations.push(animation)
      const finished = () => {
        animation.onfinish = null; animation.oncancel = null
        record.animations = record.animations.filter(item => item !== animation)
        if (!record.animations.length && active.get(icon) === record) {
          active.delete(icon)
          if (!active.size && win.performance.now() > lastClickUntil) unobserve()
        }
      }
      animation.onfinish = finished
      animation.oncancel = finished
    }
    if (!record.animations.length) active.delete(icon)
  }
  function playForClick(icon, control, click) {
    if (destroyed || media?.matches || imageMode() || !click || recentClicks.get(control) !== click ||
      win.performance.now() > click.until || !eligible(icon, control)) return
    const name = icon.getAttribute('data-app-icon')
    let played = click.played.get(icon)
    if (played?.has(name)) return
    if (!played) { played = new Set(); click.played.set(icon, played) }
    played.add(name)
    play(icon, control)
  }
  function clicked(event) {
    if (destroyed || media?.matches || imageMode() || (event.button != null && event.button !== 0)) return
    const element = event.target?.nodeType === 1 ? event.target : event.target?.parentElement
    const control = element?.closest?.(CONTROL)
    if (!control || control.closest(BLOCKED)) return
    const until = win.performance.now() + CLICK_WINDOW
    lastClickUntil = Math.max(lastClickUntil, until)
    const click = { until, played: new WeakMap() }
    recentClicks.set(control, click)
    observe()
    // Vue normally updates busy flags and active icons before this microtask.
    // Neither the action nor navigation waits for the animation.
    win.queueMicrotask(() => {
      if (destroyed || media?.matches || imageMode()) return
      for (const icon of control.querySelectorAll('svg[data-app-icon]')) {
        playForClick(icon, control, click)
      }
    })
  }
  function preferenceChanged() { if (media.matches) { recentClicks = new WeakMap(); lastClickUntil = -Infinity; cancelAll(); unobserve() } }
  document.addEventListener('click', clicked)
  media?.addEventListener?.('change', preferenceChanged)
  return {
    destroy() {
      destroyed = true; recentClicks = new WeakMap(); lastClickUntil = -Infinity; document.removeEventListener('click', clicked)
      media?.removeEventListener?.('change', preferenceChanged)
      unobserve(); cancelAll()
    },
  }
}
