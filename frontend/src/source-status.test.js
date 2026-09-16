import test from 'node:test'
import assert from 'node:assert/strict'
import { describeSource, sourceForGame, capabilityLabel } from './source-status.js'

test('an independent public news source cannot override game account health', () => {
  const status = sourceForGame('nte', [
    { game_id: 'nte', capability: 'account', state: 'ok' },
    { game_id: 'nte', capability: 'news', scope: 'public_source', state: 'error' },
  ])
  assert.equal(status.state, 'ok')
})

test('offline and unconfigured are nonfault states, retaining successful data where available', () => {
  const offline = describeSource({ state: 'offline', last_success_at: '2026-09-14T12:00:00Z', consecutive_failures: 0 })
  assert.equal(offline.label, '客户端离线'); assert.equal(offline.tone, 'muted'); assert.equal(offline.retained, true)
  assert.equal(describeSource({ state: 'unconfigured' }).label, '未配置')
  assert.equal(describeSource(null).label, '尚未采集')
})
test('backend auth failure takes priority over a fresh stored payload', () => {
  const s = sourceForGame('nte', [{ game_id: 'nte', capability: 'stamina', state: 'ok' },
    { game_id: 'nte', capability: 'roles', state: 'auth_expired', error: '重新登录' }])
  assert.equal(s.label, '登录失效'); assert.equal(s.tone, 'danger')
})
test('status aggregation isolates games and keeps native capability names', () => {
  const rows = [{ game_id: 'nte', state: 'error' }, { game_id: 'league_of_legends', state: 'offline' }]
  assert.equal(sourceForGame('league_of_legends', rows).label, '客户端离线')
  assert.equal(sourceForGame('missing', rows), null)
  assert.equal(capabilityLabel('progress', 'nte'), '成就进度')
  assert.equal(capabilityLabel('progress', 'wuthering_waves'), '周期进度')
})
