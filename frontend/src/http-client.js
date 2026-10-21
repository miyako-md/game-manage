// Explicit deployment mode; never infer cloud mode from API failure or hostname.
let mode = import.meta.env?.VITE_SERVICE_MODE === 'cloud' || globalThis.document?.documentElement?.dataset.serviceMode === 'cloud' ? 'cloud' : 'local'
let epoch = 0, scopeEpoch = 0, csrf = '', csrfPending = null, scope = null
const controllers = new Map(), invalidationListeners = new Set()   // controller -> bound to the active account scope
const registrationErrorCodes = new Set(['invalid_username','invalid_password','invalid_invite','registration_unavailable'])
const cancelled = () => new DOMException('会话或角色已变化', 'AbortError')
export const isCloudMode = () => mode === 'cloud'
export const getAccountScope = () => scope
// Server text is shown only when it is Chinese; machine codes (csrf_required, authorization_changed ...) get the caller's fixed text.
export const safeDetail = (detail, fallback) => typeof detail === 'string' && /[\u4e00-\u9fff]/.test(detail) ? detail.slice(0, 256) : fallback
function invalidateRequests() { epoch++; for (const controller of controllers.keys()) controller.abort(cancelled()); controllers.clear() }
// An account or role switch ends only the reads routed under that scope; session-level reads do not depend on it.
function invalidateScope() { scopeEpoch++; for (const [controller, bound] of controllers) if (bound) { controller.abort(cancelled()); controllers.delete(controller) } }
export function invalidateSession() {
  invalidateRequests(); csrf = ''; csrfPending = null; scope = null
  for (const listener of invalidationListeners) listener()
}
export function subscribeSessionInvalidation(listener) { invalidationListeners.add(listener); return () => invalidationListeners.delete(listener) }
export function configureHttpClient({ mode: next = 'local' } = {}) { invalidateSession(); mode = next }
export function setAccountScope(next) {
  if (JSON.stringify(next) !== JSON.stringify(scope)) invalidateScope()
  scope = next ? structuredClone(next) : null
}
export class HttpError extends Error {
  constructor(status, code = '', retryAfter = 0) {
    super(({401:'网站会话已失效，请重新登录',403:'操作验证失效，请刷新页面',404:'当前授权没有这项数据',409:'账号状态已变化，请重试',429:'请求过于频繁，请稍后重试',422:'参数无效，请检查输入',503:'来源暂时不可用，保留已有数据'})[status] || '请求失败，请稍后重试')
    this.name = 'HttpError'; this.status = status; this.code = code; this.retryAfter = retryAfter
    if (status === 401 && code === 'auth_expired') this.message = '游戏授权不可用，请到「账号与授权」重新登录'
  }
}
// Drops the cached token without a request; the next write fetches a fresh one.
export function clearCsrf() { csrf = ''; csrfPending = null }
export async function obtainCsrf(force = false) {
  if (force) clearCsrf()
  if (csrf) return csrf
  if (!csrfPending) {
    const current = epoch
    const promise = requestJson('/api/identity/csrf').then(data => {
      if (current !== epoch) throw cancelled()
      if (typeof data?.csrf_token !== 'string' || !data.csrf_token) throw new Error('网站验证响应异常')
      return (csrf = data.csrf_token)
    }).finally(() => { if (csrfPending === promise) csrfPending = null })
    csrfPending = promise
  }
  return csrfPending
}
function cloudPath(path, method) {
  if ((method === 'GET' && path === '/api/system/update') || (method === 'POST' && ['/api/system/update/check', '/api/system/update/apply'].includes(path))) return path
  if (['GET','PUT'].includes(method) && /^\/api\/admin\/qq\/groups\/[^/?]+\/settings$/.test(path)) return path
  if (/^\/api\/(identity(?:\/|$)|accounts(?:\/|$)|qq(?:\/|$)|public\/games\/)/.test(path)) return path
  if (/^\/api\/admin\/bilibili-source\/login\/(?:status|sessions(?:\/[^/?]+(?:\/(?:qr\/poll|commit|cookie))?)?)$/.test(path)) return path
  if (/^\/api\/admin\/bilibili-source\/(?:status|(?:wuthering_waves|nte|endfield|league_of_legends)\/refresh)$/.test(path)) return path
  if (['GET','POST'].includes(method) && path === '/api/admin/collect') return path
  if (method === 'GET' && /^\/api\/public\/(?:nte\/guides(?:\/sources\/[^/?]+)?|wuwa\/guides\/(?:updates|tower)|endfield\/(?:public|map(?:\/marks\/[^/?]+)?))(?:\?.*)?$/.test(path)) return path
  if (method === 'POST' && /^\/api\/admin\/(?:nte\/guides\/sources\/[^/?]+\/refresh|wuwa\/guides\/(?:updates(?:\/extract)?|tower\/check)|endfield\/public\/refresh)$/.test(path)) return path
  const pathname = path.split('?')[0]
  const publicRead = /^\/api\/(?:nte\/guides(?:\/sources\/[^/?]+)?|wuwa\/guides\/(?:updates|tower)|endfield\/(?:public|map(?:\/marks\/[^/?]+)?))$/
  const publicWrite = /^\/api\/(?:nte\/guides\/sources\/[^/?]+\/refresh|wuwa\/guides\/(?:updates(?:\/extract)?|tower\/check)|endfield\/public\/refresh)$/
  if (method === 'GET' && publicRead.test(pathname)) return '/api/public/' + path.slice(5)
  if (method === 'POST' && path === pathname && publicWrite.test(pathname)) return '/api/admin/' + path.slice(5)
  if (scope) {
    const ownedRead = {
      kuro: /^\/api\/wuwa\/(?:history|gacha(?:\/export)?|roles\/[^/?]+|resources\/(?:week|month|version)\/[^/?]+)$/,
      tajiduo: /^\/api\/nte\/gacha\/(?:summary|records|export|rules)$/,
      hypergryph: /^\/api\/endfield\/gacha\/(?:summary|records|export)$/,
      skland: /^\/api\/endfield\/(?:blueprints(?:\/export)?|skland\/(?:card|attendance|operators\/[^/?]+|challenges|tools))$/,
    }
    const ownedWrite = {
      kuro: method === 'POST' && ['/api/wuwa/gacha/preview','/api/wuwa/gacha/import','/api/wuwa/gacha/rules','/api/wuwa/history/backfill'].includes(pathname),
      tajiduo: method === 'POST' && /^\/api\/nte\/gacha\/(?:preview|import|rules)$/.test(pathname),
      skland: (method === 'POST' && pathname === '/api/endfield/blueprints') ||
        (['PUT','DELETE'].includes(method) && /^\/api\/endfield\/blueprints\/(?!export$)[^/?]+$/.test(pathname)),
    }
    const provider = pathname.startsWith('/api/endfield/gacha/') ? 'hypergryph'
      : /^\/api\/endfield\/(?:skland\/|blueprints(?:\/|$))/.test(pathname) ? 'skland' : scope.provider
    const target = scope.sources ? scope.sources[provider] : scope.provider === provider ? scope : null
    if (target?.provider === provider && target.account_id && target.role_id && ((method === 'GET' && ownedRead[provider]?.test(pathname)) || (path === pathname && ownedWrite[provider]))) {
      const prefix = `/api/accounts/${encodeURIComponent(target.account_id)}/roles/${encodeURIComponent(target.role_id)}`
      return prefix + path.slice(4)
    }
  }
  throw new Error('此功能尚未提供云端接口')
}
export class RequestTimeoutError extends Error {
  constructor() { super('读取超时，请重试；已有数据仍保留。'); this.name = 'RequestTimeoutError' }
}
export async function requestJson(path, options = {}) {
  const { response: returnResponse = false, body, timeoutMs = 0, readResponse, ...rest } = options
  if (!path.startsWith('/api/') || path.includes('..') || path.includes('\\')) throw new Error('无效的服务路径')
  const current = epoch, scopedCurrent = scopeEpoch, cloud = isCloudMode(), method = (rest.method || 'GET').toUpperCase()
  // Logout must finish after the UI synchronously drops the active scope. Its
  // response never carries private data and cannot restore cleared state.
  const logout = cloud && path === '/api/identity/logout' && method === 'POST'
  path = cloud ? cloudPath(path, method) : path
  const bound = cloud && !!scope && [scope, ...Object.values(scope.sources || {})].some(target =>
    target?.account_id && target?.role_id && path.startsWith(`/api/accounts/${encodeURIComponent(target.account_id)}/roles/${encodeURIComponent(target.role_id)}/`))
  const stale = () => current !== epoch || (bound && scopedCurrent !== scopeEpoch)
  const headers = { Accept: 'application/json', ...rest.headers }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    if (cloud) headers['X-CSRF-Token'] = await obtainCsrf()
    else headers['X-Game-Assistant'] = '1'
  }
  if (!logout && stale()) throw cancelled()
  if (body !== undefined) headers['Content-Type'] ??= 'application/json'
  const controller = new AbortController(); if (!logout) controllers.set(controller, bound)
  const signal = rest.signal ? AbortSignal.any([controller.signal, rest.signal]) : controller.signal
  let deadline
  const timeout = Number.isFinite(timeoutMs) && timeoutMs > 0 ? new Promise((_resolve, reject) => {
    deadline = setTimeout(() => {
      const error = new RequestTimeoutError()
      controller.abort(error); reject(error)
    }, timeoutMs)
  }) : null
  let abortRead
  const aborted = readResponse ? new Promise((_resolve, reject) => {
    abortRead = () => reject(signal.reason || cancelled())
    if (signal.aborted) abortRead()
    else signal.addEventListener('abort', abortRead, { once: true })
  }) : null
  const bounded = promise => timeout || aborted ? Promise.race([promise, ...[timeout, aborted].filter(Boolean)]) : promise
  try {
    let result
    try {
      result = await bounded(fetch(path, { ...rest, method, headers, credentials: 'same-origin', cache: 'no-store', referrerPolicy: 'no-referrer', signal,
        ...(body === undefined ? {} : { body: typeof body === 'string' ? body : JSON.stringify(body) }) }))
    } catch (error) {
      // An unreachable service rejects with an English TypeError ("Failed to fetch").
      // Keep the type: wrappers with their own wording still recognise it.
      throw error instanceof TypeError ? new TypeError('无法连接服务，请稍后重试') : error
    }
    if (!logout && stale()) throw cancelled()
    if (cloud && result.status === 401) {
      // An expired game authorization also answers 401 (Skland passport: error_code auth_expired; Wuwa detail reads:
      // detail private_query_failed). Only a website-session 401 ends the site session, and so does any 401 that is
      // unreadable or not recognised.
      let denial = null
      try { denial = await bounded(result.clone().json()) } catch(error) { if(error instanceof RequestTimeoutError) throw error /* unreadable: treated as a website-session 401 */ }
      if (!logout && stale()) throw cancelled()
      if (denial?.error_code !== 'auth_expired' && denial?.detail !== 'private_query_failed') { invalidateSession(); throw new HttpError(401) }
    }
    // A caller-owned reader keeps legacy status/JSON errors while the transport
    // owns its deadline and cancellation until the response body has been read.
    if (readResponse) {
      const data = await bounded(readResponse(result))
      if (!logout && stale()) throw cancelled()
      return data
    }
    // Legacy wrappers retain their existing error/response validation, while all
    // transports share the same headers, route boundary and invalidation engine.
    if (returnResponse) {
      if (cloud) {
        const read = result.json.bind(result)
        result.json = async () => { const data = await read(); if (stale()) throw cancelled(); return data }
      }
      return result
    }
    const data = await bounded(result.json().catch(() => null))
    if (!logout && stale()) throw cancelled()
    if (!result.ok) {
      // Identity errors use detail; only fixed registration codes may cross
      // this boundary. Arbitrary backend detail never becomes display text.
      const code = path === '/api/identity/register' && result.status === 400 && registrationErrorCodes.has(data?.detail)
        ? data.detail : typeof data?.error_code === 'string' ? data.error_code : ''
      throw new HttpError(result.status, code, Number(result.headers?.get('Retry-After')) || 0)
    }
    if (data === null && result.status !== 204) throw new Error('服务响应异常，请稍后重试')
    return data
  } finally { clearTimeout(deadline); controllers.delete(controller); if (abortRead) signal.removeEventListener('abort', abortRead) }
}
export const requestResponse = (path, options = {}) => requestJson(path, { ...options, response: true })
