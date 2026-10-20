import { requestJson, requestResponse } from './http-client.js'
async function j(resp) {
  if (!resp.ok) throw new Error(`${resp.status}`)
  return resp.json()
}

export const getGames = () => requestResponse('/api/games').then(j)
export const getStatus = () => requestResponse('/api/status').then(j)
export const getSnapshot = (gameId, cap, { signal } = {}) =>
  requestJson(`/api/games/${gameId}/snapshot/${cap}`, { timeoutMs: 20000, signal, readResponse: j })
export const refreshGame = (gameId) =>
  requestResponse(`/api/games/${gameId}/refresh`, { method: 'POST', headers: { 'X-Game-Assistant': '1' } }).then(j)
// 对局详情按需实时拉取：成功 {payload}，失败 {error}（200）
export const getMatchDetail = (gameId, matchId) =>
  requestResponse(`/api/games/${gameId}/match/${matchId}/detail`).then(j)
