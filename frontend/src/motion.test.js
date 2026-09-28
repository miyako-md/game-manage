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
const style = document.createElement('style')
style.textContent = readFileSync(new URL('./motion.css', import.meta.url), 'utf8')
document.head.append(style)

function navigation(t, initial = '') {
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
      offsetWidth: { get: () => 184 }, offsetHeight: { get: () => 42 },
      offsetLeft: { get: () => 0 }, offsetTop: { get: () => index * 46 },
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
