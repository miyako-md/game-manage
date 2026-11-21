<script setup>
import { computed, ref } from 'vue'
import { display, viewModel } from './models.js'
import { GAME_LABELS, buildEndfieldRoleCard, buildNteRoleCard, buildWuwaRoleCard } from './role-meta.js'
import { skinOf } from '../game-themes.js'
import { newestFirst } from '../role-order.js'
import OverviewRoleCard from './OverviewRoleCard.vue'

const props = defineProps({ input: Object })
const model = computed(() => viewModel(props.input))
// A picture that did not arrive shows the drawn fallback, not its alt text (a long
// nickname in the 64px avatar ring broke the layout audit and the whole image).
const failedImages = ref(new Set())
const shown = url => !!url && !failedImages.value.has(url)
const imageFailed = url => { failedImages.value = new Set([...failedImages.value, url]) }

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
      const roles = [...rawRoles].sort(newestFirst('wuthering_waves')).slice(0, 6).map(r => buildWuwaRoleCard(r))

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
      const rolesPayload = findCap('roles')
      const rawRoles = Array.isArray(rolesPayload)
        ? rolesPayload
        : Array.isArray(rolesPayload?.entries)
          ? rolesPayload.entries
          : []

      const roles = [...rawRoles].sort(newestFirst('nte')).slice(0, 6).map(r => buildNteRoleCard(r))

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
    const roles = rawOps.slice(0, 6).map(r => buildEndfieldRoleCard(r))

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

      <!-- Section 2: 角色信息 (5-Column / 6-Column Character Card Grid) -->
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
          <OverviewRoleCard v-for="role in block.roles" :key="role.id" :role="role" />
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
