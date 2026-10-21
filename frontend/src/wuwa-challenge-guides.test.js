import test from 'node:test'
import assert from 'node:assert/strict'
import { challengeGuides, mergeTowerGuides, previousTowerGuides, selectChallengeGuides } from './wuwa-challenge-guides.js'
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
  const next=Date.parse('2026-11-09T04:00:00+08:00')
  for(const now of [start,end-1]) {
    assert.deepEqual(selectChallengeGuides('tower','',now).map(g=>g.id),['1549413440713461760'])
  }
  for(const now of [end,next-1]) assert.deepEqual(selectChallengeGuides('tower','',now).map(g=>g.id),['1559169379056631808'])
  for(const now of [start-1,next,next+86400000]) assert.deepEqual(selectChallengeGuides('tower','',now),[])
})

const found=(values={})=>({id:'9',modes:['tower'],format:'图文攻略',title:'鸣潮逆境深塔261109期推荐阵容',author:'作者甲',
  scope:'2026-11-09 期深境区',publishedAt:'2026-11-09 12:00',version:null,status:'unreviewed',lineupImages:[],
  periodStart:'2026-11-09T04:00:00+08:00',periodEnd:'2026-12-07T04:00:00+08:00',url:'https://www.kurobbs.com/forum/post/9',...values})

test('automatically found tower posts fill only periods without a reviewed entry',()=>{
  const next=Date.parse('2026-11-10T12:00:00+08:00')
  const extra=mergeTowerGuides([found(),found({id:'1559169379056631808'}),found({id:'8',periodStart:'2026-10-12T04:00:00+08:00'}),
    found({id:'7',url:'https://evil.example/post/7'}),found({id:'6',format:'视频攻略'}),found({id:'5',periodEnd:'bad'}),null])
  assert.deepEqual(extra.map(g=>g.id),['9'])
  assert.deepEqual(selectChallengeGuides('tower','',next,extra).map(g=>g.id),['9'])
  assert.deepEqual(mergeTowerGuides(undefined),[])
})

test('the previous period is only the most recently ended one',()=>{
  const next=Date.parse('2026-11-10T12:00:00+08:00')
  assert.deepEqual(previousTowerGuides(next).map(g=>g.id),['1559169379056631808'])
  assert.deepEqual(previousTowerGuides(Date.parse('2026-12-08T12:00:00+08:00'),[found()]).map(g=>g.id),['9'])
  assert.deepEqual(previousTowerGuides(Date.parse('2026-01-01T00:00:00+08:00')),[])
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
