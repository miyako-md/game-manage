import test from 'node:test'
import assert from 'node:assert/strict'
import { challengeGuides, selectChallengeGuides } from './wuwa-challenge-guides.js'
import { guideSourceUrl } from './wuwa-guides.js'

test('challenge sources stay mode and boss specific, with newer sources first',()=>{
  const tower=selectChallengeGuides('tower','',Date.parse('2026-09-26T12:00:00+08:00'))
  assert.equal(tower[0].id,'1549413440713461760')
  assert.ok(tower.every(g=>g.modes.includes('tower')))
  const boss=selectChallengeGuides('hologram','海维夏')
  assert.ok(boss.length)
  assert.ok(boss.every(g=>g.boss==='海维夏'))
  assert.deepEqual(selectChallengeGuides('hologram','尚未收录的首领'),[])
  assert.deepEqual(selectChallengeGuides('unknown'),[])
})

test('tower only shows current-period illustrated guides and never falls back across resets',()=>{
  const start=Date.parse('2026-09-14T04:00:00+08:00')
  const end=Date.parse('2026-10-12T04:00:00+08:00')
  for(const now of [start,end-1]) {
    assert.deepEqual(selectChallengeGuides('tower','',now).map(g=>g.id),['1549413440713461760'])
  }
  for(const now of [start-1,end,end+86400000]) assert.deepEqual(selectChallengeGuides('tower','',now),[])
})
test('each source has public attribution and encounter scope, without pretending unknown versions are current',()=>{
  assert.equal(new Set(challengeGuides.map(g=>g.id)).size,challengeGuides.length)
  for(const g of challengeGuides){
    assert.ok(guideSourceUrl(g.url));assert.ok(g.title&&g.author&&g.scope&&g.publishedAt)
    assert.ok(g.version===null||/^\d+\.\d+$/.test(g.version))
    if(g.format==='视频攻略') assert.match(g.summary,/未转写/)
  }
  assert.equal(challengeGuides.find(g=>g.boss==='炉芯机骸').version,null)
  assert.doesNotMatch(JSON.stringify(challengeGuides),/游戏UID|token|account_id|100840380/)
})
