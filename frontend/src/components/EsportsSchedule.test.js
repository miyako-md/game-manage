import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive, nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const Component = await loadVue(new URL('./EsportsSchedule.vue', import.meta.url))
test('zero completed scores stay visible and unsafe links are not rendered', t => {
  const root = mount(t, Component, { filters: {}, payload: { matches: [{ id: 'm', status: 'completed', score_a: 0, score_b: 3, source_url: 'javascript:alert(1)' }] } })
  assert.match(content(root), /0 : 3/); assert.equal(nodes(root, 'a').length, 0)
})

test('linked match is brought into view and focused for keyboard return', async t => {
  const filters = reactive({ matchId: 'target' })
  const root = mount(t, Component, { filters, payload: { matches: [{ id: 'target', status: 'scheduled' }] } })
  const article = nodes(root, 'article')[0]
  let scrolled = false, focused = false
  article.scrollIntoView = () => { scrolled = true }
  article.focus = () => { focused = true }
  await nextTick(); await nextTick()
  assert.ok(scrolled && focused)
  assert.match(content(root), /比赛摘要/)
})
