import test from 'node:test'
import assert from 'node:assert/strict'
import { cloudGameView, cloudOverviewView, snapshotCollection } from './cloud-view-model.js'

const account=(id,provider,capabilities=['account'])=>({account_id:id,provider,state:'active',capabilities,roles:[{role_id:`${id}-role`,is_default:true}]})

test('shared overview preserves website owner order, revoked filtering and Endfield identity selection',()=>{
  const accounts=[{...account('revoked','kuro'),state:'revoked'},account('ww-first','kuro'),{...account('ww-default','kuro'),is_default:true},account('passport','hypergryph'),account('skland','skland')]
  const view=cloudOverviewView({accounts})
  assert.equal(view.owners.wuthering_waves.account_id,'ww-first')
  assert.equal(view.owners.endfield.account_id,'skland')
  assert.deepEqual(view.games.map(game=>game.game_id),['wuthering_waves','endfield'])
  assert.equal(view.games[1].platform,'终末地 / 森空岛档案')
  assert.deepEqual(view.games[1].capabilities,['account','stamina'])
})

test('shared overview projects Skland zero and unknown stamina without mutating the cached source',()=>{
  const snapshotsByAccount={a:{account:{state:'ok',payload:{base:{name:'本人',level:0},stamina:{current:0,maximum:240}}}},b:{account:{state:'ok',payload:{base:{name:'未知体力'}}}}}
  const before=structuredClone(snapshotsByAccount)
  const view=cloudOverviewView({accounts:[account('a','skland')],snapshotsByAccount})
  assert.deepEqual(view.snapshots.endfield.account.payload,{schema_version:1,nickname:'本人',level:0})
  assert.deepEqual(view.snapshots.endfield.stamina.payload,{schema_version:1,current:0,maximum:240})
  assert.equal(cloudOverviewView({accounts:[account('b','skland')],snapshotsByAccount}).snapshots.endfield.stamina.payload,null)
  assert.deepEqual(snapshotsByAccount,before)
})

test('both surfaces use the same error envelope and failure-state collection mapping',()=>{
  const privateSnapshots={account:{state:'source_error',payload:{nickname:'旧昵称'},fetched_at:'2026-10-14T00:00:00Z',poll_status:{error:'安全来源错误'}},stamina:{state:'ok',payload:{current:0,maximum:240}}}
  const view=cloudOverviewView({accounts:[account('a','tajiduo',['account','stamina'])],snapshotsByAccount:{a:privateSnapshots}})
  const game=cloudGameView(account('a','tajiduo',['account','stamina']),privateSnapshots)
  assert.equal(view.readErrors.nte,'安全来源错误')
  const redacted=structuredClone(privateSnapshots)
  delete redacted.account.poll_status.error
  const afterRedaction=cloudOverviewView({accounts:[account('a','tajiduo',['account','stamina'])],snapshotsByAccount:{a:redacted}})
  assert.equal(afterRedaction.readErrors.nte,'来源读取异常')
  assert.equal(afterRedaction.collection[0].state,view.collection[0].state)
  assert.deepEqual(view.collection,game.collection)
  assert.equal(view.collection[0].state,'error')
  assert.equal(view.collection[0].last_success_at,'2026-10-14T00:00:00Z')
  assert.equal(view.collection[1].state,'ok')
  assert.equal(snapshotCollection('nte',{account:{state:'invalid_data'}})[0].state,'error')
  assert.equal(snapshotCollection('nte',{account:{state:'auth_expired'}})[0].state,'error')
  assert.equal(snapshotCollection('nte',{account:{state:'never'}})[0].state,'never')
})

test('shared overview retains passport platform and the website public/calendar overlay precedence',()=>{
  const privateNews={payload:['private']},publicNews={payload:['public']},calendarEvents={payload:['calendar']}
  const view=cloudOverviewView({accounts:[account('a','hypergryph',['account','gacha'])],snapshotsByAccount:{a:{news:privateNews}},publicSnapshots:{endfield:{news:publicNews,events:{payload:['public']}}},calendarSnapshots:{endfield:{events:calendarEvents}}})
  assert.equal(view.games[0].platform,'终末地 / 鹰角寻访')
  assert.equal(view.snapshots.endfield.news,publicNews)
  assert.equal(view.snapshots.endfield.events,calendarEvents)
  assert.deepEqual(view.collection,[])
})

test('game wrapper uses the same provider capabilities and source status for every supported identity',()=>{
  for(const [provider,id,name] of [['kuro','wuthering_waves','鸣潮'],['tajiduo','nte','异环'],['skland','endfield','终末地'],['hypergryph','endfield','终末地']]) {
    const view=cloudGameView(account('a',provider,['account','roles']))
    assert.equal(view.game.game_id,id)
    assert.equal(view.game.display_name,name)
    assert.deepEqual(view.game.capabilities,['account','roles','news','events'])
  }
})
