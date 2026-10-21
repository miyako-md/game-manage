import test from 'node:test'
import assert from 'node:assert/strict'
import { nextTick, reactive } from 'vue'
import { loadVue, mount, nodes, content, choose } from '../test-utils/vue.js'
import { configureHttpClient, requestJson, invalidateSession } from '../http-client.js'
const CloudApp = await loadVue(new URL('../CloudApp.vue', import.meta.url))
const Connector = await loadVue(new URL('./CloudSklandConnect.vue', import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }
const button = (root, text) => nodes(root, 'button').find(node => content(node) === text)
const menuTrigger = (root, label) => nodes(root, 'button').find(node => node.props.role === 'combobox' && node.props['aria-label'] === label)
const submit = (root, label) => nodes(root, 'form').find(node => node.props['aria-label'] === label).props.onSubmit({ preventDefault() {} })
const account = (id, provider = 'hypergryph', state = 'active') => ({ account_id: id, grant_id: `grant-${id}`, version: 1, game: 'endfield', provider, state, capabilities: [], roles: [{ role_id: `role-${id}`, display_name: `角色${id}`, is_default: true }, { role_id: `other-${id}`, display_name: `备选${id}`, is_default: false }] })
async function setup(t, handler, rows = [account('A'), account('B'), account('profile', 'skland')]) {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, options, body: options.body && JSON.parse(options.body) })
    const response = await handler?.(path, options, calls)
    if (response) return response
    const data = path === '/api/identity/me' ? { user_id: 'owner' } : path.endsWith('/csrf') ? { csrf_token: 'csrf-fixture' } : path === '/api/accounts' ? { accounts: rows } : path.endsWith('/status') ? { configured: false } : { state: 'never', payload: null }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, CloudApp); await tick(); await tick()
  button(root, '账号与授权').props.onClick(); await tick(); await tick()
  return { root, calls, rows }
}
async function chooseSource(root, id = 'B', role = 'other-B') {
  const accounts = menuTrigger(root, '用于连接森空岛的鹰角授权')
  assert.ok(accounts, 'cloud account page must offer owned source selection')
  choose(root, '用于连接森空岛的鹰角授权', id); await tick()
  choose(root, '用于连接森空岛的鹰角角色', role); await tick()
}

test('cloud passport button submits selected internal IDs with CSRF then refreshes independent authorizations', async t => {
  let connected = false
  const { root, calls } = await setup(t, path => {
    if (path.endsWith('/skland/passport')) { connected = true; return new Response(JSON.stringify({ ok: true, account_id: 'derived', role_id: 'derived-role', grant_id: 'derived-grant', version: 1 })) }
    if (path === '/api/accounts' && connected) return new Response(JSON.stringify({ accounts: [account('A'), account('B'), { ...account('derived', 'skland'), authorization_source: 'passport', parent_account_id: 'B', parent_role_id: 'other-B' }] }))
  })
  assert.equal(button(root, '一键连接森空岛档案').props.disabled, true)
  assert.equal(calls.filter(call => call.path.endsWith('/skland/passport')).length, 0, 'login/page entry must not auto-connect')
  await chooseSource(root)
  await submit(root, '通过鹰角授权连接森空岛'); await tick(); await tick()
  const write = calls.find(call => call.path.endsWith('/skland/passport'))
  assert.deepEqual(write.body, { account_id: 'B', role_id: 'other-B' })
  assert.equal(write.options.method, 'POST'); assert.equal(write.options.headers['X-CSRF-Token'], 'csrf-fixture')
  assert.equal(write.options.credentials, 'same-origin')
  assert.match(content(root), /森空岛档案已连接/)
  assert.match(content(root), /来源：鹰角授权/)
  assert.match(content(nodes(root, 'nav').find(node => node.props['aria-label'] === '本人游戏角色').children.find(node => node.props['aria-pressed'] === true)), /角色A/)
  assert.equal(nodes(root, 'article').filter(node => content(node).includes('撤销这项游戏授权')).length, 3)
  assert.ok(calls.filter(call => call.path === '/api/accounts').length > 1)
  assert.ok(calls.every(call => !call.path.startsWith('/api/endfield/skland/passport')))
})

test('changed source authorization is distinguished from a role mismatch without exposing backend detail', async t => {
  const { root } = await setup(t, path => path.endsWith('/skland/passport') ? new Response(JSON.stringify({ error_code: 'authorization_changed', detail: 'SECRET' }), { status: 409 }) : null)
  await chooseSource(root)
  await submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.match(content(root), /来源授权已变化.*重新选择/)
  assert.doesNotMatch(content(root), /未能匹配|SECRET/)
})

test('an expired Hypergryph authorization is reported as such and does not sign the user out of the site', async t => {
  const { root } = await setup(t, path => path.endsWith('/skland/passport') ? new Response(JSON.stringify({ error_code: 'auth_expired', detail: '鹰角授权已失效，请重新登录' }), { status: 401 }) : null)
  await chooseSource(root)
  await submit(root, '通过鹰角授权连接森空岛'); await tick(); await tick()
  assert.match(content(root), /游戏授权不可用，请到「账号与授权」重新登录；已有授权已保留/)
  assert.doesNotMatch(content(root), /网站登录|网站会话已失效/)
  assert.ok(button(root, '一键连接森空岛档案'), 'the account page is still shown')
})

test('successful connection with a failed account-list refresh retains the previous authorization list', async t => {
  let connected = false
  const { root } = await setup(t, path => {
    if (path.endsWith('/skland/passport')) { connected = true; return new Response(JSON.stringify({ ok: true, account_id: 'derived', role_id: 'derived-role', grant_id: 'derived-grant', version: 1 })) }
    if (path === '/api/accounts' && connected) return new Response('{}', { status: 503 })
  })
  await chooseSource(root)
  await submit(root, '通过鹰角授权连接森空岛'); await tick(); await tick()
  assert.match(content(root), /森空岛档案已连接/)
  assert.match(content(root), /来源暂时不可用，保留已有数据/)
  assert.equal(nodes(root, 'article').filter(node => content(node).includes('撤销这项游戏授权')).length, 3)
})

test('website invalidation removes the connector and discards a late ignored-abort response', async t => {
  let finish, signal
  const { root, calls } = await setup(t, (path, options) => path.endsWith('/skland/passport') ? new Promise(resolve => { finish = resolve; signal = options.signal }) : null)
  await chooseSource(root)
  const pending = submit(root, '通过鹰角授权连接森空岛'); await tick()
  const reads = calls.filter(call => call.path === '/api/accounts').length
  invalidateSession(); await tick()
  assert.equal(signal.aborted, true)
  finish(new Response(JSON.stringify({ ok: true, account_id: 'late-private' }))); await pending; await tick()
  assert.doesNotMatch(content(root), /森空岛档案已连接|late-private/)
  assert.equal(calls.filter(call => call.path === '/api/accounts').length, reads)
})

test('source grant version change cancels the pending connector result without refreshing another grant', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let finish, signal, changed = 0
  t.mock.method(globalThis, 'fetch', async (path, options) => path.endsWith('/csrf') ? new Response(JSON.stringify({ csrf_token: 'fixture' })) : new Promise(resolve => { finish = resolve; signal = options.signal }))
  const props = reactive({ accounts: [account('B')], userId: 'owner', onChanged: () => changed++ })
  const root = mount(t, Connector, props)
  await chooseSource(root)
  const pending = submit(root, '通过鹰角授权连接森空岛'); await tick()
  props.accounts[0].version = 2; await tick()
  assert.equal(signal.aborted, true)
  finish(new Response(JSON.stringify({ ok: true }))); await pending; await tick()
  assert.equal(changed, 0)
  assert.doesNotMatch(content(root), /森空岛档案已连接/)
})

test('cloud passport failure is safe, preserves prior grants and retries only on explicit action', async t => {
  const { root, calls } = await setup(t, path => path.endsWith('/skland/passport') ? new Response(JSON.stringify({ detail: 'PRIVATE-UPSTREAM-SECRET', error_code: 'skland_role_mismatch' }), { status: 409 }) : null)
  await chooseSource(root)
  await submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.match(content(root), /角色.*匹配|匹配.*角色/)
  assert.match(content(root), /手动/)
  assert.doesNotMatch(content(root), /PRIVATE-UPSTREAM-SECRET/)
  assert.equal(nodes(root, 'article').filter(node => content(node).includes('撤销这项游戏授权')).length, 3)
  assert.equal(calls.filter(call => call.path.endsWith('/skland/passport')).length, 1)
  await submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.equal(calls.filter(call => call.path.endsWith('/skland/passport')).length, 2)
  assert.equal(button(root, '一键连接森空岛档案').props.disabled, false)
})

test('busy cloud passport blocks duplicate submits until the request settles', async t => {
  let finish
  const { root, calls } = await setup(t, path => path.endsWith('/skland/passport') ? new Promise(resolve => { finish = resolve }) : null)
  await chooseSource(root)
  const pending = submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.equal(menuTrigger(root, '用于连接森空岛的鹰角授权').props.disabled, true)
  await submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.equal(calls.filter(call => call.path.endsWith('/skland/passport')).length, 1)
  finish(new Response('{}', { status: 503 })); await pending; await tick()
  assert.match(content(root), /保留已有/)
})

test('source selector excludes revoked, expired, foreign-owned and non-Hypergryph rows and rejects fabricated roles', async t => {
  const { root, calls } = await setup(t, null, [account('A'), account('revoked', 'hypergryph', 'revoked'), account('expired', 'hypergryph', 'expired'), account('skland', 'skland'), { ...account('foreign'), user_id: 'different-owner' }])
  const chooser = menuTrigger(root, '用于连接森空岛的鹰角授权')
  assert.ok(chooser)
  const choices=nodes(root,'ul').find(node=>node.props.role==='listbox'&&node.props['aria-label']==='用于连接森空岛的鹰角授权')
  assert.deepEqual(nodes(choices,'li').filter(node=>node.props['data-value']).map(node=>node.props['data-value']), ['A'])
  choose(root,'用于连接森空岛的鹰角授权','A'); await tick()
  const roleOptions=nodes(root,'ul').find(node=>node.props['aria-label']==='用于连接森空岛的鹰角角色')
  assert.ok(!nodes(roleOptions,'li').some(node=>node.props['data-value']==='role-skland'))
  await submit(root, '通过鹰角授权连接森空岛'); await tick()
  assert.equal(calls.filter(call => call.path.endsWith('/skland/passport')).length, 0)
  assert.equal(button(root, '一键连接森空岛档案').props.disabled, true)
  await assert.rejects(requestJson('/api/endfield/skland/passport', { method: 'POST' }), /云端/)
})

test('cloud manual fallback retains its separate cred route and clears sensitive inputs', async t => {
  const { root, calls } = await setup(t)
  const form = nodes(root, 'form').find(node => node.props['aria-label'] === '手动连接森空岛')
  assert.ok(form)
  const inputs = nodes(form, 'input')
  inputs[0].props['onUpdate:modelValue']('manual-fixture'); inputs[1].props['onUpdate:modelValue']('device-fixture')
  await submit(root, '手动连接森空岛'); await tick()
  const write = calls.find(call => call.path.endsWith('/skland/connect'))
  assert.deepEqual(write.body, { cred: 'manual-fixture', device_id: 'device-fixture' })
  assert.equal(write.options.headers['X-CSRF-Token'], 'csrf-fixture')
  assert.ok(nodes(form, 'input').every(node => !node.props.value))
})

test('the Endfield guide link scrolls the connector into view; a plain visit does not', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const scrolled = [], location = globalThis.location
  // Test renderer nodes are plain objects; give them the one DOM method the connector calls.
  Object.defineProperty(Object.prototype, 'scrollIntoView', { configurable: true, value(options) { scrolled.push([this.type, options]) } })
  t.after(() => { delete Object.prototype.scrollIntoView; if (location === undefined) delete globalThis.location; else globalThis.location = location })
  globalThis.location = { hash: '#/accounts' }
  mount(t, Connector, { accounts: [account('A')], userId: 'owner' })
  assert.deepEqual(scrolled, [])
  globalThis.location = { hash: '#/accounts?focus=skland' }
  mount(t, Connector, { accounts: [account('A')], userId: 'owner' })
  assert.deepEqual(scrolled, [['section', { block: 'start' }]])
})
