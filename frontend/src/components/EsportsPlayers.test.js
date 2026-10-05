import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content } from '../test-utils/vue.js'
const Component = await loadVue(new URL('./EsportsPlayers.vue', import.meta.url))
test('national and club relations coexist without guessed transfer dates', t => {
  const root = mount(t, Component, { filters: { playerId: 'p' }, payload: { players: [{ id: 'p', nickname: 'Player' }], teams: [{ id: 'a', name: 'Club' }, { id: 'b', name: 'National' }], roster_memberships: [{ team_id: 'a', player_id: 'p', scope: 'source_current' }, { team_id: 'b', player_id: 'p', scope: 'season_registered' }] } })
  assert.match(content(root), /Club/); assert.match(content(root), /National/); assert.match(content(root), /位置未提供/); assert.match(content(root), /赛季报名阵容/)
})
test('player directory shows source position without inferring match appearances', t => {
  const root = mount(t, Component, { filters: {}, payload: {
    players: [{ id: 'p', nickname: 'Player' }], teams: [{ id: 'a', name: 'Club' }],
    roster_memberships: [{ team_id: 'a', player_id: 'p', scope: 'source_current', position: '打野' }],
  } })
  assert.match(content(root), /打野/); assert.match(content(root), /来源阵容/)
})
