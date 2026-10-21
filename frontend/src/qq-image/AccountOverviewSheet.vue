<script setup>
import { computed, ref } from 'vue'
import { asset, display, roleIdentity, viewModel } from './models.js'
import wuwaIcons from '../wuwa-icon-catalog.js'
import nteIcons from '../nte-icon-catalog.js'
import endfieldIcons from '../endfield-icon-catalog.js'
import { skinOf } from '../game-themes.js'
import { newestFirst } from '../role-order.js'

const props = defineProps({ input: Object })
const model = computed(() => viewModel(props.input))
// A picture that did not arrive shows the drawn fallback, not its alt text (a long
// nickname in the 64px avatar ring broke the layout audit and the whole image).
const failedImages = ref(new Set())
const shown = url => !!url && !failedImages.value.has(url)
const imageFailed = url => { failedImages.value = new Set([...failedImages.value, url]) }

const GAME_LABELS = {
  wuthering_waves: '鸣潮',
  nte: '异环',
  endfield: '终末地',
}

const WUWA_CHAR_META = {
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

function chainLabel(game, num) {
  const n = Math.max(0, Math.min(6, Number(num) || 0))
  if (game === 'wuthering_waves') return CHAIN_NAMES[n]
  if (game === 'nte') return AWAKEN_NAMES[n]
  return `潜能${n}`
}

function chainClass(num) {
  const n = Number(num) || 0
  if (n >= 6) return 'chain-max'
  if (n >= 3) return 'chain-mid'
  if (n >= 1) return 'chain-low'
  return 'chain-zero'
}

function attrByCharId(id) {
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

function resolveWuwaIcon(name, id, rawUrl) {
  const direct = asset(rawUrl)
  if (direct) return direct
  const byChar = wuwaIcons.characters?.[String(id)]?.icon
  if (asset(byChar)) return asset(byChar)
  const clean = String(name || '').replace(/（.*?）$/, '')
  const byRole = wuwaIcons.roles?.[clean]?.icon || wuwaIcons.roles?.[name]?.icon
  if (asset(byRole)) return asset(byRole)
  return ''
}

function resolveNteIcon(name, id, rawUrl) {
  const direct = asset(rawUrl)
  if (direct) return direct
  const byName = nteIcons.roles?.[name]?.icon
  if (asset(byName)) return asset(byName)
  const found = Object.values(nteIcons.roles || {}).find(r => String(r.id) === String(id))
  if (found && asset(found.icon)) return asset(found.icon)
  return ''
}

function resolveEndfieldIcon(name, rawUrl) {
  const direct = asset(rawUrl)
  if (direct) return direct
  const found = Object.values(endfieldIcons.roles || {}).find(r => r.name === name)
  if (found && asset(found.icon)) return asset(found.icon)
  return ''
}

function normalizeElementKey(attr) {
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

function normalizeWeaponKey(weaponType) {
  const s = String(weaponType || '')
  if (/长刃|重装|近卫/.test(s)) return 'broadblade'
  if (/佩枪|狙击|特种/.test(s)) return 'pistols'
  if (/臂铠|先锋/.test(s)) return 'gauntlets'
  if (/音感仪|术师|辅助|医疗|弧盘/.test(s)) return 'rectifier'
  return 'sword'
}

const gameBlocks = computed(() => {
  const panels = props.input?.snapshot?.display_data?.panels || []
  const order = []
  const byGame = {}
  for (const p of panels) {
    if (!byGame[p.game]) {
      byGame[p.game] = []
      order.push(p.game)
    }
    byGame[p.game].push(p)
  }

  return order.map(game => {
    const gPanels = byGame[game]
    const findCap = (cap, provider) =>
      gPanels.find(p => p.capability === cap && (!provider || p.provider === provider))?.snapshot?.payload
    const findSnap = (cap, provider) =>
      gPanels.find(p => p.capability === cap && (!provider || p.provider === provider))?.snapshot

    if (game === 'wuthering_waves') {
      const accountPayload = findCap('account') || {}
      // Kuro keeps active days, achievements, beacons, chests and world level under extra.profile;
      // top-level account fields (nickname, level) still win.
      const acc = { ...(accountPayload.extra?.profile || {}), ...accountPayload }
      const stam = findCap('stamina')
      const cal = findCap('calabash')
      const gacha = findCap('gacha')
      const rolesPayload = findCap('roles')
      const rawRoles = Array.isArray(rolesPayload)
        ? rolesPayload
        : Array.isArray(rolesPayload?.entries)
          ? rolesPayload.entries
          : Array.isArray(rolesPayload?.roles)
            ? rolesPayload.roles
            : []

      // The service already sends the six newest; the same order and cut keep any other input bounded.
      const roles = [...rawRoles].sort(newestFirst('wuthering_waves')).slice(0, 6).map(r => {
        const ident = roleIdentity('wuthering_waves', r)
        const name = ident.name || r.role_name || r.name || '共鸣者'
        const cleanName = name.replace(/（.*?）$/, '')
        const meta = WUWA_CHAR_META[name] || WUWA_CHAR_META[cleanName] || {}
        const id = r.role_id ?? r.id
        const star = Number(r.star_level ?? r.quality ?? meta.star ?? 5)
        const attr = r.attribute || r.attribute_name || r.element || meta.attr || attrByCharId(id) || '衍射'
        const weaponType = r.weapon_type_name || meta.weapon || '迅刀'
        const chain = r.chain ?? r.chain_unlock_num ?? r.extra?.chain_unlock_num ?? 0
        const level = r.level ?? r.role_level
        const image = resolveWuwaIcon(name, id, r.role_icon_url || r.icon_url || ident.icon)
        const weaponIcon = asset(r.weapon_icon || r.weapon?.weapon_icon || wuwaIcons.weapons?.[r.weapon_name]?.icon)
        return {
          id: String(id || name),
          name,
          level,
          star,
          isGold: star >= 5,
          attr,
          elemKey: normalizeElementKey(attr),
          weaponType,
          weaponKey: normalizeWeaponKey(weaponType),
          weaponIcon,
          chain,
          chainText: chainLabel('wuthering_waves', chain),
          chainCls: chainClass(chain),
          image,
        }
      })

      const goldCount = roles.filter(r => r.isGold).length
      const boxes = Array.isArray(acc.box_list)
        ? acc.box_list
        : Array.isArray(acc.treasure_box_list)
          ? acc.treasure_box_list
          : []
      const boxCells = boxes.slice(0, 4).map(b => ({
        label: b.box_name || b.name || '奇藏箱',
        value: display(b.num ?? b.count ?? 0),
      }))
      while (boxCells.length < 4) {
        const fallbacks = [
          { label: '朴素奇藏箱', value: stam ? `${display(stam.energy ?? stam.current)}/${display(stam.max_energy ?? stam.maximum)}` : '未提供', overrideLabel: stam ? '结晶波片' : '朴素奇藏箱' },
          { label: '基准奇藏箱', value: stam?.liveness != null ? `${display(stam.liveness)}/${display(stam.liveness_max_count ?? 100)}` : '未提供', overrideLabel: stam?.liveness != null ? '每日活跃' : '基准奇藏箱' },
          { label: '精密奇藏箱', value: stam?.weekly_inst_count != null ? display(stam.weekly_inst_count) : '未提供', overrideLabel: stam?.weekly_inst_count != null ? '周本剩余' : '精密奇藏箱' },
          { label: '辉光奇藏箱', value: gacha?.total != null ? display(gacha.total) : '未提供', overrideLabel: gacha?.total != null ? '记录总抽数' : '辉光奇藏箱' },
        ]
        const fb = fallbacks[boxCells.length]
        boxCells.push({ label: fb.overrideLabel, value: fb.value })
      }

      const stats = [
        { label: '活跃天数', value: display(acc.active_days) },
        { label: '解锁角色', value: display(acc.character_count ?? acc.role_total ?? (rawRoles.length || null)) },
        // The roles panel holds at most six entries; full totals ride on the account panel.
        { label: '五星角色', value: display(acc.gold_role_total ?? ((acc.role_total ?? rawRoles.length) > roles.length ? null : roles.length ? goldCount : gacha?.gold_total)) },
        {
          label: cal?.level != null ? '数据坞等级' : '结晶单质',
          value: cal?.level != null ? display(cal.level) : display(stam?.store_energy),
        },
        { label: '已达成成就', value: display(acc.achievement_count) },
        { label: '成就星数', value: display(acc.achievement_star) },
        { label: '小型信标', value: display(acc.small_count) },
        { label: '中型信标', value: display(acc.big_count) },
        ...boxCells,
      ]

      const heroStats = [
        { value: acc.level != null ? `Lv.${acc.level}` : '未知', label: '账号等级' },
        { value: acc.world_level != null ? `Lv.${acc.world_level}` : '未知', label: '世界等级' },
      ]
      if (stam && (stam.energy != null || stam.current != null)) {
        heroStats.push({
          value: `${display(stam.energy ?? stam.current)}/${display(stam.max_energy ?? stam.maximum ?? 240)}`,
          label: '结晶波片',
          isAccent: true,
        })
      }

      const avatarRole = roles.find(r => r.image && r.isGold) || roles.find(r => r.image)
      const subParts = [
        acc.server_name ? `区服: ${acc.server_name}` : '库街区授权档案',
        acc.active_days != null ? `活跃 ${acc.active_days} 天` : null,
      ].filter(Boolean)

      return {
        game,
        gameName: GAME_LABELS[game],
        nickname: display(acc.nickname || acc.name),
        subTag: subParts.join(' · '),
        extraProvider: '',
        avatarUrl: avatarRole?.image || '',
        heroStats,
        stats,
        roles,
      }
    }

    if (game === 'nte') {
      const acc = findCap('account') || {}
      const stam = findCap('stamina')
      const gacha = findCap('gacha')
      const rolesPayload = findCap('roles')
      const rawRoles = Array.isArray(rolesPayload)
        ? rolesPayload
        : Array.isArray(rolesPayload?.entries)
          ? rolesPayload.entries
          : []

      const roles = [...rawRoles].sort(newestFirst('nte')).slice(0, 6).map(r => {
        const ident = roleIdentity('nte', r)
        const name = r.name || ident.name || '异能者'
        const id = r.id ?? r.role_id
        const quality = String(r.quality || 'S').toUpperCase()
        const isGold = quality.includes('S') || Number(r.star_level) >= 5
        const attr = r.element || r.attribute || '光'
        const chain = r.awaken_level ?? r.chain ?? 0
        const image = resolveNteIcon(name, id, r.icon_url || ident.icon)
        const weaponName = r.weapon?.name || r.weapon_name
        const weaponIcon = asset(r.weapon?.icon_url || nteIcons.weapons?.[weaponName]?.icon)
        return {
          id: String(id || name),
          name,
          level: r.level,
          star: isGold ? 5 : 4,
          isGold,
          attr,
          elemKey: normalizeElementKey(attr),
          weaponType: '弧盘',
          weaponKey: 'rectifier',
          weaponIcon,
          chain,
          chainText: chainLabel('nte', chain),
          chainCls: chainClass(chain),
          image,
        }
      })

      const sCount = roles.filter(r => r.isGold).length
      const stats = [
        { label: '活跃天数', value: display(acc.active_days) },
        { label: '解锁角色', value: display(acc.character_count ?? acc.role_total ?? (rawRoles.length || null)) },
        { label: 'S级角色', value: display(acc.gold_role_total ?? ((acc.role_total ?? rawRoles.length) > roles.length ? null : roles.length ? sCount : null)) },
        { label: '大亨等级', value: acc.tycoon_level != null ? `Lv.${acc.tycoon_level}` : '未提供' },
        { label: '已达成成就', value: display(acc.achievement_count) },
        { label: '成就总数', value: display(acc.achievement_total) },
        {
          label: '拥有房产',
          value: acc.house_count != null && acc.house_total != null
            ? `${acc.house_count}/${acc.house_total}`
            : display(acc.house_count),
        },
        {
          label: '拥有载具',
          value: acc.vehicle_count != null && acc.vehicle_total != null
            ? `${acc.vehicle_count}/${acc.vehicle_total}`
            : display(acc.vehicle_count),
        },
        {
          label: '当前体力',
          value: stam && stam.current != null ? `${display(stam.current)}/${display(stam.maximum)}` : '未提供',
        },
        {
          label: '城区体力',
          value: stam && stam.city_current != null ? `${display(stam.city_current)}/${display(stam.city_maximum)}` : '未提供',
        },
        { label: '每日活跃', value: display(stam?.daily_activity) },
        { label: '周本剩余', value: display(stam?.weekly_remaining) },
      ]

      const heroStats = [
        { value: acc.level != null ? `Lv.${acc.level}` : '等级：未知', label: '市民等级' },
        { value: acc.tycoon_level != null ? `Lv.${acc.tycoon_level}` : '未提供', label: '大亨等级' },
      ]
      if (stam && stam.current != null) {
        heroStats.push({
          value: `${display(stam.current)}/${display(stam.maximum ?? 240)}`,
          label: '当前体力',
          isAccent: true,
        })
      }

      const accSnap = findSnap('account')
      const stateParts = [
        acc.server_name ? `区服: ${acc.server_name}` : '异环官方社区档案',
        accSnap?.stale ? '显示旧快照' : null,
        accSnap?.complete === false ? '完整性：不完整' : null,
      ].filter(Boolean)

      const avatarRole = roles.find(r => r.image && r.isGold) || roles.find(r => r.image)
      return {
        game,
        gameName: GAME_LABELS[game],
        nickname: display(acc.nickname || acc.name),
        subTag: stateParts.join(' · '),
        extraProvider: '',
        avatarUrl: avatarRole?.image || '',
        heroStats,
        stats,
        roles,
      }
    }

    // endfield
    const skAcc = findCap('account', 'skland') || findCap('account') || {}
    const hgAcc = findCap('account', 'hypergryph')
    const report = skAcc.report || {}
    const overview = report.overview || {}
    const base = overview.base || skAcc.base || skAcc
    const stam = overview.stamina || skAcc.stamina || findCap('stamina')
    const todos = overview.todos || {}
    const training = report.training || {}
    const regions = report.regions?.summary || {}
    const ship = report.ship?.summary || {}
    const honor = report.honor?.summary || {}
    const gachaPayload = findCap('gacha')
    const gachaPools = gachaPayload?.report?.pools || gachaPayload?.pools || []
    const gachaTotal = gachaPools.length
      ? gachaPools.reduce((sum, p) => sum + (Number(p.total ?? p.total_pulls) || 0), 0)
      : null

    const rolesPanel = findCap('roles')
    const rawOps = Array.isArray(rolesPanel?.operators)
      ? rolesPanel.operators
      : Array.isArray(training.items)
        ? training.items
        : Array.isArray(skAcc.operators)
          ? skAcc.operators
          : []

    // Endfield keeps the service's level order; six are shown, counts use the whole roster.
    const roster = Array.isArray(skAcc.operators) && skAcc.operators.length > rawOps.length ? skAcc.operators : rawOps
    const roles = rawOps.slice(0, 6).map(r => {
      const name = r.name || '干员'
      const rarity = Number(r.rarity ?? 6)
      const isGold = rarity >= 6
      const attr = r.property || r.profession || '物理'
      const weaponType = r.profession || '近卫'
      const potential = r.potential ?? 0
      const image = resolveEndfieldIcon(name, r.avatar_url || r.icon_url)
      const weaponIcon = asset(r.weapon?.icon_url || endfieldIcons.weapons?.[r.weapon?.name]?.icon)
      return {
        id: String(r.id || r.char_id || name),
        name,
        level: r.level,
        star: isGold ? 5 : 4,
        isGold,
        attr,
        elemKey: normalizeElementKey(attr),
        weaponType,
        weaponKey: normalizeWeaponKey(weaponType),
        weaponIcon,
        chain: potential,
        chainText: chainLabel('endfield', potential),
        chainCls: chainClass(potential),
        image,
      }
    })

    const rCounts = training.summary?.rarity_counts || {}
    const sixCount = rCounts['6'] ?? roster.filter(r => Number(r.rarity ?? 6) >= 6).length
    const fiveCount = rCounts['5'] ?? roster.filter(r => Number(r.rarity ?? 6) < 6).length

    const stats = [
      { label: '已记录干员', value: display(training.summary?.listed_count ?? base.char_count ?? (roster.length || null)) },
      { label: '六星干员', value: display(sixCount) },
      { label: '五星干员', value: display(fiveCount) },
      { label: '最高等级', value: display(training.summary?.max_level) },
      { label: '平均等级', value: display(training.summary?.average_level) },
      { label: '持有武器', value: display(base.weapon_count) },
      {
        label: '当前理智',
        value: stam && stam.current != null ? `${display(stam.current)}/${display(stam.maximum)}` : '未提供',
      },
      { label: '建设地区', value: display(regions.region_count) },
      { label: '聚落数量', value: display(regions.settlement_count) },
      { label: '帝江号房间', value: display(ship.room_count ?? (Array.isArray(report.ship?.rooms) ? report.ship.rooms.length : null)) },
      { label: '蚀刻奖章', value: display(honor.listed_count ?? skAcc.achievements?.count) },
      {
        label: gachaTotal != null ? '寻访总抽数' : '每日任务',
        value: gachaTotal != null
          ? display(gachaTotal)
          : todos.daily?.current != null
            ? `${display(todos.daily.current)}/${display(todos.daily.maximum)}`
            : '未提供',
      },
    ]

    const heroStats = [
      { value: base.level != null ? `Lv.${base.level}` : '未知', label: '权限等级' },
      { value: base.world_level != null ? `Lv.${base.world_level}` : '未知', label: '世界等级' },
    ]
    if (stam && stam.current != null) {
      heroStats.push({
        value: `${display(stam.current)}/${display(stam.maximum ?? 240)}`,
        label: '当前理智',
        isAccent: true,
      })
    }

    const avatarRole = roles.find(r => r.image && r.isGold) || roles.find(r => r.image)
    const subParts = [
      base.server_name ? `区服: ${base.server_name}` : '森空岛档案',
      base.main_mission ? `主线: ${base.main_mission}` : null,
    ].filter(Boolean)

    return {
      game,
      gameName: GAME_LABELS[game],
      nickname: display(base.nickname || base.name || hgAcc?.nickname),
      subTag: subParts.join(' · '),
      extraProvider: hgAcc && (hgAcc.nickname || hgAcc.name) ? `鹰角寻访独立授权：${display(hgAcc.nickname || hgAcc.name)}` : '',
      avatarUrl: avatarRole?.image || '',
      heroStats,
      stats,
      roles,
    }
  })
})

const notices = computed(() => props.input?.snapshot?.display_data?.notices || [])
</script>

<template>
  <div class="ao-canvas">
    <!-- Multi-game top bar when showing all games -->
    <div v-if="gameBlocks.length > 1" class="ao-multi-topbar">
      <span class="ao-multi-badge">GAME ASSISTANT · ACCOUNT OVERVIEW</span>
      <span class="ao-multi-title">{{ model.title }}</span>
      <span class="ao-multi-cmd">指令：{{ model.command }}</span>
    </div>

    <!-- Per-Game Account Overview Block -->
    <section v-for="block in gameBlocks" :key="block.game" class="ao-game-block" :data-skin="skinOf(block.game)">
      <!-- Top Stadium Pill Identity Banner -->
      <header class="ao-capsule-banner">
        <div class="ao-identity-pill">
          <div class="ao-avatar-ring">
            <img v-if="shown(block.avatarUrl)" :src="block.avatarUrl" :alt="block.nickname" class="ao-avatar-img" @error="imageFailed(block.avatarUrl)" />
            <svg v-else class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
              <defs>
                <linearGradient id="ao-crest-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                  <stop offset="0%" stop-color="#f2d9a6" />
                  <stop offset="100%" stop-color="#b8904c" />
                </linearGradient>
              </defs>
              <circle cx="32" cy="32" r="28" fill="#181c28" />
              <path d="M32 10 L37 25 L52 30 L37 35 L32 50 L27 35 L12 30 L27 25 Z" fill="url(#ao-crest-grad)" opacity="0.9" />
              <circle cx="32" cy="30" r="5" fill="#12141c" />
            </svg>
          </div>
          <div class="ao-identity-meta">
            <div class="ao-name-row">
              <svg class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M12 1 L14.8 9.2 L23 12 L14.8 14.8 L12 23 L9.2 14.8 L1 12 L9.2 9.2 Z" fill="#e6c98f" />
              </svg>
              <span class="ao-nickname">{{ block.nickname }}</span>
              <span class="ao-game-tag">{{ block.gameName }}</span>
            </div>
            <div class="ao-subtag-row">
              <span class="ao-subtag-pill">{{ block.subTag }}</span>
              <span v-if="block.extraProvider" class="ao-extra-pill">{{ block.extraProvider }}</span>
            </div>
          </div>
        </div>

        <div class="ao-hero-stats">
          <div v-for="hs in block.heroStats" :key="hs.label" class="ao-hero-col" :class="{ 'is-accent': hs.isAccent }">
            <strong class="ao-hero-val">{{ hs.value }}</strong>
            <span class="ao-hero-lbl">{{ hs.label }}</span>
          </div>
        </div>
      </header>

      <!-- Section 1: 基本信息 (6-Column Dark Stat Grid) -->
      <div class="ao-section">
        <div class="ao-section-head">
          <span class="ao-head-line left"></span>
          <h2 class="ao-section-title">
            <span class="ao-diamond">◇</span>
            <span>基本信息</span>
            <span class="ao-diamond">◇</span>
          </h2>
          <span class="ao-head-line right"></span>
        </div>

        <div class="ao-stat-grid">
          <div v-for="stat in block.stats" :key="stat.label" class="ao-stat-cell">
            <strong class="ao-stat-val">{{ stat.value }}</strong>
            <span class="ao-stat-lbl">{{ stat.label }}</span>
          </div>
        </div>
      </div>

      <!-- Section 2: 角色信息 (5-Column Character Card Grid) -->
      <div v-if="block.roles.length" class="ao-section">
        <div class="ao-section-head">
          <span class="ao-head-line left"></span>
          <h2 class="ao-section-title">
            <span class="ao-diamond">◇</span>
            <span>角色信息</span>
            <span class="ao-diamond">◇</span>
          </h2>
          <span class="ao-head-line right"></span>
        </div>

        <div class="ao-role-grid" :class="{ 'is-six-col': block.roles.length === 6 }">
          <div
            v-for="role in block.roles"
            :key="role.id"
            class="ao-role-card"
            :class="role.isGold ? 'is-rarity-gold' : 'is-rarity-purple'"
          >
            <div class="ao-role-portrait">
              <img v-if="shown(role.image)" :src="role.image" :alt="role.name" class="ao-role-img" @error="imageFailed(role.image)" />
              <svg v-else class="ao-role-fallback" viewBox="0 0 120 120" aria-hidden="true">
                <circle cx="60" cy="52" r="32" fill="rgba(255,255,255,0.04)" stroke="rgba(214,188,138,0.22)" stroke-width="1.2" />
                <text x="60" y="64" text-anchor="middle" fill="rgba(240,218,172,0.34)" font-size="34" font-weight="800">{{ role.name.slice(0, 1) }}</text>
              </svg>
              <div class="ao-rarity-glow"></div>

              <!-- Top-Right Element Badge -->
              <span class="ao-elem-badge" :class="'elem-' + role.elemKey" :title="role.attr">
                <svg v-if="role.elemKey === 'spectro'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 2L14.2 8.8L21 9.5L15.6 13.8L17.5 20.5L12 16.6L6.5 20.5L8.4 13.8L3 9.5L9.8 8.8Z" fill="#ffe17d" />
                </svg>
                <svg v-else-if="role.elemKey === 'havoc'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M14.5 3.5A8.5 8.5 0 1 0 20.5 16.5A7 7 0 1 1 14.5 3.5Z" fill="#ff7aa8" />
                  <circle cx="15" cy="9" r="2.2" fill="#ffd1e2" />
                </svg>
                <svg v-else-if="role.elemKey === 'electro'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M13.5 2L5.5 13H11.5L10 22L18.5 10.5H12.5L13.5 2Z" fill="#d09bff" />
                </svg>
                <svg v-else-if="role.elemKey === 'fusion'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12.5 2.5C12.5 2.5 18.5 7.5 18.5 13.5C18.5 17.6 15.4 21 11.5 21C7.6 21 5 17.6 5 13.8C5 10.5 7.2 7.8 7.2 7.8C7.2 7.8 7 10.8 9.2 11.5C8.5 8.2 12.5 2.5 12.5 2.5Z" fill="#ff8563" />
                </svg>
                <svg v-else-if="role.elemKey === 'glacio'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5Z" fill="#7be0ff" />
                </svg>
                <svg v-else-if="role.elemKey === 'aero'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 13C7.5 8 13.5 7 19.5 10C15.5 12.5 11.5 13.5 4 13ZM6 17.5C10 14.5 15 14 20 15.5C16.5 18 11.5 19 6 17.5Z" fill="#6bf2c3" />
                </svg>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                  <polygon points="12,3 21,12 12,21 3,12" fill="#dbe3f0" />
                </svg>
              </span>

              <!-- Bottom-Right Weapon Emblem -->
              <span class="ao-weapon-badge" :title="role.weaponType">
                <img v-if="role.weaponIcon" :src="role.weaponIcon" :alt="role.weaponType" class="ao-weapon-img" />
                <svg v-else-if="role.weaponKey === 'broadblade'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M18 3L21 6L9 18L5 19L6 15L18 3ZM4 20L7 17L9 19L6 22L4 20Z" fill="#e6cfa3" />
                </svg>
                <svg v-else-if="role.weaponKey === 'pistols'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M4 7H19L21 10L17 12H11L9 18H5L7 12H4V7Z" fill="#e6cfa3" />
                </svg>
                <svg v-else-if="role.weaponKey === 'gauntlets'" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M6 8L11 4L18 7L19 15L13 20L6 16Z" fill="#e6cfa3" />
                </svg>
                <svg v-else-if="role.weaponKey === 'rectifier'" viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="12" cy="12" r="5" fill="none" stroke="#e6cfa3" stroke-width="2" />
                  <path d="M12 2V6M12 18V22M2 12H6M18 12H22" stroke="#e6cfa3" stroke-width="2" />
                </svg>
                <svg v-else viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M19 3L21 5L8.5 17.5L6.5 15.5L19 3ZM5 17L7 19L4 22L2 20L5 17Z" fill="#e6cfa3" />
                </svg>
              </span>

              <!-- Character Name Overlay -->
              <span class="ao-role-name-tag">{{ role.name }}</span>
            </div>

            <!-- Card Footer: Chain/Awakening/Potential Pill + Level -->
            <div class="ao-role-footer">
              <span class="ao-chain-pill" :class="role.chainCls">{{ role.chainText }}</span>
              <span class="ao-role-lv">{{ role.level != null ? `LV.${role.level}` : 'LV.—' }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Notices Strip (if any) -->
    <div v-if="notices.length" class="ao-notices">
      <p v-for="(note, idx) in notices" :key="idx" class="ao-notice-item">✦ {{ note }}</p>
    </div>

    <!-- Bottom Credit Footer -->
    <footer class="ao-footer">
      <span>Power by GameAssistant · 游戏管家</span>
      <span>·</span>
      <span>更新于 {{ model.asOf }}</span>
      <span>·</span>
      <span>指令：{{ model.command }}</span>
    </footer>
  </div>
</template>
