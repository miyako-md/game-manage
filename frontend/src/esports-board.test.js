import test from 'node:test'
import assert from 'node:assert/strict'
import * as esports from './esports.js'
const payload = { tournaments: [{ id: 't', family: 'lpl' }], matches: [
  { id: 'old', tournament_id: 't', status: 'completed', start_at: '2026-10-01T16:00:00Z', team_a_id: 'a' },
  { id: 'live', tournament_id: 't', status: 'live', start_at: '2026-10-04T10:00:00Z' },
  { id: 'future', tournament_id: 't', status: 'scheduled', start_at: '2026-10-06T09:00:00Z' },
  { id: 'new', tournament_id: 't', status: 'completed', start_at: '2026-10-03T17:00:00Z', team_a_id: 'b' },
  { id: 'undated', tournament_id: 't', status: 'completed' },
  { id: 'postponed', tournament_id: 't', status: 'postponed' },
] }
test('board separates live, upcoming, recent results and exceptional statuses with Beijing dates', () => {
  assert.equal(typeof esports.esportsSections, 'function')
  const sections = esports.esportsSections(payload, {})
  assert.deepEqual(sections.map(s => s.key), ['live', 'scheduled', 'completed', 'other'])
  assert.deepEqual(sections[2].groups.flatMap(g => g.matches.map(m => m.id)), ['new', 'old', 'undated'])
  assert.equal(sections[2].groups[0].date, '2026-10-04')
  assert.equal(sections[3].groups[0].matches[0].status, 'postponed')
})
test('results paginate descending without dropping undated rows; team and date filters apply before pagination', () => {
  assert.equal(typeof esports.esportsSections, 'function')
  const section = esports.esportsSections(payload, { view: 'results', page: 2 }, 2)[0]
  assert.equal(section.total, 3); assert.equal(section.pages, 2)
  assert.deepEqual(section.groups.flatMap(g => g.matches.map(m => m.id)), ['undated'])
  const filtered = esports.esportsSections(payload, { view: 'results', filterTeamId: 'a', date: '2026-10-02' })[0]
  assert.equal(filtered.total, 1); assert.equal(filtered.groups[0].matches[0].id, 'old')
  assert.equal(esports.esportsSections(payload, { view: 'results', page: 99 }, 2)[0].page, 2)
})
test('winner presentation never invents a winner from scores or an unrelated ID', () => {
  assert.equal(typeof esports.esportsOutcome, 'function')
  const m = { status: 'completed', team_a_id: 'a', team_b_id: 'b', score_a: 0, score_b: 3 }
  assert.equal(esports.esportsOutcome(m, 'a'), '')
  assert.equal(esports.esportsOutcome({ ...m, winner_team_id: 'x' }, 'b'), '')
  assert.equal(esports.esportsOutcome({ ...m, winner_team_id: 'b' }, 'a'), '负')
  assert.equal(esports.esportsOutcome({ ...m, winner_team_id: 'b' }, 'b'), '胜')
  assert.equal(esports.esportsOutcome({ ...m, status: 'live', winner_team_id: 'b' }, 'b'), '')
})
