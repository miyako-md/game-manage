import test from 'node:test'
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { shipResident, shipPercent, trustStage, SHIP_CONVERSION_MODEL } from './endfield-ship.js'
import { profileReport } from './endfield-reports.js'

test('ship uses the reviewed static ranges and exact trust boundaries shared with QQ', () => {
  for (const [raw, percent, stage] of [[0,0,'友好'],[3,1,'友好'],[57,19,'友好'],[69,23,'友好'],[299,99,'友好'],[300,100,'亲近'],[312,101,'亲近'],[336,103,'亲近'],[996,158,'亲近'],[1499,199,'亲近'],[1500,200,'信任'],[2000,200,'信任']]) {
    const item=shipResident({physicalStrength:raw,favorability:raw})
    assert.equal(item.trust_percent,percent,`trust ${raw}`)
    assert.equal(item.trust_level_name,stage)
  }
  assert.equal(shipResident({physicalStrength:10000}).mood_percent,100)
  const outside=shipResident({physicalStrength:10001})
  assert.equal(outside.mood_percent,null);assert.equal(outside.mood_raw,10001)
  for(const [value, shown] of [[0,'0%'],[33.35,'33.4%'],[0.05,'0.1%'],[99.99,'100%'],[200,'200%'],[null,'未知']]) assert.equal(shipPercent(value),shown)
})

test('ship decimal observations reject coercion and cross-language numeric spellings',()=>{
  for(const value of [null,undefined,true,false,{},[],NaN,Infinity,-1,'',' ','NaN','Infinity','0x10','0b11','0o10','1_0','１２','١٢']) {
    const item=shipResident({physicalStrength:value,favorability:value})
    assert.equal(item.mood_raw,null,`${String(value)} mood`);assert.equal(item.trust_raw,null)
    assert.equal(item.mood_percent,null);assert.equal(item.trust_percent,null);assert.equal(item.trust_level_name,null)
  }
  for(const [raw,value] of [['+3e2',300],['3E+2',300],['300.',300],['.5',.5],['-.0',-0],[' 0 ',0]]) {
    const item=shipResident({physicalStrength:raw,favorability:raw})
    assert.equal(item.mood_raw,value);assert.equal(item.trust_raw,value)
  }
})

test('new derived nulls remain authoritative while old report and raw residents gain the model',()=>{
  const original={id:'a',mood_raw:5000,trust_raw:312,mood_percent:null,trust_percent:null,trust_level_name:null}
  assert.deepEqual(shipResident(original),original)
  const old={schema_version:1,ship:{rooms:[{operators:[{id:'a',mood_raw:3335,trust_raw:996}]}]},training:{items:[{id:'a',name:'干员甲',avatar_url:'https://bbs.hycdn.cn/a.png'}]}}
  const result=profileReport({report:old}).ship
  assert.equal(result.rooms[0].operators[0].mood_percent,33.35)
  assert.equal(result.rooms[0].operators[0].trust_percent,158)
  assert.equal(result.rooms[0].operators[0].name,'干员甲')
  assert.equal(result.conversion_model.id,SHIP_CONVERSION_MODEL.id)
  assert.equal(old.ship.rooms[0].operators[0].mood_percent,undefined)
  const legacy=profileReport({ship:[{operators:[{charId:'a',physicalStrength:0,favorability:0}]}],operators:[{id:'a',name:'干员甲',avatar_url:'https://bbs.hycdn.cn/a.png'}]}).ship
  assert.equal(legacy.rooms[0].operators[0].name,'干员甲')
  assert.equal(legacy.rooms[0].operators[0].avatar_url,'https://bbs.hycdn.cn/a.png')
  assert.equal(legacy.rooms[0].operators[0].mood_percent,0)
})

test('legacy ship summaries require complete room and staff observation, preserving explicit report null',()=>{
  const summary=payload=>profileReport(payload).ship.summary
  assert.deepEqual(summary({availability:{ship:true},ship:[]}),{room_count:0,staffed_rooms:0,operator_slots:0})
  assert.deepEqual(summary({ship:[]}),{room_count:null,staffed_rooms:null,operator_slots:null})
  const known={availability:{ship:true},ship:[{operators:[],operators_available:true},{operators:[{charId:'a'},{charId:'b'}]}]}
  assert.deepEqual(summary(known),{room_count:2,staffed_rooms:1,operator_slots:2})
  assert.deepEqual(summary({...known,ship:[...known.ship,{operators:[]}]}),{room_count:3,staffed_rooms:null,operator_slots:null})
  assert.deepEqual(summary({...known,ship:[{operators:[{charId:'a'}],operators_available:false}]}),{room_count:1,staffed_rooms:null,operator_slots:null})
  assert.equal(summary({report:{schema_version:1,ship:{available:true,rooms:[],summary:{staffed_rooms:null}}}}).staffed_rooms,null)
})

test('saved ship observations join exact template MD5 roster IDs without replacing resident IDs or source fields',()=>{
  // Synthetic IDs cover both MD5 padding boundaries and multiple blocks.
  const ids = ['chr_0001_synthetic',...Array.from({length:75},(_,index)=>`chr_1234_${'a'.repeat(index+1)}`)]
  const operators = ids.map((id,index)=>({id:createHash('md5').update(id,'utf8').digest('hex'),name:`合成驻守 ${index}`,avatar_url:`https://bbs.hycdn.cn/${index}.png`}))
  const ship = [{operators:ids.map(charId=>({charId,physicalStrength:0,favorability:0}))}]
  for (const payload of [{ship,operators},{report:{schema_version:1,ship:{rooms:ship},training:{items:operators}}}]) {
    const residents = profileReport(payload).ship.rooms[0].operators
    assert.deepEqual(residents.map(item=>item.name),operators.map(item=>item.name))
    assert.deepEqual(residents.map(item=>item.avatar_url),operators.map(item=>item.avatar_url))
    assert.deepEqual(residents.map(item=>item.id),ids)
  }
  assert.equal(ship[0].operators[0].name,undefined)
  assert.equal(operators[0].char_id,undefined)
})

test('ship ID lookup keeps direct matches first and hashes only unchanged standard template IDs',()=>{
  const id='chr_1234_synthetic',hash=value=>createHash('md5').update(value,'utf8').digest('hex')
  const invalid=['chr_synthetic','CHR_1234_synthetic','chr_123_synthetic','chr_1234_Synthetic','chr_1234_合成',` ${id}`,`${id} `,`${id}\n`,`${id}\r\n`]
  const operators=[{id:hash(id),name:'哈希匹配'},{id:'owned-id',char_id:id,name:'直接匹配'},...invalid.map(value=>({id:hash(value),name:'不可借用'}))]
  const residents=profileReport({ship:[{operators:[{charId:id,name:'来源姓名',avatar_url:'https://bbs.hycdn.cn/source.png'},{charId:id},...invalid.map(charId=>({charId}))]}],operators}).ship.rooms[0].operators
  assert.equal(residents[0].name,'来源姓名');assert.equal(residents[0].avatar_url,'https://bbs.hycdn.cn/source.png')
  assert.equal(residents[1].name,'直接匹配')
  assert.ok(residents.slice(2).every(item=>item.name==null))
  assert.deepEqual(residents.slice(2).map(item=>item.id),invalid)
})

test('trust stage progress restarts at each stage and is full once trusted', () => {
  for (const [percent, level, value] of [[0,'友好',0],[99,'友好',99],[100,'亲近',0],[163,'亲近',63],[199,'亲近',99],[200,'信任',100]]) {
    assert.deepEqual(trustStage(percent, level), { level, value, max: 100 }, `${percent}`)
    assert.deepEqual(trustStage(percent, null), { level, value, max: 100 }, `${percent} derived`)
  }
  for (const missing of [null, undefined, -1, 201, '']) assert.equal(trustStage(missing, '亲近'), null)
})
