import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { Window } from 'happy-dom'
import { cardAvoidance, createCardAvoidance } from './card-avoidance.js'

const viewport = { left: 0, right: 1440 }
const box = (left, top, width, height = 200) => ({ left, top, width, height, right: left + width, bottom: top + height })
const menuAt = left => box(left, 20, 220, 400)
const wide = box(24, 100, 1392)

test('cards react independently, with no response outside the menu rectangle', () => {
  const menu = menuAt(16)
  const affected = cardAvoidance(box(24, 100, 900), menu, viewport)
  assert.ok(affected.loss > 0)
  for (const rect of [box(1000, 100, 400), box(24, 500, 900), box(24, -250, 900)]) {
    const result = cardAvoidance(rect, menu, viewport)
    assert.equal(result.loss, 0)
    assert.equal(result.inset, 0)
  }
})

test('edge docking clears a card when there is room, but central travel adds only a limited response', () => {
  const edge = cardAvoidance(wide, menuAt(16), viewport)
  assert.equal(edge.covered, false)
  assert.ok(wide.left + edge.inset >= menuAt(16).right)
  let previous = edge
  for (const x of [150, 300, 500, 650]) {
    const result = cardAvoidance(wide, menuAt(x), viewport, previous.side)
    assert.ok(result.loss - edge.loss <= (x - 16) / 3 + 0.01, 'extra squeezing cannot follow full menu travel')
    assert.ok(result.loss < wide.width / 3 + 0.01, 'the response remains bounded')
    assert.equal(result.side, edge.side, 'crossing the middle must not flip the response direction')
    previous = result
  }
  assert.equal(previous.covered, true, 'a central menu may cover a card once its response is exhausted')
})

test('both small and large cards allow overlap when clearing the menu would squeeze them too far', () => {
  for (const width of [240, 320, 600, 1392]) {
    const rect = box(24, 100, width)
    const menu = menuAt(width < 400 ? 40 : 300)
    const result = cardAvoidance(rect, menu, viewport, 'left')
    assert.equal(result.covered, true, `width ${width}: overlap must remain allowed`)
    assert.ok(result.loss <= width / 3)
    assert.ok(width - result.loss >= Math.min(width, 272), 'a readable card cannot be reduced indefinitely')
    assert.equal(result.inset, result.loss)
  }
})

test('reaching the opposite edge restores a clear response on that side', () => {
  const start = cardAvoidance(wide, menuAt(16), viewport)
  const middle = cardAvoidance(wide, menuAt(600), viewport, start.side)
  const end = cardAvoidance(wide, menuAt(1204), viewport, middle.side)
  assert.equal(middle.side, start.side)
  assert.equal(end.side, 'right')
  assert.equal(end.covered, false)
  assert.equal(end.inset, 0)
  assert.ok(wide.right - end.loss <= menuAt(1204).left)
})

const window = new Window()
after(() => window.happyDOM.close())
function setup(t) {
  const root = window.document.createElement('main')
  root.innerHTML = '<section class="ov-hero"></section><section class="ov-tasks"></section>'
  window.document.body.append(root)
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1440 })
  Object.defineProperty(window, 'scrollY', { configurable: true, value: 0, writable: true })
  let nextId = 0, now = 0
  const frames = new Map()
  t.mock.method(window, 'requestAnimationFrame', callback => { frames.set(++nextId, callback); return nextId })
  t.mock.method(window, 'cancelAnimationFrame', id => frames.delete(id))
  const geometries = [box(24, 100, 900), box(1000, 100, 400)]
  const reads = [0, 0]
  const cards = [...root.children]
  cards.forEach((el, i) => { el.getBoundingClientRect = () => { reads[i]++; return geometries[i] } })
  const controller = createCardAvoidance(root)
  const step = () => {
    const callbacks = [...frames.values()]; frames.clear(); now += 16.67
    callbacks.forEach(callback => callback(now))
  }
  const flush = () => {
    for (let i = 0; i < 240 && frames.size; i++) {
      step()
    }
    assert.equal(frames.size, 0, 'animation must settle')
  }
  t.after(() => { controller.destroy(); root.remove() })
  return { root, cards, geometries, reads, controller, flush, step, frames }
}

test('DOM updates change only overlapping cards and leave elastic transforms untouched', t => {
  const { cards, controller, flush } = setup(t)
  cards[0].style.translate = '4px 2px'
  cards[0].style.rotate = '.2deg'
  cards[0].style.scale = '.994'
  cards[0].style.transform = 'translateY(6px)'
  const before = ['translate', 'rotate', 'scale', 'transform'].map(key => cards[0].style[key])
  controller.update(menuAt(16), true); flush()
  assert.ok(parseFloat(cards[0].style.width) < 900)
  assert.ok(parseFloat(cards[0].style.marginLeft) > 0)
  assert.equal(cards[1].style.cssText, '', 'unaffected cards retain their original styles')
  assert.deepEqual(['translate', 'rotate', 'scale', 'transform'].map(key => cards[0].style[key]), before)
})

test('page and nested-rail scrolling, resize and explicit refresh measure the layout again', t => {
  const { cards, geometries, reads, controller, flush } = setup(t)
  controller.update(menuAt(16), true); flush()
  let previous = reads[0]
  geometries[0] = box(400, 100, 900)
  cards[0].dispatchEvent(new window.Event('scroll'))
  flush()
  assert.ok(reads[0] > previous)
  assert.equal(cards[0].style.width, '', 'a card scrolled away from the menu returns to its normal width')
  previous = reads[0]
  window.document.dispatchEvent(new window.Event('scroll')); flush()
  assert.ok(reads[0] > previous)
  previous = reads[0]
  window.dispatchEvent(new window.Event('resize')); flush()
  assert.ok(reads[0] > previous)
  previous = reads[0]
  geometries[0] = box(24, 100, 900)
  controller.refresh(); flush()
  assert.ok(reads[0] > previous)
  assert.ok(parseFloat(cards[0].style.width) < 900)
})

test('route content replacement is discovered and removed cards recover original styles', async t => {
  const { root, cards, controller, flush } = setup(t)
  cards[0].style.width = '80%'
  controller.update(menuAt(16), true); flush()
  const replacement = window.document.createElement('section')
  replacement.className = 'cap-card'
  replacement.getBoundingClientRect = () => box(24, 100, 800)
  cards[0].replaceWith(replacement)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  flush()
  assert.equal(cards[0].style.width, '80%')
  assert.ok(parseFloat(replacement.style.width) < 800)
  assert.equal(root.contains(replacement), true)
})

test('mobile disable and destruction restore exact inline values and priorities', t => {
  const { cards, controller, flush, frames } = setup(t)
  const card = cards[0]
  card.style.setProperty('width', '80%', 'important')
  card.style.setProperty('margin-left', '3px', 'important')
  card.style.marginRight = '7px'
  card.style.color = 'red'
  const saved = card.style.cssText
  controller.update(menuAt(16), true); flush()
  assert.notEqual(card.style.cssText, saved)
  controller.update(menuAt(16), false)
  assert.equal(card.style.cssText, saved)
  assert.equal(card.hasAttribute('data-menu-avoidance'), false)
  controller.update(menuAt(16), true); flush()
  controller.update(menuAt(300), true)
  assert.ok(frames.size)
  controller.destroy()
  assert.equal(card.style.cssText, saved)
  assert.equal(frames.size, 0)
  window.dispatchEvent(new window.Event('resize'))
  assert.equal(frames.size, 0)
})

test('remeasuring after scroll or resize preserves the approach side while the menu remains central', t => {
  const { cards, geometries, controller, flush } = setup(t)
  geometries[0] = wide
  controller.update(menuAt(16), true); flush()
  controller.update(menuAt(720), true); flush()
  assert.ok(parseFloat(cards[0].style.marginLeft) > 0, 'central travel retains its left-edge approach')
  window.document.dispatchEvent(new window.Event('scroll')); flush()
  assert.ok(parseFloat(cards[0].style.marginLeft) > 0, 'scroll measurement must not switch to the other side')
  window.dispatchEvent(new window.Event('resize')); flush()
  assert.ok(parseFloat(cards[0].style.marginLeft) > 0, 'resize measurement must retain the same approach')
})

test('cards moved by text wrapping in earlier rows use their actual vertical position', t => {
  const { cards, geometries, controller, flush } = setup(t)
  geometries[1] = box(1000, 500, 400)
  controller.update(menuAt(1100), true); flush()
  assert.equal(cards[1].style.width, '')
  // Layout changed without a route mutation, scroll, or viewport resize.
  geometries[1] = box(1000, 100, 400)
  controller.update(menuAt(1100), true); flush()
  assert.ok(parseFloat(cards[1].style.width) < 400)
  geometries[1] = box(1000, 500, 400)
  controller.update(menuAt(1100), true); flush()
  assert.equal(cards[1].style.width, '')
})

test('independent card movement does not resnap every sibling in a horizontal rail', async t => {
  const { root, cards, controller, flush } = setup(t)
  const rail = window.document.createElement('div')
  rail.className = 'h-rail-track'
  rail.style.setProperty('scroll-snap-type', 'x mandatory', 'important')
  rail.style.overflowAnchor = 'auto'
  root.append(rail); rail.append(cards[0])
  await new Promise(resolve => window.setTimeout(resolve, 0))
  controller.update(menuAt(16), true); flush()
  assert.equal(rail.style.scrollSnapType, 'none')
  assert.equal(rail.style.overflowAnchor, 'none')
  controller.update(menuAt(1100), true); flush()
  assert.equal(rail.style.scrollSnapType, 'x mandatory')
  assert.equal(rail.style.getPropertyPriority('scroll-snap-type'), 'important')
  assert.equal(rail.style.overflowAnchor, 'auto')
  controller.update(menuAt(16), true); flush()
  controller.update(null, false)
  assert.equal(rail.style.scrollSnapType, 'x mandatory')
})

test('standalone game navigation, identity and status rows follow the same edge rule as cards', async t => {
  const { root, controller, flush } = setup(t)
  const page = window.document.createElement('section')
  page.className = 'game-card'
  page.innerHTML = '<div class="detail-navigation"><nav>游戏分区</nav></div><header class="lol-header">账号</header><div class="lol-toolbar"><nav>时间与模式</nav></div><p class="coverage-line">当前展示</p><section class="cap-card"><header>卡片里的标题</header></section>'
  for (const el of page.children) el.getBoundingClientRect = () => box(24, 100, 1392)
  root.append(page)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  controller.update(menuAt(16), true); flush()
  for (const el of page.children) {
    assert.ok(parseFloat(el.style.marginLeft) > 0, el.className)
    assert.equal(el.dataset.menuAvoidance, 'clear', el.className)
  }
  assert.equal(page.style.width, '', 'the multi-card page remains in its original layout')
  assert.equal(page.querySelector('.cap-card header').style.width, '', 'content inside a card follows its card once')
})

test('the Endfield pool row and the record list clear the menu as whole rows, since a single pool tile is too narrow to move', async t => {
  const { root, controller, flush } = setup(t)
  const page = window.document.createElement('section')
  page.className = 'endfield-gacha'
  page.innerHTML = '<nav class="eg-pools"><button class="pool-tile">特许寻访</button><button class="pool-tile">武器申领</button></nav><details class="panel record-list"><summary>逐条记录</summary></details>'
  const rows = [...page.querySelectorAll('.eg-pools, .record-list')]
  for (const el of rows) el.getBoundingClientRect = () => box(24, 100, 1392)
  root.append(page)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  controller.update(menuAt(16), true); flush()
  for (const el of rows) {
    assert.ok(parseFloat(el.style.marginLeft) > 0, el.className)
    assert.equal(el.dataset.menuAvoidance, 'clear', el.className)
  }
  assert.equal(page.style.width, '', 'the gacha section keeps its own layout')
  assert.equal(page.querySelector('.pool-tile').style.width, '', 'a tile follows its row once')
})

test('scroll approach grows continuously before the card border reaches the menu', () => {
  const menu = menuAt(16)
  const losses = [1, 12, 32, 64, 96].map(depth => cardAvoidance(box(24, menu.bottom+64-depth, 900), menu, viewport).loss)
  assert.ok(losses[0] < 1)
  assert.ok(losses[1] < losses.at(-1) / 10)
  assert.ok(losses.every((value, i) => !i || value > losses[i-1]))
})

test('scroll and remeasurement keep the current spring position rather than snapping to its target', t => {
  const { cards, geometries, controller, flush, step } = setup(t)
  geometries[0] = box(24, 500, 900)
  controller.update(menuAt(16), true); flush()
  geometries[0] = box(24, 100, 900)
  window.document.dispatchEvent(new window.Event('scroll')); step()
  const first = parseFloat(cards[0].style.marginLeft)
  assert.ok(first > 0 && first < 40, 'the first scroll frame only begins the response')
  controller.refresh(); step()
  const second = parseFloat(cards[0].style.marginLeft)
  assert.ok(second > first && second < 80, 'measurement retains both position and momentum')
  flush()
  const full = parseFloat(cards[0].style.marginLeft)
  assert.ok(full > 200)
  geometries[0] = box(24, 500, 900)
  window.document.dispatchEvent(new window.Event('scroll')); step()
  const returning = parseFloat(cards[0].style.marginLeft)
  assert.ok(returning > 150 && returning < full, 'leaving the menu also returns through the spring')
  flush(); assert.equal(cards[0].style.width, '')
})

test('account panel frames and Wuwa section headings participate without double-moving their children', async t => {
  const { root, controller, flush } = setup(t)
  const panel = window.document.createElement('section')
  panel.className = 'login-panel'; panel.innerHTML='<header class="panel-header">账号</header><div class="account-row">鸣潮</div>'
  const heading=window.document.createElement('header');heading.className='wuwa-board-head';heading.textContent='玩法进度'
  for(const el of [panel, heading]){el.getBoundingClientRect=()=>box(24,100,1392);root.append(el)}
  await new Promise(resolve=>window.setTimeout(resolve,0));controller.update(menuAt(16),true);flush()
  assert.equal(panel.dataset.menuAvoidance,'clear');assert.equal(heading.dataset.menuAvoidance,'clear')
  assert.ok(parseFloat(panel.style.marginLeft)>200)
  assert.equal(panel.querySelector('.account-row').style.width,'')
})

test('Endfield source footer avoids independently when collapsed or expanded, and restores after scrolling', async t => {
  let resize
  t.mock.method(window, 'ResizeObserver', class {
    constructor(callback) { resize = callback }
    observe() {}
    disconnect() {}
  })
  const { root, controller, flush } = setup(t)
  const page = window.document.createElement('section')
  page.className = 'endfield-reports'
  page.innerHTML = '<section class="ef-card"><footer class="ef-source"><details><summary>卡内来源</summary></details></footer></section><footer class="ef-source"><details><summary>档案来源</summary><p>森空岛档案 · 已采集资料</p></details></footer>'
  const [card, footer] = page.children
  const details = footer.querySelector('details')
  let top = 100
  card.getBoundingClientRect = () => box(24, 600, 1392)
  footer.getBoundingClientRect = () => box(24, top, 1392, details.open ? 120 : 32)
  root.append(page)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  controller.update(menuAt(16), true); flush()
  assert.equal(footer.dataset.menuAvoidance, 'clear', 'collapsed source row clears the edge menu')
  assert.ok(parseFloat(footer.style.marginLeft) > 200)
  assert.equal(page.style.width, '', 'the report container keeps its full layout')
  assert.equal(card.style.width, '', 'a separate non-overlapping card stays unchanged')
  for (const child of footer.querySelectorAll('*')) assert.equal(child.style.width, '', 'source contents follow their footer once')

  // Opening details can grow back into the menu from above, without a route
  // mutation or viewport change. ResizeObserver must refresh vertical targets.
  top = -80
  window.document.dispatchEvent(new window.Event('scroll')); flush()
  assert.equal(footer.style.width, '', 'the collapsed row has scrolled above the menu')
  details.open = true
  resize([{ target: footer }]); flush()
  assert.equal(footer.dataset.menuAvoidance, 'clear', 'expanded source content now reaches the menu')
  assert.ok(parseFloat(footer.style.marginLeft) > 200)
  const loss = 1392 - parseFloat(footer.style.width)
  assert.ok(loss <= 1392 / 3, 'the footer keeps the same maximum width loss as cards')
  for (const child of footer.querySelectorAll('*')) assert.equal(child.style.width, '')

  card.getBoundingClientRect = () => box(24, 100, 1392)
  controller.refresh(); flush()
  assert.equal(card.dataset.menuAvoidance, 'clear')
  assert.equal(card.querySelector('.ef-source').style.width, '', 'a source nested inside a participating card is never moved twice')
  top = 600
  window.document.dispatchEvent(new window.Event('scroll')); flush()
  assert.equal(footer.style.cssText, '', 'the source row restores its styles below the menu')
  controller.update(null, false)
  assert.equal(card.style.width, '', 'mobile mode restores participating source containers too')
})

test('Endfield source footer responds immediately with reduced motion and restores when disabled', async t => {
  t.mock.method(window, 'matchMedia', () => ({ matches: true, addEventListener() {}, removeEventListener() {} }))
  const { root, controller, step, frames } = setup(t)
  const footer = window.document.createElement('footer')
  footer.className = 'ef-source'
  footer.innerHTML = '<details open><summary>档案来源</summary><p>森空岛档案</p></details>'
  footer.getBoundingClientRect = () => box(24, 100, 1392, 100)
  root.append(footer)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  controller.update(menuAt(16), true); step()
  assert.equal(footer.dataset.menuAvoidance, 'clear')
  assert.ok(parseFloat(footer.style.marginLeft) > 200)
  assert.equal(frames.size, 0, 'reduced motion does not run a settling animation')
  controller.update(null, false)
  assert.equal(footer.style.cssText, '')
  assert.equal(footer.dataset.menuAvoidance, undefined)
})

test('overview collection progress banner avoids the floating menu when dynamically inserted without double-moving its children', async t => {
  const { root, controller, flush } = setup(t)
  controller.update(menuAt(16), true); flush()
  const status = window.document.createElement('section')
  status.className = 'ov-collect-status'
  status.innerHTML = '<ul><li><strong>鸣潮</strong><span>采集中</span></li></ul><p>已同时请求刷新本人账号的 3 项私人数据。</p>'
  status.getBoundingClientRect = () => box(24, 100, 1392, 68)
  root.prepend(status)
  await new Promise(resolve => window.setTimeout(resolve, 0))
  flush()
  assert.equal(status.dataset.menuAvoidance, 'clear')
  assert.ok(parseFloat(status.style.marginLeft) > 200)
  for (const child of status.querySelectorAll('*')) assert.equal(child.style.width, '')
})
