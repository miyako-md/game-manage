import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive, nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
import { createEsportsBrowseState } from '../esports.js'
const Panel = await loadVue(new URL('./LolEsportsPanel.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
const button = (r, name) => nodes(r, 'button').find(n => content(n).trim() === name)
const snapshot = () => ({ stale: true, payload: { schema_version: 1, season_year: 2026, missing_families: ['worlds'],
  tournaments: [{ id: 't', family: 'lpl', name: 'LPL' }], teams: [{ id: 'a', name: 'Alpha', tournament_ids: ['t'] }, { id: 'b', name: 'Beta', tournament_ids: ['t'] }],
  matches: Array.from({ length: 23 }, (_, i) => ({ id: 'm' + i, tournament_id: 't', team_a_id: 'a', team_b_id: 'b', team_a_name: 'Alpha', team_b_name: 'Beta', status: 'completed', start_at: `2026-09-${String(i + 1).padStart(2, '0')}T09:00:00Z`, score_a: 0, score_b: 3, winner_team_id: 'b' })) } })
test('results page and detail return preserve page, filters and row focus target', async t => {
  const browse = reactive({ ...createEsportsBrowseState(), view: 'results', family: 'lpl' })
  const root = mount(t, Panel, { snap: snapshot(), browseState: browse, 'onBrowse-change': patch => Object.assign(browse, patch) })
  assert.ok(button(root, '下一页'), 'result pagination is available')
  button(root, '下一页').props.onClick(); await flush()
  assert.equal(browse.page, 2)
  const opener = nodes(root, 'button').find(n => n.props['data-open-match'] === 'm2')
  assert.ok(opener); opener.props.onClick(); await flush()
  assert.match(content(root), /比赛摘要/); assert.match(content(root), /0 : 3/)
  button(root, '← 返回').props.onClick(); await flush()
  assert.equal(browse.page, 2); assert.equal(browse.family, 'lpl'); assert.equal(browse.matchId, '')
  assert.ok(nodes(root, 'button').some(n => n.props['data-open-match'] === 'm2'))
})
test('cached-only results remain useful while missing future coverage and unknown winner are explicit', t => {
  const snap = snapshot(); snap.payload.matches = [{ ...snap.payload.matches[0], winner_team_id: 'unrelated' }]
  const root = mount(t, Panel, { snap, browseState: createEsportsBrowseState() })
  assert.match(content(root), /当前缓存未收录进行中或未来比赛/)
  assert.match(content(root), /近期赛果/); assert.match(content(root), /胜者未确认/)
  assert.match(content(root), /全球总决赛.*资料暂缺/)
  assert.equal(nodes(root, 'span').filter(n => n.props.class === 'es-outcome').length, 0)
})
test('changing a match filter resets pagination and clears match detail', async t => {
  const browse = reactive({ ...createEsportsBrowseState(), view: 'results', page: 2 })
  const root = mount(t, Panel, { snap: snapshot(), browseState: browse, 'onBrowse-change': patch => Object.assign(browse, patch) })
  const teamSelect = nodes(root, 'select').find(n => n.props['aria-label'] === '筛选战队')
  assert.ok(teamSelect); teamSelect.props.onChange({ target: { value: 'a' } }); await flush()
  assert.equal(browse.filterTeamId, 'a'); assert.equal(browse.page, 1)
})
test('mobile filter disclosure has an explicit operable expanded state', async t => {
  const root = mount(t, Panel, { snap: snapshot(), browseState: createEsportsBrowseState() })
  const toggle = nodes(root, 'button').find(n => n.props['aria-controls'] === 'es-filter-fields')
  assert.ok(toggle); assert.equal(toggle.props['aria-expanded'], false)
  toggle.props.onClick(); await flush()
  assert.equal(toggle.props['aria-expanded'], true)
})
