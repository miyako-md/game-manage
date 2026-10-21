import { reactive } from 'vue'
import { requestJson, subscribeSessionInvalidation } from './http-client.js'

// Administrator "collect and backfill": one POST, then progress from GET /api/admin/collect.
const PATH = '/api/admin/collect'
const NAMES = { wuthering_waves: '鸣潮', nte: '异环', endfield: '终末地', league_of_legends: '英雄联盟' }
export const COLLECT_LABELS = { queued: '已排队', running: '采集中', done: '已完成', failed: '部分来源失败，已保留已有数据', backoff: '已完成，B站处于失败退避期，本次跳过' }
export const COLLECT_POLL_MS = 2500
export const COLLECT_LIMIT_MS = 5 * 60 * 1000
const TERMINAL = new Set(['done', 'failed', 'backoff'])

// A game is finished once a public job completed after the receipt was issued (a merged job counts).
export function collectProgress(receipt, row) {
  if (row && row.generation > receipt.generation && row.outcome) {
    if (row.outcome.state === 'failed') return 'failed'
    return row.outcome.bilibili === 'backoff' ? 'backoff' : 'done'
  }
  return row?.queue_state === 'running' ? 'running' : 'queued'
}

const wait = seconds => seconds > 60 ? `${Math.ceil(seconds / 60)} 分钟` : `${seconds} 秒`

export function createCollectController({ onDone } = {}) {
  const state = reactive({ busy: false, games: [], privateRequested: null, message: '', error: '' })
  let run = 0, timer, controller = new AbortController(), receipts = [], deadline = 0, failures = 0
  const reset = () => { run++; clearTimeout(timer); controller.abort(); controller = new AbortController() }
  const unsubscribe = subscribeSessionInvalidation(() => { reset(); Object.assign(state, { busy: false, games: [], privateRequested: null, message: '', error: '' }) })
  const stop = message => { state.busy = false; state.message = message }

  async function poll(current) {
    if (current !== run) return
    try {
      const status = await requestJson(PATH, { signal: controller.signal })
      if (current !== run) return
      const rows = new Map((Array.isArray(status?.games) ? status.games : []).map(row => [row.game_id, row]))
      state.games = receipts.map(receipt => ({ game_id: receipt.game_id, name: NAMES[receipt.game_id] || receipt.game_id, progress: collectProgress(receipt, rows.get(receipt.game_id)) }))
      failures = 0
      if (state.games.every(game => TERMINAL.has(game.progress))) {
        stop(state.games.some(game => game.progress === 'failed') ? '采集结束：部分来源失败，已保留已有数据；总览已重新读取。' : '采集完成，总览已重新读取。')
        onDone?.()
        return
      }
    } catch (error) {
      if (current !== run || error.name === 'AbortError') return
      if (++failures >= 3) return stop('暂时无法读取采集进度，任务仍在后台进行，可稍后点「刷新数据」查看。')
    }
    if (Date.now() >= deadline) return stop('仍在后台进行，可稍后点「刷新数据」查看。')
    timer = setTimeout(() => poll(current), COLLECT_POLL_MS)
  }

  async function start() {
    if (state.busy) return
    reset()
    const current = run
    Object.assign(state, { busy: true, games: [], privateRequested: null, message: '', error: '' })
    try {
      const result = await requestJson(PATH, { method: 'POST', body: { backfill: true }, signal: controller.signal })
      if (current !== run) return
      if (!Array.isArray(result?.games)) throw new Error('采集响应异常')
      receipts = result.games.filter(game => typeof game?.game_id === 'string' && Number.isInteger(game.generation))
      state.games = receipts.map(receipt => ({ game_id: receipt.game_id, name: NAMES[receipt.game_id] || receipt.game_id, progress: 'queued' }))
      const requested = result.private_refresh?.requested
      state.privateRequested = Number.isInteger(requested) ? requested : null
      deadline = Date.now() + COLLECT_LIMIT_MS; failures = 0
      timer = setTimeout(() => poll(current), COLLECT_POLL_MS)
    } catch (error) {
      if (current !== run || error.name === 'AbortError') return
      state.busy = false
      state.error = error.status === 429 ? `刚刚已经采集过，请${error.retryAfter ? ` ${wait(error.retryAfter)}` : '稍'}后再试。`
        : error.status === 503 ? '后台采集暂不可用，请稍后重试。' : '无法提交采集任务，请稍后重试。'
    }
  }

  function dispose() { reset(); unsubscribe() }
  return { state, start, dispose }
}
