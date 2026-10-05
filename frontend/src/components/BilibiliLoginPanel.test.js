import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { createRenderer, nextTick } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'
const url = new URL('./BilibiliLoginPanel.vue', import.meta.url)
let component
async function mount(t) {
  assert.ok(existsSync(url), 'Bilibili component missing')
  if (!component) {
    let compiled = compileScript(parse(readFileSync(url,'utf8')).descriptor, {id:'bili-login-tests'}).content
    for (const [,name] of [...compiled.matchAll(/from ['"]([^'"]+)['"]/g)]) {
      const absolute = name.startsWith('.') ? new URL(name,url).href : import.meta.resolve(name)
      compiled = compiled.replaceAll(`'${name}'`,`'${absolute}'`).replaceAll(`"${name}"`,`"${absolute}"`)
    }
    component = (await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)).default
    component.render=()=>null
  }
  const renderer=createRenderer({createComment:()=>({}),insert(){},remove(){},parentNode(){},nextSibling(){}})
  const app=renderer.createApp(component); app.mount({}); t.after(()=>app.unmount())
  await flush(); return {vm:app._instance.setupState,app}
}
const flush=async()=>{await new Promise(resolve=>setImmediate(resolve));await nextTick()}
function network(t, override) {
  const requests=[];let count=0
  t.mock.method(globalThis,'fetch', async (url,options)=> {
    const body=options.body?JSON.parse(options.body):null;requests.push({url,body})
    const custom=await override?.(url,body)
    if (custom instanceof Response) return custom
    const data=custom??(url.endsWith('/sessions')?{session_id:`FAKE-${++count}`,mode:body.mode,state:body.mode==='qr'?'waiting_scan':'ready',qr_image:'data:image/png;base64,FAKE',qr_expires_in:180,expires_in:600}
      :url.endsWith('/captcha')?{gt:'FAKE_GT',challenge:'FAKE_CHALLENGE'}:{state:'waiting_scan'})
    return new Response(JSON.stringify(data))
  });return requests
}
function widget(t) {
  const old=globalThis.window;let success
  globalThis.window={initGeetest:(_config,callback)=>callback({onReady(fn){fn()},onSuccess(fn){success=fn},onError(){},onFail(){},verify(){},destroy(){},getValidate(){return{geetest_challenge:'FAKE_CHALLENGE',geetest_validate:'FAKE_VALID',geetest_seccode:'FAKE_SECCODE'}}})}
  t.after(()=>{if(old===undefined)delete globalThis.window;else globalThis.window=old})
  return ()=>success()
}
test('default QR has one 3-second polling loop and unmount cancels it',async t=> {
  const requests=network(t);t.mock.timers.enable({apis:['setTimeout']})
  const {vm,app}=await mount(t);assert.equal(vm.mode,'qr')
  t.mock.timers.tick(2999);await flush();assert.equal(requests.filter(r=>r.url.endsWith('/qr/poll')).length,0)
  t.mock.timers.tick(1);await flush();assert.equal(requests.filter(r=>r.url.endsWith('/qr/poll')).length,1)
  app.unmount();t.mock.timers.tick(30000);await flush()
  assert.equal(requests.filter(r=>r.url.endsWith('/qr/poll')).length,1)
  assert.ok(requests.some(r=>r.url.endsWith('/sessions/FAKE-1')&&r.body===null))
})
test('switching discards a stale session result and cancels its own SID',async t=> {
  let release;const requests=network(t,(url,body)=>url.endsWith('/sessions')&&body.mode==='qr'?new Promise(resolve=>{release=resolve}):undefined)
  const {vm}=await mount(t);await vm.selectMode('password');const sid=vm.session.session_id
  release({session_id:'FAKE-OLD',mode:'qr',state:'waiting_scan',qr_image:'data:image/png;base64,OLD'});await flush()
  assert.equal(vm.mode,'password');assert.equal(vm.session.session_id,sid)
  assert.ok(requests.some(r=>r.url.endsWith('/sessions/FAKE-OLD')))
})
test('password preserves spaces, human proof is one-use and secrets clear on submit',async t=> {
  const requests=network(t,(url)=>url.endsWith('/password')?{state:'complete',account:{configured:true}}:undefined)
  const succeed=widget(t);const {vm}=await mount(t)
  await vm.selectMode('password');vm.username='fake';await nextTick();vm.password=' FAKE_PASSWORD '
  await vm.prepareCaptcha();succeed();await flush();await vm.submitPassword()
  const request=requests.find(r=>r.url.endsWith('/password'))
  assert.equal(request.body.password,' FAKE_PASSWORD ');assert.equal(vm.password,'');assert.equal(vm.proof,null)
  assert.equal(vm.state,'complete')
})
test('SMS only sends on click, binds phone and applies cooldown',async t=> {
  const requests=network(t,(url)=>url.endsWith('/sms/send')?{state:'sms_sent',retry_after:60}:undefined)
  const succeed=widget(t);const {vm}=await mount(t);await vm.selectMode('sms');vm.mobile='13800000000';await nextTick()
  await vm.prepareCaptcha();succeed();await flush();assert.equal(requests.filter(r=>r.url.endsWith('/sms/send')).length,0)
  await vm.sendSms();assert.equal(vm.cooldown,60)
  await vm.sendSms();assert.equal(requests.filter(r=>r.url.endsWith('/sms/send')).length,1)
  vm.code='012345';vm.mobile='13900000000';await nextTick();assert.equal(vm.session,null);assert.equal(vm.code,'')
})
test('QR pending-save stops poll; retry commits without consuming QR again',async t=> {
  const requests=network(t,url=>url.endsWith('/qr/poll')?new Response(JSON.stringify({detail:'稍后保存',state:'pending_save',error_code:'COLLECTION_BUSY'}),{status:409})
    :url.endsWith('/commit')?{state:'complete',account:{configured:true}}:undefined)
  const {vm}=await mount(t);await vm.pollQr();assert.equal(vm.state,'pending_save')
  await vm.retrySave();assert.equal(vm.state,'complete')
  assert.equal(requests.filter(r=>r.url.endsWith('/qr/poll')).length,1)
})

test('replaced captcha ignores late success callbacks and expires after 120 seconds',async t=> {
  network(t);const callbacks=[];const old=globalThis.window
  globalThis.window={initGeetest:(_config,callback)=>callback({onReady(fn){fn()},onSuccess(fn){callbacks.push(fn)},onError(){},onFail(){},verify(){},destroy(){},getValidate(){return{geetest_challenge:'FAKE_CHALLENGE',geetest_validate:'FAKE_VALID',geetest_seccode:'FAKE_SECCODE'}}})}
  t.after(()=>{if(old===undefined)delete globalThis.window;else globalThis.window=old})
  const {vm}=await mount(t);await vm.selectMode('password');vm.username='fake';await nextTick()
  await vm.prepareCaptcha();await vm.prepareCaptcha();callbacks[0]();assert.equal(vm.proof,null)
  callbacks[1]();assert.ok(vm.proof)
  const now=Date.now();t.mock.method(Date,'now',()=>now+120000);vm.password='FAKE_PASSWORD';await vm.submitPassword()
  assert.equal(vm.proof,null);assert.match(vm.error,/重新验证/)
})

test('documented Geetest v3 widget without onFail opens and accepts proof',async t=> {
  network(t);const old=globalThis.window;let success,ready=0
  globalThis.window={initGeetest:(_config,callback)=>callback({onReady(fn){ready++;fn()},onSuccess(fn){success=fn},onError(){},onClose(){},verify(){},destroy(){},getValidate(){return{geetest_validate:'FAKE_VALID',geetest_seccode:'FAKE_SECCODE'}}})}
  t.after(()=>{if(old===undefined)delete globalThis.window;else globalThis.window=old})
  const {vm}=await mount(t);await vm.selectMode('password');vm.username='fake';await nextTick();await vm.prepareCaptcha()
  assert.equal(ready,1);success();assert.ok(vm.proof);assert.equal(vm.error,'')
})

test('phone edit keeps deadline-based SMS cooldown advancing',async t=> {
  network(t,url=>url.endsWith('/sms/send')?{state:'sms_sent',retry_after:60}:undefined)
  const succeed=widget(t);let now=Date.now();t.mock.method(Date,'now',()=>now);t.mock.timers.enable({apis:['setTimeout']})
  const {vm}=await mount(t);await vm.selectMode('sms');vm.mobile='13800000000';await nextTick()
  await vm.prepareCaptcha();succeed();await vm.sendSms();assert.equal(vm.cooldown,60)
  vm.mobile='13900000000';await nextTick();now+=61000;t.mock.timers.tick(61000);await flush()
  assert.equal(vm.cooldown,0)
})
