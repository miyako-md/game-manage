import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content } from '../test-utils/vue.js'
const Panel = await loadVue(new URL('./SourceStatusPanel.vue', import.meta.url))
test('collection panel displays retained data, native capability and actual attempts', t => {
  const root = mount(t, Panel, { game: { game_id: 'nte', capabilities: ['progress', 'roles'] }, collection: [
    { game_id: 'nte', capability: 'progress', state: 'error', consecutive_failures: 3, error: '上游异常', last_success_at: '2026-09-14T12:00:00Z', last_attempt_at: '2026-09-14T17:00:00Z' },
  ] })
  const text = content(root)
  for (const expected of ['成就进度', '采集异常', '保留旧数据', '2026-09-14 20:00', '2026-09-15 01:00', '3', '上游异常', '角色练度', '尚未采集']) assert.ok(text.includes(expected), expected)
})

test('first offline attempt never claims an old snapshot was retained', t => {
  const root = mount(t, Panel, { game: { game_id: 'league_of_legends', capabilities: ['account'] },
    collection: [{ game_id: 'league_of_legends', capability: 'account', state: 'offline', last_success_at: null, consecutive_failures: 0 }] })
  assert.match(content(root), /客户端离线.*暂无成功快照/)
  assert.doesNotMatch(content(root), /已保留快照|保留旧数据/)
})
