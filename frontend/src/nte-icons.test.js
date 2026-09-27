import test from 'node:test'
import assert from 'node:assert/strict'
import { safeNteIcon, nteRoleIcon, nteSkillIcon, tokenizeNteGuide } from './nte-icons.js'
import catalog from './nte-icon-catalog.js'

test('icon rendering preserves advice order, conditions and every character',()=>{
  for(const [kind,text] of [['weapons','优先「罪与罚」，也可考虑「当心头顶」或「思考喵」。'],['teams','残虹、灵可、早雾、伊洛伊；主角·零可替换。'],['sets','主 C／副 C：恶魔之血·诅咒。'],['skills','普通攻击 = 极轨终结 > 变轨技能 > 援护技。']]){
    const tokens=tokenizeNteGuide(text,kind,'黑羽')
    assert.equal(tokens.map(x=>x.text).join(''),text)
    assert.ok(tokens.some(x=>x.entity),kind)
  }
})
test('skill lookup is character-specific and never borrows another character icon',()=>{
  const role=catalog.roles['黑羽']
  assert.ok(role?.id)
  const skills=catalog.skills[role.id]
  const [name,entry]=Object.entries(skills)[0]
  assert.equal(nteSkillIcon(role.id,name),safeNteIcon(entry.icon))
  assert.equal(nteSkillIcon('missing-role',name),'')
  assert.equal(nteRoleIcon('主角·零'),'')
})
test('single-character names cannot replace ordinary prose and unsafe URLs are rejected',()=>{
  assert.equal(tokenizeNteGuide('翳障不代表角色','teams','黑羽').filter(x=>x.entity).length,0)
  assert.equal(tokenizeNteGuide('所有技能均可升级','skills','黑羽').filter(x=>x.entity).length,0)
  for(const url of ['javascript:alert(1)','https://evil.invalid/a.png','https://u:p@webstatic.tajiduo.com/a.png','https://webstatic.tajiduo.com/a.png?token=secret','http://webstatic.tajiduo.com/a.png'])assert.equal(safeNteIcon(url),'')
})
