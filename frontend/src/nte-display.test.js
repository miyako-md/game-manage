import test from 'node:test'
import assert from 'node:assert/strict'
const display=await import('./nte-display.js').catch(()=>({}))

test('NTE descriptions decode known formatting without corrupting English or inventing template values',()=>{
  assert.equal(display.displayNteText?.('伤害</>。rn获得增益。\\n持续。'),'伤害。\n获得增益。\n持续。')
  assert.equal(display.displayNteText?.('Return the horn'),'Return the horn')
  assert.equal(display.displayNteText?.('攻击提高{0}，持续{1}秒'),'效果数值待核验')
  assert.equal(display.displayNteText?.('Effect5'),'效果说明待核验')
  assert.equal(display.displayNteText?.(0),'0')
})
test('NTE item IDs resolve exact known names and flag conflicting or unknown data',()=>{
  assert.equal(display.nteItemLabel?.('fork_butterfly','角色/弧盘 fork_butterfly'),'现实避难所')
  assert.equal(display.nteItemLabel?.('fork_jingmotingyuan','角色/弧盘 fork_jingmotingyuan'),'茶花会')
  assert.equal(display.nteItemLabel?.('fork_butterfly','另一个名称'),'名称待核验')
  assert.equal(display.nteItemLabel?.('fork_unverified',''),'名称待核验')
})
test('negative durability stays unexplained rather than becoming zero or unlimited',()=>{
  assert.equal(display.displayVehicleStat?.({name:'车辆耐久',value:'-1'}),'来源未说明')
  assert.equal(display.displayVehicleStat?.({name:'车辆耐久',value:'0'}),'0')
  assert.equal(display.displayVehicleStat?.({name:'加速度',value:'5'}),'5')
})
test('vehicle decorations show a Chinese slot type and fall back to a generic decoration',()=>{
  assert.equal(display.vehicleDecorationType?.('evmt_tyre'),'轮胎')
  for(const unknown of ['evmt_paint','',null,undefined]) assert.equal(display.vehicleDecorationType?.(unknown),'装饰')
})
