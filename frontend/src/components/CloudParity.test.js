import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content, flushAsyncComponents } from '../test-utils/vue.js'
import { configureHttpClient } from '../http-client.js'
import { createCloudDashboard } from '../cloud-dashboard.js'
const Card = await loadVue(new URL('./CloudGameCard.vue', import.meta.url))
const App = await loadVue(new URL('../CloudApp.vue', import.meta.url))
const Status = await loadVue(new URL('./CloudSnapshotStatus.vue', import.meta.url))
const Calendar = await loadVue(new URL('./CalendarPage.vue', import.meta.url))
const Articles = await loadVue(new URL('./AnnouncementList.vue', import.meta.url))
const tick = flushAsyncComponents
const button = (root, label) => nodes(root, 'button').find(n => content(n) === label)
const account = (provider, id = provider) => ({ account_id: id, provider, state: 'active', capabilities: ['account', 'stamina'], roles: [{ role_id: `${id}-default`, display_name: `${id}默认角色`, is_default: true }, { role_id: `${id}-other`, display_name: `${id}另一角色` }] })
test('wuwa card forwards calendar and shows public news inside its existing tab', async t => {
  let opened = 0
  const root = mount(t, Card, { account: account('kuro'), role: 'kuro-default', publicSnapshots: { news: { state: 'ok', fetched_at: '2026-10-14T00:00:00Z', payload: [{ title: '公共卡池公告', content: '合成公告' }] } }, onCalendar: () => opened++ })
  await flushAsyncComponents()
  button(root, '活动日历').props.onClick(); assert.equal(opened, 1)
  button(root, '公告与资讯').props.onClick(); await tick()
  assert.match(content(root), /公共卡池公告/)
})
test('nte uses original module summaries and restored guide entry', async t => {
  const root = mount(t, Card, { account: { ...account('tajiduo'), capabilities: ['account','stamina','roles','realestate','gacha'] }, role: 'tajiduo-default', snapshots: { stamina: { payload: { schema_version:1,current:0,maximum:120 } } } })
  await flushAsyncComponents()
  assert.ok(button(root, '角色')); assert.ok(button(root, '房产、载具与探索'))
  assert.ok(nodes(root, 'section').some(n => n.props.class?.includes('nte-module-card')))
  button(root,'角色').props.onClick();await tick();assert.ok(button(root,'浏览全部攻略'));assert.doesNotMatch(content(root), /暂未开放/)
  assert.doesNotMatch(content(root), /审核攻略|管理员来源配置/)
})
test('nte exploration sits with real estate and vehicles, not with roles', async t => {
  const root = mount(t, Card, { account: { ...account('tajiduo'), capabilities: ['account','roles','exploration','realestate'] }, role: 'tajiduo-default' })
  await flushAsyncComponents()
  const modules = () => content(nodes(root, 'div').find(n => n.props.class === 'cap-list'))
  button(root,'角色').props.onClick();await tick();assert.match(modules(), /角色练度/);assert.doesNotMatch(modules(), /探索/)
  button(root,'房产、载具与探索').props.onClick();await tick();assert.match(modules(), /探索进度/);assert.match(modules(), /房产/);assert.doesNotMatch(modules(), /角色练度/)
})
test('overview reads every owner default role and discards delayed results after user changes', async t => {
  const finishes=[]
  const d = createCloudDashboard({ getAccountSnapshot: (id, role, cap) => id === 'b' ? new Promise(resolve => { finishes.push(resolve) }) : Promise.resolve({ payload: { nickname: `${id}/${role}/${cap}` }, state:'ok' }) }); t.after(d.dispose)
  d.state.user = { user_id:'A' }; d.state.accounts = [account('kuro','a'), account('tajiduo','b')]; d.selectAccount(d.state.accounts[0], 'a-other')
  const pending = d.loadOverview(); await tick()
  assert.match(JSON.stringify(d.state.overview), /a-default/); assert.doesNotMatch(JSON.stringify(d.state.overview.a.snapshots), /a-other/)
  d.clear(); d.state.user = { user_id:'B' }; finishes.forEach(resolve=>resolve({ payload:{nickname:'迟到A'}, state:'ok' })); await pending
  assert.deepEqual(d.state.overview, {})
})
test('cloud owner overview navigates to wuwa and its calendar preselects the game', async t => {
  configureHttpClient({mode:'cloud'}); t.after(() => configureHttpClient({mode:'local'}))
  const paths = []
  t.mock.method(globalThis,'fetch', async path => { paths.push(path); return new Response(JSON.stringify(path === '/api/identity/me' ? {user_id:'A'} : path.endsWith('/csrf') ? {csrf_token:'fixture'} : path === '/api/accounts' ? {accounts:[account('kuro'),account('tajiduo')]} : {state:'ok',payload:path.endsWith('/news') ? [{title:'共用公共资讯'}] : path.endsWith('/events') ? [] : {schema_version:1,nickname:'本人昵称',current:0,maximum:120}})) })
  const root = mount(t,App); await tick(); await tick()
  assert.match(content(root), /今日总览/); assert.doesNotMatch(content(root), /数据保存在本机/)
  const overview = nodes(root,'button').find(n => n.props.class?.includes('game-summary') && content(n).includes('鸣潮')); assert.ok(overview)
  overview.props.onClick(); await tick(); await tick()
  assert.match(content(root), /kuro默认角色/)
  button(root,'公告与资讯').props.onClick(); await tick(); assert.match(content(root), /共用公共资讯/)
  nodes(root,'button').filter(n=>content(n)==='活动日历').at(-1).props.onClick(); await tick(); await tick()
  assert.ok(nodes(root,'button').some(n => n.props['aria-label'] === '筛选游戏' && content(n).includes('鸣潮')))
  assert.ok(paths.every(path => !path.startsWith('/api/games/') && !path.startsWith('/api/collection')))
})
test('public source state uses nested source statuses and retains original Beijing content time',t=>{
  const root=mount(t,Status,{capabilities:['news'],snapshots:{news:{state:'ok',fetched_at:'2026-10-14T00:00:00Z',primary_source:'bilibili',version:'3.0',poll_status:{source_statuses:{community:{state:'error',last_success_at:'2026-10-13T00:00:00Z',error:'原生来源失败'},bilibili:{state:'ok',last_success_at:'2026-10-14T00:00:00Z'}}}}}})
  assert.match(content(root),/原生来源失败/);assert.match(content(root),/2026-10-14 08:00/);assert.match(content(root),/版本 3.0/)
})
test('public partial-source failures distinguish fresh contributing fallback from retained stale data', t=>{
  for(const stale of [false,true]) {
    const snap={state:'error',stale,primary_source:'community',fetched_at:'2026-10-14T00:00:00Z',payload:[{name:'可用来源活动',title:'可用来源资讯',source:'community',source_stale:stale,start_at:null,end_at:null}],poll_status:{source_statuses:{community:{state:'ok',stale:false},bilibili:{state:'error',error:'B站412'}}}}
    const calendar=mount(t,Calendar,{games:[{game_id:'wuthering_waves',display_name:'鸣潮',capabilities:['events']}],snapshots:{wuthering_waves:{events:snap}}})
    const articles=mount(t,Articles,{snap}), status=mount(t,Status,{capabilities:['events'],snapshots:{events:snap}})
    assert.match(content(calendar),/可用来源活动/)
    assert.match(content(articles),/可用来源资讯/)
    if(!stale) {
      for(const view of [articles,status])assert.match(content(view),/部分来源不可用，显示可用来源数据/)
      assert.doesNotMatch(content(calendar),/活动更新暂不可用|活动采集失败|保留上次成功快照|数据可能过期/)
      assert.doesNotMatch(content(articles),/采集失败，保留上次成功数据|旧记录|数据可能过期/)
    } else {
      assert.match(content(calendar),/活动更新暂不可用.*正在显示已有活动/)
      const staleDetails=nodes(calendar,'details').find(node=>node.props.class==='calendar-source-states')
      assert.ok(staleDetails)
      assert.ok(!staleDetails.props.open)
      assert.match(content(staleDetails),/数据可能过期/)
      assert.match(content(articles),/采集失败，保留上次成功数据/)
      for(const view of [calendar,articles,status])assert.doesNotMatch(content(view),/部分来源不可用，显示可用来源数据/)
    }
  }
})
