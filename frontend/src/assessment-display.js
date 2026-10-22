// Display rules shared by the assessment block and the per-echo badges. A default score is
// unofficial: every place that shows one names it so, with where its weights come from.
const GRADES = new Set(['c', 'b', 'a', 's', 'ss', 'sss'])
export const gradeLabel = grade => typeof grade === 'string' && GRADES.has(grade.toLowerCase()) ? grade.toUpperCase() : ''
export const isDefaultScore = score => score?.origin === 'builtin_default'
export const attributionLabel = score => !isDefaultScore(score) ? ''
  : score.attribution === 'gpl_snapshot' ? '权重改编自 WutheringWavesUID（GPL-3.0）'
  : score.attribution === 'self_made' ? '自制权重' : ''
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
