import test from 'node:test'
import assert from 'node:assert/strict'
import { reactive } from 'vue'
import { loadVue, mount, nodes, content, flushAsyncComponents } from '../test-utils/vue.js'

const Card = await loadVue(new URL('./GameCard.vue', import.meta.url))
const game = (game_id, capabilities) => ({game_id,display_name:game_id,capabilities,credentials_configured:false})

test('integrated NTE keeps inline resources and guides inside the role module', async t => {
  const root=mount(t,Card,{game:game('nte',['stamina','roles']),externalSnapshots:{stamina:{payload:{schema_version:1,current:0,maximum:320}}}})
  await flushAsyncComponents()
  assert.ok(nodes(root,'progress').some(n=>n.props.value===0 && n.props.max===320))
  assert.ok(!nodes(root,'button').some(n=>/查看体力/.test(content(n))))
  const guides=nodes(root,'button').find(n=>content(n)==='浏览全部攻略')
  assert.ok(guides);guides.props.onClick();await flushAsyncComponents()
  assert.equal(nodes(root,'dialog').length,1)
  assert.ok(!nodes(root,'nav').filter(n=>n.props['aria-label']==='游戏数据分区').some(n=>content(n).includes('角色攻略')))
})

test('ordinary local shell hides collection diagnostics and keeps a useful reauthorization notice', async t => {
  const root=mount(t,Card,{game:{...game('nte',['stamina']),credentials_configured:true},externalSnapshots:{stamina:{payload:{schema_version:1,current:20,maximum:320}}},externalError:'private_collector_error',collectionStatus:[{game_id:'nte',capability:'stamina',state:'auth_expired',error:'private_collector_error',consecutive_failures:3}]})
  await flushAsyncComponents()
  assert.match(content(root),/社区授权已失效.*重新登录/)
  assert.doesNotMatch(content(root),/采集状态|private_collector_error|连续失败/)
  assert.ok(nodes(root,'progress').some(node=>node.props.value===20 && node.props.max===320))
})

test('integrated shell retains the upstream Endfield gacha panel', async t => {
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({connected:false,roles:[]})}))
  const props=reactive({game:game('endfield',['gacha']),externalSnapshots:{}})
  const root=mount(t,Card,props)
  await flushAsyncComponents()
  nodes(root,'button').find(n=>content(n)==='抽卡统计').props.onClick()
  await flushAsyncComponents()
  assert.match(content(root),/请登录有效的鹰角通行证/)
  assert.equal(nodes(root,'button').find(n=>content(n)==='导出记录'),undefined)
  props.game={...props.game,credentials_configured:true};props.externalSnapshots={account:{payload:{role_id:'r'}}};await flushAsyncComponents()
  assert.match(content(root),/寻访记录/)
  assert.doesNotMatch(content(root),/敬请期待/)
})

test('integrated LOL shell exposes both announcements and local archive analysis', async t => {
  t.mock.method(globalThis,'fetch',async()=>({ok:true,json:async()=>({matches:[],overview:{},coverage:{}})}))
  const root=mount(t,Card,{game:game('league_of_legends',['account','news','announcement','match']),externalSnapshots:{}})
  await flushAsyncComponents()
  for (let i=0;i<3;i++) { await new Promise(setImmediate); await flushAsyncComponents() }   // the dashboard is loaded on demand
  assert.ok(nodes(root,'button').some(n=>content(n)==='公告与资讯'))
  assert.ok(nodes(root,'button').some(n=>content(n)==='个人总览'))
})

test('NTE guides receive the account roles for the owned-only filter', async t => {
  const catalog = { reviewed_at:'2026-09-26', sources:[{ id:1, title:'原帖', author:'作者', version:'1.3', url:'https://www.tajiduo.com/bbs/index.html#/post?postId=1' }],
    guides:[{ id:'甲', name:'甲', aliases:[], element:'魂', role:'主 C', status:'reviewed', source_id:1, pages:[1], sections:[] },
            { id:'乙', name:'乙', aliases:[], element:'灵', role:'辅助', status:'reviewed', source_id:1, pages:[1], sections:[] }] }
  t.mock.method(globalThis,'fetch',async url=>({ok:true,json:async()=>url.endsWith('/guides') ? catalog : { id:1, images:[], paragraphs:[] }}))
  const root=mount(t,Card,{game:game('nte',['roles']),externalSnapshots:{roles:{payload:{schema_version:1,entries:[{name:'甲'}]}}}})
  await flushAsyncComponents()
  nodes(root,'button').find(n=>content(n)==='浏览全部攻略').props.onClick()
  for (let i=0;i<3;i++) { await new Promise(setImmediate); await flushAsyncComponents() }
  nodes(nodes(root,'dialog')[0],'input').find(n=>n.props.type==='checkbox').props['onUpdate:modelValue'](true);await flushAsyncComponents()
  const listed=nodes(nodes(root,'dialog')[0],'button').map(n=>n.props['aria-label']).filter(label=>/^查看.攻略$/.test(label||''))
  assert.deepEqual(listed,['查看甲攻略'])
  assert.doesNotMatch(content(root),/尚无角色资料/)
})
