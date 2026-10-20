import test from 'node:test'
import assert from 'node:assert/strict'
import { areaViews, gachaRating, gachaTone, gachaView, gauge, houseView, luckTone, officialPullIcon, progressView, pullTime, roleBreakdown, rosterOrder, vehicleView } from './nte-charts.js'

test('a gauge needs both counts and a positive total, keeps zero, and reports excess without growing the ring', () => {
  assert.equal(gauge(null, 10).known, false)
  assert.equal(gauge(3, 0).known, false)
  assert.equal(gauge(3, null).pct, null)
  assert.deepEqual([gauge(0, 5).known, gauge(0, 5).pct], [true, 0])
  const over = gauge(105, 100)
  assert.deepEqual([over.pct, over.over, over.current], [100, true, 105])
  assert.equal(gauge(100, 100).over, false)
  assert.equal(gauge('4', '8').pct, 50)
})

test('areas keep their detail lines and never invent a percentage for unknown counts', () => {
  const [a, b] = areaViews([{ id: 'a', name: '中心区', current: 48, total: 50, details: [{ name: '宝箱', current: null, total: 10 }, null] }, { name: '  ', current: null, total: 5 }, null])
  assert.equal(a.pct, 96)
  assert.deepEqual(a.details.map(d => [d.name, d.known]), [['宝箱', false]])
  assert.deepEqual([b.name, b.known, b.key], ['', false, 1])
  assert.deepEqual(areaViews(undefined), [])
})

test('progress separates the three medal tiers and leaves a missing tier unknown rather than zero', () => {
  const view = progressView({ completed: 5, total: 20, bronze: 0, silver: 2, gold: null, categories: [{ id: 'x', name: '都市', current: 1, total: 4 }] })
  assert.equal(view.ring.pct, 25)
  assert.deepEqual(view.medals.map(m => [m.key, m.value]), [['gold', null], ['silver', 2], ['bronze', 0]])
  assert.deepEqual(view.categories.map(c => [c.name, c.pct]), [['都市', 25]])
  assert.equal(progressView(null).ring.known, false)
})

test('roster counts order S before A and elements by size, and ignore roles that do not report a field', () => {
  const entries = [
    { name: '甲', quality: 'A', element: '光', level: 40 }, { name: '乙', quality: 'S', element: '光', level: 60 },
    { name: '丙', quality: 'S', element: '魂', level: 55 }, { name: '丁', element: '', level: null }, null,
  ]
  const stats = roleBreakdown(entries)
  assert.equal(stats.total, 4)
  assert.deepEqual(stats.quality, [{ label: 'S', value: 2 }, { label: 'A', value: 1 }])
  assert.deepEqual(stats.element, [{ label: '光', value: 2 }, { label: '魂', value: 1 }])
  assert.deepEqual([stats.averageLevel, stats.maxLevel], [52, 60])
  assert.deepEqual(roleBreakdown([]), { total: 0, quality: [], element: [], averageLevel: null, maxLevel: null })
})

test('the roster rail lists the strongest roles first and puts unknown levels last without mutating the source', () => {
  const entries = [{ name: '丁' }, { name: '甲', quality: 'A', level: 60 }, { name: '乙', quality: 'S', level: 50 }, { name: '丙', quality: 'S', level: 60 }, { name: '戊', quality: 'S' }]
  const before = entries.map(role => role.name).join()
  assert.deepEqual(rosterOrder(entries).map(role => role.name), ['丙', '乙', '戊', '甲', '丁'])
  assert.equal(entries.map(role => role.name).join(), before)
})

test('rating and tone codes follow the community page, and an unknown code is never coloured', () => {
  assert.deepEqual([0, 1, 2, 3, 4, 99].map(code => gachaTone({ lucky_type: code })), ['medium', 'short', 'short', 'medium', 'long', 'unknown'])
  assert.deepEqual([0, 1, 2, 3, 4].map(code => gachaRating({ lucky_type: code })), ['', '超欧', '欧', '非', '超非'])
  assert.deepEqual([0, 1, 5, 6, 10, 11, 15, 16].map(luckTone), ['unknown', 'short', 'short', 'medium', 'medium', 'long', 'long', 'unknown'])
})

test('pull icons come from the numeric role id or the fork id and nowhere else', () => {
  assert.equal(officialPullIcon('1001'), 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/tall/1001.PNG')
  assert.equal(officialPullIcon('fork_night'), 'https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/character/fork/fork_night.png')
  assert.equal(officialPullIcon('a'), null)
  assert.equal(officialPullIcon('../1'), null)
  assert.equal(officialPullIcon(undefined), null)
})

test('pull times without a zone are Beijing time, and a missing or bad time sorts last', () => {
  assert.equal(pullTime('2026-09-20 21:14:00'), Date.parse('2026-09-20T21:14:00+08:00'))
  assert.equal(pullTime('2026-09-20T13:14:00Z'), Date.parse('2026-09-20T21:14:00+08:00'))
  assert.equal(pullTime(''), null)
  assert.equal(pullTime('later'), null)
  assert.equal(pullTime(null), null)
  assert.equal(pullTime(1789910040000), null)
  assert.equal(pullTime(new Date('2026-09-20T13:14:00Z')), null)
  assert.equal(pullTime('2026-02-30T10:00:00+08:00'), null)
  assert.equal(pullTime('2026-09-20T21:14:00+0800'), Date.parse('2026-09-20T13:14:00Z'))
})

test('gacha view totals the pools, splits S pulls by luck and lists the newest pulls first', () => {
  const view = gachaView({ luck_title: '欧气冲天', luck_type: 3, pools: [
    { name: '限定', total_draws: 100, s_count: 2, average: 50, guarantee: 90, details: [
      { item_id: 'a', name: '甲', pity: 80, obtained_at: '2026-09-01T00:00:00Z', lucky_type: 4 },
      { item_id: 'b', name: '乙', pity: 20, obtained_at: '2026-09-02T00:00:00Z', lucky_type: 1 },
    ] },
    { name: '常驻', total_draws: 0, s_count: 0, average: null, details: [] },
    { total_draws: null, s_count: null, average: null, guarantee: 0, details: [{ item_id: 'c', pity: null, obtained_at: null }] },
  ] })
  assert.deepEqual([view.title, view.titleTone, view.totalDraws, view.totalS, view.pulls], ['欧气冲天', 'short', 100, 2, 3])
  assert.deepEqual(view.recent.map(item => item.entry.item_id), ['b', 'a', 'c'])
  assert.deepEqual(view.tones, { short: 1, medium: 0, long: 1, unknown: 1 })
  assert.deepEqual(view.pools.map(pool => pool.name), ['限定', '常驻', '未命名卡池'])
  assert.equal(view.pools[0].reach.pct, (50 / 90) * 100)
  assert.equal(view.pools[1].reach, null, 'no average, no ring')
  assert.equal(view.pools[2].guarantee, null, 'a zero scale is no scale')
  assert.equal(gachaView({ pools: [{ details: Array.from({ length: 30 }, (_, i) => ({ item_id: String(i) })) }] }, 5).recent.length, 5)
  assert.deepEqual([gachaView(null).totalDraws, gachaView({ pools: [] }).totalS], [null, null])
})

test('the source totals win over the pool sums, and unknown pool counts stay unknown', () => {
  assert.equal(gachaView({ total_draws: 638, pools: [{ total_draws: 1 }] }).totalDraws, 638)
  assert.equal(gachaView({ pools: [{ total_draws: 1 }, { total_draws: 2 }] }).totalDraws, 3)
  assert.equal(gachaView({ pools: [{ total_draws: null }] }).totalDraws, null)
})

test('houses and vehicles count furniture and read stats as the source wrote them', () => {
  const house = houseView({ name: '海景房', owned: false, resident_ids: [1019, '1020'], furniture: [{ owned: true }, { owned: null }, { owned: true }] })
  assert.deepEqual([house.owned, house.residents, house.furnitureOwned, house.furnitureTotal], [false, ['1019', '1020'], 2, 3])
  assert.equal(houseView({ owned: null }).owned, null)
  const car = vehicleView({ id: 'v1', name: '街道之星', owned: true, base: [{ name: '极速', value: '146 km/h' }, { name: '座位' }], advanced: [{ name: '引擎', value: '4', maximum: '5' }, { name: '悬挂', value: '0', maximum: null }], models: [{}, {}] }, 'v1')
  assert.equal(car.showcase, true)
  assert.deepEqual(car.base, [{ name: '极速', value: '146 km/h' }, { name: '座位', value: '未知' }])
  assert.deepEqual(car.advanced.map(stat => [stat.pct, stat.known]), [[80, true], [null, false]])
  assert.equal(car.models, 2)
  assert.equal(vehicleView({ id: 'v1' }, '').showcase, false)
  assert.equal(vehicleView({ id: 'v1' }, undefined).showcase, false)
})


test('recent pull ordering uses the same validated date contract as display', () => {
  const view = gachaView({ pools: [{ details: [
    { item_id: 'invalid', obtained_at: '2026-02-30T10:00:00+08:00' },
    { item_id: 'known', obtained_at: '2026-02-28T10:00:00+0800' },
  ] }] })
  assert.deepEqual(view.recent.map(item => item.entry.item_id), ['known', 'invalid'])
})
