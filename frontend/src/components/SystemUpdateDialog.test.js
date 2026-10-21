import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { Window } from 'happy-dom'
const window = new Window()
for (const key of ['document', 'Element', 'HTMLElement', 'SVGElement', 'Node']) globalThis[key] = window[key]
globalThis.window = window
globalThis.matchMedia = window.matchMedia.bind(window)
after(() => window.happyDOM.close())
const { createApp, h, nextTick, ref } = await import('vue')
const { loadVue } = await import('../test-utils/vue.js')
const { configureHttpClient, invalidateSession } = await import('../http-client.js')
const Dialog = await loadVue(new URL('./SystemUpdateDialog.vue', import.meta.url))
const OLD = '1'.repeat(40), TARGET = '2'.repeat(40)
const snapshot = extra => ({ repository: 'miyako-md/game-manage', branch: 'main', current: { sha: OLD, frontend_sha: OLD, dirty: false },
  latest: { sha: TARGET, message: '改进页面加载速度', committed_at: '2026-10-18T01:00:00Z' },
  relation: 'ahead', checked_at: 100, stale: false, check_error: null, can_apply: true, unavailable_reason: null,
  worker_available: true, job: null, ...extra })
const job = phase => ({ job_id: 'job-one', phase, previous_sha: OLD, target_sha: TARGET, updated_at: 100 })
const reply = body => new Response(JSON.stringify(body))
const settle = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
function mountDialog(t, respond) {
  configureHttpClient({ mode: 'local' })
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => { calls.push({ path, options }); return respond(path, options) })
  const trigger = document.createElement('button')
  const root = document.createElement('div')
  document.body.append(trigger, root); trigger.focus()
  const open = ref(true)
  const app = createApp({ render: () => open.value ? h(Dialog, { onClose: () => { open.value = false } }) : null })
  app.mount(root)
  t.after(() => { app.unmount(); root.remove(); trigger.remove(); document.body.style.overflow = '' })
  const button = label => [...root.querySelectorAll('button')].find(button => button.textContent.trim() === label || button.getAttribute('aria-label') === label)
  return { root, trigger, calls, button, app }
}

test('opening locks the dialog, reads only status and restores focus on animated close', async t => {
  const { root, trigger, calls, button } = mountDialog(t, () => reply(snapshot()))
  await settle()
  const dialog = root.querySelector('dialog')
  assert.equal(dialog.open, true)
  assert.equal(dialog.getAttribute('aria-modal'), 'true')
  assert.equal(document.getElementById(dialog.getAttribute('aria-labelledby')).textContent, '系统更新')
  assert.equal(document.body.style.overflow, 'hidden')
  assert.deepEqual(calls.map(call => call.path), ['/api/system/update'])
  assert.match(root.textContent, /1111111.*2222222.*改进页面加载速度/s)
  assert.equal(root.querySelector('[aria-live="polite"]').getAttribute('aria-atomic'), 'true')
  button('关闭系统更新').click()
  dialog.dispatchEvent(new window.AnimationEvent('animationend', { animationName: 't-dialog-exit' }))
  await settle()
  assert.equal(root.querySelector('dialog'), null)
  assert.equal(document.body.style.overflow, '')
  assert.equal(document.activeElement, trigger)
})

test('checking exposes the available version; apply requires the inline target confirmation', async t => {
  const { root, calls, button } = mountDialog(t, path => reply(path.endsWith('/check') ? snapshot() : path.endsWith('/apply') ? snapshot({ job: job('queued'), can_apply: false }) : snapshot({ latest: null, relation: 'unknown', can_apply: false })))
  await settle()
  assert.equal(button('更新到此版本'), undefined)
  button('检查更新').click(); await settle()
  assert.ok(button('更新到此版本'))
  button('更新到此版本').click(); await settle()
  assert.equal(calls.some(call => call.path.endsWith('/apply')), false)
  assert.match(root.querySelector('[role="group"]').textContent, /更新到 2222222/)
  assert.match(root.querySelector('[role="group"]').textContent, /请先保存正在编辑的内容/)
  assert.doesNotMatch(root.querySelector('[role="group"]').textContent, /页面会保留/)
  button('确认更新').click(); button('确认更新')?.click(); await settle()
  const apply = calls.filter(call => call.path.endsWith('/apply'))
  assert.equal(apply.length, 1)
  assert.deepEqual(JSON.parse(apply[0].options.body), { expected_sha: OLD, target_sha: TARGET })
  assert.match(root.textContent, /更新已排队/)
  assert.equal(button('刷新页面'), undefined)
})

test('an up-to-date installation and a preview never offer an update', async t => {
  for (const value of [snapshot({ relation: 'up_to_date', can_apply: false, unavailable_reason: 'up_to_date' }),
    snapshot({ can_apply: false, unavailable_reason: 'preview_only' })]) {
    const { root, button, app } = mountDialog(t, () => reply(value))
    await settle()
    assert.equal(button('更新到此版本'), undefined)
    assert.match(root.textContent, value.relation === 'up_to_date' ? /当前已是最新版本/ : /模拟预览中不会更新程序/)
    app.unmount()
  }
})

test('completed jobs expose refresh only after backend and frontend running commits both match, with no automatic reload', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let reads = 0
  const reload = t.mock.method(window.location, 'reload', () => {})
  const { root, button } = mountDialog(t, () => reply(snapshot({ job: job('completed'), can_apply: false,
    current: { sha: TARGET, frontend_sha: ++reads === 1 ? OLD : TARGET } })))
  await settle()
  assert.equal(button('刷新页面'), undefined)
  assert.match(root.textContent, /正在核对运行版本/)
  assert.equal(reload.mock.callCount(), 0)
  t.mock.timers.tick(2000); await settle()
  assert.ok(button('刷新页面'))
  assert.match(root.textContent, /新版本已开始运行/)
  assert.equal(reload.mock.callCount(), 0)
  button('刷新页面').click()
  assert.equal(reload.mock.callCount(), 1)
})

test('closing immediately aborts a pending request and leaves no polling after the close animation', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let resolve
  const { root, calls, button } = mountDialog(t, () => new Promise(done => { resolve = done }))
  await settle()
  button('关闭系统更新').click()
  assert.equal(calls[0].options.signal.aborted, true)
  resolve(reply(snapshot({ job: job('restarting'), can_apply: false }))); await settle()
  t.mock.timers.tick(220); await settle()
  assert.equal(root.querySelector('dialog'), null)
  t.mock.timers.tick(30000); await settle()
  assert.equal(calls.length, 1)
})

test('session invalidation clears displayed commit and job information', async t => {
  const { root, button } = mountDialog(t, () => reply(snapshot()))
  await settle()
  assert.match(root.textContent, /2222222/)
  button('更新到此版本').click(); await settle()
  invalidateSession(); await settle()
  assert.doesNotMatch(root.textContent, /1111111|2222222|改进页面加载速度/)
  assert.match(root.textContent, /网站会话已变化/)
  assert.equal(root.querySelector('[role="group"]'), null)
  assert.equal(button('检查更新').disabled, true)
})


test('a retained completed job cannot hide a newer main candidate on the next update', async t => {
  const newer = '3'.repeat(40)
  const { root, button } = mountDialog(t, () => reply(snapshot({ job: job('completed'),
    current: { sha: TARGET, frontend_sha: TARGET }, latest: { sha: newer, message: '后续改进' }, can_apply: true })))
  await settle()
  assert.match(root.textContent, /发现新版本/)
  assert.ok(button('更新到此版本'))
  assert.equal(button('刷新页面'), undefined)
  button('更新到此版本').click(); await settle()
  assert.match(root.querySelector('[role="group"]').textContent, /3333333/)
})
