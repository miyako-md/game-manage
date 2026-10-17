import test from 'node:test'
import assert from 'node:assert/strict'
import { requestJson, requestResponse, configureHttpClient, invalidateSession, subscribeSessionInvalidation, setAccountScope, safeDetail } from './http-client.js'
import { loadFavorites, saveFavorites } from './nte-roles.js'
import { readdirSync, readFileSync } from 'node:fs'
import { logoutSite } from './identity-api.js'
import { createAuthSession, getAuthStatus } from './auth-api.js'
import { wuwaRequest } from './wuwa-api.js'
import { connectCloudSklandPassport } from './accounts-api.js'

const json = value => new Response(JSON.stringify(value))
test('csrf added to every mutation and stable across authenticated writes', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const requests = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    requests.push({ path, options }); return json(path.endsWith('/csrf') ? { csrf_token: 'csrf-only' } : { ok: true })
  })
  for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) await requestJson('/api/accounts/a/default-role', { method, body: { role_id: 'r' } })
  assert.equal(requests.filter(x => x.path.endsWith('/csrf')).length, 1)
  for (const { options } of requests.filter(x => !x.path.endsWith('/csrf'))) {
    assert.equal(options.headers['X-CSRF-Token'], 'csrf-only'); assert.equal(options.credentials, 'same-origin')
  }
})
test('late response from previous user or role is ignored even when transport ignores abort', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let finish
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => { finish = resolve }))
  const pending = requestJson('/api/accounts')
  invalidateSession(); finish(json({ accounts: ['private-A'] }))
  await assert.rejects(pending, error => error.name === 'AbortError')
  setAccountScope({ account_id: 'a', role_id: 'r1', provider: 'kuro' })
  const rolePending = requestJson('/api/accounts/a/roles/r1/snapshot/account')
  setAccountScope({ account_id: 'a', role_id: 'r2', provider: 'kuro' }); finish(json({ payload: 'old-role' }))
  await assert.rejects(rolePending, error => error.name === 'AbortError')
})
test('401 revocation invalidates private state and blocks cloud legacy routes before fetch', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let cleared = 0, fetched = 0
  const stop = subscribeSessionInvalidation(() => cleared++); t.after(stop)
  t.mock.method(globalThis, 'fetch', async () => { fetched++; return new Response('{}', { status: 401 }) })
  await assert.rejects(requestJson('/api/accounts'), error => error.status === 401)
  assert.equal(cleared, 1)
  await assert.rejects(requestJson('/api/lol/collect', { method: 'POST' }), /云端/)
  assert.equal(fetched, 1)
})
function hungReads(t) {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const answers = new Map()
  t.mock.method(globalThis, 'fetch', (path, options) => new Promise((resolve, reject) => {
    answers.set(path, resolve); options.signal.addEventListener('abort', () => reject(options.signal.reason), { once: true })
  }))
  return { answers, read: path => requestJson(path).then(data => ({ data }), error => ({ error })) }
}
test('an account switch ends only the reads routed under that account', async t => {
  const { answers, read } = hungReads(t)
  setAccountScope({ account_id: 'a', role_id: 'r1', provider: 'kuro' })
  const accounts = read('/api/accounts'), links = read('/api/qq/link-attempts')
  const snapshot = read('/api/accounts/a/roles/r1/snapshot/account'), history = read('/api/wuwa/history?kind=tower')
  setAccountScope({ account_id: 'a', role_id: 'r2', provider: 'kuro' })
  for (const { error } of await Promise.all([snapshot, history])) assert.equal(error?.name, 'AbortError', 'a read of the previous role survived the switch')
  answers.get('/api/accounts')(json({ accounts: ['kept'] })); answers.get('/api/qq/link-attempts')(json({ links: ['kept'] }))
  assert.deepEqual(await accounts, { data: { accounts: ['kept'] } }, 'the account list read was aborted by the switch')
  assert.deepEqual(await links, { data: { links: ['kept'] } }, 'the QQ link read was aborted by the switch')
})
test('a session change ends every read, and an abort carries the cancellation of the project', async t => {
  const { read } = hungReads(t)
  setAccountScope({ account_id: 'a', role_id: 'r1', provider: 'kuro' })
  const scoped = read('/api/accounts/a/roles/r1/snapshot/account'), session = read('/api/accounts')
  setAccountScope({ account_id: 'a', role_id: 'r2', provider: 'kuro' })
  const switched = await scoped
  invalidateSession()
  for (const { error } of [switched, await session]) { assert.equal(error?.name, 'AbortError'); assert.equal(error.message, '会话或角色已变化') }
})
test('an expired game authorization answers 401 without ending the website session; any other 401 still does', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  let cleared = 0, reply
  const stop = subscribeSessionInvalidation(() => cleared++); t.after(stop)
  t.mock.method(globalThis, 'fetch', async path => path.endsWith('/csrf') ? json({ csrf_token: 'csrf' }) : new Response(reply, { status: 401 }))
  reply = JSON.stringify({ error_code: 'auth_expired', detail: '鹰角授权已失效，请重新登录' })
  const passport = await connectCloudSklandPassport('a', 'r').catch(error => error)
  assert.equal(cleared, 0, 'an expired Hypergryph authorization ended the website session')
  assert.equal(passport.status, 401); assert.equal(passport.code, 'auth_expired')
  assert.equal(passport.message, '游戏授权不可用，请到「账号与授权」重新登录')
  setAccountScope({ account_id: 'a', role_id: 'r', provider: 'kuro' })
  reply = JSON.stringify({ detail: 'private_query_failed' })
  await assert.rejects(wuwaRequest('roles/1'), /请重新登录鸣潮账号/)
  assert.equal(cleared, 0, 'an expired Kuro authorization ended the website session')
  for (const body of [{ detail: 'authentication_required' }, {}, { error_code: 'something_new' }, { detail: 'private_query_failed_later' }, '<html>', '']) {
    const before = cleared; reply = typeof body === 'string' ? body : JSON.stringify(body)
    const failure = await requestJson('/api/accounts').catch(error => error)
    assert.equal(failure.status, 401); assert.equal(failure.message, '网站会话已失效，请重新登录')
    assert.equal(cleared, before + 1, `a website-session or unrecognised 401 (${reply || 'empty body'}) must end the session`)
  }
})
test('server text is shown only when it is Chinese, capped, and everything else gets the fixed text', () => {
  assert.equal(safeDetail('短信发送过于频繁', '请稍后重试'), '短信发送过于频繁')
  assert.equal(safeDetail('x'.repeat(10) + '错'.repeat(300), '请稍后重试').length, 256)
  for (const detail of ['csrf_required', 'Not Found', '', '  ', undefined, null, 404, ['短信'], { detail: '短信' }]) assert.equal(safeDetail(detail, '请稍后重试'), '请稍后重试')
})
test('canonical community auth and role detail use owned cloud routes with CSRF', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => { calls.push([path,options]); return json(path.endsWith('/csrf') ? { csrf_token: 'csrf' } : path === '/api/accounts' ? { accounts: [] } : { ok: true }) })
  await getAuthStatus(); await createAuthSession('wuthering_waves'); await createAuthSession('nte'); await createAuthSession('endfield')
  setAccountScope({ account_id: 'a', role_id: 'r', provider: 'kuro' }); await wuwaRequest('roles/123')
  assert.deepEqual(calls.filter(x => !x[0].endsWith('/csrf')).map(x => x[0]), ['/api/accounts','/api/accounts/auth/kuro/sessions','/api/accounts/auth/tajiduo/sessions','/api/accounts/auth/hypergryph/sessions','/api/accounts/a/roles/r/wuwa/roles/123'])
  for (const [,options] of calls.filter(x => x[1].method === 'POST')) assert.equal(options.headers['X-CSRF-Token'],'csrf')
  await wuwaRequest('gacha/import', {body:{}}); assert.equal(calls.at(-1)[0],'/api/accounts/a/roles/r/wuwa/gacha/import'); assert.equal(calls.at(-1)[1].headers['X-CSRF-Token'],'csrf')
})
test('the Wuwa record import may preview and set its pity rule in the cloud, for a Kuro authorization only', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => { calls.push(`${options.method} ${path}`); return json(path.endsWith('/csrf') ? { csrf_token: 'csrf' } : { ok: true }) })
  setAccountScope({ account_id: 'a', role_id: 'r', provider: 'kuro' })
  const steps = ['gacha/preview', 'gacha/rules', 'gacha/import', 'history/backfill']
  for (const step of steps) await wuwaRequest(step, { body: {} })
  assert.deepEqual(calls.filter(call => !call.endsWith('/csrf')), steps.map(step => `POST /api/accounts/a/roles/r/wuwa/${step}`))
  setAccountScope({ account_id: 'b', role_id: 'r', provider: 'tajiduo' })
  await assert.rejects(wuwaRequest('gacha/preview', { body: {} }), /尚未提供云端接口/)
})
test('the Wuwa record backup can be exported in the cloud', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => { calls.push(`${options.method} ${path}`); return json({ items: [] }) })
  setAccountScope({ account_id: 'a', role_id: 'r', provider: 'kuro' })
  await wuwaRequest('gacha/export?limit=2000&offset=0')
  assert.deepEqual(calls, ['GET /api/accounts/a/roles/r/wuwa/gacha/export?limit=2000&offset=0'])
})
test('logout mutation reaches server while private scope is cleared', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async path => { calls.push(path); return json(path.endsWith('/csrf') ? { csrf_token:'csrf' } : {}) })
  await requestJson('/api/accounts/a/default-role',{method:'PUT',body:{role_id:'r'}})
  setAccountScope({ account_id:'a',role_id:'r',provider:'kuro' })
  const pending = logoutSite(); setAccountScope(null); await pending
  assert.ok(calls.includes('/api/identity/logout'))
})
test('legacy detail json parsing ignores late old user data, and cloud favorites never touch shared storage', async t => {
  configureHttpClient({ mode:'cloud' }); t.after(() => configureHttpClient({mode:'local'}))
  let finish
  t.mock.method(globalThis,'fetch',async () => ({ok:true,status:200,json:() => new Promise(resolve => { finish=resolve })}))
  const response=await requestResponse('/api/accounts/a/roles/r/snapshot/account')
  const pending=response.json(); invalidateSession(); finish({payload:'old-user'})
  await assert.rejects(pending,error=>error.name==='AbortError')
  const storage={getItem(){throw new Error('private storage read')},setItem(){throw new Error('private storage write')}}
  assert.deepEqual(loadFavorites('game-uid',storage),{ids:[],error:null})
  assert.equal(saveFavorites('game-uid',['character'],storage).error,null)
})
test('every production fetch remains behind the audited HTTP broker', () => {
  const root = new URL('.',import.meta.url)
  const callers = readdirSync(root,{recursive:true}).filter(name => /\.(js|vue)$/.test(name) && !name.endsWith('.test.js') && /\bfetch\s*\(/.test(readFileSync(new URL(name.replaceAll('\\','/'),root),'utf8')))
  assert.deepEqual(callers,['http-client.js'])
})
test('Skland reads in the cloud go to the owned role routes with their query, and only for a Skland authorization', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async path => { calls.push(path); return json({}) })
  setAccountScope({ account_id: 's', role_id: 'a', provider: 'skland' })
  const reads = ['card', 'attendance', 'operators/char%2F1', 'challenges?kind=war', 'challenges?kind=monument', 'tools?kind=materials']
  for (const read of reads) await requestJson(`/api/endfield/skland/${read}`)
  assert.deepEqual(calls, reads.map(read => `/api/accounts/s/roles/a/endfield/skland/${read}`))
  setAccountScope({ account_id: 'h', role_id: 'a', provider: 'hypergryph' })
  await assert.rejects(requestJson('/api/endfield/skland/operators/char1'), /尚未提供云端接口/)
})

test('system update cloud allowlist accepts only the three exact method/path pairs', async t => {
  configureHttpClient({ mode: 'cloud' }); t.after(() => configureHttpClient({ mode: 'local' }))
  const calls = []
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, options }); return json(path === '/api/identity/csrf' ? { csrf_token: 'csrf-update' } : { ok: true })
  })
  await requestJson('/api/system/update')
  await requestJson('/api/system/update/check', { method: 'POST', body: {} })
  await requestJson('/api/system/update/apply', { method: 'POST', body: { expected_sha: 'old', target_sha: 'new' } })
  const accepted = calls.length
  for (const [path, method] of [
    ['/api/system/update', 'POST'], ['/api/system/update/check', 'GET'], ['/api/system/update/apply', 'DELETE'],
    ['/api/system/update/', 'GET'], ['/api/system/update?other=1', 'GET'], ['/api/system/update/apply/extra', 'POST'],
    ['/api/system/update/apply?target=other', 'POST'], ['/api/system/anything', 'GET'],
  ]) await assert.rejects(requestJson(path, { method }), /尚未提供云端接口/)
  assert.equal(calls.length, accepted, 'unsupported update paths must not reach the network')
})
