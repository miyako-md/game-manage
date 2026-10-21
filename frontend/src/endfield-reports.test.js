import test from 'node:test'
import assert from 'node:assert/strict'
import { selectOperators, selectMedals, profileReport, operatorImage, operatorArtwork, gachaArtwork, rarityParts, phaseParts, medalCategoryParts, recentMedals, platedSummary, collectionTotals } from './endfield-reports.js'

test('operator filters combine name rarity and profession; stable numeric sorting preserves zero and unknown last', () => {
  const items = [{ id:'missing',name:'未知',rarity:6,profession:'近卫' },{id:'zero',name:'管理员零',level:0,rarity:6,profession:'近卫'},
    {id:'high',name:'管理员甲',level:70,rarity:6,profession:'近卫'},{id:'same',name:'管理员乙',level:70,rarity:5,profession:'先锋'}]
  assert.deepEqual(selectOperators(items).map(item=>item.id),['high','same','zero','missing'])
  assert.deepEqual(selectOperators(items,{search:'管理员',rarity:'6',profession:'近卫'}).map(item=>item.id),['high','zero'])
  assert.equal(items[0].id,'missing')
})

test('newest first reads the chr_NNNN template id, not the roster instance hash, and puts unplaced operators last', () => {
  const items = [{ id:'0f3a', char_id:'chr_0003_a', name:'甲', level:90 },{ id:'chr_0026_b', name:'乙', level:1 },
    { id:'9c1d', name:'无模板', level:99 },{ id:'77aa', char_id:'chr_0010_d', name:'丁' },{ id:'11bb', char_id:'legacy', name:'旧编号', level:50 }]
  assert.deepEqual(selectOperators(items,{sort:'newest'}).map(item=>item.name),['乙','丁','甲','旧编号','无模板'])
  assert.deepEqual(selectOperators(items).map(item=>item.name),['无模板','甲','旧编号','乙','丁'])
})

test('source reports remain authoritative and old profiles do not invent todos or aggregate values', () => {
  const report={schema_version:1,overview:{todos:[]}}
  assert.equal(profileReport({report}).overview,report.overview)
  const legacy=profileReport({stamina:{current:0},operators:[],progress:[{name:'每日',cur:0,total:100}]})
  assert.equal(legacy.overview.stamina.current,0)
  assert.equal(legacy.overview.todos,null)
  assert.equal(legacy.training.summary.average_level,undefined)
  assert.equal(legacy.training.summary.listed_count,null)
  assert.equal(profileReport({regions:[],ship:[]}).regions.summary.region_count,null)
  assert.equal(profileReport({regions:[],ship:[]}).ship.summary.room_count,null)
})

test('operator artwork accepts only reviewed HTTPS image origins and no arbitrary media URLs', () => {
  assert.equal(operatorImage('https://example.com/avatar.png'),null)
  assert.equal(operatorImage('http://bbs.hycdn.cn/avatar.png'),null)
  assert.equal(operatorImage('https://bbs.hycdn.cn/avatar.svg'),null)
  assert.equal(operatorImage('https://bbs.hycdn.cn/avatar.png?token=x'),null)
  assert.equal(operatorImage('https://user:secret@bbs.hycdn.cn/avatar.png'),null)
})

test('official artwork fallback uses exact website keys or unique names, not inferred character IDs', () => {
  assert.match(operatorArtwork({id:'akekuri'}),/akekuri\./)
  assert.match(operatorArtwork({id:'char_123_unknown',name:'秋栗'}),/akekuri\./)
  assert.equal(operatorArtwork({id:'char_123_akekuri'}),null)
  assert.equal(operatorArtwork({name:'管理员'}),null)
  assert.ok(operatorArtwork({id:'endministrator1',name:'管理员'}))
  assert.equal(operatorArtwork({name:'秋栗',avatar_url:'https://bbs.hycdn.cn/known.png'}),'https://bbs.hycdn.cn/known.png')
})

test('detail portraits use reviewed exact identities, preserving ambiguous and unknown fallbacks', () => {
  const portrait=operatorArtwork({name:'佩丽卡'},{portrait:true})
  assert.match(portrait,/prelica\./)
  assert.notEqual(portrait,operatorArtwork({name:'佩丽卡'}))
  assert.equal(operatorArtwork({name:'管理员'},{portrait:true}),null)
  assert.equal(operatorArtwork({id:'char_123_perlica'},{portrait:true}),null)
  assert.equal(operatorArtwork({name:'未收录',avatar_url:'https://bbs.hycdn.cn/known.png'},{portrait:true}),'https://bbs.hycdn.cn/known.png')
})

test('legacy honors preserve all listed medals, confirmed zeros, unknowns and observed icon variants', () => {
  const medals=Array.from({length:12},(_,id)=>({achievementData:{id,name:'奖章'+id,initIcon:'init',reforge2Icon:'two',reforge3Icon:'three',platedIcon:'plated'},level:3,isPlated:id===0,obtainTs:1792029600}))
  const honor=profileReport({achievements:{count:0,medals}}).honor
  assert.equal(honor.items.length,12)
  assert.equal(honor.summary.declared_count,0)
  assert.equal(honor.items[0].icon_url,'plated')
  assert.equal(honor.items[1].icon_url,'three')
  assert.match(honor.items[0].obtained_at,/^2026-/)
  assert.equal(profileReport({achievements:{medals:[]}}).honor.summary.listed_count,null)
  assert.equal(profileReport({availability:{honor:true},achievements:{medals:[]}}).honor.summary.listed_count,0)
  const unknown=profileReport({achievements:{medals:[{obtainTs:'no',level:false}]}}).honor.items[0]
  assert.equal(unknown.level,null)
  assert.equal(unknown.obtained_at,null)
  assert.equal(unknown.is_plated,null)
})

test('saved region reports and legacy collection-only profiles gain names without changing observations', () => {
  const region={levels:[{id:'map01_lv001'}],collections:[{level_id:'map01_lv001',name:'上游新名称'}],areas:[{id:'map01_lv001',name:'枢纽区',collections:[]},{id:'map02_lv002',name:null}]}
  const saved={schema_version:1,regions:{items:[region]}}
  const result=profileReport({report:saved}).regions.items[0]
  assert.deepEqual(result.areas.map(item=>item.name),['上游新名称','武陵城'])
  assert.equal(region.areas[0].name,'枢纽区')
  const legacy=profileReport({regions:[{collections:[{level_id:'map02_lv001',chest_count:0},{level_id:'future'}]}]}).regions.items[0]
  assert.deepEqual(legacy.areas.map(item=>item.name),['景玉谷','future'])
  assert.equal(legacy.areas[0].chests.count,0)
  assert.equal(legacy.areas[0].chests.total,undefined)
})

test('legacy region money spelling alias keeps known zero before conut',()=>{
 const report=profileReport({regions:[{money:{count:0,conut:9}},{money:{count:null,conut:9}},{money:{conut:7}}]})
 assert.deepEqual(report.regions.items.map(item=>item.money.count),[0,9,7])
})

test('honor categories backfill only an unambiguous observed ID and preserve explicit unknown',()=>{
 const raw=[{achievementData:{id:0,cateName:' 探索 '}},{achievementData:{id:'dupe',cateName:'甲'}},{achievementData:{id:'dupe',cateName:'乙'}},{achievementData:{id:'explicit',cateName:'探索'}},{achievementData:{id:'invalid',cateName:42}}]
 const items=[{id:'0'},{id:'dupe'},{id:'explicit',category:null},{id:'invalid'},{id:'new',category:' 战斗 '}]
 const result=profileReport({achievements:{medals:raw},report:{schema_version:1,honor:{items}}}).honor.items
 assert.deepEqual(result.map(item=>item.category),['探索',null,null,null,'战斗'])
 assert.equal(items[0].category,undefined)
 assert.equal(profileReport({achievements:{medals:raw}}).honor.items[0].category,'探索')
})

test('honor filters intersect while time sorting leaves unknown dates last and never mutates source',()=>{
 const items=[{id:'u',name:'未知时间',category:null},{id:'a',name:'探索甲',category:'探索',obtained_at:'2025-10-15T00:00:00Z'},{id:'b',name:'探索乙',category:'探索',obtained_at:'2026-10-15T00:00:00Z'},{id:'c',name:'战斗甲',category:'战斗',obtained_at:'invalid'}]
 assert.deepEqual(selectMedals(items).map(item=>item.id),['b','a','u','c'])
 assert.deepEqual(selectMedals(items,{sort:'oldest'}).map(item=>item.id),['a','b','u','c'])
 assert.deepEqual(selectMedals(items,{sort:'source'}),items)
 assert.deepEqual(selectMedals(items,{search:'甲',category:'探索'}).map(item=>item.id),['a'])
 assert.deepEqual(selectMedals(items,{category:null}).map(item=>item.id),['u'])
 assert.equal(items[0].id,'u')
})

test('rarity and phase counts become ordered chart parts and ignore unusable entries', () => {
  assert.deepEqual(rarityParts({ 4: 6, 6: 2, 5: 8 }).map(part => [part.label, part.value]), [['6★', 2], ['5★', 8], ['4★', 6]])
  assert.deepEqual(phaseParts({ 3: 5, 0: 2, 4: 6 }).map(part => [part.key, part.label, part.value]), [['0', '精英阶段 0', 2], ['3', '精英阶段 3', 5], ['4', '精英阶段 4', 6]])
  assert.deepEqual(rarityParts({ 6: 0 }).map(part => part.value), [0])
  for (const bad of [null, undefined, [], 'x', { x: 1 }, { 6: null }, { 6: -1 }, { 6: '2' }]) assert.deepEqual(rarityParts(bad), [])
})

test('medal categories sort by count, name the unclassified ones and fold the long tail', () => {
  const items = ['探索', '探索', '战斗', null, '建设', '收集', '社交', '社交', '成长'].map(category => ({ category }))
  const parts = medalCategoryParts(items)
  // Equal counts follow Chinese collation; the unclassified bucket sorts after named ones.
  assert.deepEqual(parts.map(part => [part.label, part.value]), [['社交', 2], ['探索', 2], ['成长', 1], ['建设', 1], ['其他分类', 3]])
  assert.equal(parts.reduce((sum, part) => sum + part.value, 0), items.length)
  assert.deepEqual(medalCategoryParts(items, 20).at(-1), { key: null, label: '未提供分类', value: 1 })
  const unclassified = medalCategoryParts([{ category: null }, { category: '  ' }, {}])
  assert.deepEqual(unclassified.map(part => [part.label, part.value]), [['未提供分类', 3]])
  assert.deepEqual(medalCategoryParts([]), [])
})

test('recent medals need a real acquisition time and come newest first', () => {
  const items = [{ name: '无时间' }, { name: '旧', obtained_at: '2026-01-01T00:00:00Z' }, { name: '新', obtained_at: '2026-10-01T00:00:00Z' }, { name: '坏', obtained_at: 'x' }]
  assert.deepEqual(recentMedals(items).map(item => item.name), ['新', '旧'])
  assert.equal(recentMedals(items, 1).length, 1)
})

test('plating counts separate reported false from not reported', () => {
  assert.deepEqual(platedSummary([{ is_plated: true }, { is_plated: false }, {}, { is_plated: 'yes' }]), { plated: 1, known: 2, listed: 4 })
  assert.deepEqual(platedSummary(undefined), { plated: 0, known: 0, listed: 0 })
})

test('gacha artwork uses the exact weapon catalog without borrowing operator images', () => {
  assert.match(gachaArtwork({name:'破碎君王'},'weapon'), /^https:\/\/bbs\.hycdn\.cn\/image\/.+\.png$/)
  assert.match(gachaArtwork({name:'玉中身'},'weapon'), /^https:\/\/bbs\.hycdn\.cn\/image\/.+\.png$/)
  assert.notEqual(gachaArtwork({name:'玉中身'},'weapon'),gachaArtwork({name:'破碎君王'},'weapon'))
  assert.equal(gachaArtwork({name:'祀'},'character'),operatorArtwork({name:'祀'}))
  assert.equal(gachaArtwork({name:'祀'},'weapon'),null)
  assert.equal(gachaArtwork({name:'破碎君王'},'character'),null)
  assert.equal(gachaArtwork({name:'未收录武器'},'weapon'),null)
  assert.equal(gachaArtwork({name:'破碎君王'},undefined),null)
  assert.equal(gachaArtwork({name:'破碎'},'weapon'),null)
})

test('collection totals sum only fully known areas and flag partial sums instead of treating unknown as zero', () => {
  const area = (chests, puzzles) => [{ key:'chests', label:'宝箱', ...chests }, { key:'puzzles', label:'醚质', ...puzzles }]
  const totals = collectionTotals([area({ current:28, total:40 }, { current:0, total:8 }), area({ current:2, total:null }, { current:1, total:8 }), area({ current:10, total:20 }, { current:null, total:5 })])
  assert.deepEqual(totals, [{ key:'chests', label:'宝箱', current:38, total:60, partial:true, percent:63 }, { key:'puzzles', label:'醚质', current:1, total:16, partial:true, percent:6 }])
  assert.deepEqual(collectionTotals([area({ current:null, total:null }, { current:0, total:0 })]), [{ key:'chests', label:'宝箱', current:null, total:null, partial:false, percent:null }, { key:'puzzles', label:'醚质', current:0, total:0, partial:false, percent:null }])
  assert.deepEqual(collectionTotals([]), [])
})
