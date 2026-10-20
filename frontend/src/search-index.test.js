import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { GAME_SECTIONS, buildSearchIndex, searchItems, groupResults, sectionsFor } from './search-index.js'

// Windows checkouts turn LF into CRLF; the slicing below looks for ']\n'.
const source = name => readFileSync(new URL(`./components/${name}`, import.meta.url), 'utf8').replaceAll('\r\n', '\n')
// [id, label] pairs from a `const tabs = [...]` list or GameCard's NTE groups.
const pairs = text => [...text.matchAll(/\[\s*'([a-z]+)',\s*'([^']+)'\s*\]/g)].map(([, id, label]) => [id, label])
const tabsIn = name => { const text = source(name); return pairs(text.slice(text.indexOf('const tabs = ['), text.indexOf(']\n', text.indexOf('const tabs = [')) + 2)) }

test('search tabs repeat the game pages tab lists, in order', () => {
  assert.deepEqual(GAME_SECTIONS.wuthering_waves, tabsIn('WuwaDashboard.vue'))
  assert.deepEqual(GAME_SECTIONS.endfield, tabsIn('EndfieldDashboard.vue'))
  assert.deepEqual(GAME_SECTIONS.league_of_legends, tabsIn('LolDashboard.vue'))
  const card = source('GameCard.vue'), groups = card.slice(card.indexOf('const groups = computed'), card.indexOf('].filter(group =>'))
  const nte = [...groups.matchAll(/\{ id: '([a-z]+)', label: '([^']+)', caps: (\[[^\]]*\]|props\.game\.capabilities)/g)].filter(([, id]) => id !== 'all')
  assert.deepEqual(GAME_SECTIONS.nte.map(([id, label, caps]) => [id, label, JSON.stringify(caps)]), nte.map(([, id, label, caps]) => [id, label, JSON.stringify(JSON.parse(caps.replaceAll("'", '"')))]))
})

const now = Date.parse('2026-10-17T12:00:00+08:00')
const games = [
  { game_id: 'wuthering_waves', display_name: '鸣潮', capabilities: ['stamina', 'roles', 'events'] },
  { game_id: 'nte', display_name: '异环', capabilities: ['account', 'roles', 'events'] },
]
const snapshots = {
  wuthering_waves: {
    roles: { payload: [{ name: '今汐' }, { name: '长离' }, { name: '今汐' }, { name: '' }, null] },
    events: { payload: [{ name: '海市寻游', start_at: '2026-10-10 10:00', end_at: '2026-10-20 03:59' }, { name: '已结束', start_at: '2026-10-01 10:00', end_at: '2026-10-05 03:59' }] },
  },
  nte: { roles: { payload: { schema_version: 1, entries: [{ name: '零' }] } } },
}
const pages = [{ label: '今日总览', href: '#/' }, { label: '活动日历', href: '#/calendar' }]
const index = buildSearchIndex({ pages, games, snapshots, now })

test('the index holds pages, games, their tabs, named roles once, and only events still running', () => {
  assert.deepEqual(index.filter(item => item.kind === 'role').map(item => [item.title, item.href]), [['今汐', '#/game/wuthering_waves?tab=roles'], ['长离', '#/game/wuthering_waves?tab=roles'], ['零', '#/game/nte?tab=characters']])
  assert.deepEqual(index.filter(item => item.kind === 'event').map(item => [item.title, item.href]), [['海市寻游', '#/calendar?game=wuthering_waves']])
  // NTE shows a group only when the game has one of its capabilities; guides are inside characters.
  assert.deepEqual(sectionsFor(games[1]).map(([id]) => id), ['overview', 'characters'])
  assert.equal(index.filter(item => item.kind === 'section' && item.gameId === 'wuthering_waves').length, 8)
})

test('an empty query offers pages and games; a query ranks title matches before game-name matches', () => {
  assert.deepEqual(searchItems(index, '').map(item => item.title), ['今日总览', '活动日历', '鸣潮', '异环'])
  assert.deepEqual(searchItems(index, '鸣潮抽卡').map(item => item.href), ['#/game/wuthering_waves?tab=gacha'])
  // 「角色」 finds the tabs named for roles, not every role through its hint.
  assert.deepEqual(searchItems(index, '角色').map(item => [item.title, item.hint]), [['角色', '鸣潮'], ['角色', '异环']])
  assert.equal(searchItems(index, '今汐')[0].kind, 'role')
  assert.deepEqual(searchItems(index, '没有这个').length, 0)
  assert.deepEqual(groupResults(searchItems(index, '鸣潮')).map(group => group.label), ['游戏', '栏目', '角色', '活动'])
})
