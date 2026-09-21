async function request(path, body) {
  const response = await fetch(`/api/nte/gacha/${path}`, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Game-Assistant': '1' }, body: JSON.stringify(body),
  })
  let result
  try { result = await response.json() } catch { throw new Error('抽卡账本服务返回异常，请稍后重试') }
  if (!response.ok) throw new Error(typeof result?.detail === 'string' ? result.detail : '账本请求失败，请检查导入文件或当前账号')
  return result
}
export const getLedgerSummary = () => request('summary')
export const getLedgerRecords = (pool = '', offset = 0) => request(`records?${new URLSearchParams({ pool_id: pool, offset, limit: 100 })}`)
export const previewLedger = body => request('preview', body)
export const importLedger = body => request('import', body)
export const getLedgerRules = () => request('rules')
export const saveLedgerRule = body => request('rules', body)
export const exportLedger = (pool = '', offset = null, limit = 2000) => request(`export?${new URLSearchParams({ pool_id: pool, ...(offset == null ? {} : { offset, limit }) })}`)

export function pityLabel(pity = {}) {
  if (pity.status === 'exact' && Number.isInteger(pity.count)) return `${pity.count} 抽`
  if (pity.status === 'lower_bound' && Number.isInteger(pity.count)) return `至少 ${pity.count} 抽`
  return '未知'
}
export function ledgerDate(value) {
  if (value === null || value === undefined || value === '') return '未提供'
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)) return value
  const time = typeof value === 'number' ? value * (value < 1e12 ? 1000 : 1) : value
  const date = new Date(time)
  return Number.isNaN(date.getTime()) ? '未提供' : new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(date)
}
export const poolLabel = value => ({ Lottery_Permanent: '常驻棋盘', Lottery_LimitedCharacter: '限定角色棋盘', Arc_MiracleBox: '弧盘研募', Gashapon_MysteryBox: '神秘盲盒' })[value] || value
export const requirementLabel = value => ({
  import_pull_history: '请先导入真实逐抽记录', identity_confirmation: '请核对文件所属角色', latest_and_continuity_confirmation: '尚未确认最新记录和连续范围',
  latest_records_confirmation: '尚未确认记录覆盖最新一抽', continuous_records_confirmation: '尚未确认记录连续无缺页', resolve_source_gaps: '文件存在缺页或解码警告，请补全原始记录',
  rotation_and_reset_rules: '盲盒仍缺每期身份及重置规则', resolve_record_order: '同时间记录序号不完整，请补全记录顺序', identify_pull_reward_semantics: '部分奖励的计数类型无法确认',
  hard_pity_rule: '尚未设置并核对该池的保底规则', rule_record_conflict: '记录与所设保底规则冲突，请核对', user_confirmed: '按你确认的连续范围计算', unconfirmed: '数据覆盖范围尚未确认',
  known_records_missing_from_segment: '已保存记录不在此次确认范围内，请补齐连续范围',
  SKIPPED_RECORDS: '导出时有记录被跳过', SOURCE_WARNING: '导出器报告了数据警告', ORDINAL_GAP: '同时间记录顺序存在缺口', DID_NOT_START_AT_PAGE_1: '未从历史第 1 页开始采集',
  ARCHIVE_SEGMENTED: '这是分段归档，恢复流水后仍需原始连续记录证明垫抽范围',
})[value] || value
export const resultLabel = value => ({ dice: '计数投掷', single_pull: '单次抽取', points_gift: '集点赠礼', sleeping_land: '沉眠地奖励', chase_reward: '额外奖励' })[value] || value || '类型未提供'
