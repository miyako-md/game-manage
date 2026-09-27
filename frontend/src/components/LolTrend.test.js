import test from 'node:test'
import assert from 'node:assert/strict'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'
const LolTrend = await loadVue(new URL('./LolTrend.vue', import.meta.url))

test('winrate plots the supplied decided-result rate rather than all archived games', t => {
  const root = mount(t, LolTrend, { metric: 'winrate', label: '胜率趋势', unit: '%', rows: [
    { date: '2026-09-01', games: 4, wins: 1, winrate: 50 }, // one loss, one unknown, one remake
    { date: '2026-09-02', games: 1, wins: 0, winrate: null }, // remake only
  ] })
  assert.equal(nodes(root, 'circle').length, 1)
  assert.equal(nodes(root, 'circle')[0].props.cy, 82)
  assert.match(content(root), /重开与未知胜负不计入胜率分母/)
  assert.match(content(nodes(root, 'table')[0]), /2026-09-01 4 50%.*2026-09-02 1 未知/)
})

test('trend shows real zero, skips null, and never joins across unknown values', t => {
  const root = mount(t, LolTrend, { metric: 'winrate', label: '胜率趋势', unit: '%', rows: [
    { date: '2026-09-01', games: 1, winrate: 0 },
    { date: '2026-09-02', games: 1, winrate: null },
    { date: '2026-09-03', games: 1, winrate: 100 },
  ] })
  assert.equal(nodes(root, 'circle').length, 2)
  assert.equal(nodes(root, 'polyline').length, 2)
  assert.equal(nodes(root, 'circle')[0].props.cy, 138)
  assert.match(content(root), /0%/)
  assert.match(content(root), /未知/)
})

test('score chart uses 3–16 reference scale and an explicit empty state', t => {
  const root = mount(t, LolTrend, { metric: 'average_score', label: '参考评分趋势', min: 3, max: 16, rows: [{ date: '2026-09-01', average_score: null }] })
  assert.equal(nodes(root, 'circle').length, 0)
  assert.match(content(root), /缺失指标不会按 0/)
})
