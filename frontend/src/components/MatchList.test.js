import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const MatchList = await loadVue(new URL('./MatchList.vue', import.meta.url))
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r }); return { promise, resolve } }
const detail = name => new Response(JSON.stringify({ payload: { teams: [{ team_id: 100, win: true, participants: [{ champion_name: name }] }] } }))

test('switching matches ignores stale detail and stale loading cleanup', async t => {
  const first = deferred(), second = deferred()
  t.mock.method(globalThis, 'fetch', async url => url.includes('/first/') ? first.promise : second.promise)
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [{ match_id: 'first' }, { match_id: 'second' }] } })
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[1].props.onClick(); await nextTick()
  first.resolve(detail('不应出现的旧详情')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /对局详情加载中/)
  assert.doesNotMatch(content(root), /不应出现/)
  second.resolve(detail('当前对局详情')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /当前对局详情/)
})

test('a closed detail response cannot overwrite a newly selected match', async t => {
  const first = deferred(), second = deferred()
  t.mock.method(globalThis, 'fetch', async url => url.includes('/first/') ? first.promise : second.promise)
  const root = mount(t, MatchList, { gameId: 'lol', snap: { payload: [{ match_id: 'first' }, { match_id: 'second' }] } })
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[0].props.onClick(); await nextTick()
  nodes(root, 'button')[1].props.onClick(); await nextTick()
  second.resolve(detail('当前')); await new Promise(setImmediate); await nextTick()
  first.resolve(detail('旧')); await new Promise(setImmediate); await nextTick()
  assert.match(content(root), /当前/); assert.doesNotMatch(content(root), /旧/)
})
