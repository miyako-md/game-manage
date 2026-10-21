import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick } from 'vue'
import { loadVue, mount, content, nodes } from '../test-utils/vue.js'

const component = name => loadVue(new URL(`./${name}.vue`, import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
const find = (root, predicate) => {
  const found = []
  const walk = n => { if (predicate(n)) found.push(n); n.children.forEach(walk) }
  walk(root)
  return found
}
const byClass = (root, name) => find(root, n => String(n.props.class ?? '').split(/\s+/).includes(name))
const meters = root => find(root, n => n.props.role === 'meter')
const snap = payload => ({ payload, fetched_at: '2026-10-16T04:00:00Z', stale: false })
const identity = { role_id: 'account', server_id: 'server' }
const reply = payload => ({ ok: true, json: async () => payload })

test('stamina is a ring with its figure; a full gauge says so and an unknown one draws nothing', async t => {
  const Stamina = await component('StaminaCard')
  const root = mount(t, Stamina, { label: '结晶波片', snap: snap({ current: 160, maximum: 240, expected_full_at: '2026-10-17T13:00:00Z' }) })
  const [ring] = meters(root)
  assert.deepEqual([ring.props['aria-valuenow'], ring.props['aria-valuemax'], ring.props['aria-label']], [160, 240, '结晶波片'])
  assert.match(content(root), /160 \/ 240/)
  assert.match(content(root), /预计 .* 恢复满/)
  assert.match(content(mount(t, Stamina, { label: '理智', snap: snap({ current: 240, maximum: 240 }) })), /理智已满/)
  const unknown = mount(t, Stamina, { snap: snap({ current: null, maximum: 240 }) })
  assert.equal(meters(unknown).length, 0)
  assert.match(content(unknown), /未知 \/ 240/)
})

test('periodic progress rings only the rows that state a cap, and keeps unknown, zero and over-cap readable', async t => {
  const root = mount(t, await component('ProgressCard'), { snap: snap([
    { name: '冥歌海墟', cur: 22500, total: 24000 }, { name: '未知挑战', cur: null, total: 30 },
    { name: '终焉矩阵', cur: 0, total: 0 }, { name: '超额', cur: 120, total: 100 },
  ]) })
  assert.deepEqual(meters(root).map(n => [n.props['aria-label'], n.props['aria-valuenow'], n.props['aria-valuemax']]), [['冥歌海墟', 22500, 24000], ['超额', 120, 100]])
  assert.match(content(root), /94%/)
  assert.match(content(root), /未知 \/ 30/)
  assert.match(content(root), /终焉矩阵 0/)
  assert.match(content(root), /120 \/ 100/)
})

test('exploration rings every region and the phantom levels; area chips stay out of the compact summary', async t => {
  const Exploration = await component('ExplorationCard')
  const data = snap({
    country_groups: [{ name: '瑝珑', progress: 96.4, areas: [{ name: '今州', progress: 100 }] }, { name: '新区', progress: null, areas: [] }],
    detections: { total: 199, by_level: { 轻波级: 112, 巨浪级: 51 } },
  })
  const full = mount(t, Exploration, { snap: data })
  assert.deepEqual(meters(full).map(n => [n.props['aria-label'], n.props['aria-valuenow']]), [['瑝珑 探索度', 96.4]])
  assert.match(content(full), /今州 100%/)
  assert.match(content(full), /新区/)
  assert.match(content(full), /残象已收录 199/)
  assert.match(content(full), /轻波级 112/)
  const compact = mount(t, Exploration, { snap: data, compact: true })
  assert.doesNotMatch(content(compact), /今州/)
  assert.match(content(compact), /瑝珑/)
})

test('the roster strip counts every recorded role and stays out of the bot image', async t => {
  const Roles = await component('WuwaRoles')
  const roles = [
    { role_id: '1', name: '甲', star_level: 5, level: 90, chain: 6, attribute: '衍射', weapon: '长刃' },
    { role_id: '2', name: '乙', star_level: 4, level: 70, chain: 0, attribute: '冷凝', weapon: '音感仪' },
    { role_id: '3', name: '丙', star_level: 5, level: 90, chain: 1, attribute: '衍射', weapon: '长刃' },
  ]
  const web = mount(t, Roles, { snap: snap(roles) })
  const strip = byClass(web, 'roster-summary')[0]
  assert.ok(strip)
  assert.match(content(strip), /已记录角色 3 位/)
  assert.match(content(strip), /5 星 2/)
  assert.match(content(strip), /满级 2/)
  assert.match(content(strip), /满链 1/)
  assert.match(content(strip), /衍射 2 位/)
  assert.equal(byClass(strip, 'bar-col').length, 3)
  const image = mount(t, Roles, { snap: snap(roles), imageMode: true })
  assert.equal(byClass(image, 'roster-summary').length, 0)
})

test('the combat cards chart the deep zone, list a boss once with its best record and show each slash challenge', async t => {
  const Combat = await component('WuwaCombat')
  const floor = (n, star, roles) => ({ floor: n, star, max_star: 3, role_list: roles.map(role_id => ({ role_id, role_name: `角色${role_id}` })) })
  const combat = snap({
    tower: { data: { season_end_at: '2099-01-01T00:00:00+08:00', difficulty_list: [
      { difficulty: 3, tower_area_list: [
        { area_name: '甲塔', star: 10, max_star: 12, floor_list: [floor(1, 3, [1]), floor(2, 3, []), floor(3, 3, []), floor(4, 1, [])] },
        { area_name: '乙塔', star: 6, max_star: 12, floor_list: [floor(1, 3, [2]), floor(2, 3, [3, 4, 5, 6]), floor(3, 0, []), floor(4, 0, [])] },
      ] },
      { difficulty: 4, difficulty_name: '超载区', tower_area_list: [{ star: 10, max_star: 12 }, { star: 8, max_star: 12 }] },
    ] } },
    hologram: { data: { challenge_info: { a: [
      { boss_name: '首领甲', difficulty: 1, pass_time: '01:00' }, { boss_name: '首领甲', difficulty: 5, pass_time: '02:30' },
    ] } } },
    slash: { data: { difficulty_list: [{ difficulty_name: '深潜', all_score: 100, max_score: 400, challenge_list: [
      { challenge_name: '虚兽巢', score: 60, rank: 'S', half_list: [
        { half_name: '上半场', score: 30, role_list: [{ role_id: 7, role_name: '角色7' }, { role_id: 8 }, { role_id: 9 }, { role_id: 10 }] },
        { half_name: '下半场', score: 30, role_list: [] },
      ] },
      { challenge_name: '潮汐门', score: 40, rank: 'SS' }, { challenge_name: '未评', score: 0, rank: null },
    ] }] } },
  })
  const root = mount(t, Combat, { snap: combat })
  const ring = meters(root).find(n => n.props['aria-label'] === '深境区总星数')
  assert.deepEqual([ring.props['aria-valuenow'], ring.props['aria-valuemax']], [16, 24])
  assert.match(content(root), /甲塔 10 \/ 12/)
  assert.match(content(byClass(root, 'tower-metrics')[0]), /满星层数 5 \/ 8 层 本期剩余 \d+ 天后结束/)
  assert.match(content(byClass(root, 'tower-team')[0]), /本期队伍 乙塔 · 第 2 层 角色3 角色4 角色5$/, 'the deepest team, three roles at most')
  assert.match(content(byClass(root, 'tower-zones')[0]), /超载区 18 \/ 24 星/)
  assert.equal(nodes(byClass(root, 'boss-list')[0], 'li').length, 1)
  assert.match(content(root), /首领甲 难度 5 · 通关时间 02:30/)
  assert.match(content(root), /深潜 最高评级 SS 100 \/ 400/)
  assert.match(content(root), /虚兽巢 60 评级 S/)
  const teams = byClass(root, 'slash-team')
  assert.deepEqual(teams.map(team => [team.props['aria-label'], nodes(team, 'li').length]), [['上半场', 3]], 'a half without a team draws nothing')
  assert.match(content(teams[0]), /角色7/)
  assert.equal(byClass(root, 'is-hero').length, 1)
  // The bot image embeds the whole record below each card: the card keeps its old summary.
  const image = mount(t, Combat, { snap: combat, imageMode: true })
  for (const name of ['tower-metrics', 'tower-team', 'tower-zones', 'slash-teams']) assert.equal(byClass(image, name).length, 0, name)
  assert.doesNotMatch(content(image), /最高评级/)
  assert.match(content(byClass(image, 'combat-tower')[0]), /天后结束/)
})

test('an unknown floor count stays unknown and a zone without floors or a team adds nothing', async t => {
  const root = mount(t, await component('WuwaCombat'), { snap: snap({ tower: { data: { season_end_at: '2099-01-01T00:00:00+08:00', difficulty_list: [
    { difficulty: 3, tower_area_list: [{ area_name: '甲塔', star: 5, max_star: 12, floor_list: [{ floor: 1, star: 3, max_star: 3 }, { floor: 2, star: 2 }] }] },
    { difficulty: 1, difficulty_name: '稳定区', tower_area_list: [{ star: null, max_star: 12 }] },
  ] } } }) })
  assert.match(content(byClass(root, 'tower-metrics')[0]), /满星层数 未知 \/ 2 层/)
  assert.equal(byClass(root, 'tower-team').length, 0)
  assert.equal(byClass(root, 'tower-zones').length, 0)
  assert.doesNotMatch(content(root), /最高评级/)
})

test('activity cards draw a ring per pair and the time-limited one leads with its countdown', async t => {
  const root = mount(t, await component('WuwaActivities'), { snap: snap({ sections: {
    a: { title: '收集', sort: 1, num: 3, max_num: 4 },
    b: { title: '赏令', sort: 2, level: 4, max_level: 8, exp: 5, max_exp: null, end_time: '2099-01-01T00:00:00+08:00' },
  } }) })
  assert.deepEqual(meters(root).map(n => [n.props['aria-valuenow'], n.props['aria-valuemax']]), [[3, 4], [4, 8]])
  assert.match(content(root), /3 \/ 4/)
  assert.match(content(root), /5 \/ 未知/, 'an unknown cap keeps its pair without a ring')
  assert.match(content(root), /天后结束/)
  assert.equal(byClass(root, 'is-hero').length, 1)
})

test('resources chart every currency, largest source first, and keep the total before its legend', async t => {
  const root = mount(t, await component('WuwaResources'), { accountKey: 'account:server', snap: snap({
    periods: {},
    current: { kind: 'week', period: '1', data: {
      total_coin: 1000, coin_inc: '+12%', coin_list: [{ type: '日常', num: 300 }, { type: '活动', num: 600 }, { type: '空', num: null }],
      total_star: 5, star_list: [],
    } },
  }) })
  assert.match(content(root), /贝币 1,000 环比 \+12%/)
  assert.match(content(root), /活动 600 67% 日常 300 33%/)
  assert.match(content(root), /空 未知/)
  assert.match(content(root), /星声 5/)
  assert.match(content(root), /未提供明细/)
})

test('the gacha overview totals every pool and rings only an exact pity; the image has no rail', async t => {
  const Gacha = await component('WuwaGacha')
  const archive = {
    total: 120, gold_total: 3, items: [], coverage: {},
    pools: [
      { pool: '1', name: '角色池', total: 80, rarity_distribution: { 3: 70, 4: 9, 5: 1 }, pity: { status: 'exact', count: 12, hard_pity_remaining: 68 } },
      { pool: '2', name: '武器池', total: 40, rarity_distribution: { 3: 36, 4: 2, 5: 2 }, pity: { status: 'lower_bound', count: 5 } },
    ],
    gold: [{ draw_id: 'a', pool: '1', name: '旧五星', rarity: 5, time: '2026-09-01T10:00:00' }, { draw_id: 'b', pool: '2', name: '新五星', rarity: 5, time: '2026-10-01T10:00:00' }],
  }
  const image = mount(t, Gacha, { imageMode: true, snapshot: archive })
  assert.match(content(image), /已导入记录 120 抽/)
  assert.match(content(image), /五星 3/)
  assert.match(content(image), /5 星 3 3%/)
  assert.deepEqual(meters(image).map(n => [n.props['aria-label'], n.props['aria-valuenow'], n.props['aria-valuemax']]), [['角色池 当前垫抽', 12, 80]])
  assert.equal(byClass(image, 'gold-card').length, 0)
  t.mock.method(globalThis, 'fetch', async () => reply({ ...identity, ...archive }))
  const web = mount(t, Gacha, { accountKey: 'account:server' })
  await tick()
  const cards = byClass(web, 'gold-card')
  assert.deepEqual(cards.map(card => content(card).includes('新五星')), [true, false])
  assert.ok(String(cards[0].props.class).includes('is-latest'))
  assert.match(content(cards[0]), /最近一次/)
  assert.doesNotMatch(content(cards[1]), /最近一次/)
})

test('history draws a role line only from its second observation and season bars only from the second season', async t => {
  const History = await component('WuwaHistory')
  const item = (id, subject, level, day) => ({ id, subject, observed_at: `2026-10-${day}T12:00:00+08:00`, payload: { role_id: Number(subject), name: `角色${subject}`, level }, delta: null })
  const answer = items => async () => reply({ ...identity, items, total: items.length, archive_started_at: '2026-10-01', coverage: '' })
  t.mock.method(globalThis, 'fetch', answer([]))
  const once = mount(t, History, { accountKey: 'account:server' })
  await tick()
  assert.match(content(once), /暂无记录/)
  t.mock.method(globalThis, 'fetch', answer([item(1, '7', 80, '11'), item(2, '7', 70, '10'), item(3, '8', 60, '10')]))
  const roles = mount(t, History, { accountKey: 'account:server' })
  await tick()
  nodes(roles, 'button').find(n => content(n) === '角色练度变化').props.onClick()
  await tick()
  const charts = byClass(roles, 'trend-chart')
  assert.equal(charts.length, 1, 'only the newest record of a role carries its line')
  assert.deepEqual(find(charts[0], n => n.type === 'li').map(content), ['2026-10-10 12:00：70 级', '2026-10-11 12:00：80 级'])
  const season = (id, end, stars) => ({ id, season: end, observed_at: end, subject: '', payload: { difficulty_list: [{ difficulty: 3, tower_area_list: stars.map(star => ({ star, max_star: 12 })) }] }, delta: null })
  t.mock.method(globalThis, 'fetch', answer([season(1, '2026-09-14T04:00:00+08:00', [12, 6])]))
  const single = mount(t, History, { accountKey: 'account:server' })
  await tick()
  assert.equal(byClass(single, 'bar-chart').length, 0)
  t.mock.method(globalThis, 'fetch', answer([season(1, '2026-09-14T04:00:00+08:00', [12, 6]), season(2, '2026-08-17T04:00:00+08:00', [8])]))
  const seasons = mount(t, History, { accountKey: 'account:server' })
  await tick()
  assert.equal(byClass(seasons, 'bar-chart').length, 1)
  assert.match(content(seasons), /8 星 08-17 18 星 09-14/)
})

test('the account page shows the base box tiers as a donut and every other collection as bars', async t => {
  const Profile = await component('WuwaProfile')
  const account = list => snap({ nickname: '漂泊者', level: 90, extra: { ...identity, profile: { next_exp: 5, exp_limit: 10, box_list: list, treasure_box_list: [{ name: '瑝珑', num: 50 }, { name: '黑海岸', num: 25 }] } } })
  const donut = mount(t, Profile, { snap: account([{ box_name: '基础', num: 3 }, { box_name: '珍奇', num: 1 }]) })
  assert.match(content(donut), /基础 3 75% 珍奇 1 25%/)
  assert.match(content(donut), /瑝珑 50/)
  assert.equal(byClass(donut, 'bar-row').length, 2, 'the region counts stay as bars')
  assert.equal(meters(donut)[0].props['aria-valuenow'], 5)
  const single = mount(t, Profile, { snap: account([{ box_name: '秘密箱', num: 0 }]) })
  assert.match(content(single), /秘密箱 0/)
  assert.equal(byClass(single, 'bar-row').length, 3)
})
