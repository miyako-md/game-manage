import { stepSpringRk4 } from './motion.js'

const CARD = [
  '.workspace-topbar', '.page-heading', '.h-rail-head', '.ov-section > .section-heading', '.ov-hero', '.ov-tasks', '.ov-deadlines', '.ov-gacha', '.ov-news', '.ov-game', '.event-card',
  '.card-head', '.cap-card', '.wuwa-panel', '.wuwa-board-head', '.wuwa-board > .toolbar', '.wuwa-role', '.calendar-board', '.calendar-agenda', '.calendar-detail', '.account-row',
  '.calendar-stat', '.calendar-split', '.ef-card', '.ef-count', '.ef-locked', '.ef-detail > .ef-detail-toolbar', '.ef-detail > header', '.ef-detail > .ef-detail-time', '.eg-card', '.endfield-gacha > .eg-pools', '.endfield-gacha > .record-list', '.pool-card', '.hl-card', '.challenge-report',
  '.ef-news-summary', '.ef-attendance', '.ef-source', '.loadout-hero', '.loadout-module', '.ef-gacha-summary', '.ef-tactical', '.match-item', '.match-detail', '.role-card',
  '.game-card > .error-bar', '.game-card > .detail-navigation', '.wuwa-nav', '.endfield-nav', '.endfield-stack > p',
  '.lol-header', '.lol-toolbar', '.coverage-line', '.lol-dashboard > .lol-notice', '.lol-dashboard > .lol-error', '.lol-view > .legacy-note',
  '.es-header', '.esports-panel > .es-note', '.esports-panel > .es-warning', '.es-notices', '.es-tabs', '.es-filter-disclosure', '.es-footer',
  '.ov-collect-status', '.ov-alert', '.inline-warning', '.service-error', '.cloud-content > p', '.cloud-game-heading', '.cloud-calendar-controls',
  '.login-panel', '.connection-note', '.cloud-account-settings > h2', '.cloud-account-settings > p',
  '.bili-panel', '.cloud-owner-note > summary', '.cloud-owner-note > p',
  '.cloud-snapshot-states > summary', '.cloud-snapshot-states > div',
].join(', ')
const PROPERTIES = ['width', 'margin-left', 'margin-right']
const GAP = 16

/** Each card keeps its own layout slot. A menu can overlap it once its limited
 * response is exhausted; resolving a collision never squeezes the whole page. */
export function cardAvoidance(rect, menu, viewport, previousSide) {
  const ramp = Math.max(1, Math.min(96, (rect.bottom - rect.top) / 2, (menu.bottom - menu.top) / 4))
  const lead = Math.min(64, ramp)
  const overlap = Math.min(rect.bottom, menu.bottom + lead) - Math.max(rect.top, menu.top - lead)
  if (rect.left >= menu.right || rect.right <= menu.left || overlap <= 0) return { inset: 0, loss: 0, side: null, covered: false }
  const distances = { left: menu.right + GAP - rect.left, right: rect.right - menu.left + GAP }
  const nearLeft = menu.left <= viewport.left + menu.width * .5
  const nearRight = menu.right >= viewport.right - menu.width * .5
  let side = previousSide || (distances.left < distances.right ? 'left' : 'right')
  // Keep the approach direction while crossing a card, rather than switching
  // sides at its centre. Only a nearby exit or a viewport edge can change it.
  if (nearLeft) side = 'left'
  else if (nearRight) side = 'right'
  else if (distances.left <= menu.width / 3) side = 'left'
  else if (distances.right <= menu.width / 3) side = 'right'
  const dockInset = side === 'left'
    ? Math.max(0, viewport.left + menu.width + GAP * 2 - rect.left)
    : Math.max(0, rect.right - (viewport.right - menu.width - GAP * 2))
  const readableWidth = Math.min(rect.width, 272)
  const limit = Math.max(0, Math.min(rect.width / 3, rect.width - readableWidth))
  const required = distances[side]
  const canClear = required <= limit && (nearLeft || nearRight || required <= menu.width / 3)
  const response = dockInset + Math.min(Math.max(0, required - dockInset) / 3, menu.width / 3)
  // Begin gently before the border touches the menu, so headings have room by
  // the time they reach it. Pressure and its slope stay continuous at both ends.
  const t = Math.min(1, overlap / ramp)
  const pressure = t * t * (3 - 2 * t)
  const loss = Math.min(limit, required, canClear ? required : response) * pressure
  return { inset: side === 'left' ? loss : 0, loss, side, covered: loss < required }
}

export function createCardAvoidance(root) {
  const view = root?.ownerDocument?.defaultView
  if (!view || !root.querySelectorAll) return { update() {}, refresh() {}, destroy() {} }
  const doc = root.ownerDocument
  const media = view.matchMedia('(prefers-reduced-motion: reduce)')
  const rails = new Map()
  const heights = new WeakMap()
  const sizes = view.ResizeObserver ? new view.ResizeObserver(entries => {
    let changed = false
    for (const { target } of entries) {
      const height = target.getBoundingClientRect().height
      if (heights.get(target) !== height) { heights.set(target, height); changed = true }
    }
    // Expanded navigation rows and wrapped content can move the rows below
    // without adding nodes or changing the viewport. Width writes alone do not
    // invalidate the original horizontal slots or restart their measurement.
    if (changed) schedule()
  }) : null
  let records = [], menu = null, enabled = false, listening = false, dirty = true, frame = 0, time = 0, disposed = false
  function restoreRail(rail, saved) {
    for (const [name, value, priority] of saved) {
      if (value) rail.style.setProperty(name, value, priority)
      else rail.style.removeProperty(name)
    }
    rails.delete(rail)
  }
  function syncRails() {
    const active = new Set(records.filter(record => record.target.loss > 0 || record.loss >= .05)
      .map(record => record.el.closest('.h-rail-track')).filter(Boolean))
    for (const rail of active) {
      if (rails.has(rail)) continue
      rails.set(rail, ['scroll-snap-type', 'overflow-anchor'].map(name => [name, rail.style.getPropertyValue(name), rail.style.getPropertyPriority(name)]))
      // Resizing the first card changes its snap point. Keep the track still
      // instead of letting the browser scroll every sibling along with it.
      rail.style.scrollSnapType = 'none'
      rail.style.overflowAnchor = 'none'
    }
    for (const [rail, saved] of rails) if (!active.has(rail)) restoreRail(rail, saved)
  }
  const restore = record => {
    PROPERTIES.forEach((name, i) => {
      const [value, priority] = record.saved[i]
      if (value) record.el.style.setProperty(name, value, priority)
      else record.el.style.removeProperty(name)
    })
    delete record.el.dataset.menuAvoidance
  }
  function measure() {
    const previous = new Map(records.map(record => [record.el, record]))
    records.forEach(restore)
    sizes?.disconnect()
    const nodes = [...root.querySelectorAll(CARD)].filter(el => !el.parentElement?.closest(CARD)
      && !el.closest('dialog, .sheet-dialog, .render-image, [hidden]'))
    records = nodes.flatMap(el => {
      const rect = el.getBoundingClientRect()
      if (!rect.width || !rect.height) return []
      const style = view.getComputedStyle(el)
      const old = previous.get(el)
      return [{ el, rect: { left: rect.left, right: rect.right, top: rect.top + view.scrollY, bottom: rect.bottom + view.scrollY, width: rect.width },
        saved: PROPERTIES.map(name => [el.style.getPropertyValue(name), el.style.getPropertyPriority(name)]),
        ml: parseFloat(style.marginLeft) || 0, mr: parseFloat(style.marginRight) || 0,
        inset: old?.inset || 0, loss: old?.loss || 0, vi: old?.vi || 0, vl: old?.vl || 0,
        target: null, side: old?.side || null, fresh: !old }]
    })
    for (const record of records) sizes?.observe(record.el)
    dirty = false
  }
  function targets() {
    const viewport = { left: 0, right: doc.documentElement.clientWidth || view.innerWidth }
    for (const record of records) {
      // Width changes can wrap text and move later rows. Read their actual
      // vertical positions, while keeping horizontal geometry in original slots.
      const actual = record.el.getBoundingClientRect()
      const rect = { ...record.rect, top: actual.top, bottom: actual.bottom }
      record.target = cardAvoidance(rect, menu, viewport, record.side)
      record.side = record.target.side
    }
  }
  function paint(record) {
    if (record.loss < .05 && record.target.loss === 0) { restore(record); return }
    record.el.style.width = `${(record.rect.width - record.loss).toFixed(2)}px`
    // Both margins preserve the original slot, including inside horizontal rails.
    // Other cards neither inherit this offset nor get pushed out of their slots.
    record.el.style.marginLeft = `${(record.ml + record.inset).toFixed(2)}px`
    record.el.style.marginRight = `${(record.mr + record.loss - record.inset).toFixed(2)}px`
    record.el.dataset.menuAvoidance = record.target.covered ? 'overlap' : 'clear'
  }
  function tick(now) {
    frame = 0
    if (disposed || !enabled || !menu) return
    if (dirty) measure()
    targets()
    syncRails()
    const dt = Math.min(.032, time ? (now - time) / 1000 : 1 / 60)
    time = now
    let moving = false
    for (const record of records) {
      for (const [key, velocity] of [['inset', 'vi'], ['loss', 'vl']]) {
        const target = record.target[key]
        if (record.fresh || media.matches) { record[key] = target; record[velocity] = 0 }
        else {
          ;[record[key], record[velocity]] = stepSpringRk4(record[key], record[velocity], target, 260, 28, dt)
          if (Math.abs(target - record[key]) < .05 && Math.abs(record[velocity]) < .1) { record[key] = target; record[velocity] = 0 }
          else moving = true
        }
      }
      record.fresh = false
      paint(record)
    }
    if (moving) frame = view.requestAnimationFrame(tick)
    else { time = 0; syncRails() }
  }
  function schedule() { if (!disposed && enabled && !frame) frame = view.requestAnimationFrame(tick) }
  function refresh() { dirty = true; schedule() }
  function scrolled(event) {
    // Page scrolling only changes vertical targets: preserve position and
    // momentum. A nested rail can change the original horizontal slots.
    if (event.target?.nodeType === 1 && event.target !== doc.body && event.target !== doc.documentElement) refresh()
    else schedule()
  }
  const observer = new view.MutationObserver(changes => {
    if (changes.some(change => [...change.addedNodes, ...change.removedNodes].some(node => node.nodeType === 1))) refresh()
  })
  function connect() {
    if (listening || disposed) return
    listening = true
    observer.observe(root, { childList: true, subtree: true })
    // Scroll is not cancelled. Re-measure horizontal rails against their own slots.
    doc.addEventListener('scroll', scrolled, { capture: true, passive: true })
    view.addEventListener('resize', refresh)
    media.addEventListener?.('change', schedule)
  }
  function disconnect() {
    if (!listening) return
    listening = false
    observer.disconnect()
    sizes?.disconnect()
    doc.removeEventListener('scroll', scrolled, true)
    view.removeEventListener('resize', refresh)
    media.removeEventListener?.('change', schedule)
  }
  return {
    update(rect, active) {
      menu = rect
      if (!active) {
        if (!enabled && !records.length && !rails.size) return
        enabled = false
        disconnect()
        if (frame) view.cancelAnimationFrame(frame)
        frame = 0; time = 0; dirty = true
        records.forEach(restore); records = []
        for (const [rail, saved] of rails) restoreRail(rail, saved)
        return
      }
      enabled = true
      connect()
      schedule()
    },
    refresh,
    destroy() {
      disposed = true
      disconnect()
      if (frame) view.cancelAnimationFrame(frame)
      records.forEach(restore); records = []
      for (const [rail, saved] of rails) restoreRail(rail, saved)
    },
  }
}
