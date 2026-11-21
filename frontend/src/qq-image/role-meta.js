import { asset, display, roleIdentity } from './models.js'
import wuwaIcons from '../wuwa-icon-catalog.js'
import nteIcons from '../nte-icon-catalog.js'
import endfieldIcons from '../endfield-icon-catalog.js'
import { operatorArtwork } from '../endfield-reports.js'

export const GAME_LABELS = {
  wuthering_waves: '鸣潮',
  nte: '异环',
  endfield: '终末地',
}

export const WUWA_CHAR_META = {
  '散华': { star: 4, attr: '冷凝', weapon: '迅刀' },
  '白芷': { star: 4, attr: '冷凝', weapon: '音感仪' },
  '凌阳': { star: 5, attr: '冷凝', weapon: '臂铠' },
  '折枝': { star: 5, attr: '冷凝', weapon: '音感仪' },
  '釉瑚': { star: 4, attr: '冷凝', weapon: '臂铠' },
  '珂莱塔': { star: 5, attr: '冷凝', weapon: '佩枪' },
  '绯雪': { star: 5, attr: '冷凝', weapon: '迅刀' },
  '洛瑟菈': { star: 5, attr: '冷凝', weapon: '音感仪' },
  '穗穗': { star: 4, attr: '冷凝', weapon: '佩枪' },
  '炽霞': { star: 4, attr: '热熔', weapon: '佩枪' },
  '安可': { star: 5, attr: '热熔', weapon: '音感仪' },
  '莫特斐': { star: 4, attr: '热熔', weapon: '佩枪' },
  '长离': { star: 5, attr: '热熔', weapon: '迅刀' },
  '露帕': { star: 5, attr: '热熔', weapon: '长刃' },
  '莫宁': { star: 5, attr: '热熔', weapon: '长刃' },
  '爱弥斯': { star: 5, attr: '热熔', weapon: '迅刀' },
  '达妮娅': { star: 4, attr: '热熔', weapon: '音感仪' },
  '卡卡罗': { star: 5, attr: '导电', weapon: '长刃' },
  '渊武': { star: 4, attr: '导电', weapon: '臂铠' },
  '今汐': { star: 5, attr: '衍射', weapon: '长刃' },
  '相里要': { star: 5, attr: '导电', weapon: '臂铠' },
  '吟霖': { star: 5, attr: '导电', weapon: '音感仪' },
  '卜灵': { star: 4, attr: '导电', weapon: '音感仪' },
  '丽贝卡': { star: 5, attr: '导电', weapon: '佩枪' },
  '奥古斯塔': { star: 5, attr: '导电', weapon: '长刃' },
  '心': { star: 5, attr: '导电', weapon: '音感仪' },
  '秧秧': { star: 4, attr: '气动', weapon: '迅刀' },
  '秋水': { star: 4, attr: '气动', weapon: '佩枪' },
  '忌炎': { star: 5, attr: '气动', weapon: '长刃' },
  '鉴心': { star: 5, attr: '气动', weapon: '臂铠' },
  '夏空': { star: 5, attr: '气动', weapon: '佩枪' },
  '漂泊者·气动': { star: 5, attr: '气动', weapon: '迅刀' },
  '卡提希娅': { star: 5, attr: '气动', weapon: '迅刀' },
  '尤诺': { star: 5, attr: '气动', weapon: '臂铠' },
  '仇远': { star: 5, attr: '气动', weapon: '迅刀' },
  '清宵': { star: 5, attr: '气动', weapon: '长刃' },
  '维里奈': { star: 5, attr: '衍射', weapon: '音感仪' },
  '灯灯': { star: 4, attr: '衍射', weapon: '长刃' },
  '守岸人': { star: 5, attr: '衍射', weapon: '音感仪' },
  '菲比': { star: 5, attr: '衍射', weapon: '音感仪' },
  '赞妮': { star: 5, attr: '衍射', weapon: '臂铠' },
  '千咲': { star: 5, attr: '湮灭', weapon: '长刃' },
  '琳奈': { star: 5, attr: '衍射', weapon: '佩枪' },
  '露西': { star: 5, attr: '衍射', weapon: '佩枪' },
  '陆·赫斯': { star: 5, attr: '衍射', weapon: '臂铠' },
  '西格莉卡': { star: 5, attr: '气动', weapon: '臂铠' },
  '桃祈': { star: 4, attr: '湮灭', weapon: '长刃' },
  '丹瑾': { star: 4, attr: '湮灭', weapon: '迅刀' },
  '椿': { star: 5, attr: '湮灭', weapon: '迅刀' },
  '洛可可': { star: 5, attr: '湮灭', weapon: '臂铠' },
  '坎特蕾拉': { star: 5, attr: '湮灭', weapon: '音感仪' },
  '弗洛洛': { star: 5, attr: '湮灭', weapon: '音感仪' },
  '嘉贝莉娜': { star: 5, attr: '热熔', weapon: '佩枪' },
  '布兰特': { star: 5, attr: '热熔', weapon: '迅刀' },
  '秧秧·玄翎': { star: 5, attr: '湮灭', weapon: '迅刀' },
  '漂泊者': { star: 5, attr: '衍射', weapon: '迅刀' },
  '漂泊者·衍射': { star: 5, attr: '衍射', weapon: '迅刀' },
  '漂泊者·湮灭': { star: 5, attr: '湮灭', weapon: '迅刀' },
}

const CHAIN_NAMES = ['零链', '一链', '二链', '三链', '四链', '五链', '六链']
const AWAKEN_NAMES = ['零觉', '一觉', '二觉', '三觉', '四觉', '五觉', '六觉']

export function chainLabel(game, num, { preserveUnknown = false } = {}) {
  if (preserveUnknown && (num == null || num === '')) {
    if (game === 'wuthering_waves') return '链未知'
    if (game === 'nte') return '觉未知'
    return '潜能未知'
  }
  const n = Math.max(0, Math.min(6, Number(num) || 0))
  if (game === 'wuthering_waves') return CHAIN_NAMES[n]
  if (game === 'nte') return AWAKEN_NAMES[n]
  return `潜能${n}`
}

export function chainClass(num) {
  if (num == null || num === '') return 'chain-zero'
  const n = Number(num) || 0
  if (n >= 6) return 'chain-max'
  if (n >= 3) return 'chain-mid'
  if (n >= 1) return 'chain-low'
  return 'chain-zero'
}

export function attrByCharId(id) {
  const s = String(id || '')
  if (s === '1304') return '衍射'
  if (s.startsWith('11')) return '冷凝'
  if (s.startsWith('12')) return '热熔'
  if (s.startsWith('13')) return '导电'
  if (s.startsWith('14')) return '气动'
  if (s.startsWith('15')) return '衍射'
  if (s.startsWith('16')) return '湮灭'
  return ''
}

export function resolveWuwaIcon(name, id, rawUrl) {
  const direct = asset(rawUrl)
  if (direct) return direct
  const byChar = wuwaIcons.characters?.[String(id)]?.icon
  if (asset(byChar)) return asset(byChar)
  const clean = String(name || '').replace(/（.*?）$/, '')
  const byRole = wuwaIcons.roles?.[clean]?.icon || wuwaIcons.roles?.[name]?.icon
  if (asset(byRole)) return asset(byRole)
  return ''
}

export function resolveNteIcon(name, id, rawUrl) {
  const direct = asset(rawUrl)
  if (direct) return direct
  const byName = nteIcons.roles?.[name]?.icon
  if (asset(byName)) return asset(byName)
  const found = Object.values(nteIcons.roles || {}).find(r => String(r.id) === String(id))
  if (found && asset(found.icon)) return asset(found.icon)
  return ''
}

export function resolveEndfieldIcon(name, rawUrl, operator = null) {
  const direct = asset(rawUrl)
  if (direct) return direct
  if (operator) {
    const byArt = operatorArtwork(operator)
    if (asset(byArt)) return asset(byArt)
  }
  const found = Object.values(endfieldIcons.roles || {}).find(r => r.name === name)
  if (found && asset(found.icon)) return asset(found.icon)
  return ''
}

export function normalizeElementKey(attr) {
  const s = String(attr || '')
  if (/衍射|光/.test(s)) return 'spectro'
  if (/湮灭|暗/.test(s)) return 'havoc'
  if (/导电|电磁/.test(s)) return 'electro'
  if (/热熔|灼热|咒/.test(s)) return 'fusion'
  if (/冷凝|寒冷|魂/.test(s)) return 'glacio'
  if (/气动|自然|灵/.test(s)) return 'aero'
  if (/相|物理/.test(s)) return 'physical'
  return 'spectro'
}

export function normalizeWeaponKey(weaponType) {
  const s = String(weaponType || '')
  if (/长刃|重装|近卫/.test(s)) return 'broadblade'
  if (/佩枪|狙击|特种|突击/.test(s)) return 'pistols'
  if (/臂铠|先锋/.test(s)) return 'gauntlets'
  if (/音感仪|术师|辅助|医疗|弧盘/.test(s)) return 'rectifier'
  return 'sword'
}

export function buildWuwaRoleCard(r, { detailed = false } = {}) {
  const ident = roleIdentity('wuthering_waves', r)
  const name = ident.name || r.role_name || r.name || '共鸣者'
  const cleanName = name.replace(/（.*?）$/, '')
  const meta = WUWA_CHAR_META[name] || WUWA_CHAR_META[cleanName] || {}
  const id = r.role_id ?? r.id
  const star = Number(r.star_level ?? r.quality ?? meta.star ?? 5)
  const attr = r.attribute || r.attribute_name || r.element || meta.attr || attrByCharId(id) || '衍射'
  const weaponType = r.weapon_type_name || r.weapon || meta.weapon || '迅刀'
  const rawChain = r.chain ?? r.chain_unlock_num ?? r.extra?.chain_unlock_num
  const chain = detailed ? rawChain : (rawChain ?? 0)
  const level = r.level ?? r.role_level
  const image = resolveWuwaIcon(name, id, r.role_icon_url || r.icon_url || ident.icon)
  const weaponIcon = asset(r.weapon_icon || r.weapon?.weapon_icon || wuwaIcons.weapons?.[r.weapon_name]?.icon)
  const skillSum = r.extra?.total_skill_level
  const subParts = detailed
    ? [attr, skillSum != null ? `技能 ${skillSum}` : weaponType].filter(Boolean)
    : []
  return {
    id: String(id || name),
    game: 'wuthering_waves',
    name,
    level,
    star,
    isGold: star >= 5,
    rarityTag: detailed && Number.isFinite(star) ? `${star}★` : '',
    attr,
    elemKey: normalizeElementKey(attr),
    weaponType,
    weaponKey: normalizeWeaponKey(weaponType),
    weaponIcon,
    chain,
    chainText: chainLabel('wuthering_waves', chain, { preserveUnknown: detailed }),
    chainCls: chainClass(chain),
    image,
    subline: subParts.join(' · '),
  }
}

export function buildNteRoleCard(r, { detailed = false } = {}) {
  const ident = roleIdentity('nte', r)
  const name = r.name || ident.name || '异能者'
  const id = r.id ?? r.role_id
  const quality = String(r.quality || 'S').toUpperCase()
  const isGold = quality.includes('S') || Number(r.star_level) >= 5
  const attr = r.element || r.attribute || '光'
  const rawChain = r.awaken_level ?? r.chain
  const chain = detailed ? rawChain : (rawChain ?? 0)
  const image = resolveNteIcon(name, id, r.icon_url || ident.icon)
  const weaponName = r.weapon?.name || r.weapon_name
  const weaponIcon = asset(r.weapon?.icon_url || nteIcons.weapons?.[weaponName]?.icon)
  const mixText = r.mix_level != null ? `混频 ${r.mix_level}` : ''
  const subline = detailed
    ? [attr, mixText || (r.affinity_exp != null ? `羁遇 ${display(r.affinity_exp)}` : '')].filter(Boolean).join(' · ')
    : ''
  return {
    id: String(id || name),
    game: 'nte',
    name,
    level: r.level,
    star: isGold ? 5 : 4,
    isGold,
    rarityTag: detailed ? quality : '',
    attr,
    elemKey: normalizeElementKey(attr),
    weaponType: '弧盘',
    weaponKey: 'rectifier',
    weaponIcon,
    chain,
    chainText: chainLabel('nte', chain, { preserveUnknown: detailed }),
    chainCls: chainClass(chain),
    image,
    subline,
  }
}

export function buildEndfieldRoleCard(r, { detailed = false, portrait = false, phaseTone = '' } = {}) {
  const name = r.name || '干员'
  const rarity = Number(r.rarity ?? 6)
  const isGold = rarity >= 6
  const attr = r.property || r.profession || '物理'
  const weaponType = r.profession || '近卫'
  const rawPot = r.potential
  const potential = detailed ? rawPot : (rawPot ?? 0)
  const image = resolveEndfieldIcon(name, r.avatar_url || r.icon_url, r)
  const weaponIcon = asset(r.weapon?.icon_url || endfieldIcons.weapons?.[r.weapon?.name]?.icon)
  const phaseVal = r.evolve_phase ?? r.phase
  const phaseLabel = detailed ? (phaseVal != null ? `精英${phaseVal}` : '精英—') : ''
  const profLabel = detailed ? (r.profession || r.property || '') : ''
  return {
    id: String(r.id || r.char_id || name),
    operatorId: String(r.char_id || r.id || ''),
    rawAvatarUrl: r.avatar_url || r.icon_url || '',
    game: 'endfield',
    name,
    level: r.level,
    star: isGold ? 5 : 4,
    rarity,
    isGold,
    rarityTag: detailed ? `${Number.isFinite(rarity) ? rarity : '—'}★` : '',
    attr,
    elemKey: normalizeElementKey(attr),
    weaponType,
    weaponKey: normalizeWeaponKey(weaponType),
    weaponIcon,
    chain: potential,
    chainText: chainLabel('endfield', potential, { preserveUnknown: detailed }),
    chainCls: chainClass(potential),
    image,
    portraitMode: portrait,
    phaseLabel,
    phaseTone,
    subline: profLabel,
  }
}
