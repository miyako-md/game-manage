import test from 'node:test'
import assert from 'node:assert/strict'
import { createEsportsBrowseState, selectEsportsMatches, esportsGroupLabel, officialEsportsUrl } from './esports.js'
import { createDashboard } from './dashboard.js'

test('Beijing date selection, missing dates and chronological ordering', () => {
  const payload = { tournaments: [{ id: 't', family: 'lpl' }], matches: [
    { id: 'unknown', tournament_id: 't' },
    { id: 'late', tournament_id: 't', start_at: '2026-10-01T17:00:00Z' },
    { id: 'early', tournament_id: 't', start_at: '2026-10-01T16:00:00Z' },
  ] }
  assert.deepEqual(selectEsportsMatches(payload, { family: 'lpl', date: '2026-10-02' }).map(m => m.id), ['early', 'late'])
  assert.equal(selectEsportsMatches(payload, {}).at(-1).id, 'unknown')
  assert.equal(selectEsportsMatches(payload, { family: 'worlds' }).length, 0)
})
test('source and local timestamps remain distinct and untrusted links are rejected', () => {
  const label = esportsGroupLabel({ last_success_at: '2026-10-04T00:00:00Z', source_updated_at: '2026-07-02T00:00:00Z', source_lagging: true })
  assert.match(label, /10-04/); assert.match(label, /07-02/); assert.match(label, /滞后/)
  assert.equal(officialEsportsUrl('javascript:alert(1)'), '')
  assert.equal(officialEsportsUrl('https://lpl.qq.com.evil.com/web202301/live.html'), '')
  assert.equal(officialEsportsUrl('https://lpl.qq.com/web202301/live.html?bgid=238&bmid=1'), 'https://lpl.qq.com/web202301/live.html?bgid=238&bmid=1')
})
test('public browsing state survives account invalidation and factories do not share state', () => {
  const dashboard = createDashboard({})
  dashboard.state.esportsBrowse.league_of_legends.family = 'lpl'
  dashboard.state.snapshots.league_of_legends = { esports: { payload: { schema_version: 1 } }, account: {} }
  dashboard.invalidateGame('league_of_legends')
  assert.equal(dashboard.state.esportsBrowse.league_of_legends.family, 'lpl')
  assert.equal(dashboard.state.snapshots.league_of_legends.esports.payload.schema_version, 1)
  assert.equal(createEsportsBrowseState().family, '')
})
