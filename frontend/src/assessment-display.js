// Display rules shared by the assessment block and the per-echo badges. A default score is
// unofficial: every place that shows one names it so, with where its weights come from.
const GRADES = new Set(['c', 'b', 'a', 's', 'ss', 'sss'])
export const gradeLabel = grade => typeof grade === 'string' && GRADES.has(grade.toLowerCase()) ? grade.toUpperCase() : ''
export const isDefaultScore = score => score?.origin === 'builtin_default'
export const attributionLabel = score => !isDefaultScore(score) ? ''
  : score.attribution === 'gpl_snapshot' ? '权重改编自 WutheringWavesUID（GPL-3.0）'
  : score.attribution === 'self_made' ? '自制权重' : ''

/** Scored default items by the echo they belong to. Equipped items are named
 * `echo:<position in the source list>:<source id>`; an unscorable item, or one whose
 * source id differs from the echo at that position, gets no badge. */
export function echoBadges(assessment, echoes) {
  const badges = new Map()
  if (!isDefaultScore(assessment) || !Array.isArray(echoes) || !Array.isArray(assessment.item_results)) return badges
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
