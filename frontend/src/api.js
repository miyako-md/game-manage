async function j(resp) {
  if (!resp.ok) throw new Error(`${resp.status}`)
  return resp.json()
}

export const getGames = () => fetch('/api/games').then(j)
export const getStatus = () => fetch('/api/status').then(j)
export const getSnapshot = (gameId, cap) =>
  fetch(`/api/games/${gameId}/snapshot/${cap}`).then(j)
export const refreshGame = (gameId) =>
  fetch(`/api/games/${gameId}/refresh`, { method: 'POST' }).then(j)
// 对局详情按需实时拉取：成功 {payload}，失败 {error}（200）
export const getMatchDetail = (gameId, matchId) =>
  fetch(`/api/games/${gameId}/match/${matchId}/detail`).then(j)
