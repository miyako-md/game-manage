async function request(path = '', { refresh = false, signal } = {}) {
  let response
  try {
    response = await fetch(`/api/nte/guides${path}`, { signal, ...(refresh ? { method:'POST', headers:{ 'X-Game-Assistant':'1' } } : {}) })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw Error('攻略服务暂时无法连接，请稍后重试。')
  }
  let data
  try { data = await response.json() } catch { throw Error('攻略服务返回异常，请稍后重试。') }
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : '原帖暂时无法读取。')
  return data
}
export const getGuideCatalog = signal => request('', { signal })
export const getGuideSource = (id, refresh = false, signal) => request(`/sources/${encodeURIComponent(id)}${refresh ? '/refresh' : ''}`, { refresh, signal })
export function safeGuideUrl(value, image = false) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value), allowed = image ? ['bbs-upload.tajiduo.com','webstatic.tajiduo.com'] : ['www.tajiduo.com']
    return url.protocol === 'https:' && allowed.includes(url.hostname) && !url.username && !url.password && (!url.port || url.port === '443') ? url.href : null
  } catch { return null }
}
