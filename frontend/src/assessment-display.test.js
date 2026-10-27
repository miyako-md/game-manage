import test from 'node:test'
import assert from 'node:assert/strict'
import { attributionLabel, echoBadges, gradeLabel, isDefaultScore, isNoDefault, nteBadges, scoreLine } from './assessment-display.js'

test('grades read upper case and only the six known grades are shown', () => {
  assert.deepEqual(['c', 'b', 'a', 's', 'ss', 'sss', 'SS'].map(gradeLabel), ['C', 'B', 'A', 'S', 'SS', 'SSS', 'SS'])
  for (const grade of [null, undefined, '', 'x', 'ssss', 3]) assert.equal(gradeLabel(grade), '')
  // NTE grades.
  assert.deepEqual(['d', 'ACE', 'Ace'].map(gradeLabel), ['D', 'ACE', 'ACE'])
})

test('only a default score carries an attribution', () => {
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: 'gpl_snapshot' }), '权重改编自 WutheringWavesUID（GPL-3.0）')
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: 'self_made' }), '自制权重')
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: 'nte_workshop' }), '权重配置来自：异环工坊')
  assert.equal(attributionLabel({ origin: 'builtin_default', attribution: null }), '')
  assert.equal(attributionLabel({ origin: 'user_configured', attribution: 'gpl_snapshot' }), '')
  assert.equal(isDefaultScore(null), false)
})

test('echo badges follow the source position, skip unscorable items and a different echo at that position', () => {
  const echoes = [{ phantom_prop: { phantom_id: 7 } }, null, { phantom_prop: {} }, { phantom_prop: { phantom_id: 9 } }]
  const item = (item_id, extra = {}) => ({ item_id, status: 'scored', value: '30.05', grade: 'a', max_value: 50, ...extra })
  const badges = echoBadges({ origin: 'builtin_default', item_results: [
    item('echo:0:7', { grade: 'sss' }), item('echo:2:unknown'), item('echo:3:8'),
    item('echo:1:unknown'), item('echo:9:unknown'), { item_id: 'echo:3:unknown', status: 'unscorable', value: null, max_value: null },
  ] }, echoes)
  assert.deepEqual([...badges].map(([echo, badge]) => [echoes.indexOf(echo), badge]), [[0, { value: '30.05', grade: 'SSS' }], [2, { value: '30.05', grade: 'A' }]])
  assert.equal(echoBadges({ origin: 'user_configured', item_results: [item('echo:0:7', { grade: null, max_value: null })] }, echoes).size, 0)
  assert.equal(echoBadges(null, echoes).size, 0)
})

test('the header line shows a total only for a scored set and always names a default unofficial', () => {
  const base = { origin: 'builtin_default', attribution: 'gpl_snapshot', max_value: 250 }
  assert.deepEqual(scoreLine({ ...base, status: 'scored', value: '146.82', grade: 'b' }), { total: '总分 146.82 / 250 · B', source: '非官方 · 权重改编自 WutheringWavesUID（GPL-3.0）' })
  assert.deepEqual(scoreLine({ ...base, status: 'unscorable', value: null, partial: true }), { total: '', source: '非官方 · 权重改编自 WutheringWavesUID（GPL-3.0）' })
  assert.deepEqual(scoreLine({ origin: 'user_configured', status: 'scored', value: '3.00', max_value: null }), { total: '评分 3.00', source: '个人权重' })
  assert.deepEqual(scoreLine(null), { total: '', source: '' })
  assert.equal(isNoDefault({ status: 'unconfigured', model_version: 'unconfigured' }), true)
  assert.equal(isNoDefault({ status: 'unconfigured', model_version: 'mine' }), false)
})

test('NTE badges follow group and position and skip a different piece there', () => {
  const suit = { core: [{ id: 'nature_orange' }], pie: [{ id: 'cell2_style1_1_blue' }, null] }
  const item = (item_id, extra = {}) => ({ item_id, status: 'scored', value: '10.00', max_value: '20', grade: 'ace', ...extra })
  const badges = nteBadges({ item_results: [item('core:0:nature_orange'), item('pie:0:cell3_style1_1_blue'), item('pie:1:unknown'), item('pie:9:unknown'), item('echo:0:1')] }, suit)
  assert.deepEqual([...badges.values()], [{ value: '10.00', max: '20', grade: 'ACE' }])
  assert.equal(badges.get(suit.core[0]).max, '20')
  assert.equal(nteBadges(null, suit).size, 0)
  assert.equal(nteBadges({ item_results: [item('core:0:unknown', { max_value: null })] }, suit).size, 0)
})
