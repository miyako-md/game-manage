import test from 'node:test'
import assert from 'node:assert/strict'
import { getMap, getMapMark, getSklandTools, getSklandOperator, chooseSklandRole, saveBlueprint, safeExternalUrl } from './endfield-tools-api.js'

test('map filters are encoded and role selection sends both identifiers', async t => {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, json: async () => ({}) }
  })
  await getMap({ map_id: '地下 1', level_id: 'A&B', type_id: '资源', q: '蓝 矿', offset: 100, limit: 100 })
  assert.equal(calls[0].url, '/api/endfield/map?map_id=%E5%9C%B0%E4%B8%8B+1&level_id=A%26B&type_id=%E8%B5%84%E6%BA%90&q=%E8%93%9D+%E7%9F%BF&offset=100&limit=100')
  await chooseSklandRole('role-7', 'server-2')
  assert.deepEqual(JSON.parse(calls[1].options.body), { role_id: 'role-7', server_id: 'server-2' })
  await saveBlueprint({ name: '工厂', code: 'ABC', notes: '' })
  assert.equal(calls[2].options.method, 'POST')
  assert.equal(calls[2].options.headers['X-Game-Assistant'], '1')
  await getMapMark('map 1', 'point/2')
  assert.equal(calls[3].url, '/api/endfield/map/marks/point%2F2?map_id=map%201')
  await getSklandTools('rules', 'char/1')
  assert.equal(calls[4].url, '/api/endfield/skland/tools?kind=rules&char_id=char%2F1')
  await getSklandOperator('char/1')
  assert.equal(calls[5].url, '/api/endfield/skland/operators/char%2F1')
})

test('external links allow only ordinary HTTPS URLs', () => {
  assert.equal(safeExternalUrl('https://example.com/map'), 'https://example.com/map')
  for (const url of ['javascript:alert(1)', 'http://example.com', 'https://user:pass@example.com']) assert.equal(safeExternalUrl(url), null)
})
