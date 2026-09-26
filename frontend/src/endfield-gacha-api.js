async function request(path) {
  const response = await fetch(`/api/endfield/gacha/${path}`)
  let result
  try { result = await response.json() } catch { throw new Error('寻访账本服务返回异常，请稍后重试') }
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '寻访账本请求失败，请稍后重试')
  return result
}
export const getRecords = (poolKey = '', offset = 0, limit = 50) => request(`records?${new URLSearchParams({ pool_key: poolKey, offset, limit })}`)
export const exportRecords = () => request('export')

export function pityText(pity) {
  if (!pity || !Number.isInteger(pity.count)) return '未知'
  return pity.status === 'exact' ? `${pity.count} 抽` : `≥${pity.count} 抽`
}
export function pullDate(value) {
  if (!Number.isFinite(value)) return '时间未提供'
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(new Date(value))
}
export const rarityLabel = value => Number.isInteger(value) ? `${value}★` : '稀有度未知'
