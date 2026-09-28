import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { Window } from 'happy-dom'

const window = new Window()
for (const key of ['document', 'Element', 'HTMLElement', 'SVGElement', 'Node', 'MutationObserver', 'ResizeObserver']) {
  globalThis[key] = window[key]
}
globalThis.window = window
globalThis.matchMedia = window.matchMedia.bind(window)
let nextFrame = 0
const frames = new Map()
globalThis.requestAnimationFrame = callback => { frames.set(++nextFrame, callback); return nextFrame }
globalThis.cancelAnimationFrame = id => frames.delete(id)
function flushFrames() {
  const callbacks = [...frames.values()]
  frames.clear()
  callbacks.forEach(callback => callback())
}
after(() => window.happyDOM.close())

const { createApp, h, nextTick, ref, withDirectives } = await import('vue')
const { vGlide, vSpotlight } = await import('./motion.js')
const { loadVue } = await import('./test-utils/vue.js')
const WuwaRoleDialog = await loadVue(new URL('./components/WuwaRoleDialog.vue', import.meta.url))
const style = document.createElement('style')
style.textContent = readFileSync(new URL('./motion.css', import.meta.url), 'utf8')
document.head.append(style)

function navigation(t, initial = '', horizontal = false) {
  const selected = ref(initial)
  const games = ref(['鸣潮', '英雄联盟', '异环', '终末地'])
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp({ render: () => withDirectives(h('nav', {
    class: ['game-nav', { 'game-theme': !!selected.value }],
  }, games.value.map(name => h('a', {
    href: `#${name}`, class: { active: selected.value === name },
    'aria-current': selected.value === name ? 'page' : undefined,
  }, [h('img', { alt: `${name}图标` }), h('span', name)]))), [[vGlide, undefined, undefined, { hover: true }]]) })
  app.mount(root)
  const nav = root.querySelector('nav')
  // happy-dom runs Vue's real DOM patcher; geometry is supplied because it has no layout engine.
  for (const [index, link] of [...nav.querySelectorAll('a')].entries()) {
    Object.defineProperties(link, {
      offsetWidth: { get: () => horizontal ? 90 : 184 }, offsetHeight: { get: () => 42 },
      offsetLeft: { get: () => horizontal ? index * 100 : 0 }, offsetTop: { get: () => horizontal ? 0 : index * 46 },
    })
  }
  const unmount = () => { app.unmount(); root.remove() }
  t.after(() => { unmount(); frames.clear() })
  return { nav, games, selected, unmount }
}

test('Vue class updates keep all game labels and icons above the selected background', async t => {
  const { nav, selected } = navigation(t)
  for (const name of ['鸣潮', '终末地', '异环', '英雄联盟', '', '鸣潮']) {
    selected.value = name
    await nextTick()
    flushFrames()
    assert.equal(window.getComputedStyle(nav).position, 'relative')
    assert.equal(window.getComputedStyle(nav).isolation, 'isolate')
    for (const link of nav.querySelectorAll('a')) {
      assert.equal(window.getComputedStyle(link).position, 'relative', `${name}: link must keep its own layer`)
      assert.equal(window.getComputedStyle(link).zIndex, '1')
      assert.ok(link.querySelector('img'))
      assert.ok(link.textContent)
    }
    const pill = nav.querySelector('.t-glide')
    assert.equal(window.getComputedStyle(pill).zIndex, '0')
    assert.equal(window.getComputedStyle(pill).pointerEvents, 'none')
    assert.equal(pill.style.opacity, name ? '1' : '0')
    if (name) assert.equal(pill.style.transform, `translate(0px, ${['鸣潮', '英雄联盟', '异环', '终末地'].indexOf(name) * 46}px)`)
  }
})

test('selection recognizes aria-current without a class and ignores nested active content', async t => {
  const { nav } = navigation(t)
  nav.querySelector('a span').className = 'active'
  const links = nav.querySelectorAll('a')
  links[2].setAttribute('aria-current', 'page')
  vGlide.updated(nav)
  flushFrames()
  assert.equal(nav.querySelector('.t-glide').style.transform, 'translate(0px, 92px)')
  links[2].removeAttribute('aria-current')
  vGlide.updated(nav)
  flushFrames()
  assert.equal(nav.querySelector('.t-glide').style.opacity, '0')
})

test('a hovered item becoming selected clears the hover background', async t => {
  t.mock.method(globalThis, 'matchMedia', () => ({ matches: true }))
  const { nav, selected } = navigation(t)
  nav.querySelector('a img').dispatchEvent(new window.PointerEvent('pointerover', { bubbles: true, pointerType: 'mouse' }))
  assert.equal(nav.querySelector('.t-glide-hover').style.opacity, '1')
  selected.value = '鸣潮'
  await nextTick()
  flushFrames()
  assert.equal(nav.querySelector('.t-glide-hover').style.opacity, '0')
  assert.equal(nav.querySelector('.t-glide').style.opacity, '1')
})

test('rapid selections settle on the last item and disposal cancels pending work', async t => {
  const { nav, selected, unmount } = navigation(t)
  selected.value = '鸣潮'
  selected.value = '异环'
  selected.value = '终末地'
  await nextTick()
  flushFrames()
  assert.equal(nav.querySelector('.t-glide').style.transform, 'translate(0px, 138px)')
  vGlide.updated(nav)
  assert.ok(frames.size > 0)
  unmount()
  assert.equal(frames.size, 0)
  assert.equal(nav.querySelector('.t-glide'), null)
  assert.equal(nav.hasAttribute('data-glide'), false)
})

test('removing the selected game hides the indicator', async t => {
  const { nav, selected, games } = navigation(t)
  selected.value = '异环'
  await nextTick()
  flushFrames()
  games.value = []
  await nextTick()
  flushFrames()
  assert.equal(nav.querySelector('.t-glide').style.opacity, '0')
})

test('an offscreen selected tab scrolls into view without overriding manual scrolling', async t => {
  const { nav, selected } = navigation(t, '', true)
  Object.defineProperties(nav, { clientWidth: { value: 180 }, scrollWidth: { value: 400 } })
  const scroll = t.mock.method(nav, 'scrollTo', ({ left }) => { nav.scrollLeft = left })
  selected.value = '异环'
  await nextTick()
  flushFrames()
  assert.deepEqual(scroll.mock.calls[0].arguments[0], { left: 155, behavior: 'smooth' })
  nav.scrollLeft = 0
  vGlide.updated(nav)
  flushFrames()
  assert.equal(scroll.mock.callCount(), 1)
  selected.value = '鸣潮'
  await nextTick()
  flushFrames()
  assert.equal(scroll.mock.callCount(), 1, 'visible controls must not move the strip')
})

test('tab scrolling respects reduced motion and clamps at the end of the strip', async t => {
  t.mock.method(globalThis, 'matchMedia', query => ({ matches: query.includes('prefers-reduced-motion') }))
  const { nav, selected } = navigation(t, '', true)
  Object.defineProperties(nav, { clientWidth: { value: 180 }, scrollWidth: { value: 400 } })
  const scroll = t.mock.method(nav, 'scrollTo', () => {})
  selected.value = '终末地'
  await nextTick()
  flushFrames()
  assert.deepEqual(scroll.mock.calls[0].arguments[0], { left: 220, behavior: 'auto' })
})

test('card spotlight coalesces movement, honors reduced motion, and cleans up', t => {
  const media = new window.EventTarget()
  media.matches = true
  t.mock.method(globalThis, 'matchMedia', () => media)
  const card = document.createElement('button')
  card.getBoundingClientRect = () => ({ left: 20, top: 40 })
  vSpotlight.mounted(card)
  const move = (x, y, pointerType = 'mouse') => card.dispatchEvent(new window.PointerEvent('pointermove', { clientX: x, clientY: y, pointerType }))
  move(50, 80); move(90, 100)
  assert.equal(frames.size, 1)
  flushFrames()
  assert.equal(card.style.getPropertyValue('--spotlight-x'), '70px')
  assert.equal(card.style.getPropertyValue('--spotlight-y'), '60px')
  assert.ok(card.hasAttribute('data-spotlight-active'))
  move(70, 90)
  media.matches = false
  media.dispatchEvent(new window.Event('change'))
  assert.equal(frames.size, 0)
  assert.equal(card.hasAttribute('data-spotlight-active'), false)
  move(100, 100)
  assert.equal(frames.size, 0)
  media.matches = true
  move(100, 100, 'touch')
  assert.equal(frames.size, 0)
  move(100, 100)
  vSpotlight.unmounted(card)
  assert.equal(frames.size, 0)
  move(120, 120)
  assert.equal(frames.size, 0)
})

test('reduced-motion styles disable transitions and entrances while retaining navigation layers', async () => {
  const reduced = new Window({ settings: { device: { prefersReducedMotion: 'reduce' } } })
  try {
    const sheet = reduced.document.createElement('style')
    sheet.textContent = style.textContent + readFileSync(new URL('./style.css', import.meta.url), 'utf8')
    reduced.document.head.append(sheet)
    reduced.document.body.innerHTML = '<nav data-glide class="game-nav game-theme"><span class="t-glide"></span><a class="active">鸣潮</a></nav><div class="t-item">内容</div>'
    const css = el => reduced.getComputedStyle(reduced.document.querySelector(el))
    assert.equal(css('.t-item').animation, 'none')
    assert.equal(css('.t-glide').transition, 'none')
    assert.equal(css('a').zIndex, '1')
    assert.equal(css('.t-glide').zIndex, '0')
  } finally {
    await reduced.happyDOM.close()
  }
})

function modal(t, reducedMotion = false) {
  t.mock.method(globalThis, 'matchMedia', () => ({ matches: reducedMotion }))
  const trigger = document.createElement('button')
  const root = document.createElement('div')
  document.body.append(trigger, root)
  trigger.focus()
  const open = ref(true)
  let closes = 0
  const app = createApp({ render: () => open.value ? h(WuwaRoleDialog, {
    title: '账号档案', eyebrow: 'WUTHERING WAVES', onClose() { closes++; open.value = false },
  }, () => h('p', '账号详情')) : null })
  app.mount(root)
  const dialog = root.querySelector('dialog')
  const button = dialog.querySelector('button')
  t.after(() => { app.unmount(); root.remove(); trigger.remove() })
  return { dialog, button, trigger, open, closes: () => closes }
}

test('dialog keeps its modal state through the exit, then restores focus and scrolling once', async t => {
  const { dialog, button, trigger, closes } = modal(t)
  assert.equal(dialog.open, true)
  assert.equal(document.body.style.overflow, 'hidden')
  assert.equal(document.getElementById(dialog.getAttribute('aria-labelledby')).textContent, '账号档案')
  button.focus()
  button.click(); button.click()
  await nextTick()
  assert.equal(closes(), 0)
  assert.equal(dialog.open, true)
  assert.equal(dialog.hasAttribute('data-closing'), true)
  button.dispatchEvent(new window.AnimationEvent('animationend', { bubbles: true, animationName: 't-dialog-exit' }))
  assert.equal(closes(), 0, 'a child animation must not close the dialog')
  dialog.dispatchEvent(new window.AnimationEvent('animationend', { animationName: 't-dialog-exit' }))
  await nextTick()
  assert.equal(closes(), 1)
  assert.equal(dialog.isConnected, false)
  assert.equal(document.activeElement, trigger)
  assert.equal(document.body.style.overflow, '')
})

test('Escape closes a reduced-motion dialog immediately and backdrop drags do not dismiss it', async t => {
  const { dialog, button, closes } = modal(t, true)
  button.dispatchEvent(new window.PointerEvent('pointerdown', { bubbles: true }))
  dialog.click()
  await nextTick()
  assert.equal(closes(), 0)
  dialog.dispatchEvent(new window.Event('cancel', { cancelable: true }))
  await nextTick()
  assert.equal(closes(), 1)
  assert.equal(dialog.isConnected, false)
})

test('dialog close has a bounded fallback when animation events do not arrive', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { dialog, closes } = modal(t)
  dialog.dispatchEvent(new window.PointerEvent('pointerdown', { bubbles: true }))
  dialog.click()
  await nextTick()
  assert.equal(closes(), 0)
  t.mock.timers.tick(220)
  await nextTick()
  assert.equal(closes(), 1)
})

test('unmounting during dialog exit cancels the deferred close', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const { dialog, button, open, closes } = modal(t)
  button.click()
  await nextTick()
  open.value = false
  await nextTick()
  t.mock.timers.tick(300)
  dialog.dispatchEvent(new window.AnimationEvent('animationend', { animationName: 't-dialog-exit' }))
  assert.equal(closes(), 0)
  assert.equal(document.body.style.overflow, '')
})
