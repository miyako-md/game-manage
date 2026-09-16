import test from 'node:test'
import assert from 'node:assert/strict'
import { filterRoles, comparisonGroups, favoritesKey, loadFavorites, saveFavorites } from './nte-roles.js'

const roles = [
  { id: '1', name: '薄荷', quality: 'S', element: '灵', level: 0, awaken_level: null, mix_level: 3 },
  { id: '2', name: '白藏', quality: 'A', element: '光', level: null, awaken_level: 2, mix_level: 0 },
  { id: '3', name: '薄荷二', quality: 'S', element: '光', level: 30, awaken_level: 0, mix_level: null },
]
test('combined filters intersect and do not mutate the source', () => {
  assert.deepEqual(filterRoles(roles, { search: ' 薄荷 ', quality: 'S', element: '光', favoritesOnly: true, favorites: ['3'] }).map(r => r.id), ['3'])
  assert.deepEqual(roles.map(r => r.id), ['1', '2', '3'])
})
test('all numeric sorting puts missing values last in both directions and preserves zero', () => {
  for (const [sort, direction, ids] of [
    ['level', 'desc', ['3', '1', '2']], ['level', 'asc', ['1', '3', '2']],
    ['awaken_level', 'desc', ['2', '3', '1']], ['mix_level', 'asc', ['2', '1', '3']],
  ]) assert.deepEqual(filterRoles(roles, { sort, direction }).map(r => r.id), ids)
  const names = filterRoles([{ name: null }, { name: 'Beta' }, { name: 'Alpha' }], { sort: 'name', direction: 'asc' })
  assert.deepEqual(names.map(r => r.name), ['Alpha', 'Beta', null])
})
test('comparison aligns source field names, preserves zero and raw units, and labels missing', () => {
  const groups = comparisonGroups([
    { name: '甲', level: 0, weapon: { name: '弧光', mix_level: 0 }, properties: [{ name: '攻击', value: '320' }, { name: '暴击', value: '0.05' }], skills: [{ name: '战技', level: 0 }] },
    { name: '乙', properties: [{ name: '暴击', value: '5%' }, { name: '生命', value: 100 }], city_skills: [{ name: '城区', level: 2 }] },
  ])
  const row = (group, name) => groups.find(g => g.name === group).rows.find(r => r.name === name).values
  assert.deepEqual(row('基础', '等级'), [0, '未提供'])
  assert.deepEqual(row('弧盘', '混频'), [0, '未提供'])
  assert.deepEqual(row('属性', '攻击'), ['320', '未提供'])
  assert.deepEqual(row('属性', '暴击'), ['0.05', '5%'])
  assert.deepEqual(row('属性', '生命'), ['未提供', 100])
  assert.deepEqual(row('战技', '战技'), [0, '未提供'])
  assert.deepEqual(row('城区技能', '城区'), ['未提供', 2])
})
test('favorites persist by NTE account, missing identity never accesses storage, failures are visible', () => {
  const map = new Map(), storage = { getItem: k => map.get(k) ?? null, setItem: (k, v) => map.set(k, v) }
  assert.notEqual(favoritesKey('a'), favoritesKey('b'))
  assert.equal(favoritesKey('  '), null)
  assert.equal(saveFavorites('a', ['1', '1'], storage).error, null)
  assert.deepEqual(loadFavorites('a', storage).ids, ['1'])
  assert.deepEqual(loadFavorites('b', storage).ids, [])
  const fail = { getItem() { throw Error('blocked') }, setItem() { throw Error('quota') } }
  assert.equal(loadFavorites('', fail).error, null)
  assert.equal(saveFavorites('', ['1'], fail).error, null)
  assert.ok(loadFavorites('a', fail).error)
  assert.ok(saveFavorites('a', ['1'], fail).error)
  map.set(favoritesKey('a'), '{bad')
  assert.ok(loadFavorites('a', storage).error)
})
