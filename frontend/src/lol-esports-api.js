async function request(refresh, { signal } = {}) {
  const controller = new AbortController(), cancel = () => controller.abort()
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; cancel() }, refresh ? 135000 : 30000)
  try {
    const response = await fetch(refresh ? '/api/lol/esports/refresh' : '/api/games/league_of_legends/snapshot/esports', {
      method: refresh ? 'POST' : 'GET', signal: controller.signal, cache: 'no-store', referrerPolicy: 'no-referrer',
      ...(refresh ? { headers: { 'X-Game-Assistant': '1' } } : {}),
    })
    if (response.status === 429) throw new Error(`更新冷却中，请在 ${Number(response.headers.get('Retry-After')) || 60} 秒后重试`)
    if (!response.ok) throw new Error('赛事服务暂不可用，已有缓存仍保留')
    const value = await response.json(), snapshot = refresh ? value.snapshot : value
    if (snapshot?.payload?.schema_version !== 1) throw new Error('赛事数据版本不兼容，请更新服务')
    return value
  } catch (error) {
    if (timedOut) throw new Error('赛事请求超时，已有缓存仍保留')
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('本地赛事服务暂不可用')
    throw error
  } finally { clearTimeout(timer); signal?.removeEventListener('abort', cancel) }
}
export const getLolEsports = (options = {}) => request(false, options)
export const refreshLolEsports = (options = {}) => request(true, options)
