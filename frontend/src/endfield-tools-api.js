const base = '/api/endfield'

async function request(path, { method = 'GET', body, signal } = {}) {
  let response
  try {
    response = await fetch(`${base}${path}`, {
      method, signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      ...(method === 'GET' ? {} : { headers: { 'Content-Type': 'application/json', 'X-Game-Assistant': '1' } }),
    })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error('暂时无法连接服务，请稍后重试。')
  }
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const detail = data.detail || data.error
    throw new Error(typeof detail === 'string' ? detail : '请求未完成，请稍后重试。')
  }
  return data
}

export const getPublic = signal => request('/public', { signal })
export const refreshPublic = signal => request('/public/refresh', { method: 'POST', signal })
export const getMap = (filters = {}, signal) => {
  const query = new URLSearchParams()
  for (const key of ['map_id', 'level_id', 'type_id', 'q', 'offset', 'limit']) if (filters[key] !== undefined && filters[key] !== '') query.set(key, filters[key])
  return request(`/map${query.size ? `?${query}` : ''}`, { signal })
}
export const getMapMark = (mapId, markId, signal) => request(`/map/marks/${encodeURIComponent(markId)}?map_id=${encodeURIComponent(mapId)}`, { signal })
export const getSklandStatus = signal => request('/skland/status', { signal })
export const connectSkland = (cred, device_id) => request('/skland/connect', { method: 'POST', body: { cred, ...(device_id ? { device_id } : {}) } })
export const chooseSklandRole = (role_id, server_id) => request('/skland/role', { method: 'POST', body: { role_id, server_id } })
export const disconnectSkland = () => request('/skland/connection', { method: 'DELETE' })
export const getSklandCard = signal => request('/skland/card', { signal })
export const getSklandOperator = (id, signal) => request(`/skland/operators/${encodeURIComponent(id)}`, { signal })
export const getSklandTools = (kind, charId = '', signal) => request(`/skland/tools?kind=${encodeURIComponent(kind)}${charId ? `&char_id=${encodeURIComponent(charId)}` : ''}`, { signal })
export const refreshSklandCard = () => request('/skland/refresh', { method: 'POST' })
export const getAttendance = signal => request('/skland/attendance', { signal })
export const signAttendance = () => request('/skland/attendance', { method: 'POST' })
export const getChallenges = (kind, signal) => request(`/skland/challenges?kind=${encodeURIComponent(kind)}`, { signal })
export const getBlueprints = signal => request('/blueprints', { signal })
export const exportBlueprints = () => request('/blueprints/export')
export const saveBlueprint = item => request('/blueprints', { method: 'POST', body: item })
export const updateBlueprint = (id, item) => request(`/blueprints/${encodeURIComponent(id)}`, { method: 'PUT', body: item })
export const deleteBlueprint = id => request(`/blueprints/${encodeURIComponent(id)}`, { method: 'DELETE' })

export function safeExternalUrl(value) {
  if (typeof value !== 'string') return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password ? url.href : null
  } catch { return null }
}
