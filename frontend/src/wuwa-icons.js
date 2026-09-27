import icons from './wuwa-icon-catalog.js'

export function safeWuwaIcon(value) {
  if (typeof value !== 'string') return ''
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password && !url.hash && !url.search &&
      ['web-static.kurobbs.com', 'prod-alicdn-community.kurobbs.com'].includes(url.hostname) &&
      /\.(png|webp|jpe?g)$/i.test(url.pathname) ? value : ''
  } catch { return '' }
}

export const characterIcon = id => safeWuwaIcon(icons.characters[String(id)]?.icon)
export const namedIcon = (bucket, name) => safeWuwaIcon(icons[bucket]?.[name]?.icon)

const skillAliases = {
  固有技能: '固有技能', 共鸣回路: '共鸣回路', 回路: '共鸣回路',
  共鸣解放: '共鸣解放', 解放: '共鸣解放', 共鸣技能: '共鸣技能', 技能: '共鸣技能',
  变奏技能: '变奏技能', 变奏: '变奏技能', 常态攻击: '常态攻击', 常态: '常态攻击', 普攻: '常态攻击',
}
const aliases = {
  weapons: { 忌炎专武: '苍鳞千嶂' },
  teams: {
    气动漂泊者: '漂泊者·气动', 湮灭漂泊者: '漂泊者-女-湮灭', 衍射漂泊者: '漂泊者-女-衍射',
  },
  echo_sets: {
    '梦魇亚当·重锤': '共鸣回响·梦魇亚当·重锤', 芙露德莉斯: '共鸣回响·芙露德莉斯',
    碎梦: '碎梦亡鬼之魇', 剪心: '剪心辑梦之影', 冥雷: '彻空冥雷', 余音: '不绝余音',
    雪落: '雪落无声之愿', 失序: '失序彼岸之梦', 轻云: '轻云出月', 逆光: '逆光跃彩之约', 高天: '高天共奏之曲',
  },
  echo_stats: { 效率: '共鸣效率', 攻击百分比: '攻击', 固定攻击: '攻击', 防御百分比: '防御', 固定防御: '防御', 生命百分比: '生命', 固定生命: '生命', 暴伤: '暴击伤害', 治疗: '治疗效果加成' },
}

// Tokenize only for presentation: preserve every original character and connector.
// Never infer ranks, teams, stats or skill order from icon catalog order.
export function tokenizeGuide(text, sectionKey, characterId) {
  if (!text) return []
  const buckets = { weapons: ['weapons'], teams: ['roles'], echo_sets: ['sets', 'echoes'], echo_stats: ['stats'] }[sectionKey] || []
  const entries = Object.assign({}, ...buckets.map(b => icons[b]))
  const candidates = new Map(Object.entries(entries).map(([name, entity]) => [name, { ...entity, name }]))
  for (const [alias, name] of Object.entries(aliases[sectionKey] || {})) {
    if (entries[name]) candidates.set(alias, { ...entries[name], name })
  }
  if (sectionKey === 'skill_priority') {
    const skills = icons.characters[String(characterId)]?.skills || {}
    for (const [alias, type] of Object.entries(skillAliases)) {
      candidates.set(alias, { name: skills[type]?.name || type, icon: skills[type]?.icon, kind: 'skill' })
    }
  }
  const names = [...candidates.keys()].sort((a, b) => b.length - a.length)
  const tokens = []
  let at = 0, plain = ''
  while (at < text.length) {
    const name = names.find(n => {
      if (!text.startsWith(n, at)) return false
      if (n.length !== 1) return true
      const after = text[at + 1] || '', before = text[at - 1] || ''
      return !/[\p{L}\p{N}]/u.test(after) && (!/[\p{L}\p{N}]/u.test(before) || (n === '角' && /首位$/.test(text.slice(0, at))))
    })
    if (!name) { plain += text[at++]; continue }
    if (plain) { tokens.push({ text: plain }); plain = '' }
    const entity = candidates.get(name)
    tokens.push({ text: name, name: entity.name, icon: safeWuwaIcon(entity.icon), entity: true, kind: entity.kind || sectionKey })
    at += name.length
  }
  if (plain) tokens.push({ text: plain })
  return tokens
}
