// Display rules shared by the assessment block and the per-echo badges. A default score is
// unofficial: every place that shows one names it so, with where its weights come from.
// WuWa echo grades c…sss; NTE drive/cartridge grades d…ace.
const GRADES = new Set(['c', 'b', 'a', 's', 'ss', 'sss', 'd', 'ace'])
export const gradeLabel = grade => typeof grade === 'string' && GRADES.has(grade.toLowerCase()) ? grade.toUpperCase() : ''
// One colour ladder for both games' grades (WuWa C…SSS, NTE D…ACE): 0 lowest … 7 highest.
const TIERS = { d: 0, c: 1, b: 2, a: 3, s: 4, ss: 5, sss: 6, ace: 7 }
export const gradeTier = grade => typeof grade === 'string' ? TIERS[grade.toLowerCase()] ?? null : null
export const isDefaultScore = score => score?.origin === 'builtin_default'
export const attributionLabel = score => !isDefaultScore(score) ? ''
  : score.attribution === 'gpl_snapshot' ? '权重改编自 WutheringWavesUID（GPL-3.0）'
  : score.attribution === 'self_made' ? '自制权重'
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
 * source id differs from the echo at that position, is left out. */
function echoItems(assessment, echoes) {
  const items = new Map()
  if (!Array.isArray(echoes) || !Array.isArray(assessment?.item_results)) return items
  for (const item of assessment.item_results) {
    const [, index, source] = /^echo:(\d+):(.*)$/.exec(String(item?.item_id ?? '')) || []
    const echo = index == null ? null : echoes[Number(index)]
    if (!echo || typeof echo !== 'object' || item.status !== 'scored' || item.value == null || item.max_value == null) continue
    const id = echo.phantom_prop?.phantom_id
    if (source && source !== 'unknown' && id != null && String(id) !== source) continue
    items.set(echo, item)
  }
  return items
}

/** The badge of each scored echo. */
export function echoBadges(assessment, echoes) {
  return new Map([...echoItems(assessment, echoes)].map(([echo, item]) => [echo, { value: String(item.value), grade: gradeLabel(item.grade) }]))
}

/** Effective flags of each scored echo's stat rows: `main_props:<row>` / `sub_props:<row>` → true/false.
 * Rows of an unscored echo, or without a flag, stay unknown (no colour either way). */
export function echoStatFlags(assessment, echoes) {
  return new Map([...echoItems(assessment, echoes)].map(([echo, item]) => [echo,
    new Map((Array.isArray(item.contributions) ? item.contributions : [])
      .filter(c => typeof c?.observation_id === 'string' && typeof c.effective === 'boolean').map(c => [c.observation_id, c.effective]))]))
}

/** Scored NTE items by the piece they belong to. Equipped items are named
 * `<core|pie>:<position in the source list>:<source id>`; an unscorable item, or one whose
 * source id differs from the piece at that position, is left out. */
function nteItems(assessment, suit) {
  const items = new Map()
  if (!suit || typeof suit !== 'object' || !Array.isArray(assessment?.item_results)) return items
  for (const item of assessment.item_results) {
    const [, group, index, source] = /^(core|pie):(\d+):(.*)$/.exec(String(item?.item_id ?? '')) || []
    const piece = group == null || !Array.isArray(suit[group]) ? null : suit[group][Number(index)]
    if (!piece || typeof piece !== 'object' || item.status !== 'scored' || item.value == null || item.max_value == null) continue
    if (source && source !== 'unknown' && piece.id != null && String(piece.id) !== source) continue
    items.set(piece, item)
  }
  return items
}

/** The badge of each scored NTE piece. */
export function nteBadges(assessment, suit) {
  return new Map([...nteItems(assessment, suit)].map(([piece, item]) => [piece, { value: String(item.value), max: String(item.max_value), grade: gradeLabel(item.grade) }]))
}

/** Effective flags of each scored piece's stats: `main:<stat id>` / `sub:<stat id>` (lower case) → true/false. */
export function nteStatFlags(assessment, suit) {
  return new Map([...nteItems(assessment, suit)].map(([piece, item]) => [piece,
    new Map((Array.isArray(item.contributions) ? item.contributions : [])
      .filter(c => typeof c?.contribution_id === 'string' && typeof c.effective === 'boolean').map(c => [c.contribution_id, c.effective]))]))
}

/** A stat row's colour class from its flag: effective, ineffective, or none while unknown. */
export const statTone = flag => flag === true ? 'stat-effective' : flag === false ? 'stat-ineffective' : undefined

/** The score card of a role image: the grade and total once the set is scored, else what is known.
 * kind: scored | partial | none (no default weights) | unscorable | absent (no assessment at all). */
export function scoreHero(score) {
  if (!score || typeof score !== 'object') return { kind: 'absent' }
  const { source } = scoreLine(score)
  if (score.status === 'scored' && score.value != null)
    return { kind: 'scored', grade: gradeLabel(score.grade), value: String(score.value), max: score.max_value == null ? '' : String(score.max_value), source }
  if (isNoDefault(score)) return { kind: 'none', source }
  const scored = Array.isArray(score.item_results) ? score.item_results.filter(i => i?.status === 'scored').length : 0
  if (score.partial && score.partial_known_total != null) return { kind: 'partial', value: String(score.partial_known_total), count: scored, source }
  return { kind: 'unscorable', source }
}
