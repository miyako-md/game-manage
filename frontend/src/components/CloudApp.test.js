import test from 'node:test'
import assert from 'node:assert/strict'
import { Window } from 'happy-dom'
import { nextTick } from 'vue'
import { loadVue, mount, nodes, content, choose } from '../test-utils/vue.js'
import { configureHttpClient } from '../http-client.js'
const CloudApp = await loadVue(new URL('../CloudApp.vue', import.meta.url))
const tick = async () => { await new Promise(resolve => setImmediate(resolve)); await nextTick() }

test('public read failures do not label a successful private game as unreadable',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  t.mock.method(globalThis,'fetch',async path=>{
    if(path.startsWith('/api/public/')) throw new Error('读取超时，请重试；已有数据仍保留。')
    return new Response(JSON.stringify(path==='/api/identity/me'?{user_id:'A'}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path==='/api/accounts'?{accounts:[{account_id:'a',provider:'kuro',state:'active',capabilities:['account','stamina'],roles:[{role_id:'r',is_default:true}]}]}:{state:'ok',payload:{nickname:'合成角色',level:1,current:100,maximum:240}}))
  })
  const root=mount(t,CloudApp);for(let i=0;i<8;i++)await tick()
  assert.match(content(root),/活动日历.*读取超时/)
  assert.doesNotMatch(content(root),/读取异常|暂时无法读取/)
})

test('restoring an accounts page does not load private snapshots',async t=>{
  const previous=globalThis.window
  globalThis.window={location:{hash:'#/accounts'},addEventListener(){},removeEventListener(){},scrollTo(){}}
  t.after(()=>{globalThis.window=previous})
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const calls=[]
  t.mock.method(globalThis,'fetch',async path=>{
    calls.push(path)
    return new Response(JSON.stringify(path==='/api/identity/me'?{user_id:'A'}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path==='/api/accounts'?{accounts:[{account_id:'a',provider:'kuro',state:'active',capabilities:['account'],roles:[{role_id:'r',is_default:true}]}]}:{}))
  })
  mount(t,CloudApp);for(let i=0;i<6;i++)await tick()
  assert.deepEqual(calls.filter(p=>p.includes('/snapshot/')),[])
})
for (const failingNews of [false, true]) test(`overview refresh stays busy through every read even when news fails: ${failingNews}`, async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let hold = false
  const pending = [], paths = []
  t.mock.method(globalThis, 'fetch', async path => {
    paths.push(path)
    if (hold && failingNews && path.startsWith('/api/public/') && path.endsWith('/news')) {
      return new Response(JSON.stringify({ detail: 'source temporarily unavailable' }), { status: 502 })
    }
    if (hold && (path.endsWith('/snapshot/account') || path.startsWith('/api/public/'))) {
      await new Promise(resolve => pending.push({ path, resolve }))
    }
    const data = path === '/api/identity/me' ? { user_id: 'overview-user' }
      : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
        : path === '/api/accounts' ? { accounts: [{ account_id: 'overview-account', provider: 'kuro', game: 'wuthering_waves', state: 'active', capabilities: ['account'], roles: [{ role_id: 'overview-role', is_default: true }] }] }
          : { account_id: 'overview-account', role_id: 'overview-role', state: 'ok', payload: null }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, CloudApp)
  for (let i = 0; i < 8; i++) await tick()
  const refresh = nodes(root, 'button').find(n => String(n.props.class).includes('ov-refresh'))
  assert.equal(refresh.props.disabled, false)
  hold = true; refresh.props.onClick(); await tick()
  assert.ok(pending.some(p => p.path.endsWith('/snapshot/account')))
  assert.equal(refresh.props.disabled, true)
  assert.equal(refresh.props['aria-busy'], true)
  const firstReads = paths.length
  refresh.props.onClick(); await tick(); assert.equal(paths.length, firstReads)
  while (pending.some(p => p.path.endsWith('/snapshot/account'))) {
    for (let i=pending.length-1;i>=0;i--) {
      if(pending[i].path.endsWith('/snapshot/account')) pending.splice(i,1)[0].resolve()
    }
    await tick()
  }
  for (let i = 0; i < 4; i++) await tick()
  assert.ok(pending.some(p => p.path.startsWith('/api/public/')))
  assert.equal(refresh.props.disabled, true, 'public artwork and event reads are still pending')
  assert.match(content(refresh), /刷新中/)
  hold = false
  for (const request of pending.splice(0)) request.resolve()
  for (let i = 0; i < 6; i++) await tick()
  assert.equal(refresh.props.disabled, false)
  assert.equal(refresh.props['aria-busy'], undefined)
})
test('public Bilibili authorization entry is visible only for the website administrator', async t => {
  for (const is_admin of [false,true]) {
    await t.test(String(is_admin), async sub => {
      configureHttpClient({mode:'cloud'});sub.after(()=>configureHttpClient({mode:'local'}))
      sub.mock.method(globalThis,'fetch',async path=> {
        const data=path==='/api/identity/me'?{user_id:'fixture',is_admin}:path==='/api/accounts'?{accounts:[]}:path==='/api/identity/sessions'?{sessions:[]}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path.endsWith('/status')?{configured:false}:{state:'never',payload:null}
        return new Response(JSON.stringify(data))
      })
      const root=mount(sub,CloudApp);await tick();await tick()
      nodes(root,'button').find(n=>content(n)==='账号与授权').props.onClick();await tick()
      assert.equal(content(root).includes('管理员 · B 站公共源授权'),is_admin)
      assert.equal(content(root).includes('管理员 · QQ 群设置'),is_admin)
      assert.equal(content(root).includes('管理员 · 攻略更新'),is_admin)
    })
  }
})
test('minute session check defers during an accepted refresh and resumes after short tracking settles', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let identityReads = 0, posts = 0, reads = 0, postReads = 0
  t.mock.method(globalThis, 'fetch', async path => {
    let data
    if (path === '/api/identity/me') { identityReads++; data = { user_id: 'A' } }
    else if (path.endsWith('/csrf')) data = { csrf_token: 'fixture' }
    else if (path === '/api/accounts') data = { accounts: [{ account_id: 'a', provider: 'hypergryph', state: 'active', capabilities: ['account'], roles: [{ role_id: 'r', is_default: true }] }] }
    else if (path.endsWith('/refresh/account')) { posts++; data = { state: 'queued' } }
    else if (path.endsWith('/snapshot/account')) { reads++; if(posts)postReads++; data = { account_id:'a',role_id:'r',state: 'ok', payload: { role_id:'r',nickname: postReads > 1 ? '定时交互新快照' : '定时交互旧快照' }, poll_status: { refresh_state: posts && postReads === 1 ? 'queued' : 'idle' } } }
    else data = { state: 'never', payload: null }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, CloudApp); await tick(); await tick()
  nodes(root,'button').find(n=>content(n)==='终末地').props.onClick(); await tick(); await tick()
  t.mock.timers.tick(59000); await tick()
  await nodes(root, 'button').find(n => content(n) === '刷新数据').props.onClick(); await tick()
  t.mock.timers.tick(1000); await tick(); await tick()
  assert.equal(identityReads, 1, 'minute check must not invalidate active short tracking')
  assert.match(content(root), /刷新已排队/)
  t.mock.timers.tick(2000); await tick()
  assert.match(content(root), /定时交互新快照/); assert.doesNotMatch(content(root), /刷新已排队|刷新结果未确认/)
  assert.equal(postReads, 2); assert.equal(posts, 1)
  t.mock.timers.tick(58000); await tick(); await tick()
  assert.equal(identityReads, 2, 'normal session checks resume on the next minute')
  assert.equal(postReads, 3)
})
test('the minute check pauses in a background tab, catches up once shown after a missed minute, and never reads CSRF', async t => {
  t.mock.timers.enable({ apis: ['setInterval', 'Date'] })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const listeners = new Set(), previous = globalThis.document, show = hidden => { doc.hidden = hidden; listeners.forEach(fn => fn()) }
  const doc = { hidden: false, addEventListener: (type, fn) => type === 'visibilitychange' && listeners.add(fn), removeEventListener: (type, fn) => type === 'visibilitychange' && listeners.delete(fn) }
  globalThis.document = doc
  const calls = [], settle = async () => { for (let i = 0; i < 4; i++) await tick() }
  t.mock.method(globalThis, 'fetch', async path => { calls.push(path); return new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path === '/api/accounts' ? { accounts: [] } : { state: 'never', payload: null })) })
  mount(t, CloudApp); await settle()
  // After-hooks run in order: the unmount registered by mount() first, then these.
  t.after(() => { globalThis.document = previous; assert.equal(listeners.size, 0, 'unmount removes the visibility listener') })
  assert.equal(listeners.size, 1)
  calls.length = 0; t.mock.timers.tick(60000); await settle()
  assert.ok(calls.includes('/api/identity/me'), 'a visible tab keeps the minute session check')
  assert.ok(!calls.some(path => path.endsWith('/csrf')), 'the minute check never asks for a CSRF token')
  calls.length = 0; show(true); t.mock.timers.tick(120000); await settle()
  assert.deepEqual(calls, [], 'a background tab makes no requests')
  show(false); await settle()
  assert.ok(calls.includes('/api/identity/me'), 'shown again after a missed minute, it checks at once')
  calls.length = 0; t.mock.timers.tick(59000); await settle()
  assert.deepEqual(calls, [], 'the next minute counts from the catch-up')
  t.mock.timers.tick(1000); await settle(); assert.ok(calls.includes('/api/identity/me'))
  calls.length = 0; t.mock.timers.tick(10000); show(true); show(false); await settle()
  assert.deepEqual(calls, [], 'a short switch away does not trigger an extra check')
})
test('refresh UI converges without the minute timer and public never state is explicit', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let posts = 0, reads = 0, postReads = 0
  t.mock.method(globalThis, 'fetch', async path => {
    let data
    if (path === '/api/identity/me') data = { user_id: 'A' }
    else if (path.endsWith('/csrf')) data = { csrf_token: 'fixture' }
    else if (path === '/api/accounts') data = { accounts: [{ account_id: 'a', provider: 'hypergryph', state: 'active', capabilities: ['account'], roles: [{ role_id: 'r', is_default: true }] }] }
    else if (path.endsWith('/refresh/account')) { posts++; data = { state: 'queued' } }
    else if (path.endsWith('/snapshot/account')) { reads++; if(posts)postReads++; data = { account_id:'a',role_id:'r',state: 'ok', payload: { role_id:'r',nickname: postReads > 1 ? '新快照' : '旧快照' }, poll_status: { refresh_state: posts && postReads === 1 ? 'queued' : 'idle' } } }
    else data = { state: 'never', payload: null }
    return new Response(JSON.stringify(data))
  })
  const root = mount(t, CloudApp); await tick(); await tick()
  nodes(root,'button').find(n=>content(n)==='终末地').props.onClick(); await tick(); await tick()
  const refresh = nodes(root, 'button').find(n => content(n) === '刷新数据')
  await refresh.props.onClick(); await tick(); assert.equal(refresh.props.disabled, true)
  t.mock.timers.tick(0); await tick(); assert.match(content(root), /刷新已排队/)
  t.mock.timers.tick(2000); await tick(); assert.equal(refresh.props.disabled, false)
  assert.doesNotMatch(content(root), /刷新已排队|正在读取状态/)
  assert.match(content(root), /新快照/); assert.equal(posts, 1); assert.equal(postReads, 2)
  nodes(root,'button').find(n=>content(n)==='公告与资讯').props.onClick();await tick()
  assert.match(content(root), /尚未采集公告与资讯/); assert.doesNotMatch(content(root), /暂无公告与资讯/)
})
for (const [width, user] of [[390, 'A'], [1440, 'B']]) {
  test(`cloud mock DOM ${width}px user ${user} isolates navigation and revoked session clears all private views`, async t => {
    const browser = new Window({ width, height: 900 }), originalWindow = globalThis.window
    globalThis.window = browser; t.after(() => { globalThis.window = originalWindow; browser.happyDOM.abort() })
    configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
    const paths = []
    t.mock.method(globalThis, 'fetch', async (path) => {
      paths.push(path)
      if (path === '/api/identity/sessions') return new Response('{}', { status:401 })
      const data = path === '/api/identity/me' ? { user_id: user, is_admin:false } : path.endsWith('/csrf') ? { csrf_token:'fixture-csrf' } : { accounts:[{account_id:`account-${user}`,provider:'kuro',game:'wuthering_waves',state:'active',roles:[{role_id:`role-${user}`,display_name:`私人角色${user}`,is_default:true}]}] }
      return new Response(JSON.stringify(data))
    })
    const root = mount(t, CloudApp); await tick(); await tick()
    assert.match(content(root), new RegExp(`私人角色${user}`))
    nodes(root,'button').find(n=>content(n).includes('授权 1')).props.onClick(); await tick(); await tick()
    assert.match(content(root), /尚未提供云端数据能力/)
    assert.equal(nodes(root,'nav').find(n => n.props['aria-label'] === '云端导航')?.children.filter(n => n.type === 'button').length,4)
    assert.doesNotMatch(content(root), /英雄联盟|LCU|管理员来源配置|本地工作台/)
    await nodes(root,'button').find(n => content(n) === '网站会话').props.onClick(); await tick(); await tick()
    assert.doesNotMatch(content(root), /私人角色|鹰角寻访|森空岛档案/)
    assert.match(content(root), /网站登录/)
    assert.ok(paths.every(path => /^\/api\/(identity|accounts|public)(\/|$)/.test(path)))
  })
}
test('reloading on the accounts page keeps the first reads of its panels when the account list selects an authorization', async t => {
  const browser = new Window({ width: 1440, height: 900 }), originalWindow = globalThis.window
  browser.location.hash = '#/accounts'
  globalThis.window = browser; t.after(() => { globalThis.window = originalWindow; browser.happyDOM.abort() })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const account = { account_id: 'a1', provider: 'kuro', game: 'wuthering_waves', state: 'active', capabilities: [], roles: [{ role_id: 'r1', display_name: '角色甲', is_default: true }] }
  const link = { link_id: 'l1', identity: { scene: 'group', group_openid: 'fixture-group', sender_openid: 'fixture-sender' } }
  const answers = [], requests = []
  t.mock.method(globalThis, 'fetch', (path, options = {}) => new Promise((resolve, reject) => {
    requests.push(path)
    const data = path === '/api/identity/me' ? { user_id: 'u1', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [account] } : path === '/api/qq/link-attempts' ? { links: [link] } : { state: 'never', payload: null }
    answers.push(() => resolve(new Response(JSON.stringify(data))))
    options.signal?.addEventListener('abort', () => reject(options.signal.reason), { once: true })
  }))
  const root = mount(t, CloudApp)
  // A real network answers in request order, one event-loop turn apart.
  for (let i = 0; i < 40 && (answers.length || i < 3); i++) { answers.shift()?.(); await tick() }
  for (let i = 0; i < 4; i++) await tick()
  assert.ok(requests.includes('/api/qq/link-attempts'))
  assert.match(content(root), /已关联 · 群聊/)
  assert.deepEqual(nodes(root, 'p').filter(n => n.props.role === 'alert').map(content), [])
  assert.match(content(nodes(root, 'section').find(n => String(n.props.class).includes('login-panel'))), /角色甲/)
})
test('after the cookie switches to another user, the account panels start over instead of showing the previous user', async t => {
  t.mock.timers.enable({ apis: ['setTimeout', 'setInterval'] })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const rows = { A: [{ account_id: 'a1', provider: 'kuro', game: 'wuthering_waves', state: 'active', capabilities: [], roles: [{ role_id: 'r1', display_name: '甲的昵称', is_default: true }] }],
    B: [{ account_id: 'b1', provider: 'tajiduo', game: 'nte', state: 'active', capabilities: [], roles: [{ role_id: 'r2', display_name: '乙的昵称', is_default: true }] }] }
  let who = 'A'
  t.mock.method(globalThis, 'fetch', async path => new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: who, is_admin: false }
    : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: rows[who] } : { state: 'never', payload: null })))
  const root = mount(t, CloudApp); await tick(); await tick()
  t.mock.timers.tick(30000); await tick()
  nodes(root, 'button').find(n => content(n) === '账号与授权').props.onClick(); await tick(); await tick()
  const panel = label => nodes(root, 'section').find(n => n.props['aria-label'] === label || String(n.props.class).includes(label))
  const login = panel('login-panel'), settings = panel('本人游戏授权')
  assert.match(content(login), /甲的昵称/)
  nodes(login, 'button').find(n => content(n) === '登录').props.onClick(); await tick()
  assert.ok(nodes(login, 'input').some(n => n.props.id === 'community-mobile'), "user A's login form is open")
  // Another tab signs in as B; this tab notices at its minute check and swaps the user in one synchronous step.
  who = 'B'; t.mock.timers.tick(30000); for (let i = 0; i < 6; i++) await tick()
  assert.match(content(root), /乙的昵称/)
  assert.doesNotMatch(content(panel('login-panel')), /甲的昵称/, "user A's nickname is still shown to user B")
  assert.ok(!nodes(panel('login-panel'), 'input').some(n => n.props.id === 'community-mobile'), "user A's login form is still open for user B")
  assert.notEqual(panel('login-panel'), login, 'the community-login panel was patched, not mounted again')
  assert.notEqual(panel('本人游戏授权'), settings, 'the authorization list was patched, not mounted again')
})
test('the sessions page lists the sessions after a reload on it and asks once per visit', async t => {
  const browser = new Window({ width: 1440, height: 900, url: 'https://cloud.example.test/#/sessions' }), originalWindow = globalThis.window
  globalThis.window = browser; t.after(() => { globalThis.window = originalWindow; browser.happyDOM.abort() })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = [], listed = () => calls.filter(path => path === '/api/identity/sessions').length
  t.mock.method(globalThis, 'fetch', async path => {
    calls.push(path)
    return new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] }
      : path === '/api/identity/sessions' ? { sessions: [{ session_id: 's1', created_at: '2026-10-16T14:02:00Z', expires_at: '2026-10-23T14:02:00Z' }] } : { state: 'never', payload: null }))
  })
  const root = mount(t, CloudApp); for (let i = 0; i < 6; i++) await tick()
  assert.equal(listed(), 1, 'a reload on #/sessions never asked for the session list')
  assert.match(content(root), /会话 1/)
  // A button changes the page and then the hash; the browser reports the new hash with a hashchange event after that.
  const open = async name => { const changed = new Promise(resolve => browser.addEventListener('hashchange', resolve, { once: true })); nodes(root, 'button').find(n => content(n) === name).props.onClick(); await changed; for (let i = 0; i < 4; i++) await tick() }
  await open('今日总览'); await open('网站会话')
  assert.equal(listed(), 2, 'opening the page by its navigation button must ask once per visit')
})

test('logging in again after a logout on the sessions page asks for the list once', async t => {
  const browser = new Window({ width: 1440, height: 900, url: 'https://cloud.example.test/#/sessions' }), originalWindow = globalThis.window
  const previousDocument = globalThis.Document, previousShadowRoot = globalThis.ShadowRoot
  globalThis.window = browser; globalThis.Document = class {}; globalThis.ShadowRoot = class {}
  t.after(() => { globalThis.window = originalWindow; globalThis.Document = previousDocument; globalThis.ShadowRoot = previousShadowRoot; browser.happyDOM.abort() })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let signedIn = true
  const calls = [], listed = () => calls.filter(path => path === '/api/identity/sessions').length
  t.mock.method(globalThis, 'fetch', async path => {
    calls.push(path)
    if (path === '/api/identity/login') signedIn = true
    if (path === '/api/identity/logout') signedIn = false
    if (path === '/api/identity/me' && !signedIn) return new Response('{"detail":"authentication_required"}', { status: 401 })
    return new Response(JSON.stringify(path === '/api/identity/me' || path === '/api/identity/login' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] }
      : path === '/api/identity/sessions' ? { sessions: [{ session_id: 's1', created_at: '2026-10-16T14:02:00Z', expires_at: '2026-10-23T14:02:00Z' }] } : { state: 'never', payload: null }))
  })
  const root = mount(t, CloudApp); for (let i = 0; i < 6; i++) await tick()
  await nodes(root, 'button').find(n => content(n) === '退出登录').props.onClick(); for (let i = 0; i < 6; i++) await tick()
  assert.match(content(root), /网站登录/); assert.equal(browser.location.hash, '#/sessions', 'a logout leaves the address alone')
  const inputs = nodes(root, 'input'), before = listed()
  inputs.find(x => x.props.name === 'username').props['onUpdate:modelValue']('alice')
  inputs.find(x => x.props.name === 'password').props['onUpdate:modelValue']('sample-password')
  await nodes(root, 'form')[0].props.onSubmit({ preventDefault() {} }); for (let i = 0; i < 8; i++) await tick()
  assert.equal(listed() - before, 1, 'the session list was asked for twice after logging in again')
  assert.match(content(root), /会话 1/)
})
test('logging in while the address names the sessions page lists the sessions too', async t => {
  const browser = new Window({ width: 1440, height: 900, url: 'https://cloud.example.test/#/sessions' }), originalWindow = globalThis.window
  const previousDocument = globalThis.Document, previousShadowRoot = globalThis.ShadowRoot
  globalThis.window = browser; globalThis.Document = class {}; globalThis.ShadowRoot = class {}
  t.after(() => { globalThis.window = originalWindow; globalThis.Document = previousDocument; globalThis.ShadowRoot = previousShadowRoot; browser.happyDOM.abort() })
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let signedIn = false
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options = {}) => {
    calls.push(path)
    if (path === '/api/identity/login') signedIn = true
    if (path === '/api/identity/me' && !signedIn) return new Response('{"detail":"authentication_required"}', { status: 401 })
    return new Response(JSON.stringify(path === '/api/identity/me' || path === '/api/identity/login' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] }
      : path === '/api/identity/sessions' ? { sessions: [{ session_id: 's1', created_at: '2026-10-16T14:02:00Z', expires_at: '2026-10-23T14:02:00Z' }] } : { state: 'never', payload: null }))
  })
  const root = mount(t, CloudApp); for (let i = 0; i < 4; i++) await tick()
  assert.match(content(root), /网站登录/)
  const inputs = nodes(root, 'input')
  inputs.find(x => x.props.name === 'username').props['onUpdate:modelValue']('alice')
  inputs.find(x => x.props.name === 'password').props['onUpdate:modelValue']('sample-password')
  await nodes(root, 'form')[0].props.onSubmit({ preventDefault() {} }); for (let i = 0; i < 6; i++) await tick()
  assert.equal(calls.filter(path => path === '/api/identity/sessions').length, 1, 'the session list was not asked for after the login')
  assert.match(content(root), /会话 1/)
})
test('the sessions page shows when a session was created and expires in Beijing time', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.method(globalThis, 'fetch', async path => new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] }
    : path === '/api/identity/sessions' ? { sessions: [{ session_id: 's1', created_at: '2026-10-16T14:02:00.123456Z', expires_at: '2026-10-23T14:02:00.123456Z' }] } : { state: 'never', payload: null })))
  const root = mount(t, CloudApp); await tick(); await tick()
  nodes(root, 'button').find(n => content(n) === '网站会话').props.onClick(); await tick(); await tick()
  assert.equal(content(nodes(root, 'article')[0]), '会话 1 · 创建 2026-10-16 22:02 · 过期 2026-10-23 22:02 撤销此会话')
})
test('a failed public read stays on its snapshot and is not left as an unhandled rejection', async t => {
  const unhandled = [], record = reason => unhandled.push(reason)
  process.on('unhandledRejection', record); t.after(() => process.off('unhandledRejection', record))
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async path => {
    calls.push(path)
    if (path.startsWith('/api/public/')) return new Response('{}', { status: 503 })
    return new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' }
      : path === '/api/accounts' ? { accounts: [{ account_id: 'a', provider: 'kuro', game: 'wuthering_waves', state: 'active', capabilities: [], roles: [{ role_id: 'r', is_default: true }] }] } : { state: 'never', payload: null }))
  })
  const root = mount(t, CloudApp); await tick(); await tick()
  nodes(root, 'button').find(n => content(n).includes('授权 1')).props.onClick(); for (let i = 0; i < 4; i++) await tick()
  assert.ok(calls.includes('/api/public/games/wuthering_waves/news'), 'the game page asked for the public news')
  assert.deepEqual(unhandled, [])
  assert.match(content(root), /鸣潮 · 库街区/)
})
test('cloud public events render the real calendar with unknown dates and source details', async t => {
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const calls=[]
  t.mock.method(globalThis,'fetch',async path=>{
    calls.push(path)
    const data=path==='/api/identity/me'?{user_id:'A'}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path==='/api/accounts'?{accounts:[]}:path.endsWith('/events')?{payload:[{name:'云端待定活动',category:'官方活动',start_at:null,end_at:null,source_title:'公开活动公告',source_url:'https://example.com/fixture-event'}],state:'ok',fetched_at:'2026-10-12T00:00:00Z',complete:null}:{payload:[],state:'ok'}
    return new Response(JSON.stringify(data))
  })
  const root=mount(t,CloudApp);await tick();await tick()
  nodes(root,'button').find(n=>content(n)==='活动日历').props.onClick();await tick();await tick()
  const undated=nodes(root,'button').filter(node=>node.props['aria-label']==='查看活动详情：云端待定活动')
  assert.equal(undated.length,3);assert.ok(undated.every(node=>content(node)==='云端待定活动 官方活动 · 时间待定'))
  const sources=nodes(root,'details').find(node=>String(node.props.class).includes('calendar-source-states'))
  assert.ok(sources);assert.ok(!sources.props.open)
  const trigger=nodes(root,'button').find(n=>n.props['aria-label']==='查看活动详情：云端待定活动')
  assert.ok(trigger);await trigger.props.onClick();await tick()
  const detail=nodes(root,'section').find(node=>node.props['aria-labelledby']==='calendar-detail-title')
  assert.match(content(detail),/开始时间.*未知.*截止时间.*未知/);assert.match(content(detail),/公开活动公告/)
  assert.ok(calls.includes('/api/public/games/wuthering_waves/events'))
  assert.ok(calls.every(path=>!path.startsWith('/api/games/')))
})

test('a logout that fails keeps a retry on screen instead of the login form, and the retry ends the session', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const retried = { resolve: null }, logouts = []
  t.mock.method(globalThis, 'fetch', async path => {
    if (path === '/api/identity/logout') {
      logouts.push(path)
      if (logouts.length === 1) throw new TypeError('Failed to fetch')
      return new Promise(resolve => { retried.resolve = () => resolve(new Response('{"status":"ok"}')) })
    }
    return new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] } : { state: 'never', payload: null }))
  })
  const root = mount(t, CloudApp); await tick(); await tick()
  const logout = () => nodes(root, 'button').find(n => content(n) === '退出登录')
  await logout().props.onClick(); for (let i = 0; i < 4; i++) await tick()
  assert.doesNotMatch(content(root), /网站登录/, 'the page claims to be signed out although the site session may still be valid')
  assert.match(content(root), /退出登录未完成/)
  assert.ok(logout(), 'there is no button to retry with')
  const retry = logout().props.onClick(); await tick(); await tick()
  assert.match(content(root), /退出中…/); assert.doesNotMatch(content(root), /退出登录未完成|网站登录/)
  retried.resolve(); await retry; for (let i = 0; i < 4; i++) await tick()
  assert.match(content(root), /网站登录/); assert.doesNotMatch(content(root), /退出登录未完成|退出中/)
  assert.equal(logouts.length, 2)
})
test('a logout answered with 401 ends at the login form without a retry', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  t.mock.method(globalThis, 'fetch', async path => path === '/api/identity/logout' ? new Response('{"detail":"authentication_required"}', { status: 401 })
    : new Response(JSON.stringify(path === '/api/identity/me' ? { user_id: 'A', is_admin: false } : path.endsWith('/csrf') ? { csrf_token: 'fixture' } : path === '/api/accounts' ? { accounts: [] } : { state: 'never', payload: null })))
  const root = mount(t, CloudApp); await tick(); await tick()
  await nodes(root, 'button').find(n => content(n) === '退出登录').props.onClick(); for (let i = 0; i < 4; i++) await tick()
  assert.match(content(root), /网站登录/); assert.doesNotMatch(content(root), /退出登录未完成/)
  assert.equal(nodes(root, 'button').some(n => content(n) === '退出登录'), false)
})

test('Endfield role menu selects across accounts without source switches or default-role writes',async t=>{
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const accounts=['first','second'].map(id=>({account_id:id,provider:'hypergryph',state:'active',capabilities:['account'],roles:[{role_id:`${id}-default`,display_name:`${id}默认角色`,is_default:true},{role_id:`${id}-other`,display_name:`${id}备选角色`}]}))
  const calls=[]
  t.mock.method(globalThis,'fetch',async(path,options)=>{
    calls.push({path,method:options.method})
    const data=path==='/api/identity/me'?{user_id:'owner'}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path==='/api/accounts'?{accounts}:{state:'never',payload:null}
    return new Response(JSON.stringify(data))
  })
  const root=mount(t,CloudApp);await tick();await tick()
  nodes(root,'button').find(n=>content(n)==='终末地').props.onClick();await tick();await tick()
  assert.equal(nodes(root,'select').length,0)
  assert.equal(nodes(root,'ul').some(n=>n.props['aria-label']==='查看授权'),false)
  choose(root,'查看角色','second:second-other');await tick();await tick()
  assert.ok(calls.some(call=>call.path==='/api/accounts/second/roles/second-other/snapshot/account'))
  assert.ok(!calls.some(call=>call.method==='PUT'||call.path.endsWith('/default-role')))
  const roleMenu=nodes(root,'ul').find(n=>n.props['aria-label']==='查看角色')
  assert.deepEqual(nodes(roleMenu,'li').map(n=>n.props['data-value']),['first:first-default','first:first-other','second:second-default','second:second-other'])
})


for(const page of ['accounts','calendar'])test(`entering the already selected game from ${page} starts private reads`,async t=>{
  const previous=globalThis.window
  globalThis.window={location:{hash:`#/${page}`},addEventListener(){},removeEventListener(){},scrollTo(){}}
  t.after(()=>{globalThis.window=previous})
  configureHttpClient({mode:'cloud'});t.after(()=>configureHttpClient({mode:'local'}))
  const calls=[]
  t.mock.method(globalThis,'fetch',async path=>{
    calls.push(path)
    return new Response(JSON.stringify(path==='/api/identity/me'?{user_id:'A'}:path.endsWith('/csrf')?{csrf_token:'fixture'}:path==='/api/accounts'?{accounts:[{account_id:'a',provider:'kuro',state:'active',capabilities:['account'],roles:[{role_id:'r',is_default:true}]}]}:{state:'ok',payload:{nickname:'合成角色'}}))
  })
  const root=mount(t,CloudApp);for(let i=0;i<6;i++)await tick()
  assert.deepEqual(calls.filter(p=>p.includes('/snapshot/')),[])
  nodes(root,'button').find(n=>content(n).includes('授权 1')).props.onClick();for(let i=0;i<6;i++)await tick()
  assert.equal(calls.filter(p=>p.endsWith('/snapshot/account')).length,1)
})
