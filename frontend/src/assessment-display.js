// Display rules shared by the assessment block and the per-echo badges. A default score is
// unofficial: every place that shows one names it so, with where its weights come from.
// WuWa echo grades c…sss; NTE drive/cartridge grades d…ace.
const GRADES = new Set(['c', 'b', 'a', 's', 'ss', 'sss', 'd', 'ace'])
export const gradeLabel = grade => typeof grade === 'string' && GRADES.has(grade.toLowerCase()) ? grade.toUpperCase() : ''
export const isDefaultScore = score => score?.origin === 'builtin_default'
export const attributionLabel = score => !isDefaultScore(score) ? ''
  : score.attribution === 'xwuid_snapshot' ? '权重来自 XWUID（XutheringWavesUID）'
  // The 异环工坊 endpoint asks every page showing its weights to credit it in these words.
  : score.attribution === 'nte_workshop' ? '权重配置来自：异环工坊' : ''
// No saved model and no default weights for the character: the backend's empty placeholder.
export const isNoDefault = score => score?.status === 'unconfigured' && score?.model_version === 'unconfigured'

/** The score as one header line: the total once the whole set is scored, and whose weights.
 * A default is always named unofficial with its weight source. */
export function scoreLine(score) {
  const grade = gradeLabel(score?.grade)
  const total = score?.status !== 'scored' || score.value == null ? ''
    : score.max_value != null ? `总分 ${score.value} / ${score.max_value}${grade ? ' · ' + grade : ''}` : `评分 ${score.value}`
  const source = isDefaultScore(score) ? `非官方 · ${attributionLabel(score) || '默认评分'}` : score?.origin === 'user_configured' ? '个人权重' : ''
  return { total, source }
}

/** Scored echo-formula items (default or personal) by the echo they belong to. Equipped items are named
 * `echo:<position in the source list>:<source id>`; an unscorable item, or one whose
 * source id differs from the echo at that position, gets no badge. */
export function echoBadges(assessment, echoes) {
  const badges = new Map()
  if (!Array.isArray(echoes) || !Array.isArray(assessment?.item_results)) return badges
  for (const item of assessment.item_results) {
    const [, index, source] = /^echo:(\d+):(.*)$/.exec(String(item?.item_id ?? '')) || []
    const echo = index == null ? null : echoes[Number(index)]
    if (!echo || typeof echo !== 'object' || item.status !== 'scored' || item.value == null || item.max_value == null) continue
    const id = echo.phantom_prop?.phantom_id
    if (source && source !== 'unknown' && id != null && String(id) !== source) continue
    badges.set(echo, { value: String(item.value), grade: gradeLabel(item.grade) })
  }
  return badges
}

/** Scored NTE items by the piece they belong to. Equipped items are named
 * `<core|pie>:<position in the source list>:<source id>`; an unscorable item, or one whose
 * source id differs from the piece at that position, gets no badge. */
export function nteBadges(assessment, suit) {
  const badges = new Map()
  if (!suit || typeof suit !== 'object' || !Array.isArray(assessment?.item_results)) return badges
  for (const item of assessment.item_results) {
    const [, group, index, source] = /^(core|pie):(\d+):(.*)$/.exec(String(item?.item_id ?? '')) || []
    const piece = group == null || !Array.isArray(suit[group]) ? null : suit[group][Number(index)]
    if (!piece || typeof piece !== 'object' || item.status !== 'scored' || item.value == null || item.max_value == null) continue
    if (source && source !== 'unknown' && piece.id != null && String(piece.id) !== source) continue
    badges.set(piece, { value: String(item.value), max: String(item.max_value), grade: gradeLabel(item.grade) })
  }
  return badges
}
