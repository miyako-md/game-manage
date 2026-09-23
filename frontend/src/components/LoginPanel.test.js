import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRenderer, nextTick } from 'vue'
import { compileScript, parse } from 'vue/compiler-sfc'

// Run the real Vue setup/lifecycle without introducing a browser test dependency.
const { descriptor } = parse(readFileSync(new URL('./LoginPanel.vue', import.meta.url), 'utf8'))
const compiled = compileScript(descriptor, { id: 'login-panel-tests' }).content
  .replaceAll("from 'vue'", `from '${import.meta.resolve('vue')}'`)
  .replaceAll("from '../auth-api.js'", `from '${new URL('../auth-api.js', import.meta.url).href}'`)
const { default: LoginPanel } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
LoginPanel.render = () => null

function mount(t) {
  const renderer = createRenderer({
    createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {},
  })
  const app = renderer.createApp(LoginPanel)
  app.mount({})
  t.after(() => app.unmount())
  return { vm: app._instance.setupState, app }
}

function network(t, override) {
  const requests = []
  let sessions = 0
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    const body = options.body ? JSON.parse(options.body) : null
    requests.push({ url, body })
    const data = override?.(url, body) ?? (url.endsWith('/status') ? { accounts: {} }
      : url.endsWith('/sessions') ? { session_id: `session-${++sessions}`, expires_in: 600, captcha_id: 'captcha-id' }
        : { ok: true, retry_after: 60 })
    return new Response(JSON.stringify(await data))
  })
  return requests
}

function fakeClock(t) {
  let time = Date.now()
  t.mock.method(Date, 'now', () => time)
  t.mock.timers.enable({ apis: ['setInterval', 'setTimeout'] })
  return async (seconds) => {
    time += seconds * 1000
    t.mock.timers.tick(seconds * 1000)
    await nextTick()
  }
}

function widget(t, initialize) {
  const original = globalThis.window
  globalThis.window = { initGeetest4: initialize }
  t.after(() => { if (original === undefined) delete globalThis.window; else globalThis.window = original })
}

test('NTE sends SMS only on explicit action and reuses the session until the phone changes', async (t) => {
  const requests = network(t)
  const advance = fakeClock(t)
  const { vm } = mount(t)
  vm.selectGame('nte')
  vm.mobile = '13800000000'
  await vm.startSession()
  assert.equal(requests.filter((r) => r.url.endsWith('/sms')).length, 0)
  await vm.sendSms()
  assert.equal(vm.cooldown, 60)
  await advance(61)
  await vm.sendSms()
  const sms = requests.filter((r) => r.url.endsWith('/sms'))
  assert.equal(sms.length, 2)
  assert.equal(sms[0].body.session_id, sms[1].body.session_id)
  assert.equal('captcha' in sms[0].body, false)
  vm.mobile = '13900000000'
  assert.equal(vm.session, null)
  assert.equal(vm.code, '')
})

test('Wuwa requires human captcha success and sends the captcha id without replacing the session', async (t) => {
  const requests = network(t)
  let success
  let resets = 0
  widget(t, (_config, callback) => callback({
    onReady(fn) { fn() }, onSuccess(fn) { success = fn }, onError() {}, onFail() {}, appendTo() {}, destroy() {},
    reset() { resets += 1 },
    getValidate: () => ({ lot_number: 'lot', captcha_output: 'output', pass_token: 'pass', gen_time: 'time' }),
  }))
  const { vm } = mount(t)
  vm.selectGame('wuthering_waves')
  vm.mobile = '13800000000'
  await vm.startSession()
  await vm.sendSms()
  assert.equal(requests.filter((r) => r.url.endsWith('/sms')).length, 0)
  success()
  await vm.sendSms()
  const sms = requests.find((r) => r.url.endsWith('/sms'))
  assert.equal(sms.body.captcha.captcha_id, 'captcha-id')
  assert.equal(sms.body.session_id, 'session-1')
  assert.equal(resets, 1)
  assert.equal(vm.captchaValidated, false)
})

test('changing the phone discards an in-flight session response', async (t) => {
  let resolveSession
  network(t, (url) => url.endsWith('/sessions') ? new Promise((resolve) => { resolveSession = resolve }) : undefined)
  const { vm } = mount(t)
  vm.selectGame('nte')
  vm.mobile = '13800000000'
  const pending = vm.startSession()
  vm.mobile = '13900000000'
  resolveSession({ session_id: 'old-session', expires_in: 600 })
  await pending
  assert.equal(vm.session, null)
  assert.equal(vm.busy, '')
})

test('the expired countdown blocks submission and restart creates a fresh session', async (t) => {
  const requests = network(t)
  const advance = fakeClock(t)
  const { vm } = mount(t)
  vm.selectGame('nte')
  vm.mobile = '13800000000'
  await vm.startSession()
  vm.code = '123456'
  await advance(601)
  assert.equal(vm.expired, true)
  await vm.submitLogin()
  assert.equal(requests.filter((r) => r.url.endsWith('/login')).length, 0)
  await vm.startSession()
  assert.equal(vm.session.session_id, 'session-2')
  assert.equal(vm.code, '')
})

test('a captcha callback arriving after its load timeout is destroyed and cannot be mounted', async (t) => {
  network(t)
  const advance = fakeClock(t)
  let callback
  widget(t, (_config, ready) => { callback = ready })
  const { vm } = mount(t)
  vm.mobile = '13800000000'
  await vm.startSession()
  await advance(21)
  let destroyed = 0
  let appended = 0
  callback({
    destroy() { destroyed += 1 }, appendTo() { appended += 1 },
    onReady() {}, onSuccess() {}, onError() {}, onFail() {},
  })
  assert.equal(destroyed, 1)
  assert.equal(appended, 0)
})

test('opening the login form re-reads persisted account state', async (t) => {
  let state = 'connected'
  network(t, (url) => url.endsWith('/status') ? { accounts: { nte: { configured: true, state } } } : undefined)
  const { vm } = mount(t)
  await new Promise(setImmediate)
  assert.equal(vm.accounts.nte.state, 'connected')
  state = 'expired'
  vm.selectGame('nte')
  await new Promise(setImmediate)
  assert.equal(vm.accounts.nte.state, 'expired')
})

test('idle status polling reveals expiry and stops after unmount', async (t) => {
  let state = 'connected'
  const requests = network(t, (url) => url.endsWith('/status') ? { accounts: { nte: { configured: true, state } } } : undefined)
  const advance = fakeClock(t)
  const { vm, app } = mount(t)
  await new Promise(setImmediate)
  assert.equal(vm.accounts.nte.state, 'connected')
  state = 'expired'
  await advance(61)
  await new Promise(setImmediate)
  assert.equal(vm.accounts.nte.state, 'expired')
  app.unmount()
  const calls = requests.length
  await advance(61)
  await new Promise(setImmediate)
  assert.equal(requests.length, calls)
})
