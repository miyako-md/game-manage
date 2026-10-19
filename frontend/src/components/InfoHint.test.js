import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { Window } from 'happy-dom'

const window = new Window()
for (const key of ['document', 'Element', 'HTMLElement', 'SVGElement', 'Node']) globalThis[key] = window[key]
Object.assign(globalThis, { window, innerWidth: window.innerWidth, innerHeight: window.innerHeight })
after(() => window.happyDOM.close())

const { createApp, h, nextTick } = await import('vue')
const { loadVue } = await import('../test-utils/vue.js')
const InfoHint = await loadVue(new URL('./InfoHint.vue', import.meta.url))

function escape() {
  const event = new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
  document.body.dispatchEvent(event)
  return event.defaultPrevented
}

test('Escape closes a showing tip without also closing the surrounding dialog', async t => {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp({ render: () => h(InfoHint, { text: '说明文字' }) })
  app.mount(root)
  t.after(() => { app.unmount(); root.remove() })
  const enter = new window.Event('pointerenter')
  Object.defineProperty(enter, 'pointerType', { value: 'mouse' })
  root.querySelector('.info-hint').dispatchEvent(enter)
  await nextTick()
  // A <dialog> treats an Escape keydown that nobody cancelled as a close request.
  assert.equal(escape(), true, 'the tip on screen takes the Escape')
  await nextTick()
  assert.ok(root.querySelector('.info-hint').classList.contains('is-dismissed'))
  assert.equal(escape(), false, 'with the tip gone, Escape is left to the dialog')
})

test('promotes tooltip to popover top layer and clamps horizontal and mobile bottom tabbar bounds', async t => {
  const root = document.createElement('div')
  document.body.append(root)
  const app = createApp({ render: () => h(InfoHint, { text: '说明文字', align: 'start' }) })
  app.mount(root)
  t.after(() => { app.unmount(); root.remove() })
  const hint = root.querySelector('.info-hint')
  const tip = root.querySelector('.info-hint-tip')
  const trigger = root.querySelector('.info-hint-trigger')
  assert.equal(tip.getAttribute('popover'), 'manual')
  let shown = 0, hidden = 0
  tip.showPopover = () => { shown++ }
  tip.hidePopover = () => { hidden++ }
  globalThis.innerWidth = 760
  globalThis.innerHeight = 640
  Object.defineProperty(document.documentElement, 'clientWidth', { value: 760, configurable: true })
  hint.getBoundingClientRect = () => ({ left: 720, right: 744, top: 100, bottom: 520 })
  trigger.click()
  await nextTick()
  assert.equal(shown, 1)
  assert.equal(tip.dataset.side, 'above', 'flips above when near mobile/tablet bottom tabbar')
  assert.equal(tip.style.left, '448px', 'clamps left so a 300px tooltip stays within 12px of the right edge')
  trigger.click()
  await nextTick()
  assert.equal(hidden, 1)
})

