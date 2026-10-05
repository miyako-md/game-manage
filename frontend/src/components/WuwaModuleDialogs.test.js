import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, content, nodes, choose } from '../test-utils/vue.js'
const component = name => loadVue(new URL(`./${name}.vue`, import.meta.url))
const tick = async () => { await new Promise(resolve=>setImmediate(resolve)); await nextTick() }
async function click(root,label) {
  const node=nodes(root,'button').find(n=>content(n)===label)
  assert.ok(node,label);node.props.onClick();await tick()
}
const account={payload:{nickname:'档案甲',level:0,extra:{role_id:'test',server_id:'server',profile:{box_list:[{box_name:'秘密箱明细',num:0}]}}}}

test('profile detail mounts only inside a dialog, and account change closes it',async t=>{
  const props=reactive({snaps:{account},configured:true})
  const root=mount(t,await component('WuwaDashboard'),props)
  assert.doesNotMatch(content(root),/秘密箱明细/)
  await click(root,'查看账号档案')
  assert.equal(nodes(root,'dialog').length,1)
  assert.match(content(root),/秘密箱明细/)
  props.snaps={account:{payload:{extra:{role_id:'new',server_id:'server'}}}}
  await tick()
  assert.equal(nodes(root,'dialog').length,0)
  assert.doesNotMatch(content(root),/秘密箱明细/)
})

test('gacha remains lazy and opening its dialog only reads the local archive',async t=>{
  const calls=[]
  t.mock.method(globalThis,'fetch',async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>({role_id:'test',server_id:'server',items:[],pools:[]})}})
  const root=mount(t,await component('WuwaDashboard'),{snaps:{account},configured:true,initialSection:'gacha'})
  await tick();assert.equal(calls.length,0)
  await click(root,'查看抽卡历史')
  assert.equal(nodes(root,'dialog').length,1)
  assert.ok(calls.some(c=>c.url.includes('/gacha?')))
  assert.ok(calls.every(c=>!c.options?.method||c.options.method==='GET'))
})

test('challenge guides are accessible independently of failed battle snapshots',async t=>{
  t.mock.method(Date,'now',()=>Date.parse('2026-09-26T12:00:00+08:00'))
  const root=mount(t,await component('WuwaCombat'),{snap:{payload:{tower:{state:'error',error:'战绩暂不可用'}}}})
  assert.equal(nodes(root,'dialog').length,0)
  await click(root,'查看逆境深塔')
  assert.equal(nodes(root,'dialog').length,1)
  await click(root,'社区攻略')
  assert.match(content(root),/260914/)
  assert.match(content(root),/3\.6/)
  assert.doesNotMatch(content(root),/2026-08-17|视频攻略|新手高难副本入门/)
})

test('challenge boss filtering never fills a missing boss with unrelated guides',async t=>{
  const root=mount(t,await component('WuwaChallengeGuides'),{mode:'hologram',bosses:['海维夏','叹息古龙']})
  nodes(root,'select')[0].props['onUpdate:modelValue']('海维夏')
  await tick()
  const cards=nodes(root,'article')
  assert.ok(cards.length)
  assert.ok(cards.every(n=>content(n).includes('海维夏')))
  nodes(root,'select')[0].props['onUpdate:modelValue']('叹息古龙')
  await tick()
  assert.equal(nodes(root,'article').length,0)
  assert.match(content(root),/暂未收录此首领/)
})

test('activity details retain source errors and stale status inside the dialog',async t=>{
  const root=mount(t,await component('WuwaActivities'),{snap:{stale:true,error:'玩法采集失败',payload:{sections:{one:{title:'测试玩法',progress:0}}}}})
  await click(root,'查看详情')
  const dialog=nodes(root,'dialog')[0]
  assert.match(content(dialog),/玩法采集失败/)
  assert.match(content(dialog),/旧数据/)
})

test('empty news keeps source failure visible without requiring a private account',async t=>{
  const root=mount(t,await component('WuwaDashboard'),{initialSection:'news',snaps:{news:{payload:[],stale:true,error:'公告采集失败'}}})
  assert.match(content(root),/暂无公告与资讯/)
  assert.match(content(root),/公告采集失败/)
  assert.match(content(root),/数据可能过期/)
})

test('tower lineup pictures are inline, switch per source, and recover after an image failure',async t=>{
  const { challengeGuides }=await import('../wuwa-challenge-guides.js')
  const sources=challengeGuides.filter(g=>g.modes.includes('tower')&&g.author==='轩儿Xuaner')
  assert.equal(sources.length,2)
  assert.ok(sources.every(g=>g.lineupImages.length===6))
  const props=reactive({guide:sources[0]})
  const root=mount(t,await component('WuwaGuideLineups'),props)
  assert.equal(nodes(root,'img')[0].props.src,sources[0].lineupImages[0])
  await click(root,'阵容图 6')
  assert.equal(nodes(root,'img')[0].props.src,sources[0].lineupImages[5])
  nodes(root,'img')[0].props.onError();await tick()
  assert.match(content(root),/图片暂未加载/)
  await click(root,'阵容图 2')
  assert.equal(nodes(root,'img')[0].props.src,sources[0].lineupImages[1])
  props.guide=sources[1];await tick()
  assert.equal(nodes(root,'img')[0].props.src,sources[1].lineupImages[0])
  assert.match(nodes(root,'img')[0].props.alt,/2026-08-17/)
})

test('upstream role filters and rarity display still open the local guide dialog', async t => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 502 }))
  const root = mount(t, await component('WuwaRoles'), { accountKey: 'test:server', snap: { payload: [
    { role_id: '1304', name: '今汐', star_level: 5, attribute: '衍射' },
    { role_id: '1102', name: '散华', star_level: 4, attribute: '冷凝' },
  ] } })
  choose(root, '稀有度', '5'); await tick()
  assert.match(content(root), /筛选 1 位/)
  assert.ok(nodes(root, 'span').some(n => n.props['aria-label'] === '5 星'))
  await click(root, nodes(root, 'button').map(content).find(text => text.includes('今汐')))
  await click(root, '培养攻略')
  assert.match(content(nodes(root, 'dialog')[0]), /时和岁稔/)
})

test('activity summaries retain upstream numeric pairs while nested fields stay in the dialog', async t => {
  const root = mount(t, await component('WuwaActivities'), { snap: { payload: { sections: {
    one: { title: '测试进度', count: 0, max_count: 10, extra: { title: '详细来源条目' } },
  } } } })
  assert.match(content(root), /0 \/ 10/)
  assert.doesNotMatch(content(root), /详细来源条目/)
  await click(root, '查看详情')
  assert.match(content(nodes(root, 'dialog')[0]), /详细来源条目/)
})

test('slash dialog retains upstream buffs and supplemental fields without mounting other records', async t => {
  const root = mount(t, await component('WuwaCombat'), { roleNames: { 1501: '今汐' }, snap: { payload: {
    slash: { data: { difficulty_list: [{ difficulty_name: '深海', all_score: 0, max_score: 100,
      challenge_list: [{ challenge_name: '试炼', score: 0, rank: null, half_list: [
        { half_name: '上半场', score: 0, role_list: [{ role_id: 1501 }], buff_name: '本期增益', buff_description: '增益条件', custom_field: '来源保留值' },
      ] }],
    }] } },
    hologram: { data: { challenge_info: { one: [{ boss_name: '其他模式首领' }] } } },
  } } })
  await click(root, '查看冥歌海墟')
  const dialog = content(nodes(root, 'dialog')[0])
  for (const value of ['今汐', '本期增益', '增益条件', '来源保留值', '0']) assert.ok(dialog.includes(value), value)
  assert.doesNotMatch(dialog, /其他模式首领/)
})
