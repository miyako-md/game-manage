import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, nodes, content } from '../test-utils/vue.js'
import { h } from 'vue'

test('Wuwa stamina and periodic progress are visible without opening a dialog', async t => {
  const Dashboard = await loadVue(new URL('./WuwaDashboard.vue', import.meta.url))
  const root = mount(t, Dashboard, { configured: true, snaps: {
    stamina: { payload: { current: 0, maximum: 240 } },
    progress: { payload: [{ name: '每日活跃', cur: 60, total: 100 }, { name: '未知挑战', cur: null, total: 30 }] },
  } })
  assert.ok(nodes(root, 'progress').some(n => n.props.value === 0 && n.props.max === 240))
  assert.match(content(root), /每日活跃/)
  assert.match(content(root), /未知 \/ 30/)
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.ok(!nodes(root, 'button').some(n => /查看体力|查看周期/.test(content(n))))
})

test('NTE stamina stays inline with source warning and unknown city activity', async t => {
  const Module = await loadVue(new URL('./NteModuleCard.vue', import.meta.url))
  const root = mount(t, Module, { capability: 'stamina', snap: { payload: {
    schema_version: 1, current: 0, maximum: 320, city_current: null, city_maximum: 100, daily_activity: 50,
  } } })
  assert.ok(nodes(root, 'progress').some(n => n.props.value === 0 && n.props.max === 320))
  assert.ok(!nodes(root, 'progress').some(n => n.props['aria-label'] === '都市活力'))
  assert.match(content(root), /未知 \/ 100/)
  assert.match(content(root), /塔吉多.*游戏内/)
  assert.equal(nodes(root, 'button').length, 0)
})

test('simple community cards render directly without a details button', async t => {
  const Module = await loadVue(new URL('./NteModuleCard.vue', import.meta.url))
  const Host = { setup: () => () => h(Module, {capability:'record'}, {default:()=>h('p','名片资料')}) }
  const root = mount(t, Host, {})
  assert.match(content(root), /名片资料/)
  assert.equal(nodes(root, 'button').length, 0)
})

test('visual meters preserve unknowns and zero, and clamp only the graphic for over-cap values', async t => {
  const Metrics = await loadVue(new URL('./SummaryMetrics.vue', import.meta.url))
  const root = mount(t, Metrics, {metrics:[
    {label:'未知',current:null,total:100}, {label:'未给上限',current:3,total:0},
    {label:'已清空',current:0,total:240}, {label:'超出',current:120,total:100},
  ]})
  assert.equal(nodes(root,'progress').length,2)
  assert.match(content(root),/120 \/ 100/)
  assert.ok(nodes(root,'div').some(n=>n.props.style?.['--fill']==='100%'))
  assert.ok(nodes(root,'div').some(n=>n.props.style?.['--fill']==='0%'))
})
