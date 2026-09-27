import test from 'node:test'
import assert from 'node:assert/strict'
import { tokenizeGuide, characterIcon, safeWuwaIcon } from './wuwa-icons.js'

test('icon tokens preserve recommendation text, connectors and character form', () => {
  const text = '卡提希娅／气动漂泊者／千咲或守岸人。'
  const tokens = tokenizeGuide(text, 'teams', '1409')
  assert.equal(tokens.map(t => t.text).join(''), text)
  assert.equal(tokens.filter(t => t.icon).length, 4)
  assert.ok(characterIcon('1402'))
  assert.notEqual(characterIcon('1402'), characterIcon('1610'))
})

test('skill icons belong to the selected character and preserve equal priority', () => {
  const a = tokenizeGuide('回路＝解放＞技能＞常态', 'skill_priority', '1304')
  const b = tokenizeGuide('回路＝解放＞技能＞常态', 'skill_priority', '1105')
  assert.equal(a.map(t => t.text).join(''), '回路＝解放＞技能＞常态')
  assert.notEqual(a.find(t=>t.icon).icon,b.find(t=>t.icon).icon)
  assert.equal(tokenizeGuide('固有技能', 'skill_priority', '9999').filter(t=>t.icon).length, 0)
})

test('names are matched longest-first and short echo names do not match prose', () => {
  const text = '角色首位角，梦魇·无常凶鹭／无常凶鹭。'
  const tokens = tokenizeGuide(text, 'echo_sets', '1304')
  assert.equal(tokens.map(t=>t.text).join(''),text)
  assert.equal(tokens.filter(t=>t.text==='角' && t.icon).length,1)
  assert.equal(tokens.filter(t=>t.text==='梦魇·无常凶鹭' && t.icon).length,1)
})

test('icons only accept trusted public image URLs', () => {
  for(const u of ['javascript:alert(1)','https://web-static.kurobbs.com.evil.test/a.png','https://u:p@web-static.kurobbs.com/a.png','https://web-static.kurobbs.com/a.svg#x']) assert.equal(safeWuwaIcon(u),'')
})
