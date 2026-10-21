import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive, nextTick } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'
import { createEsportsBrowseState } from '../esports.js'
const Panel = await loadVue(new URL('./LolEsportsPanel.vue', import.meta.url))
const flush = async () => { await new Promise(setImmediate); await nextTick() }
const button = (root, label) => nodes(root, 'button').find(n => content(n).includes(label))
const snap = () => ({ payload: { schema_version: 1, season_year: 2026, missing_families: ['asian_games'],
  tournaments: [{ id: 't', family: 'lpl', name: '2026 LPL' }],
  matches: [{ id: 'm', tournament_id: 't', team_a_id: 'a', team_b_id: 'b', team_a_name: 'EDG', team_b_name: 'TBD', status: 'scheduled', start_at: '2026-10-04T09:00:00Z' }],
  teams: [{ id: 'a', name: 'EDG', tournament_ids: ['t'] }], players: [{ id: 'p', nickname: 'Player' }],
  roster_memberships: [{ team_id: 'a', player_id: 'p', scope: 'source_current', position: '打野' }],
  coverage: { 'roster:a': { last_success_at: '2026-10-04T00:00:00Z', source_updated_at: '2026-07-02T00:00:00Z', source_lagging: true } },
} })

test('schedule to team to player and back retains filters; roster is not match lineup', async t => {
  const browseState = reactive({ ...createEsportsBrowseState(), family: 'lpl', date: '2026-10-04' })
  const root = mount(t, Panel, { snap: snap(), browseState, 'onBrowse-change': patch => Object.assign(browseState, patch) })
  button(root, 'EDG').props.onClick(); await flush()
  assert.match(content(root), /当前阵容/); assert.match(content(root), /来源阵容可能滞后/)
  button(root, 'Player').props.onClick(); await flush()
  assert.match(content(root), /打野/); assert.match(content(root), /当前阵容/)
  button(root, '返回').props.onClick(); await flush()
  assert.equal(browseState.view, 'teams')
  button(root, '返回').props.onClick(); await flush()
  assert.equal(browseState.view, 'schedule'); assert.equal(browseState.date, '2026-10-04')
  assert.match(content(root), /比分待定/)
})
test('missing current season and refresh failure retain useful cache', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ ok: false, snapshot: snap() })))
  const root = mount(t, Panel, { snap: snap(), browseState: createEsportsBrowseState() })
  assert.match(content(root), /亚运会 LOL.*资料暂缺/)
  button(root, '更新赛事').props.onClick(); await flush()
  assert.match(content(root), /更新未成功/); assert.match(content(root), /EDG/)
})
test('unknown schema has no guessed data', async t => {
  const root = mount(t, Panel, { snap: { payload: { schema_version: 2 } }, browseState: createEsportsBrowseState() })
  assert.match(content(root), /版本不兼容/)
})

test('late refresh preserves new view selection', async t => {
  let resolve
  t.mock.method(globalThis, 'fetch', () => new Promise(r => { resolve = r }))
  const browseState = reactive(createEsportsBrowseState())
  const root = mount(t, Panel, { snap: snap(), browseState, 'onBrowse-change': patch => Object.assign(browseState, patch) })
  button(root, '更新赛事').props.onClick(); await flush()
  button(root, '选手').props.onClick(); await flush()
  resolve(new Response(JSON.stringify({ ok: true, snapshot: snap() }))); await flush()
  assert.equal(browseState.view, 'players'); assert.match(content(root), /Player/)
})

test('web-rendered esports menus keep source choices and reset obsolete detail navigation', async t => {
  const browseState=reactive({...createEsportsBrowseState(),family:'',page:4,filterTeamId:'a',matchId:'m',teamId:'a',returnTo:[{view:'teams'}]})
  const root=mount(t,Panel,{snap:snap(),browseState,'onBrowse-change':patch=>Object.assign(browseState,patch)})
  assert.equal(nodes(root,'select').length,0)
  choose(root,'筛选赛事','lpl');await flush()
  assert.equal(browseState.family,'lpl');assert.equal(browseState.filterTeamId,'')
  assert.equal(browseState.page,1);assert.equal(browseState.matchId,'');assert.equal(browseState.teamId,'');assert.deepEqual(browseState.returnTo,[])
  choose(root,'筛选战队','a');await flush()
  assert.equal(browseState.filterTeamId,'a');assert.match(content(root),/EDG/)
  choose(root,'筛选赛事','asian_games');await flush()
  assert.equal(browseState.filterTeamId,'')
  const teams=nodes(root,'ul').find(n=>n.props['aria-label']==='筛选战队')
  assert.deepEqual(nodes(teams,'li').map(n=>n.props['data-value']),[''])
})

test('restoring an open match detail on mount does not scroll the page, while actively opening a match does', async t => {
  const browseState = reactive({ ...createEsportsBrowseState(), matchId: 'm' })
  const root = mount(t, Panel, { snap: snap(), browseState, 'onBrowse-change': patch => Object.assign(browseState, patch) })
  const restoredArticle = nodes(root, 'article').find(n => String(n.props.class ?? '').includes('es-detail'))
  let scrolled = false, focused = false
  restoredArticle.scrollIntoView = () => { scrolled = true }
  restoredArticle.focus = () => { focused = true }
  await flush()
  assert.equal(scrolled, false)
  assert.equal(focused, false)

  button(root, '← 返回').props.onClick(); await flush()
  assert.equal(browseState.matchId, '')
  const opener = nodes(root, 'button').find(n => n.props['data-open-match'] === 'm')
  opener.props.onClick()
  await nextTick()
  const openedArticle = nodes(root, 'article').find(n => String(n.props.class ?? '').includes('es-detail'))
  openedArticle.scrollIntoView = () => { scrolled = true }
  openedArticle.focus = () => { focused = true }
  await flush()
  assert.equal(scrolled, true)
  assert.equal(focused, true)
})
