import test from 'node:test'
import assert from 'node:assert/strict'
import catalog from './wuwa-guides-catalog.js'
import { getWuwaGuide, guideSourceUrl, guideVersion, guideSections } from './wuwa-guides.js'

test('each published field retains a real source, version and explicit review state', () => {
  assert.equal(catalog.guides.length, 46)
  assert.equal(new Set(catalog.guides.map(g => g.id)).size, 46)
  for (const guide of catalog.guides) {
    assert.deepEqual(guide.sections.map(s => s.key), Object.keys(guideSections))
    for (const section of guide.sections) {
      const source = guide.sources.find(s => s.id === section.sourceId)
      assert.ok(source, `${guide.name}/${section.key} needs a source`)
      assert.ok(guideSourceUrl(source.url))
      assert.notEqual(source.kind, 'preview', '前瞻不能冒充已核验推荐')
      assert.ok(['reviewed', 'partial', 'pending'].includes(section.status))
      if (section.status === 'reviewed') assert.ok(section.text.trim())
      if (section.status === 'pending') assert.equal(section.text, '')
      if (section.status !== 'reviewed') assert.ok(section.note)
    }
  }
  assert.doesNotMatch(JSON.stringify(catalog), /游戏UID|account_id|user_id|token|100080337/i)
})

test('form matching is exact and never falls back by name or partial ID', () => {
  assert.equal(getWuwaGuide('1402').attribute, '气动')
  assert.equal(getWuwaGuide('1610').name, '秧秧·玄翎')
  assert.equal(getWuwaGuide(1408).attribute, '气动')
  for (const id of ['1402extra', '秧秧', '01402', '9999', '__proto__', null]) assert.equal(getWuwaGuide(id), null)
})

test('mixed-source advice keeps the older field version instead of relabeling the whole guide', () => {
  const guide = getWuwaGuide('1105')
  const version = key => guide.sources.find(s => s.id === guide.sections.find(f => f.key === key).sourceId).version
  assert.equal(version('echo_sets'), '3.6')
  assert.equal(version('skill_priority'), '3.5')
  assert.equal(guideVersion({ version: null }), '版本未确认')
  assert.equal(guideVersion({ version: '3.7', kind: 'preview' }), 'V3.7 · 前瞻')
})

test('known image reading-order traps and incomplete upstream fields stay corrected', () => {
  assert.match(getWuwaGuide('1110').sections[4].text, /解放＞变奏＞技能＞回路＞常态/)
  assert.match(getWuwaGuide('1305').sections[4].text, /回路＝解放＞技能＞变奏＝常态/)
  assert.equal(getWuwaGuide('1402').sections[3].status, 'partial')
  assert.match(getWuwaGuide('1402').sections[3].note, /标签有冲突/)
  assert.equal(getWuwaGuide('1202').sections[4].status, 'pending')
})

test('source links only allow canonical Kurobbs public post URLs', () => {
  for (const url of ['javascript:alert(1)', 'https://www.kurobbs.com.evil.test/forum/post/1', 'https://www.kurobbs.com/forum/post/1?token=secret', 'http://www.kurobbs.com/forum/post/1']) assert.equal(guideSourceUrl(url), null)
  assert.equal(guideSourceUrl('https://www.kurobbs.com/forum/post/123'), 'https://www.kurobbs.com/forum/post/123')
})
