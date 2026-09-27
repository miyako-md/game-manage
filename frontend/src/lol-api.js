// All requests remain on the local service; server error bodies may contain LCU input.
async function request(path, { signal, method = 'GET', timeout = 30000 } = {}) {
  const controller = new AbortController()
  const cancel = () => controller.abort()
  if (signal?.aborted) cancel()
  else signal?.addEventListener('abort', cancel, { once: true })
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeout)
  try {
    const response = await fetch(`/api/lol/${path}`, {
      method, signal: controller.signal, cache: 'no-store', referrerPolicy: 'no-referrer',
      ...(method === 'POST' ? { headers: { 'X-Game-Assistant': '1' } } : {}),
    })
    if (!response.ok) throw new Error({
      404: '本机尚未保存这场对局的详情',
      409: '客户端账号已变化，请重新采集',
      422: '筛选参数无效，请重新选择',
      503: '无法连接英雄联盟客户端，请启动并登录客户端后再采集',
    }[response.status] || '本地数据读取失败，请稍后重试')
    return await response.json()
  } catch (error) {
    if (timedOut) throw new Error('请求超时，请稍后重试；本机已有归档仍保留')
    if (error?.name === 'AbortError') throw error
    if (error instanceof TypeError || error instanceof SyntaxError) throw new Error('本地服务暂时不可用，请稍后重试')
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}

export function getLolAnalysis({ days = 90, queue = '', signal } = {}) {
  const params = new URLSearchParams({ days: String(days) })
  if (queue !== '' && queue != null) params.set('queue_id', String(queue))
  return request(`analysis?${params}`, { signal })
}
export const collectLol = ({ signal } = {}) => request('collect', { signal, method: 'POST', timeout: 120000 })
export const getLolMatch = (id, { signal } = {}) => request(`matches/${encodeURIComponent(id)}`, { signal })
