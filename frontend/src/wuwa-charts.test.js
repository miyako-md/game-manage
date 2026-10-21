import test from 'node:test'
import assert from 'node:assert/strict'
import { attributeSplit, bestRank, daysUntil, otherZoneStars, towerFloors, towerTeam, endLabel, expProgress, historySubject, levelBands, levelSeries, pityGauge, poolPulls, rarityTotals, recentGold, rosterSummary, seasonStars, sourceShares, towerTotals } from './wuwa-charts.js'

test('experience keeps unknown sides unknown and clamps only the percentage', () => {
  assert.equal(expProgress(null), null)
  assert.equal(expProgress({}), null)
  assert.deepEqual(expProgress({ next_exp: 4200, exp_limit: 9000 }), { cur: 4200, max: 9000, pct: 47 })
  assert.deepEqual(expProgress({ next_exp: 12000, exp_limit: 9000 }), { cur: 12000, max: 9000, pct: 100 })
  assert.deepEqual(expProgress({ next_exp: 5, exp_limit: null }), { cur: 5, max: null, pct: 0 })
})

test('days are counted on Beijing calendar days and past dates read as ended', () => {
  const now = Date.parse('2026-10-17T23:30:00+08:00')
  assert.equal(daysUntil('2026-10-18T00:30:00+08:00', now), 1)
  assert.equal(daysUntil('2026-10-17T23:59:00+08:00', now), 0)
  assert.equal(daysUntil('nonsense', now), null)
  assert.equal(endLabel('2026-10-17T23:59:00+08:00', now), '今日结束')
  assert.equal(endLabel('2026-10-18T10:00:00+08:00', now), '明日结束')
  assert.equal(endLabel('2026-10-22T03:59:00+08:00', now), '5 天后结束')
  assert.equal(endLabel('2026-10-01T00:00:00+08:00', now), '已结束')
  assert.equal(endLabel(null, now), null)
})

test('attribute counts sort by owned roles, skip unnamed ones and fold the tail', () => {
  const roles = ['冷凝', '热熔', '冷凝', '', null, '导电', '冷凝', '热熔'].map(attribute => ({ attribute }))
  assert.deepEqual(attributeSplit(roles), [{ label: '冷凝', value: 3 }, { label: '热熔', value: 2 }, { label: '导电', value: 1 }])
  assert.deepEqual(attributeSplit(roles, 2), [{ label: '冷凝', value: 3 }, { label: '其他', value: 3 }])
  assert.deepEqual(attributeSplit(null), [])
})

test('level bands run low to high, keep empty bands between and ignore unknown levels', () => {
  const roles = [90, 90, 90, 80, 71, 60, 20, null, undefined, 'x'].map(level => ({ level }))
  assert.deepEqual(levelBands(roles), [
    { label: '≤59', value: 1 }, { label: '60–69', value: 1 }, { label: '70–79', value: 1 }, { label: '80–89', value: 1 }, { label: '90+', value: 3 },
  ])
  assert.deepEqual(levelBands([{ level: 90 }, { level: 62 }]), [
    { label: '60–69', value: 1 }, { label: '70–79', value: 0 }, { label: '80–89', value: 0 }, { label: '90+', value: 1 },
  ])
  assert.deepEqual(levelBands([{ level: null }]), [])
})

test('roster summary counts rarity, full level and full chain without guessing unknowns', () => {
  const roles = [
    { star_level: 5, level: 90, chain: 6 }, { star_level: '5', level: 80, chain: 0 },
    { star_level: 4, level: null, chain: null }, { star_level: null, level: 90, chain: 7 },
  ]
  assert.deepEqual(rosterSummary(roles), { total: 4, five: 2, four: 1, maxLevel: 2, fullChain: 2 })
  assert.deepEqual(rosterSummary(null), { total: 0, five: 0, four: 0, maxLevel: 0, fullChain: 0 })
})

test('tower totals only state a cap when every area does', () => {
  assert.deepEqual(towerTotals([{ star: 12, max_star: 12 }, { star: 10, max_star: 12 }]), { got: 22, cap: 24 })
  assert.deepEqual(towerTotals([{ star: 12, max_star: 12 }, { star: 3 }]), { got: 15, cap: null })
  assert.deepEqual(towerTotals([{ max_star: 12 }]), { got: null, cap: 12 })
  assert.deepEqual(towerTotals([]), { got: null, cap: null })
})

test('income sources sort by amount, keep unknown rows and fold the tail into one part', () => {
  const rows = [{ type: '日常', num: 5 }, { type: '活动', num: 9 }, { type: '深塔', num: null }, { num: 1 }]
  assert.deepEqual(sourceShares(rows), [
    { label: '活动', value: 9 }, { label: '日常', value: 5 }, { label: '未知来源', value: 1 }, { label: '深塔', value: null },
  ])
  const many = Array.from({ length: 8 }, (_, i) => ({ type: `源${i}`, num: 8 - i }))
  const folded = sourceShares(many, 4)
  assert.deepEqual(folded.map(part => part.label), ['源0', '源1', '源2', '其他'])
  assert.equal(folded.at(-1).value, 5 + 4 + 3 + 2 + 1)
  assert.deepEqual(sourceShares(null), [])
})

test('folding the income legend keeps the sources without a number and a known zero remainder', () => {
  const known = Array.from({ length: 7 }, (_, i) => ({ type: `源${i}`, num: 7 - i }))
  assert.deepEqual(sourceShares([...known, { type: '深塔', num: null }, { type: '海墟' }]), [
    { label: '源0', value: 7 }, { label: '源1', value: 6 }, { label: '源2', value: 5 }, { label: '源3', value: 4 },
    { label: '其他', value: 3 + 2 + 1 }, { label: '数量未知的来源（2 项）', value: null },
  ])
  assert.deepEqual(sourceShares([...known, { type: '深塔', num: null }]).map(part => part.label), ['源0', '源1', '源2', '源3', '其他', '深塔'])
  const zeros = [{ type: '甲', num: 5 }, { type: '乙', num: 4 }, { type: '丙', num: 3 }, { type: '丁', num: 0 }, { type: '戊', num: 0 }]
  assert.deepEqual(sourceShares(zeros, 4).at(-1), { label: '其他', value: 0 })
})

test('rarity totals add every pool, five stars first, and leave empty buckets out', () => {
  const pools = [
    { rarity_distribution: { 3: 40, 4: 6, 5: 1 } },
    { rarity_distribution: { 3: 20, 4: 3, 5: 2, unknown: 1 } },
    { rarity_distribution: { 5: 0, 3: null } },
    {},
  ]
  assert.deepEqual(rarityTotals(pools), [
    { rarity: '5', value: 3 }, { rarity: '4', value: 9 }, { rarity: '3', value: 60 }, { rarity: 'unknown', value: 1 },
  ])
  assert.deepEqual(rarityTotals(null), [])
})

test('pool pulls keep every pool and its slot when the total is unknown', () => {
  assert.deepEqual(poolPulls([{ pool: '1', name: '角色池', total: 77 }, { pool: '9', total: null }, { total: 3 }]), [
    { label: '角色池', value: 77 }, { label: '卡池 9', value: null }, { label: '卡池 未知', value: 3 },
  ])
})

test('recent five-star records come newest first and keep the order of equal times', () => {
  const rows = [
    { name: 'a', time: '2026-09-01T10:00:00' }, { name: 'b', time: '2026-10-01 09:00:00' },
    { name: 'c', time: '2026-10-01T09:00:00' }, { name: 'd', time: null },
  ]
  assert.deepEqual(recentGold(rows).map(row => row.name), ['b', 'c', 'a', 'd'])
  assert.deepEqual(recentGold(rows, 2).map(row => row.name), ['b', 'c'])
  assert.deepEqual(recentGold(undefined), [])
  // Instants, not strings: 02:00Z is an hour after 09:00 Beijing time.
  const offsets = [{ name: 'x', time: '2026-10-01T09:00:00+08:00' }, { name: 'y', time: '2026-10-01T02:00:00Z' }, { name: 'z', time: 'not a time' }]
  assert.deepEqual(recentGold(offsets).map(row => row.name), ['y', 'x', 'z'])
})

test('a pity ring needs an exact count and a cap from the user rule', () => {
  assert.deepEqual(pityGauge({ status: 'exact', count: 12, hard_pity_remaining: 68 }), { value: 12, max: 80 })
  assert.deepEqual(pityGauge({ status: 'exact', count: 0, hard_pity_remaining: 70 }), { value: 0, max: 70 })
  for (const pity of [{ status: 'lower_bound', count: 12, hard_pity_remaining: 68 }, { status: 'exact', count: 3 }, { status: 'unknown' }, null])
    assert.equal(pityGauge(pity), null)
})

test('level series need two observations of the same role and run in time order', () => {
  const items = [
    { id: 11, subject: '1', observed_at: '2026-10-03T10:00:00+08:00', payload: { level: 80 } },
    { id: 12, subject: '2', observed_at: '2026-10-03T10:00:00+08:00', payload: { level: 50 } },
    { id: 13, subject: '1', observed_at: '2026-10-01T10:00:00+08:00', payload: { data: { role: { level: 70 } } } },
    { id: 14, subject: '1', observed_at: 'not a date', payload: { level: 99 } },
    { id: 15, subject: '3', observed_at: '2026-10-02T10:00:00+08:00', payload: { level: null } },
    { id: 16, subject: '3', observed_at: '2026-10-04T10:00:00+08:00', payload: { level: 10 } },
  ]
  const series = levelSeries(items)
  assert.deepEqual([...series.keys()], ['1'])
  assert.deepEqual(series.get('1').points.map(point => point.value), [70, 80])
  assert.match(series.get('1').points[0].label, /2026-10-01 10:00/)
  assert.equal(series.get('1').id, 11, 'the newest record carries the chart')
  assert.equal(levelSeries(null).size, 0)
  assert.equal(historySubject({ payload: { role_id: 7 } }), '7')
  assert.equal(historySubject({ subject: 0 }), '0')
})

test('season stars add the deep zone areas and skip seasons without a total', () => {
  const season = (end, stars) => ({ season: end, payload: { difficulty_list: [
    { difficulty: 2, tower_area_list: [{ star: 99 }] },
    { difficulty: 3, tower_area_list: stars.map(star => ({ star })) },
  ] } })
  const items = [season('2026-10-12T04:00:00+08:00', [12, 12, 6]), season('2026-09-14T04:00:00+08:00', [10, 9]), season('2026-08-17T04:00:00+08:00', []), { season: '2026-07-20T04:00:00+08:00', payload: {} }]
  assert.deepEqual(seasonStars(items), [{ label: '09-14', value: 19 }, { label: '10-12', value: 30 }])
  assert.deepEqual(seasonStars(null), [])
})

test('tower floors count full floors only when every floor can be told, an area at full stars making its floors full', () => {
  const floor = (star, max_star, roles) => ({ star, max_star, role_list: roles })
  assert.equal(towerFloors(null), null)
  assert.equal(towerFloors({ tower_area_list: [{ star: 3, max_star: 12, floor_list: [] }] }), null)
  assert.deepEqual(towerFloors({ tower_area_list: [
    { star: 9, max_star: 12, floor_list: [floor(3, 3), floor(2, 3), floor(3, 3)] }, { floor_list: [floor(0, 3)] },
  ] }), { full: 2, total: 4 })
  assert.deepEqual(towerFloors({ tower_area_list: [{ star: 6, max_star: 6, floor_list: [floor(null, null), floor(3, null)] }] }), { full: 2, total: 2 })
  assert.deepEqual(towerFloors({ tower_area_list: [{ star: 5, max_star: 6, floor_list: [floor(3, 3), floor(2, null)] }] }), { full: null, total: 2 }, 'an unknown floor is not a zero')
})

test('the tower team is the deepest floor that names one, capped at three roles', () => {
  const roles = ids => ids.map(role_id => ({ role_id }))
  const zone = { tower_area_list: [
    { area_name: '甲塔', floor_list: [{ floor: 1, role_list: roles([1]) }, { floor: 4, role_list: roles([4, 5, 6, 7]) }] },
    { area_name: '乙塔', floor_list: [{ floor: 2, roles: roles([8]) }, { floor: 3, role_list: [] }] },
  ] }
  assert.deepEqual(towerTeam(zone), { area: '乙塔', floor: 2, roles: roles([8]) })
  assert.deepEqual(towerTeam({ tower_area_list: [zone.tower_area_list[0]] }), { area: '甲塔', floor: 4, roles: roles([4, 5, 6]) })
  assert.equal(towerTeam({ tower_area_list: [{ floor_list: [{ floor: 1 }] }] }), null)
  assert.equal(towerTeam(null), null)
})

test('other tower zones total their stars and leave out the deep zone and zones without earned stars', () => {
  assert.deepEqual(otherZoneStars([
    { difficulty: 3, difficulty_name: '深境区', tower_area_list: [{ star: 1, max_star: 3 }] },
    { difficulty: 4, difficulty_name: '超载区', tower_area_list: [{ star: 10, max_star: 12 }, { star: 8, max_star: 12 }] },
    { difficulty: 2, tower_area_list: [{ star: 4 }] },
    { difficulty: 1, difficulty_name: '稳定区', tower_area_list: [{ star: null, max_star: 12 }] },
  ]), [{ name: '超载区', got: 18, cap: 24 }, { name: '分区 2', got: 4, cap: null }])
  assert.deepEqual(otherZoneStars(null), [])
})

test('the best slash rank follows SSS > SS > S > A > B > C and ignores unknown ranks', () => {
  assert.equal(bestRank([{ rank: 'A' }, { rank: 'ss' }, { rank: 'S' }]), 'SS')
  assert.equal(bestRank([{ rank: 'B' }, { rank: null }, { rank: '?' }, { rank: 5 }]), 'B')
  assert.equal(bestRank([{ rank: null }, {}]), null)
  assert.equal(bestRank(null), null)
})
