import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const Component = await loadVue(new URL('./EsportsTeams.vue', import.meta.url))
test('a team with missing roster has an explicit missing state', t => {
  const root = mount(t, Component, { filters: { teamId: 'a' }, payload: { teams: [{ id: 'a', name: 'EDG' }] } })
  assert.match(content(root), /EDG/); assert.match(content(root), /阵容资料暂缺/); assert.match(content(root), /来源当前名单/)
})
test('team profile shares compact score rows and preserves a zero score', t => {
  const root = mount(t, Component, { filters: { teamId: 'a' }, payload: {
    teams: [{ id: 'a', name: 'EDG' }], matches: [{ id: 'm', team_a_id: 'a', team_b_id: 'b', team_a_name: 'EDG', team_b_name: 'TBD', status: 'completed', score_a: 0, score_b: 3 }],
  } })
  assert.match(content(root), /0 : 3/)
  assert.ok(nodes(root, 'button').some(n => n.props['data-open-match'] === 'm'))
})
