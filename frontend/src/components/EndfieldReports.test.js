import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content, choose } from '../test-utils/vue.js'
import { configureHttpClient, setAccountScope } from '../http-client.js'
const Reports=await loadVue(new URL('./EndfieldReports.vue',import.meta.url))
const Dashboard=await loadVue(new URL('./EndfieldDashboard.vue',import.meta.url))
const tick=async()=>{await new Promise(resolve=>setImmediate(resolve));await nextTick()}
const payload={report:{schema_version:1,observed_at:'2026-10-15T00:00:00Z',overview:{base:{name:'合成管理员',level:42},stamina:{current:0,maximum:240},progress:[{id:'daily',name:'每日任务',cur:0,total:100,remaining:100}],todos:[{id:'daily',name:'每日任务',remaining:100}]},
  training:{summary:{listed_count:2,declared_count:3,known_levels:1,average_level:0,max_level:0,rarity_counts:{6:1},phase_counts:{0:1}},items:[{id:'a',name:'干员甲',level:0,rarity:6,profession:'近卫',potential:0},{id:'b',name:'干员乙',rarity:5,profession:'先锋'}]},
  regions:{items:[{id:'r',name:'四号谷地',level:0,money:{current:0,total:null},settlements:[{id:'s',name:'矿区据点',coupon:{current:0,total:100},officers:[{id:'a',name:'干员甲'}]}],areas:[{name:'矿区',collections:[{key:'chests',label:'储藏箱',current:0,total:5,remaining:5,percent:0}]}]}]},
  ship:{summary:{room_count:1,staffed_rooms:1,operator_slots:1},rooms:[{id:'room',name:'培育室',level:0,operators:[{id:'a',name:'干员甲',mood_raw:0,trust_raw:0}]}]}}}

test('overview shows only backend-known todos and keeps source observation time separate', t=>{
  const root=mount(t,Reports,{payload,view:'overview',fetchedAt:'2026-10-15T01:00:00Z',stale:true})
  assert.match(content(root),/合成管理员/);assert.match(content(root),/理智 0 \/ 240/)
  assert.match(content(root),/每日任务 还需 100/);assert.match(content(root),/观测于.*08:00/);assert.match(content(root),/同步于.*09:00/)
  assert.doesNotMatch(content(root),/所有任务已完成|实时/)
})

test('roster filters without losing source totals and exposes an on-demand detail action', async t=>{
  const seen=[];const root=mount(t,Reports,{payload,view:'operators',onInspect:id=>seen.push(id)})
  assert.match(content(root),/已记录干员 2/);assert.match(content(root),/来源干员数 3/);assert.match(content(root),/已知等级均值 0/)
  nodes(root,'input')[0].props.onInput({target:{value:'干员甲'}});await nextTick()
  assert.match(content(root),/显示 1 \/ 2 名/);assert.doesNotMatch(content(root),/干员乙/)
  nodes(root,'button').find(node=>content(node)==='查看配装').props.onClick();assert.deepEqual(seen,['a'])
})

test('website operators are portrait role cards with the shared rarity tag while images keep the compact tile',t=>{
  const cards=root=>nodes(root,'article').filter(node=>String(node.props.class).includes('ef-operator'))
  const art=card=>nodes(card,'span').find(node=>String(node.props.class).split(' ').includes('endfield-artwork'))
  const web=mount(t,Reports,{payload,view:'operators'})
  assert.equal(cards(web).length,2)
  assert.ok(cards(web).every(card=>art(card).props.class.split(' ').includes('is-portrait')))
  assert.deepEqual(cards(web).map(card=>nodes(card,'small').map(node=>[node.props.class,content(node),node.props['data-tier']])[0]),[['role-rarity','6★','top'],['role-rarity','5★',undefined]])
  assert.equal(nodes(web,'div')[0].props['data-skin'],'endfield')
  const image=mount(t,Reports,{payload,view:'operators',imageMode:true})
  assert.ok(cards(image).every(card=>!art(card).props.class.split(' ').includes('is-portrait')))
  assert.deepEqual(cards(image).map(card=>nodes(card,'small')[0].props.class),['ef-tier','ef-tier'])
  assert.equal(nodes(image,'span').filter(node=>node.props.class==='role-rarity').length,0)
  assert.equal(nodes(image,'div')[0].props['data-skin'],undefined)
})

test('regions distinguish unknown limits and show settlements, assignment and remaining collections',t=>{
  const root=mount(t,Reports,{payload,view:'regions'})
  assert.match(content(root),/地区调度券 0 \/ 未知/);assert.match(content(root),/矿区据点/);assert.match(content(root),/派驻干员：干员甲/)
  assert.match(content(root),/储藏箱 0 \/ 5.*剩余 5/)
  assert.equal(nodes(root,'progress').length,1)
})

test('ship shows static zero percentages and stage with accessible scales and original observations',t=>{
  const root=mount(t,Reports,{payload,view:'ship'})
  assert.match(content(root),/培育室/);assert.match(content(root),/心情观测值 0/);assert.match(content(root),/信赖观测值 0/)
  assert.match(content(root),/心情 0%/);assert.match(content(root),/信赖 友好 0%/)
  assert.deepEqual(nodes(root,'progress').map(node=>[node.props.value,node.props.max]),[[0,'100'],[0,'100']])
  assert.match(content(root),/不外推当前状态/);assert.match(content(root),/查看原始观测值/)
})

test('saved ship report shows roster name and avatar for the observed template hash relation',t=>{
  const root=mount(t,Reports,{view:'ship',payload:{operators:[{id:'66bc7e8123d7cd04b08d5834f343003a',name:'合成驻守',avatar_url:'https://bbs.hycdn.cn/synthetic.png'}],ship:[{operators:[{charId:'chr_1234_synthetic',physicalStrength:0,favorability:0}]}]}})
  assert.match(content(root),/合成驻守/);assert.doesNotMatch(content(root),/chr_1234_synthetic|66bc7e8123d7cd04b08d5834f343003a/)
  assert.ok(nodes(root,'img').some(node=>node.props.src==='https://bbs.hycdn.cn/synthetic.png' && node.props.alt==='合成驻守'))
})

test('missing collection metadata stays unknown and fetched time does not become game observation time',t=>{
  const old={stamina:{updated_at:'2026-10-15T01:00:00Z'},operators:[],regions:[],ship:[]}
  const overview=mount(t,Reports,{payload:old,view:'overview',fetchedAt:'2026-10-15T01:00:00Z'})
  assert.match(content(overview),/观测于 未知/);assert.match(content(overview),/同步于.*09:00/)
  assert.match(content(overview),/已记录干员 未知/);assert.match(content(overview),/建设地区 未知/)
  const regions=mount(t,Reports,{payload:{report:{schema_version:1,regions:{items:[{name:'未采集据点的地区',settlements:[],settlements_available:false}]}}},view:'regions'})
  assert.match(content(regions),/据点 未知/);assert.doesNotMatch(content(regions),/据点 0/)
})

test('cloud reports consume the selected snapshot without extra profile collection and clear after owner changes',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}));setAccountScope({user_id:'u',account_id:'a',role_id:'r',provider:'skland'})
  const calls=[];t.mock.method(globalThis,'fetch',async path=>{calls.push(path);return new Response(JSON.stringify({supported:false}))})
  const props=reactive({cloudAccount:{account_id:'a',provider:'skland',roles:[{role_id:'r',display_name:'角色甲'},{role_id:'other',display_name:'角色乙'}]},cloudRole:'r',snaps:{account:{payload}},initialSection:'regions'})
  const root=mount(t,Dashboard,props);await tick()
  assert.match(content(root),/四号谷地/);assert.equal(calls.length,0)
  props.cloudRole='other';await tick();assert.doesNotMatch(content(root),/四号谷地|合成管理员/)
  props.snaps={account:{payload:{report:{schema_version:1,regions:{items:[{name:'新地区'}]}}}}};await tick()
  assert.match(content(root),/新地区/)
})

test('detail return keeps roster filters and gives cached equipment its own timestamp',async t=>{
  let returned = 0, focused = 0
  const props=reactive({payload,view:'operators',fetchedAt:'2026-10-15T04:00:00Z',operatorDetailId:'',onCloseDetail:()=>{returned++;props.operatorDetailId=''}})
  const root=mount(t,Reports,props)
  nodes(root,'input')[0].props.onInput({target:{value:'干员甲'}});await nextTick()
  nodes(root,'button').find(node=>content(node)==='查看配装').props.onClick({currentTarget:{focus(){focused++}}})
  props.operatorDetailId='a';props.operatorDetail={name:'干员甲',level:0};props.operatorStale=true;props.operatorFetchedAt='2026-10-15T01:00:00Z'
  await nextTick();await nextTick()
  assert.match(content(root),/配装同步于.*09:00/)
  assert.match(content(root),/同步于.*12:00/)
  assert.match(content(root),/上次成功读取的配装/)
  nodes(root,'button').find(node=>content(node)==='← 返回全员练度').props.onClick()
  await nextTick();await nextTick()
  assert.equal(returned,1);assert.equal(focused,1)
  assert.equal(nodes(root,'input')[0].props.value,'干员甲')
  assert.match(content(root),/显示 1 \/ 2 名/)
  assert.doesNotMatch(content(root),/配装同步于/)
})

test('missing detail time is unknown and never borrows the profile fetch time',t=>{
  const root=mount(t,Reports,{payload,view:'detail',fetchedAt:'2026-10-15T04:00:00Z',operatorDetailId:'a',operatorDetail:{name:'干员甲'}})
  assert.match(content(root),/配装同步于 未知/)
  assert.match(content(root),/来源未提供独立更新时间/)
  assert.match(content(root),/获得时间 未知（北京时间）/)
})

test('operator obtained time uses only the selected detail, independent of profile and loadout fetch times',t=>{
  for(const obtained_at of ['2025-12-31T17:02:00Z',null]) {
    const root=mount(t,Reports,{payload:{operators:[{id:'a',obtained_at:'2020-01-01T00:00:00Z'}]},view:'detail',fetchedAt:'2026-10-15T04:00:00Z',operatorFetchedAt:'2026-10-15T01:00:00Z',operatorDetailId:'a',operatorDetail:{name:'干员甲',obtained_at}})
    assert.match(content(root),/配装同步于 2026-10-15 09:00/)
    assert.match(content(root),obtained_at?/获得时间 2026-01-01 01:02（北京时间）/:/获得时间 未知（北京时间）/)
    assert.doesNotMatch(content(root),/获得时间 2026-10-15|2020-01-01/)
  }
})

test('honor displays the whole supplied medal list and preserves zero and unknown fields',t=>{
  const items=Array.from({length:12},(_,i)=>({id:`m${i}`,name:`奖章${i}`,level:i===0?0:null,is_plated:i===0?false:i===1?true:null,obtained_at:i===0?'2026-10-15T00:00:00Z':null}))
  const root=mount(t,Reports,{payload:{report:{schema_version:1,honor:{available:true,summary:{declared_count:30,listed_count:12},items}}},view:'honor'})
  assert.match(content(root),/来源成就总数 30/);assert.match(content(root),/已记录奖章 12/)
  assert.match(content(root),/奖章11/);assert.match(content(root),/等级 0 未镀层/)
  assert.match(content(root),/已镀层/);assert.match(content(root),/获得于.*08:00/)
  assert.match(content(root),/镀层未知/);assert.match(content(root),/获得于 未知/)
  assert.doesNotMatch(content(root),/100%|30 \/ 30/)
})

test('known empty officer list is different from missing assignment data',t=>{
  const root=mount(t,Reports,{payload:{report:{schema_version:1,regions:{items:[{settlements:[{name:'空据点',officers:[],officers_available:true},{name:'未知据点',officers:[],officers_available:false}]}]}}},view:'regions'})
  assert.match(content(root),/派驻干员：无派驻/);assert.match(content(root),/派驻干员：未提供/)
})

test('ship keeps unsupported values visible and independent observation/fetch dates',t=>{
  const root=mount(t,Reports,{view:'ship',fetchedAt:'2026-10-15T01:00:00Z',payload:{observed_at:'2025-12-31T00:00:00Z',ship:[{operators:[{name:'越界样本',physicalStrength:8640000,favorability:null}]},{name:'空舱',operators_available:true,operators:[]},{name:'未知舱',operators:[]}]}})
  assert.match(content(root),/心情 未知/);assert.match(content(root),/心情观测值 8640000/)
  assert.match(content(root),/信赖 阶段未知 未知/);assert.equal(nodes(root,'progress').length,0)
  assert.match(content(root),/游戏观测于 2025-12-31 08:00.*抓取于 2026-10-15 09:00/)
  assert.match(content(root),/当前没有驻守干员记录/);assert.match(content(root),/尚未采集驻守干员资料/)
})

test('overview exposes observed main mission and only confirms full stamina with a known positive limit',t=>{
  for(const [current,maximum,full] of [[240,240,true],[250,240,true],[0,0,false],[0,null,false],[null,240,false]]){
    const root=mount(t,Reports,{view:'overview',payload:{base:{main_mission:'第三章 · 合成任务'},stamina:{current,maximum}}})
    assert.match(content(root),/主线进度 第三章 · 合成任务/)
    assert.equal(content(root).includes('该次观测理智已满'),full)
    if(full)assert.doesNotMatch(content(root),/预计回满/)
  }
})

test('honor category, search and time controls keep totals and distinguish no results from no data',async t=>{
  const items=[{id:'a',name:'探索甲',category:'探索',obtained_at:'2025-10-15T00:00:00Z'},{id:'b',name:'探索乙',category:'探索',obtained_at:'2026-10-15T00:00:00Z'},{id:'c',name:'战斗甲',category:'战斗'},{id:'u',name:'未分类奖章',category:null}]
  const root=mount(t,Reports,{view:'honor',payload:{report:{schema_version:1,honor:{available:true,items,summary:{declared_count:99,listed_count:4}}}}})
  const headings=()=>nodes(root,'h3').map(content)
  assert.deepEqual(headings(),['探索乙','探索甲','战斗甲','未分类奖章'])
  choose(root,'获得时间排序','oldest');await nextTick()
  assert.deepEqual(headings(),['探索甲','探索乙','战斗甲','未分类奖章'])
  choose(root,'奖章分类','"探索"');nodes(root,'input')[0].props.onInput({target:{value:'甲'}});await nextTick()
  assert.deepEqual(headings(),['探索甲']);assert.match(content(root),/显示 1 \/ 4/);assert.match(content(root),/来源成就总数 99/);assert.match(content(root),/奖章分类/)
  assert.match(content(root),/获得于 2025-10-15 08:00/)
  nodes(root,'input')[0].props.onInput({target:{value:'不存在'}});await nextTick()
  assert.match(content(root),/没有匹配的奖章/);assert.doesNotMatch(content(root),/当前档案没有奖章记录/)
  nodes(root,'button').find(node=>content(node)==='清除奖章筛选').props.onClick();await nextTick()
  assert.equal(headings().length,4)
  choose(root,'奖章分类','null');await nextTick()
  assert.deepEqual(headings(),['未分类奖章'])
})

test('legacy regional collections use the observed game labels',t=>{
  const root=mount(t,Reports,{view:'regions',payload:{regions:[{levels:[{id:'map01_lv001',puzzles:{count:0}}]}]}})
  for(const label of ['醚质','宝箱','装备制造模板','维修灵感点','协议采录桩'])assert.ok(content(root).includes(label))
  assert.doesNotMatch(content(root),/谜质|储藏箱|装备箱|片段|黑盒/)
})

test('the source footer of every view says a profile is waiting for an update only when it is, with its own fetch time',t=>{
  for(const view of ['overview','operators','regions','ship','honor']) for(const stale of [true,false]) {
    const footer=nodes(mount(t,Reports,{payload:{ship:[],achievements:{medals:[]}},view,fetchedAt:'2025-12-31T01:00:00Z',stale}),'footer').find(node=>node.props.class==='ef-source')
    assert.match(content(footer),/同步于 2025-12-31 09:00/)
    assert.equal(content(footer).includes('正在显示已有资料，等待更新'),stale,`${view} stale=${stale}`)
    assert.equal(content(footer).includes('已采集资料'),!stale,`${view} stale=${stale}`)
  }
})

const cls = (node, name) => String(node.props.class).split(' ').includes(name)
const rich = { report: { schema_version: 1, observed_at: '2026-10-15T00:00:00Z',
  overview: { base: { name: '甲', level: 46, world_level: 5, role_id: '9' }, stamina: { current: 187, maximum: 240 },
    progress: [{ id: 'daily', name: '每日活跃', cur: 60, total: 100, remaining: 40 }, { id: 'weekly', name: '每周任务', cur: null, total: 2000, remaining: null }], todos: [] },
  training: { summary: { listed_count: 3, declared_count: 3, rarity_counts: { 6: 2, 5: 1 }, phase_counts: { 0: 1, 3: 2 } },
    items: [{ id: 'a', name: '甲六', level: 80, rarity: 6, evolve_phase: 3 }, { id: 'b', name: '乙六', level: 70, rarity: 6, evolve_phase: 3 }, { id: 'c', name: '丙五', level: 60, rarity: 5, evolve_phase: 0 }] },
  regions: { items: [], summary: { region_count: 3 } }, ship: { rooms: [], summary: { room_count: 4 } } } }

test('overview draws stamina and progress as rings and the counts as shortcut tiles that navigate', t => {
  const seen = []
  const root = mount(t, Reports, { payload: rich, view: 'overview', onNavigate: key => seen.push(key) })
  const meters = nodes(root, 'div').filter(node => node.props.role === 'meter')
  assert.deepEqual(meters.map(node => [node.props['aria-label'], node.props['aria-valuenow'], node.props['aria-valuemax']]), [['理智', 187, 240], ['每日活跃', 60, 100]])
  assert.match(content(root), /理智 187 \/ 240/); assert.match(content(root), /预计回满 未知/)
  assert.match(content(root), /每周任务 未知 \/ 2000/)
  const tiles = nodes(root, 'button').filter(node => cls(node, 'ef-count'))
  assert.deepEqual(tiles.map(node => content(node)), ['已记录干员 3 6★ 2 · 5★ 1 查看全员练度 →', '建设地区 3 查看地区建设 →', '帝江号房间 4 查看帝江号 →'])
  tiles.forEach(node => node.props.onClick())
  assert.deepEqual(seen, ['operators', 'regions', 'ship'])
})

test('in a bot image the count tiles are plain blocks without actions', t => {
  const root = mount(t, Reports, { payload: rich, view: 'overview', imageMode: true })
  assert.equal(nodes(root, 'button').length, 0)
  const tiles = nodes(root, 'div').filter(node => cls(node, 'ef-count'))
  assert.deepEqual(tiles.map(node => content(node)), ['已记录干员 3 6★ 2 · 5★ 1', '建设地区 3', '帝江号房间 4'])
  assert.doesNotMatch(content(root), /查看全员练度|UID/)
})

test('the 6★ rail follows the roster filters, has no headings of its own and opens the loadout', async t => {
  const seen = []
  const root = mount(t, Reports, { payload: rich, view: 'operators', onInspect: id => seen.push(id) })
  const rail = () => nodes(root, 'button').filter(node => cls(node, 'ef-feature'))
  // The fallback tile's first character precedes the name when art is not available.
  assert.deepEqual(rail().map(node => content(node)), ['甲 甲六 Lv. 80 潜能 未知', '乙 乙六 Lv. 70 潜能 未知'])
  assert.deepEqual(nodes(root, 'h3').map(content), ['甲六', '乙六', '丙五'])
  rail()[1].props.onClick({ currentTarget: null })
  assert.deepEqual(seen, ['b'])
  choose(root, '稀有度', '5'); await nextTick()
  assert.equal(rail().length, 0)
  assert.deepEqual(nodes(root, 'h3').map(content), ['丙五'])
  assert.doesNotMatch(content(root), /6★ 干员/)
})

test('rarity and phase distributions come from the source counts, and a lone tier stays a plain tag', t => {
  const root = mount(t, Reports, { payload: rich, view: 'operators' })
  const ring = nodes(root, 'figure').find(node => node.props['aria-label'] === '干员稀有度分布')
  assert.ok(ring)
  assert.match(content(ring), /6★ 2 名 67%/); assert.match(content(ring), /5★ 1 名 33%/)
  const bar = nodes(root, 'div').find(node => node.props.role === 'img' && cls(node, 'stack-bar'))
  assert.equal(bar.props['aria-label'], '精英阶段 0 1，精英阶段 3 2')
  const lone = mount(t, Reports, { payload: { report: { ...rich.report, training: { ...rich.report.training, summary: { listed_count: 1, rarity_counts: { 6: 1 } } } } }, view: 'operators' })
  assert.equal(nodes(lone, 'figure').length, 0)
  assert.match(content(lone), /稀有度分布 6★ 1/)
  const none = mount(t, Reports, { payload: { report: { ...rich.report, training: { items: [], summary: { listed_count: 0 } } } }, view: 'operators' })
  assert.doesNotMatch(content(none), /稀有度分布|精英阶段/)
})

test('region vouchers are a ring, settlement coupons a plain bar, and only collections stay native progress', t => {
  const report = { schema_version: 1, regions: { items: [{ id: 'r', name: '甲地', level: 3, money: { current: 5, total: 20, percent: 25 },
    settlements: [{ id: 's', name: '据点甲', coupon: { current: 1, total: 4, percent: 25 }, officers: [] }],
    areas: [{ name: '区', collections: [{ key: 'chests', label: '宝箱', current: 2, total: 4, percent: 50, remaining: 2 }] }] }] } }
  const root = mount(t, Reports, { payload: { report }, view: 'regions' })
  const meter = nodes(root, 'div').find(node => node.props.role === 'meter')
  assert.deepEqual([meter.props['aria-label'], meter.props['aria-valuenow'], meter.props['aria-valuemax']], ['地区调度券', 5, 20])
  assert.match(content(root), /地区调度券 5 \/ 20/)
  assert.equal(nodes(root, 'span').filter(node => cls(node, 'ef-bar')).length, 1)
  assert.equal(nodes(root, 'progress').length, 1)
})

test('ship rings are decorative: the native progress stays the accessible value and unknown values keep a dashed note', t => {
  const root = mount(t, Reports, { view: 'ship', payload: { report: { schema_version: 1, ship: { rooms: [{ id: 'r', name: '舱', operators: [{ id: 'a', name: '甲', mood_raw: 5000, trust_raw: 300 }, { id: 'b', name: '乙', mood_raw: 20000 }] }] } } } })
  const rings = nodes(root, 'div').filter(node => cls(node, 'ring-gauge'))
  assert.equal(rings.length, 4)
  for (const ring of rings) assert.equal(ring.props['aria-hidden'], 'true')
  const bars = nodes(root, 'progress')
  // Trust 100% opens the 亲近 stage, so its ring and accessible value start that stage at 0.
  assert.deepEqual(bars.map(node => [node.props.value, node.props.max]), [[50, '100'], [0, '100']])
  assert.equal(bars[1].props['aria-label'], '甲信赖亲近阶段进度')
  for (const bar of bars) assert.ok(cls(bar, 'sr-only'))
  assert.match(content(root), /心情 50%/); assert.match(content(root), /信赖 亲近 100%/)
  assert.match(content(root), /超出模型范围/); assert.match(content(root), /观测值未知/)
})

test('honor adds a category ring for two or more categories and a recent rail for three dated medals, never another heading', t => {
  const items = [
    { id: '1', name: '甲', category: '探索', level: 1, obtained_at: '2026-10-03T00:00:00Z' }, { id: '2', name: '乙', category: '战斗', level: 1, obtained_at: '2026-10-02T00:00:00Z' },
    { id: '3', name: '丙', category: '战斗', level: 1, obtained_at: '2026-10-01T00:00:00Z' },
  ]
  const root = mount(t, Reports, { view: 'honor', payload: { report: { schema_version: 1, honor: { available: true, items, summary: { declared_count: 9, listed_count: 3 } } } } })
  assert.ok(nodes(root, 'figure').some(node => node.props['aria-label'] === '已记录奖章的分类占比'))
  assert.match(content(root), /战斗 2 枚 67%/)
  const recent = nodes(root, 'div').filter(node => cls(node, 'ef-recent-medal'))
  assert.deepEqual(recent.map(node => content(node)), ['甲 甲 2026-10-03', '乙 乙 2026-10-02', '丙 丙 2026-10-01'])
  assert.deepEqual(nodes(root, 'h3').map(content), ['甲', '乙', '丙'])
  const one = mount(t, Reports, { view: 'honor', payload: { report: { schema_version: 1, honor: { available: true, items: items.slice(0, 2).map(item => ({ ...item, category: '探索' })), summary: { listed_count: 2 } } } } })
  assert.equal(nodes(one, 'figure').length, 0)
  assert.equal(nodes(one, 'div').filter(node => cls(node, 'ef-recent-medal')).length, 0)
  const image = mount(t, Reports, { view: 'honor', imageMode: true, payload: { report: { schema_version: 1, honor: { available: true, items, summary: { listed_count: 3 } } } } })
  assert.equal(nodes(image, 'div').filter(node => cls(node, 'ef-recent-medal')).length, 0)
  assert.equal(nodes(image, 'button').length, 0)
})

test('plated medals are counted only when plating is reported for every listed medal', t => {
  const medal = (id, is_plated) => ({ id, name: `奖章${id}`, level: 1, is_plated })
  const view = items => mount(t, Reports, { view: 'honor', payload: { report: { schema_version: 1, honor: { available: true, items, summary: { listed_count: items.length } } } } })
  assert.match(content(view([medal(1, true), medal(2, false), medal(3, true)])), /已镀层 2/)
  assert.match(content(view([medal(1, false)])), /已镀层 0/)
  assert.doesNotMatch(content(view([medal(1, true), medal(2, null)])), /已镀层 [0-9]/)
  assert.doesNotMatch(content(view([])), /已镀层 [0-9]/)
})


test('operator and honor image modes expose no web menus or native selects', t => {
  for (const view of ['operators','honor']) {
    const root = mount(t, Reports, { payload, view, imageMode: true })
    assert.equal(nodes(root,'select').length, 0)
    assert.equal(nodes(root,'button').filter(n=>n.props.role==='combobox').length, 0)
  }
})


test('empty todos distinguish unknown, partially known and fully completed task progress', t => {
  const task = (id, remaining) => ({ id, name: id === 'daily' ? '每日任务' : '每周任务', cur: remaining == null ? null : 100 - remaining, total: 100, remaining })
  for (const [progress, todos, expected] of [
    [[], [], '任务进度未知'],
    [[task('daily', null)], [], '任务进度未知'],
    [[task('daily', 0)], [], '已同步任务暂无待办，部分进度未知'],
    [[task('daily', 0), task('weekly', null)], [], '已同步任务暂无待办，部分进度未知'],
    [[task('daily', 0), task('weekly', 0)], [], '已同步的每日与每周任务已完成'],
    [[task('daily', 40), task('weekly', null)], [task('daily', 40)], '每日任务 还需 40'],
  ]) {
    const data = structuredClone(payload)
    data.report.overview.progress = progress
    data.report.overview.todos = todos
    const root = mount(t, Reports, { payload: data, view: 'overview' })
    const todo = nodes(root, 'section').find(node => node.props.class?.includes('ef-todo'))
    assert.ok(todo)
    assert.ok(content(todo).includes(expected), `${JSON.stringify(progress)}: ${content(todo)}`)
    assert.doesNotMatch(content(todo), /今日日常已完成|当前每日与每周任务没有待办项/)
  }
})

test('the trust ring fills within its stage and the image lists residents as compact rows', t => {
  const operators = [['友好', 99], ['亲近', 100], ['亲近', 163], ['信任', 200]].map(([trust_level_name, trust_percent], i) => ({ id: String(i), name: `干员${i}`, mood_percent: 50, trust_percent, trust_level_name }))
  const payload = { report: { schema_version: 1, ship: { rooms: [{ id: 'r', name: '舱', operators }] } } }
  const ringValues = root => nodes(root, 'div').filter(node => cls(node, 'ring-gauge')).map(node => node.props['aria-valuenow'])
  const web = mount(t, Reports, { view: 'ship', payload })
  assert.deepEqual(ringValues(web), [50, 99, 50, 0, 50, 63, 50, 100])
  assert.match(content(web), /信赖 亲近 163%/); assert.match(content(web), /信赖 信任 200%/)
  assert.equal(nodes(web, 'article').filter(node => cls(node, 'compact')).length, 0)
  const image = mount(t, Reports, { view: 'ship', imageMode: true, payload })
  assert.equal(nodes(image, 'article').filter(node => cls(node, 'ef-resident') && cls(node, 'compact')).length, 4)
  assert.deepEqual(ringValues(image), ringValues(web))
  assert.doesNotMatch(content(image), /查看原始观测值/)
})

test('honor image is an icon wall of names without per-medal category, level or time text', t => {
  const items = [
    { id: '1', name: '甲章', category: '探索', level: 3, is_plated: true, obtained_at: '2026-10-03T00:00:00Z', icon_url: 'https://web.hycdn.cn/a.png' },
    { id: '2', name: '乙章', category: '战斗', level: 1, is_plated: false, obtained_at: '2026-10-02T00:00:00Z' },
  ]
  const payload = { report: { schema_version: 1, honor: { available: true, items, summary: { declared_count: 9, listed_count: 2 } } } }
  const image = mount(t, Reports, { view: 'honor', imageMode: true, payload })
  const icons = nodes(image, 'figure').filter(node => cls(node, 'ef-medal-icon'))
  assert.deepEqual(icons.map(node => content(nodes(node, 'figcaption')[0])), ['甲章', '乙章'])
  assert.ok(cls(icons[0], 'plated')); assert.ok(!cls(icons[1], 'plated'))
  assert.equal(nodes(image, 'article').filter(node => cls(node, 'ef-medal')).length, 0)
  assert.doesNotMatch(content(image), /获得于|等级 3|未镀层/)
  assert.ok(nodes(image, 'figure').some(node => node.props['aria-label'] === '已记录奖章的分类占比'))
  const web = mount(t, Reports, { view: 'honor', payload })
  assert.equal(nodes(web, 'article').filter(node => cls(node, 'ef-medal')).length, 2)
  assert.match(content(web), /获得于/)
})
