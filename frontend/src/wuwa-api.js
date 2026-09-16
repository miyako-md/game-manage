import { onBeforeUnmount, watch } from 'vue'

export async function wuwaRequest(path, { signal, body } = {}) {
  const response = await fetch(`/api/wuwa/${path}`, {
    signal,
    cache: 'no-store',
    referrerPolicy: 'no-referrer',
    ...(body === undefined
      ? {}
      : {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Game-Assistant': '1',
          },
          body: JSON.stringify(body),
        }),
  })
  // Never reflect response bodies: import errors may contain sensitive source input.
  if (!response.ok)
    throw new Error(
      {
        401: '请重新登录鸣潮账号',
        409: '账号会话已变化，请重试',
        404: '当前账号没有这项数据',
        422: '导入或查询参数无效，请检查账号及文件格式',
        502: '来源暂时不可用，请稍后重试',
      }[response.status] || '请求失败，请稍后重试',
    )
  return response.json()
}

// Abort saves work; generation and payload identity checks also protect against
// transports which resolve after cancellation and against overlapping clicks.
export function useWuwaRequest(accountKey, reset = () => {}) {
  let generation = 0,
    controller
  function cancel() {
    generation++
    controller?.abort()
  }
  watch(
    accountKey,
    () => {
      cancel()
      reset()
    },
    { flush: 'sync' },
  )
  onBeforeUnmount(cancel)
  return {
    cancel,
    async run(path, body) {
      cancel()
      const version = generation,
        identity = accountKey()
      controller = new AbortController()
      try {
        const result = await wuwaRequest(path, {
          signal: controller.signal,
          body,
        })
        if (version !== generation || identity !== accountKey()) return null
        const owner = result?.payload || result
        if (
          owner?.role_id != null &&
          `${owner.role_id}:${owner.server_id}` !== identity
        )
          throw new Error('账号会话已变化，请刷新数据')
        return result
      } catch (error) {
        if (version !== generation || error?.name === 'AbortError') return null
        throw error
      }
    },
  }
}
