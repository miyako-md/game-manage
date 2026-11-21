import { asset, display, knownRoles } from './models.js'
import { GAME_LABELS, chainLabel, resolveEndfieldIcon, resolveNteIcon, resolveWuwaIcon } from './role-meta.js'
import { profileReport, rows as efRows, sourceName as efNamed, displayValue as efDisplay } from '../endfield-reports.js'
import { scoreHero } from '../assessment-display.js'
import { deepStars } from '../wuwa-charts.js'
import { percentOf } from '../dashboard.js'
import { imageTeams } from '../nte-display.js'
import nteIcons from '../nte-icon-catalog.js'
import { displayBeijing } from '../time.js'
import { newestFirst } from '../role-order.js'
import { gachaPools as efGachaPools, kindSummary as efKindSummary, syncStatus as efSyncStatus } from '../endfield-gacha-summary.js'
import { stamp } from '../wuwa-display.js'

const list = v => (Array.isArray(v) ? v.filter(Boolean) : [])

function fmtAvg(values) {
  const nums = values.map(Number).filter(n => Number.isFinite(n))
  if (!nums.length) return '未知'
  return `Lv.${(nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(1)}`
}

function topAvatar(game, entries) {
  const sorted = [...entries].sort(newestFirst(game))
  if (game === 'wuthering_waves') {
    const pick = sorted.find(r => Number(r.star_level) >= 5 && resolveWuwaIcon(r.name || r.role_name, r.role_id ?? r.id, r.role_icon_url || r.icon_url))
      || sorted.find(r => resolveWuwaIcon(r.name || r.role_name, r.role_id ?? r.id, r.role_icon_url || r.icon_url))
    return pick ? resolveWuwaIcon(pick.name || pick.role_name, pick.role_id ?? pick.id, pick.role_icon_url || pick.icon_url) : ''
  }
  if (game === 'nte') {
    const pick = sorted.find(r => String(r.quality || '').toUpperCase() === 'S' && resolveNteIcon(r.name, r.id, r.icon_url))
      || sorted.find(r => resolveNteIcon(r.name, r.id, r.icon_url))
    return pick ? resolveNteIcon(pick.name, pick.id, pick.icon_url) : ''
  }
  if (game === 'endfield') {
    const pick = entries.find(r => Number(r.rarity) >= 6 && resolveEndfieldIcon(r.name, r.avatar_url || r.icon_url, r))
      || entries.find(r => resolveEndfieldIcon(r.name, r.avatar_url || r.icon_url, r))
    return pick ? resolveEndfieldIcon(pick.name, pick.avatar_url || pick.icon_url, pick) : ''
  }
  return ''
}

export function shellMeta(input, model) {
  const snap = input?.snapshot || {}
  const data = snap.display_data || {}
  const game = snap.game || 'all'
  const gameTag = GAME_LABELS[game] || '游戏管家'
  const panels = list(data.panels)
  const firstPanel = panels[0] || null
  const cap = panels.length === 1 ? firstPanel.capability : null
  const payload = firstPanel?.snapshot?.payload

  let title = model.title || gameTag
  let subTag = `${gameTag} · 更新于 ${model.asOf}`
  let extraTag = ''
  let avatarUrl = ''
  let heroStats = []

  // 1. WuWa single role detail
  if (snap.kind === 'wuwa_role') {
    const detail = data.detail || {}
    const role = detail.role || {}
    const chains = list(detail.chain_list)
    const unlocked = chains.filter(c => c.unlocked === true).length
    const hero = scoreHero(detail.assessment)
    title = `鸣潮 · ${role.role_name || '角色详情'}`
    subTag = [
      role.attribute_name,
      role.weapon_type_name,
      data.fetched_at ? `观测于 ${displayBeijing(data.fetched_at)}` : null,
    ].filter(Boolean).join(' · ') || `库街区观测档案 · ${model.asOf}`
    avatarUrl = resolveWuwaIcon(role.role_name, role.role_id, detail.role_skin?.skin_icon || role.role_icon_url)
    heroStats = [
      { value: role.level != null ? `Lv.${role.level}` : '未知', label: '角色等级' },
      { value: chains.length ? chainLabel('wuthering_waves', unlocked) : (role.breach != null ? `突破 ${role.breach}` : '未知'), label: chains.length ? '共鸣链' : '突破阶段' },
    ]
    if (hero.kind === 'scored') {
      heroStats.push({ value: hero.grade ? `${hero.value} · ${hero.grade}` : hero.value, label: '声骸评分', isAccent: true })
    } else if (hero.kind === 'partial') {
      heroStats.push({ value: hero.value, label: '部分评分', isAccent: true })
    } else if (detail.phantom_data?.cost != null) {
      heroStats.push({ value: `COST ${detail.phantom_data.cost}`, label: '装备声骸', isAccent: true })
    }
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 2. NTE role detail & roster
  if (snap.kind === 'nte_role') {
    const entries = list(data.snapshot?.payload?.entries)
    const isDetail = data.snapshot?.display_mode === 'detail'
    if (isDetail && entries.length) {
      const r = entries[0]
      const hero = scoreHero(r.assessment)
      title = `异环 · ${display(r.name)}`
      subTag = [
        r.element ? `${r.element}属性` : null,
        r.quality ? `${r.quality}级` : null,
        data.snapshot?.fetched_at ? `观测于 ${displayBeijing(data.snapshot.fetched_at)}` : null,
      ].filter(Boolean).join(' · ') || `异环角色档案 · ${model.asOf}`
      avatarUrl = resolveNteIcon(r.name, r.id, r.icon_url)
      heroStats = [
        { value: r.level != null ? `Lv.${r.level}` : '未知', label: '角色等级' },
        { value: chainLabel('nte', r.awaken_level, { preserveUnknown: true }), label: '觉醒阶段' },
      ]
      if (hero.kind === 'scored') {
        heroStats.push({ value: hero.grade ? `${hero.value} · ${hero.grade}` : hero.value, label: '装备评分', isAccent: true })
      } else if (hero.kind === 'partial') {
        heroStats.push({ value: hero.value, label: '部分评分', isAccent: true })
      } else if (r.mix_level != null) {
        heroStats.push({ value: `Lv.${r.mix_level}`, label: '混频等级', isAccent: true })
      }
      return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
    }
    const sCount = entries.filter(r => String(r.quality || '').toUpperCase() === 'S').length
    const maxLv = entries.reduce((m, r) => (Number(r.level) > m ? Number(r.level) : m), 0)
    const atMax = maxLv > 0 ? entries.filter(r => Number(r.level) >= maxLv).length : 0
    title = '异环 · 角色练度'
    subTag = data.snapshot?.fetched_at
      ? `塔吉多档案 · 更新于 ${displayBeijing(data.snapshot.fetched_at)}`
      : `异环完整角色概览 · ${model.asOf}`
    avatarUrl = topAvatar('nte', entries)
    heroStats = [
      { value: `${entries.length}`, label: '角色总数' },
      { value: `${sCount}`, label: 'S级角色' },
      { value: maxLv ? `${atMax}` : fmtAvg(entries.map(r => r.level)), label: maxLv ? `Lv.${maxLv} 满级` : '平均等级', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 3. WuWa roster
  if (snap.kind === 'game_snapshot' && firstPanel?.game === 'wuthering_waves' && cap === 'roles') {
    const entries = Array.isArray(payload) ? payload : list(payload?.entries || payload?.roles)
    const fiveCount = entries.filter(r => Number(r.star_level) >= 5).length
    const maxLvCount = entries.filter(r => Number(r.level) >= 90).length
    title = '鸣潮 · 角色档案'
    subTag = firstPanel.snapshot?.fetched_at
      ? `库街区授权档案 · 更新于 ${displayBeijing(firstPanel.snapshot.fetched_at)}`
      : `鸣潮角色列表 · ${model.asOf}`
    avatarUrl = topAvatar('wuthering_waves', entries)
    heroStats = [
      { value: `${entries.length}`, label: '已记录角色' },
      { value: `${fiveCount}`, label: '五星角色' },
      { value: `${maxLvCount}`, label: 'Lv.90 满级', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 4. Endfield roster & operator detail
  if (snap.kind === 'game_snapshot' && firstPanel?.game === 'endfield' && cap === 'roles') {
    const report = profileReport(payload)
    const training = report.training || {}
    const ops = efRows(training.items)
    const rCounts = training.summary?.rarity_counts || {}
    const sixCount = rCounts['6'] ?? ops.filter(o => Number(o.rarity) >= 6).length
    title = '终末地 · 全员练度'
    subTag = firstPanel.snapshot?.fetched_at
      ? `森空岛档案 · 更新于 ${displayBeijing(firstPanel.snapshot.fetched_at)}`
      : `终末地干员练度 · ${model.asOf}`
    avatarUrl = topAvatar('endfield', ops)
    heroStats = [
      { value: display(training.summary?.listed_count ?? ops.length), label: '已记录干员' },
      { value: display(sixCount), label: '6★ 干员' },
      { value: training.summary?.max_level != null ? `Lv.${training.summary.max_level}` : '未知', label: '最高等级', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  if (snap.kind === 'game_snapshot' && firstPanel?.game === 'endfield' && cap === 'operator_detail') {
    const op = payload?.operator_detail || {}
    const phase = op.evolve_phase ?? op.phase
    title = `终末地 · ${op.name || '干员配装'}`
    subTag = [
      efNamed(op.profession) !== '未知' ? efNamed(op.profession) : null,
      efNamed(op.property) !== '未知' ? efNamed(op.property) : null,
      payload?.operator_fetched_at ? `配装同步于 ${displayBeijing(payload.operator_fetched_at)}` : '森空岛干员配装',
    ].filter(Boolean).join(' · ')
    if (payload?.operator_stale) extraTag = '显示上次成功观测'
    avatarUrl = resolveEndfieldIcon(op.name, op.avatar_url || op.icon_url, op)
    heroStats = [
      { value: op.level != null ? `Lv.${op.level}` : '未知', label: '干员等级' },
      { value: op.potential != null ? `潜能 ${op.potential}` : '未知', label: '潜能阶段' },
      { value: phase != null ? `精英 ${phase}` : '未知', label: '精英阶段', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 5. Guides
  if (snap.kind === 'guide') {
    const g = data.guide || {}
    title = `${gameTag} · ${g.name || '角色'}攻略`
    subTag = [
      g.attribute || g.element,
      g.role,
      '社区攻略参考',
    ].filter(Boolean).join(' · ')
    extraTag = g.freshness?.mark || (g.status === 'original_only' ? '仅原图索引' : '')
    avatarUrl = model.hero?.image || ''
    const ver = g.sources?.find(s => s?.version)?.version
    heroStats = [
      { value: ver ? `V${ver}` : '未标', label: '参考版本' },
      { value: `${list(g.sections).length}`, label: '攻略模块', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 6. Calendar / Events / Recent Events
  if (snap.kind === 'calendar' || cap === 'events' || panels.some(p => p.capability === 'events')) {
    const totalEvents = model.panels.reduce((sum, p) => sum + list(p.events).length, 0)
    const isCal = snap.kind === 'calendar'
    title = isCal ? (game === 'all' ? '活动日历 · 版本汇总' : `${gameTag} · 版本日历`) : (game === 'all' ? '进行中的活动' : `${gameTag} · 进行中活动`)
    subTag = `北京时间 · ${isCal ? '完整版本排期' : '近 14 天排期'}`
    if (model.panels.length === 1) {
      const only = model.panels[0]
      const span = only?.full ? '版本完整' : '近 14 天'
      heroStats = [
        { value: span, label: '排期窗口' },
        { value: `${totalEvents}`, label: '收录活动', isAccent: true },
      ]
    } else {
      heroStats = [
        { value: `${model.panels.length}`, label: '覆盖游戏' },
        { value: `${totalEvents}`, label: '收录活动', isAccent: true },
      ]
    }
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  if (panels.some(p => p.capability === 'recent_events')) {
    const starting = model.panels.find(p => p.title?.includes('开始'))?.rows?.length ?? 0
    const ending = model.panels.find(p => p.title?.includes('结束'))?.rows?.length ?? 0
    title = game === 'all' ? '近期活动 · 未来 72 小时' : `${gameTag} · 近期活动`
    subTag = '北京时间 · 未来 72 小时起止提醒'
    heroStats = [
      { value: `${starting}`, label: '即将开始' },
      { value: `${ending}`, label: '即将结束', isAccent: true },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 7. Gacha
  if (snap.kind === 'nte_gacha' || (snap.kind === 'game_snapshot' && firstPanel?.game === 'nte' && cap === 'gacha')) {
    const gSnap = snap.kind === 'nte_gacha' ? data.snapshot : firstPanel?.snapshot
    const gPayload = gSnap?.payload || {}
    const pools = list(gPayload.pools)
    const total = pools.reduce((s, p) => s + (Number(p.total_draws) || 0), 0)
    const sTotal = pools.reduce((s, p) => s + (Number(p.s_count) || 0), 0)
    title = '异环 · 抽卡统计'
    subTag = gSnap?.fetched_at ? `塔吉多社区统计 · 更新于 ${displayBeijing(gSnap.fetched_at)}` : '塔吉多社区抽卡统计'
    extraTag = typeof gPayload.luck_title === 'string' ? gPayload.luck_title : ''
    heroStats = [
      { value: `${total}`, label: '统计总抽' },
      { value: `${sTotal}`, label: '出 S 总数', isAccent: true },
    ]
    if (data.ledger) {
      heroStats.push({ value: `${data.ledger.total_records ?? 0}`, label: '逐抽账本', isAccent: true })
    }
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  if (snap.kind === 'wuwa_gacha' || (snap.kind === 'game_snapshot' && firstPanel?.game === 'wuthering_waves' && cap === 'gacha')) {
    const arc = (snap.kind === 'wuwa_gacha' ? data.archive : payload) || {}
    const pools = list(arc.pools)
    const total = typeof arc.total === 'number' ? arc.total : null
    const gold = typeof arc.gold_total === 'number' ? arc.gold_total : null
    const share = total > 0 && gold != null ? `${((gold / total) * 100).toFixed(1)}%` : '—'
    title = '鸣潮 · 抽卡档案'
    subTag = arc.coverage?.imported_at
      ? `本地逐抽账本 · 导入于 ${stamp(arc.coverage.imported_at)}`
      : arc.coverage?.complete === true
        ? '本地逐抽账本 · 覆盖完整'
        : '本地逐抽账本'
    extraTag = arc.state === 'need_import' ? '待导入' : arc.coverage?.complete === true ? '完整历史' : '部分历史'
    heroStats = [
      { value: display(arc.total), label: '已录抽数' },
      { value: display(arc.gold_total), label: '五星总数', isAccent: true },
      { value: total != null ? share : `${pools.length}`, label: total != null ? '五星占比' : '统计卡池' },
    ]
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  if (snap.kind === 'game_snapshot' && firstPanel?.game === 'endfield' && cap === 'gacha') {
    const gSummary = payload?.schema_version === 1 ? payload : null
    const efPools = efGachaPools(gSummary || payload)
    const charKind = efKindSummary(efPools, 'character')
    const weapKind = efKindSummary(efPools, 'weapon')
    title = '终末地 · 寻访战报'
    subTag = firstPanel.snapshot?.fetched_at
      ? `鹰角官方寻访档案 · 同步于 ${displayBeijing(firstPanel.snapshot.fetched_at)}`
      : '鹰角官方寻访记录 · 分池统计'
    extraTag = efSyncStatus(gSummary || payload, gSummary?.report)?.label || ''
    if (charKind && weapKind) {
      // Separate currencies: never sum operator headhunting and weapon requisition totals.
      heroStats = [
        { value: display(charKind.total), label: '干员寻访' },
        { value: display(weapKind.total), label: '武器申领' },
        { value: `${efPools.length}`, label: '统计卡池', isAccent: true },
      ]
    } else if (charKind || weapKind) {
      const only = charKind || weapKind
      heroStats = [
        { value: display(only.total), label: only.label },
        { value: display(only.six_star), label: '6★ 总计', isAccent: true },
        { value: only.pace?.average != null ? `${only.pace.average} 抽` : '—', label: '平均出 6★' },
      ]
    } else {
      heroStats = [{ value: `${efPools.length}`, label: '统计卡池', isAccent: true }]
    }
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 8. Help, Account Status & General Notices
  if (snap.kind === 'notice') {
    const sections = list(data.sections)
    const noticeList = list(data.notices)
    const itemCount = sections.reduce((s, sec) => s + list(sec.items).length, 0)
    if (/帮助/.test(data.title || '')) {
      title = game === 'all' ? '游戏管家 · 指令帮助' : `${gameTag} · 指令帮助`
      subTag = 'QQ 群 / 私聊可用查询指令清单'
      heroStats = [
        { value: `${sections.length}`, label: '功能分组' },
        { value: `${itemCount}`, label: '可用指令', isAccent: true },
      ]
      return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
    }
    if (/我的账号/.test(data.title || '')) {
      title = '我的账号 · 授权状态'
      subTag = 'QQ 与云端看板已绑定'
      const cardCount = sections.reduce((s, sec) => s + list(sec.items).filter(t => typeof t === 'string' && !t.includes('：')).length, 0)
      heroStats = [
        { value: `${cardCount}`, label: '授权账号', isAccent: true },
      ]
      return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
    }
    const mergedText = `${data.title || ''} ${noticeList.join(' ')}`
    if (game === 'endfield' && /攻略/.test(model.command || data.title || '')) {
      title = '终末地 · 角色攻略'
      subTag = '森空岛公共档案 · 攻略收录说明'
      extraTag = '待收录'
    } else if (/下线|停止/.test(mergedText)) {
      subTag = `${gameTag} · 指令调整说明`
      extraTag = '已下线'
    } else if (/攻略/.test(mergedText)) {
      subTag = `${gameTag} · 攻略查询引导`
      extraTag = '查询引导'
    } else if (/未绑定|绑定码/.test(mergedText)) {
      subTag = `${gameTag} · 绑定提示`
      extraTag = '待绑定'
    } else {
      subTag = `${gameTag} · 系统提示`
    }
    if (sections.length) {
      heroStats = [
        { value: `${sections.length}`, label: '说明分组' },
        { value: `${itemCount}`, label: '详情条目', isAccent: true },
      ]
    }
    return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
  }

  // 9. Remaining game snapshots (exploration, combat, progress, resources, assets, ship, honor)
  if (snap.kind === 'game_snapshot' && firstPanel) {
    const fetched = firstPanel.snapshot?.fetched_at ? `更新于 ${displayBeijing(firstPanel.snapshot.fetched_at)}` : `更新于 ${model.asOf}`
    const archivePrefix = firstPanel.game === 'wuthering_waves' ? '库街区档案' : firstPanel.game === 'nte' ? '塔吉多档案' : firstPanel.game === 'endfield' ? '森空岛档案' : gameTag
    subTag = `${archivePrefix} · ${fetched}`
    if (firstPanel.snapshot?.stale && cap !== 'combat') extraTag = '数据待更新'

    if (firstPanel.game === 'wuthering_waves' && cap === 'resources') {
      const cur = payload?.current || {}
      const curData = cur.data || {}
      const kinds = { week: '周', month: '月', version: '版本' }
      const pList = Object.entries(kinds).flatMap(([k, n]) => list(payload?.periods?.[k]).map(p => ({ ...p, kind: k, name: n })))
      const sel = pList.find(p => p.kind === cur.kind && String(p.period) === String(cur.period))
      const periodName = sel?.title || (cur.kind === 'month' && /^(\d{4})(0[1-9]|1[0-2])$/.test(String(cur.period || ''))
        ? `${String(cur.period).slice(0, 4)} 年 ${Number(String(cur.period).slice(4))} 月`
        : cur.kind === 'version' && cur.period ? `${cur.period} 版本` : '当期')
      subTag = `${periodName}资源简报 · ${fetched}`
      heroStats = [
        { value: display(curData.total_star), label: '星声收入', isAccent: true },
        { value: display(curData.total_coin), label: '贝币收入' },
      ]
    } else if (firstPanel.game === 'wuthering_waves' && cap === 'exploration') {
      const groups = list(payload?.country_groups)
      const known = groups.filter(g => typeof g.progress === 'number' && Number.isFinite(g.progress)).map(g => g.progress)
      const avg = known.length ? `${(known.reduce((a, b) => a + b, 0) / known.length).toFixed(1)}%` : '—'
      heroStats = [
        { value: `${groups.length}`, label: '探索大区' },
        { value: avg, label: '平均探索' },
        { value: display(payload?.detections?.total), label: '残象收录', isAccent: true },
      ]
    } else if (firstPanel.game === 'wuthering_waves' && cap === 'progress') {
      const items = list(payload)
      const done = items.filter(it => typeof it.cur === 'number' && typeof it.total === 'number' && it.total > 0 && it.cur >= it.total).length
      heroStats = [
        { value: `${items.length}`, label: '追踪项目' },
        { value: `${done}`, label: '已满进度', isAccent: true },
      ]
    } else if (firstPanel.game === 'wuthering_waves' && cap === 'combat') {
      const ds = deepStars(payload?.tower?.data)
      const towerVal = payload?.tower?.data?.is_unlock === false ? '未解锁'
        : ds.got != null ? `${ds.got}${ds.cap != null ? `/${ds.cap}` : ''} ★` : '未知'
      const bosses = Object.values(payload?.hologram?.data?.challenge_info || {})
        .filter(recs => list(recs).some(r => Number(r.pass_time) > 0 || list(r.roles).length || r.attempted === true)).length
      const slashZones = list(payload?.slash?.data?.difficulty_list)
      const seaZone = slashZones.find(z => typeof z.difficulty_name === 'string' && z.difficulty_name.startsWith('再生海域')) || slashZones[0]
      heroStats = [
        { value: towerVal, label: '深境星数', isAccent: true },
        { value: payload?.hologram?.data?.is_unlock === false ? '未解锁' : `${bosses}`, label: '全息首领' },
        { value: seaZone?.all_score != null ? `${seaZone.all_score}` : (payload?.slash?.data?.is_unlock === false ? '未解锁' : '未知'), label: '海墟得分' },
      ]
    } else if (firstPanel.game === 'nte' && cap === 'exploration') {
      const areas = list(payload?.areas)
      const measurable = areas.filter(a => percentOf(a.current, a.total) != null)
      const sumCur = measurable.reduce((s, a) => s + Number(a.current), 0)
      const sumTot = measurable.reduce((s, a) => s + Number(a.total), 0)
      const pct = measurable.length && sumTot > 0 ? `${Math.round((sumCur / sumTot) * 100)}%` : '—'
      heroStats = [
        { value: `${areas.length}`, label: '探索区域' },
        { value: measurable.length ? `${sumCur}/${sumTot}` : '未知', label: '合计收集' },
        { value: pct, label: '综合进度', isAccent: true },
      ]
    } else if (firstPanel.game === 'nte' && cap === 'progress') {
      const pct = percentOf(payload?.completed, payload?.total)
      heroStats = [
        { value: `${display(payload?.completed)}/${display(payload?.total)}`, label: '成就完成', isAccent: true },
        { value: pct != null ? `${Math.round(pct)}%` : '—', label: '总达成率', isAccent: true },
        { value: display(payload?.gold), label: '金奖章' },
      ]
    } else if (firstPanel.game === 'nte' && ['realestate', 'vehicles'].includes(cap)) {
      const pct = percentOf(payload?.owned_count, payload?.total)
      heroStats = [
        { value: `${display(payload?.owned_count)}/${display(payload?.total)}`, label: cap === 'vehicles' ? '拥有载具' : '拥有房产', isAccent: true },
        { value: pct != null ? `${Math.round(pct)}%` : '—', label: '收集率', isAccent: true },
      ]
    } else if (firstPanel.game === 'nte' && cap === 'teams') {
      const knownNames = [...knownRoles('nte').map(r => r.name), ...Object.keys(nteIcons.roles || {})]
      const teams = imageTeams(list(payload?.entries), list(payload?.owned_role_names), knownNames)
      subTag = `塔吉多官方推荐 · ${fetched}`
      heroStats = [
        { value: `${teams.length}`, label: '推荐配队', isAccent: true },
      ]
    } else if (firstPanel.game === 'endfield' && cap === 'ship') {
      const sum = profileReport(payload).ship?.summary || {}
      heroStats = [
        { value: efDisplay(sum.room_count), label: '舱室数' },
        { value: efDisplay(sum.staffed_rooms), label: '有驻守舱室' },
        { value: efDisplay(sum.operator_slots), label: '驻守席位', isAccent: true },
      ]
    } else if (firstPanel.game === 'endfield' && cap === 'honor') {
      const sum = profileReport(payload).honor?.summary || {}
      heroStats = [
        { value: efDisplay(sum.listed_count), label: '已录奖章' },
        { value: efDisplay(sum.declared_count), label: '来源总数', isAccent: true },
      ]
    } else if (firstPanel.game === 'endfield' && cap === 'exploration') {
      const sum = profileReport(payload).regions?.summary || {}
      heroStats = [
        { value: efDisplay(sum.region_count), label: '建设地区', isAccent: true },
        { value: efDisplay(sum.settlement_count), label: '据点总数' },
      ]
    } else if (firstPanel.game === 'endfield' && cap === 'combat') {
      const reports = list(payload?.reports)
      const avail = reports.filter(r => r && r.available === true && r.fetched_at).length
      subTag = `森空岛独立观测档案 · ${fetched}`
      heroStats = [
        { value: `${reports.length}`, label: '挑战类型' },
        { value: `${avail}`, label: '已采集项', isAccent: true },
      ]
    }
  }

  return { title, gameTag, subTag, extraTag, avatarUrl, heroStats }
}
