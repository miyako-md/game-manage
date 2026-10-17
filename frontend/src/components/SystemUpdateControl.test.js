import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { nextTick, reactive } from 'vue'
import { configureHttpClient, invalidateSession } from '../http-client.js'
import { loadVue, mount, nodes } from '../test-utils/vue.js'
const Control = await loadVue(new URL('./SystemUpdateControl.vue', import.meta.url))
const settle = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

test('an ordinary cloud user has no update entry, request or background polling', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const requests = t.mock.method(globalThis, 'fetch', async () => assert.fail('ordinary users must not request update state'))
  const root = mount(t, Control, { allowed: false })
  await settle()
  assert.equal(nodes(root, 'button').length, 0)
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.equal(requests.mock.callCount(), 0)
  const cloudSource = readFileSync(new URL('../CloudApp.vue', import.meta.url), 'utf8')
  assert.match(cloudSource, /<SystemUpdateControl :allowed="state\.user\.is_admin === true"/)
})

test('local and admin entries stay idle until opened, then only request status', async t => {
  configureHttpClient({ mode: 'local' })
  const paths = []
  t.mock.method(globalThis, 'fetch', async path => {
    paths.push(path)
    return new Response(JSON.stringify({ repository: 'miyako-md/game-manage', branch: 'main',
      current: { sha: '1'.repeat(40), frontend_sha: '1'.repeat(40) }, latest: null,
      relation: 'unknown', can_apply: false, worker_available: false, job: null }))
  })
  const root = mount(t, Control, { allowed: true })
  await settle()
  assert.equal(paths.length, 0)
  const button = nodes(root, 'button').find(node => node.props['aria-label'] === '系统更新')
  assert.ok(button)
  assert.equal(button.props['aria-expanded'], false)
  button.props.onClick()
  await settle(); await settle()
  assert.deepEqual(paths, ['/api/system/update'])
  assert.equal(nodes(root, 'dialog').length, 1)
  invalidateSession(); await settle()
  assert.equal(nodes(root, 'dialog').length, 0)
  const localSource = readFileSync(new URL('../LocalApp.vue', import.meta.url), 'utf8')
  assert.match(localSource, /<SystemUpdateControl :allowed="true"/)
})

test('revoking permission closes an already opened updater without another request', async t => {
  configureHttpClient({ mode: 'local' })
  const requests = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    requests.push({ path, options }); return new Response(JSON.stringify({ repository: 'miyako-md/game-manage', branch: 'main',
      current: { sha: null }, latest: null, relation: 'unknown', can_apply: false, worker_available: false, job: null }))
  })
  const props = reactive({ allowed: true })
  const root = mount(t, Control, props)
  nodes(root, 'button')[0].props.onClick(); await settle(); await settle()
  props.allowed = false; await settle()
  assert.equal(nodes(root, 'button').length, 0)
  assert.equal(nodes(root, 'dialog').length, 0)
  assert.equal(requests.length, 1)
})
