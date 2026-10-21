import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
const Locked = await loadVue(new URL('./EndfieldLocked.vue', import.meta.url))
const hasClass = (node, name) => String(node.props.class).split(' ').includes(name)

test('each profile tab outlines its own cards and says what connecting adds', t => {
  const expected = {
    operators: ['全员练度', '稀有度分布', '精英阶段', '6★ 干员'], regions: ['地区建设'], ship: ['帝江号', '舱室', '舱室'],
    honor: ['光荣之路', '奖章分类', '最近获得'], challenges: ['挑战记录', '各期星数'],
  }
  for (const [section, titles] of Object.entries(expected)) {
    const root = mount(t, Locked, { section })
    assert.deepEqual(nodes(root, 'h2').map(content), titles, section)
    assert.match(content(nodes(root, 'p')[0]), /^连接森空岛并选择角色后，这里显示.+。$/, section)
  }
})

test('the outline is decoration only: hidden from assistive tech, no controls, no numbers that could be read as data', t => {
  for (const section of ['operators', 'regions', 'ship', 'honor', 'challenges']) {
    const root = mount(t, Locked, { section })
    const grid = nodes(root, 'div').find(node => hasClass(node, 'locked-grid'))
    assert.equal(grid.props['aria-hidden'], 'true')
    for (const type of ['button', 'input', 'select', 'a', 'progress', 'img']) assert.equal(nodes(root, type).length, 0, `${section}: ${type}`)
    assert.doesNotMatch(content(grid).replace(/6★/g, ''), /\d/, section)
  }
})

test('an unknown section falls back to the roster outline instead of an empty page', t => {
  const root = mount(t, Locked, { section: 'nonsense' })
  assert.match(content(root), /稀有度与精英阶段分布/)
})

test('the cloud page hides the note, leaving the explanation to the authorization guide', t => {
  const root = mount(t, Locked, { section: 'operators', note: false })
  assert.equal(nodes(root, 'p').length, 0)
  assert.deepEqual(nodes(root, 'h2').map(content), ['全员练度', '稀有度分布', '精英阶段', '6★ 干员'])
})
