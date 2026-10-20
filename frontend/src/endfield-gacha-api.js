import { requestResponse, safeDetail } from './http-client.js'
async function request(path) {
  const response = await requestResponse(`/api/endfield/gacha/${path}`)
  let result
  try { result = await response.json() } catch { throw new Error('寻访账本服务返回异常，请稍后重试') }
  if (!response.ok) throw new Error(safeDetail(result.detail, '寻访账本请求失败，请稍后重试'))
  return result
}
export const getRecords = (poolKey = '', offset = 0, limit = 50, kind = '') => {
  const params = new URLSearchParams({ pool_key: poolKey, offset, limit })
  if (kind) params.set('kind', kind)
  return request(`records?${params}`)
}
export const exportRecords = () => request('export')

export function pityText(pity) {
  if (!pity || !Number.isInteger(pity.count)) return '未知'
  return pity.status === 'exact' ? `${pity.count} 抽` : `≥${pity.count} 抽`
}
const pullDateFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
})
export function pullDate(value) {
  if (!Number.isFinite(value)) return '时间未提供'
  return pullDateFormatter.format(new Date(value))
}
export const rarityLabel = value => Number.isInteger(value) ? `${value}★` : '稀有度未知'

const pullDayFormatter = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric' })
/** A pull's Beijing calendar day for compact cards, e.g. 10月16日. */
export function pullDay(value) {
  if (!Number.isFinite(value)) return '时间未提供'
  return pullDayFormatter.format(new Date(value))
}

/** The pity count split for a big numeral: `≥` marks a known minimum; the unit stays small. */
export function pityParts(pity) {
  if (!pity || !Number.isInteger(pity.count)) return null
  return { prefix: pity.status === 'exact' ? '' : '≥', count: pity.count, unit: '抽' }
}
