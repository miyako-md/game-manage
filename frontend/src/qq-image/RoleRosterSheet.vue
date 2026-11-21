<script setup>
import { computed } from 'vue'
import { display } from './models.js'
import { buildEndfieldRoleCard, buildNteRoleCard, buildWuwaRoleCard } from './role-meta.js'
import { newestFirst } from '../role-order.js'
import { hasTemplateIds, phaseParts, profileReport, rarityParts, rows as efRows, selectOperators } from '../endfield-reports.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import OverviewRoleCard from './OverviewRoleCard.vue'

const props = defineProps({ input: { type: Object, required: true } })

const snap = computed(() => props.input?.snapshot || {})
const game = computed(() => snap.value.game || 'wuthering_waves')

// Endfield elite phase palette: neutral cool greys stepping up to industrial yellow (#ffd100)
// so low tiers never turn olive on the dark surface.
const EF_PHASE_GREYS = ['#565a60', '#757980', '#9ca0a7']

const view = computed(() => {
  const s = snap.value
  const d = s.display_data || {}

  if (game.value === 'wuthering_waves') {
    const panel = (d.panels || []).find(p => p.capability === 'roles')
    const raw = panel?.snapshot?.payload
    const entries = Array.isArray(raw) ? raw : Array.isArray(raw?.entries) ? raw.entries : Array.isArray(raw?.roles) ? raw.roles : []
    const sorted = [...entries].sort(newestFirst('wuthering_waves'))
    const roles = sorted.map(r => buildWuwaRoleCard(r, { detailed: true }))
    const five = roles.filter(r => r.star >= 5).length
    const four = roles.filter(r => r.star === 4).length
    const maxLv = roles.filter(r => Number(r.level) >= 90).length
    const fullChain = roles.filter(r => Number(r.chain) >= 6).length
    const levels = roles.map(r => Number(r.level)).filter(n => Number.isFinite(n))
    const avgLv = levels.length ? `Lv.${(levels.reduce((a, b) => a + b, 0) / levels.length).toFixed(1)}` : '未知'
    return {
      summaryTitle: '练度总览',
      summaryEn: 'OVERVIEW',
      stats: [
        { label: '已记录角色', value: display(roles.length) },
        { label: '五星角色', value: display(five), accent: true },
        { label: '四星角色', value: display(four) },
        { label: '满级角色', value: display(maxLv) },
        { label: '满链角色', value: display(fullChain) },
        { label: '平均等级', value: avgLv },
      ],
      phases: [],
      rarityParts: [],
      rosterTitle: '角色档案',
      rosterEn: 'ROSTER',
      rosterMeta: `共 ${roles.length} 名`,
      roles,
      emptyText: '暂无角色记录，请在看板刷新数据。',
      stale: Boolean(panel?.snapshot?.stale),
      authExpired: panel?.snapshot?.state === 'auth_expired',
    }
  }

  if (game.value === 'nte') {
    const row = d.snapshot || (d.panels || []).find(p => p.capability === 'roles')?.snapshot
    const entries = Array.isArray(row?.payload?.entries) ? row.payload.entries : []
    const sorted = [...entries].sort(newestFirst('nte'))
    const roles = sorted.map(r => buildNteRoleCard(r, { detailed: true }))
    const sCount = roles.filter(r => r.isGold).length
    const aCount = roles.length - sCount
    const levels = roles.map(r => Number(r.level)).filter(n => Number.isFinite(n))
    const topLv = levels.length ? Math.max(...levels) : null
    const atTop = topLv != null ? levels.filter(n => n >= topLv).length : 0
    const fullAwaken = roles.filter(r => Number(r.chain) >= 6).length
    const avgLv = levels.length ? `Lv.${(levels.reduce((a, b) => a + b, 0) / levels.length).toFixed(1)}` : '未知'
    return {
      summaryTitle: '练度总览',
      summaryEn: 'OVERVIEW',
      stats: [
        { label: '角色总数', value: display(roles.length) },
        { label: 'S级角色', value: display(sCount), accent: true },
        { label: 'A级角色', value: display(aCount) },
        { label: topLv != null ? `Lv.${topLv} 角色` : '满级角色', value: topLv != null ? display(atTop) : '未知' },
        { label: '满觉角色', value: display(fullAwaken) },
        { label: '平均等级', value: avgLv },
      ],
      phases: [],
      rarityParts: [],
      rosterTitle: '角色档案',
      rosterEn: 'ROSTER',
      rosterMeta: `共 ${roles.length} 名`,
      roles,
      emptyText: '暂无角色记录，请在看板刷新数据。',
      stale: Boolean(row?.stale),
      authExpired: row?.state === 'auth_expired',
    }
  }

  // endfield
  const panel = (d.panels || []).find(p => p.capability === 'roles')
  const report = profileReport(panel?.snapshot?.payload)
  const training = report.training || {}
  const operators = efRows(training.items)
  const sortMode = hasTemplateIds(operators) ? 'newest' : 'level'
  const sorted = selectOperators(operators, { sort: sortMode })
  const rawPhases = phaseParts(training.summary?.phase_counts)
  const lastPhaseIdx = rawPhases.length - 1
  const phases = rawPhases.map((part, idx) => ({
    ...part,
    color: idx === lastPhaseIdx
      ? '#ffd100'
      : EF_PHASE_GREYS[Math.min(idx, EF_PHASE_GREYS.length - 1)],
  }))
  const phaseColor = v => phases.find(p => p.key === String(v))?.color || EF_PHASE_GREYS[0]
  const rParts = rarityParts(training.summary?.rarity_counts)
  const rCounts = training.summary?.rarity_counts || {}
  const sixCount = rCounts['6'] ?? sorted.filter(o => Number(o.rarity) >= 6).length
  const fiveCount = rCounts['5'] ?? sorted.filter(o => Number(o.rarity) === 5).length
  const avgVal = training.summary?.average_level != null ? Number(training.summary.average_level.toFixed(1)) : null
  const roles = sorted.map(op => buildEndfieldRoleCard(op, {
    detailed: true,
    portrait: true,
    phaseTone: phaseColor(op.evolve_phase ?? op.phase),
  }))

  return {
    summaryTitle: '全员练度',
    summaryEn: 'TRAINING',
    summaryMeta: `显示 ${roles.length} / ${operators.length} 名`,
    stats: [
      { label: '已记录干员', value: display(training.summary?.listed_count ?? roles.length) },
      { label: '来源干员数', value: display(training.summary?.declared_count) },
      { label: '6★ 干员', value: display(sixCount), accent: true },
      { label: '5★ 干员', value: display(fiveCount) },
      { label: '已知等级均值', value: avgVal != null ? `Lv.${avgVal}` : '未知' },
      { label: '最高已知等级', value: training.summary?.max_level != null ? `Lv.${training.summary.max_level}` : '未知' },
    ],
    phases,
    rarityParts: rParts,
    rosterTitle: '干员档案',
    rosterEn: 'OPERATORS',
    rosterMeta: `共 ${roles.length} 名`,
    roles,
    emptyText: '尚无干员资料，请在看板读取后查看。',
    stale: Boolean(panel?.snapshot?.stale),
    authExpired: panel?.snapshot?.state === 'auth_expired',
  }
})
</script>
<template>
  <div class="ov-roster-sheet">
    <p v-if="view.authExpired" class="ov-alert">授权已过期，请在云端看板重新登录。</p>
    <p v-else-if="view.stale" class="ov-alert">当前显示上次成功同步的缓存快照。</p>

    <!-- Section 1: Summary Metrics Grid -->
    <section class="ao-section">
      <OverviewSectionHead
        :title="view.summaryTitle"
        :en="view.summaryEn"
        :index="game === 'endfield' ? '01' : ''"
        :meta="view.summaryMeta || ''"
      />
      <OverviewStatGrid :stats="view.stats" :columns="6" />
    </section>

    <!-- Section 2 (Endfield): Elite Phase & Rarity Distribution Strip -->
    <section v-if="view.phases.length" class="ao-section ef-phases">
      <OverviewSectionHead title="精英阶段" en="PROMOTION" index="02" />
      <div class="ov-dist-panel">
        <div class="ov-stack-bar stack-bar" role="img" :aria-label="view.phases.map(p => `${p.label} ${p.value}`).join('，')">
          <i v-for="part in view.phases.filter(p => p.value > 0)" :key="part.key" :style="{ flex: part.value, background: part.color }"></i>
        </div>
        <ul class="ov-dist-legend">
          <li v-for="part in view.phases" :key="part.key">
            <span class="ov-legend-dot" :style="{ background: part.color }"></span>
            <span class="ov-legend-name">{{ part.label }}</span>
            <strong class="ov-legend-val">{{ part.value }}</strong>
          </li>
        </ul>
      </div>
    </section>

    <!-- Section 3: Poster Role Card Grid (5 columns) -->
    <section class="ao-section">
      <OverviewSectionHead
        :title="view.rosterTitle"
        :en="view.rosterEn"
        :index="game === 'endfield' ? (view.phases.length ? '03' : '02') : ''"
        :meta="view.rosterMeta"
      />
      <div v-if="view.roles.length" class="ao-role-grid ov-roster-grid" :class="{ 'ef-roster': game === 'endfield' }">
        <OverviewRoleCard v-for="role in view.roles" :key="role.id" :role="role" detailed />
      </div>
      <p v-else class="ov-empty">{{ view.emptyText }}</p>
    </section>
  </div>
</template>
