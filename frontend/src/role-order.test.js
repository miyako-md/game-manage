import test from 'node:test'
import assert from 'node:assert/strict'
import { newestFirst, roleRecency } from './role-order.js'

const names = list => list.map(r => r.name)

test('wuwa follows the official catalogue order, not the element-grouped role id', () => {
  const roles = [{ name: '今汐', id: 1304 }, { name: '未收录角色', id: 9999 }, { name: '心', id: 1210 }, { name: '卡提希娅', id: 1409 }]
  assert.deepEqual(names(roles.sort(newestFirst('wuthering_waves'))), ['心', '卡提希娅', '今汐', '未收录角色'])
})

test('nte uses the numeric role id and endfield the number in chr_NNNN', () => {
  assert.deepEqual(names([{ name: '早雾', id: '1003' }, { name: '真红', id: '1076' }, { name: '无编号', id: 'x' }].sort(newestFirst('nte'))), ['真红', '早雾', '无编号'])
  const ops = [{ name: '甲', id: 'chr_0003_a' }, { name: '乙', id: 'chr_0026_b' }, { name: '丙', id: 'char_000' }, { name: '丁', char_id: 'chr_0010_d' }]
  assert.deepEqual(names(ops.sort(newestFirst('endfield'))), ['乙', '丁', '甲', '丙'])
})

test('unknown games and malformed roles are unplaced, never invented', () => {
  assert.equal(roleRecency('league_of_legends', { id: '5' }), null)
  assert.equal(roleRecency('nte', null), null)
  assert.equal(roleRecency('nte', { id: '' }), null)
})

test('the generated Wuwa order is the icon catalogue order, without importing the catalogue', async () => {
  const { readFileSync } = await import('node:fs')
  const { default: catalog } = await import('./wuwa-icon-catalog.js')
  const { default: order } = await import('./wuwa-role-order.json', { with: { type: 'json' } })
  assert.deepEqual(order.names, Object.keys(catalog.roles))
  assert.doesNotMatch(readFileSync(new URL('./role-order.js', import.meta.url), 'utf8'), /wuwa-icon-catalog/)
})

test('shared sample: same overview order as the backend role_order.py', async () => {
  const { readFileSync } = await import('node:fs')
  const { cases } = JSON.parse(readFileSync(new URL('../../tests/fixtures/role_order.json', import.meta.url), 'utf8'))
  for (const { game, roles, expected } of cases) assert.deepEqual(names([...roles].sort(newestFirst(game))), expected, game)
})
