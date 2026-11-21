<script setup>
import { computed, reactive } from 'vue'
import { friendlyDataError } from '../cloud-display.js'
import { list, value, count, stamp, sourceDateTime } from '../wuwa-display.js'
import { sourceShares, deepZone, towerTotals, otherZoneStars, bestRank } from '../wuwa-charts.js'
import { share } from '../chart-math.js'
import { resetLabel } from '../time.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import { roleIdentity } from './models.js'
import { resolveWuwaIcon } from './role-meta.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const CHART_COLORS = ['#e6c98f', '#62b6ff', '#5ee6c0', '#b288ff', '#ff9e6d', '#9aa5ba', '#f07c96']
const failedUrls = reactive(new Set())
const safeImg = url => (url && !failedUrls.has(url) ? url : '')
const onImgError = url => {
  if (url) failedUrls.add(url)
}

const panel = computed(() => (props.input?.snapshot?.display_data?.panels || [])[0] || null)
const cap = computed(() => panel.value?.capability || '')
const snap = computed(() => panel.value?.snapshot || null)
const payload = computed(() => snap.value?.payload ?? null)
const asOfMs = computed(() => {
  const parsed = Date.parse(props.input?.snapshot?.as_of)
  return Number.isFinite(parsed) ? parsed : Date.now()
})
const authError = computed(() => (snap.value?.state === 'auth_expired' ? friendlyDataError('', snap.value.state) : ''))

// ---- 1A. Exploration ----
const countryGroups = computed(() =>
  list(payload.value?.country_groups).map((g, idx) => {
    const progress = typeof g.progress === 'number' && Number.isFinite(g.progress) ? g.progress : null
    const areas = list(g.areas).map((a, aIdx) => {
      const ap = typeof a.progress === 'number' && Number.isFinite(a.progress) ? a.progress : null
      return {
        key: aIdx,
        name: a.name || '-',
        progress: ap,
        pctText: ap == null ? '-' : `${ap}%`,
      }
    })
    return {
      key: idx,
      name: g.name || '-',
      progress,
      pctText: progress == null ? '-' : `${progress}%`,
      areas,
    }
  }),
)

const detections = computed(() => payload.value?.detections ?? null)
const detectionLevels = computed(() => {
  const entries = Object.entries(detections.value?.by_level || {})
  const totalKnown = entries.reduce((sum, [, n]) => sum + (typeof n === 'number' && n > 0 ? n : 0), 0)
  return entries.map(([name, n], idx) => {
    const num = typeof n === 'number' && Number.isFinite(n) ? n : null
    const pct = num != null && totalKnown > 0 ? Math.round((num / totalKnown) * 100) : null
    return {
      name,
      count: num,
      pct,
      color: CHART_COLORS[idx % CHART_COLORS.length],
    }
  })
})

const exploreStats = computed(() => {
  const known = countryGroups.value.filter(g => g.progress != null).map(g => g.progress)
  const avg = known.length ? `${(known.reduce((a, b) => a + b, 0) / known.length).toFixed(1)}%` : '—'
  const subTotal = countryGroups.value.reduce((s, g) => s + g.areas.length, 0)
  return [
    { value: `${countryGroups.value.length}`, label: '探索大区' },
    { value: `${subTotal}`, label: '收录子区' },
    { value: avg, label: '综合均度', accent: true },
    { value: detections.value?.total != null ? `${count(detections.value.total)} 只` : '未知', label: '残象收录', accent: true },
  ]
})

// ---- 1B. Progress ----
const progressRows = computed(() => {
  const items = Array.isArray(payload.value) ? payload.value.filter(Boolean) : []
  return items.map((it, idx) => {
    const total = typeof it.total === 'number' && it.total > 0 ? it.total : null
    const curNum = typeof it.cur === 'number' && Number.isFinite(it.cur) ? it.cur : null
    const ratio = total == null ? null : share(curNum, total)
    const pct = ratio == null ? null : Math.round(ratio * 100)
    const done = total != null && curNum != null && curNum >= total
    return {
      key: idx,
      label: it.name || '未命名项目',
      cur: it.cur,
      total,
      pct,
      done,
      statusText: total == null ? '周期计数' : done ? '已完成' : '进行中',
      note: resetLabel(it.refresh_at, asOfMs.value),
    }
  })
})

const progressStats = computed(() => {
  const done = progressRows.value.filter(r => r.done).length
  const active = progressRows.value.filter(r => r.total != null && !r.done).length
  return [
    { value: `${progressRows.value.length}`, label: '追踪项目' },
    { value: `${done}`, label: '已满进度', accent: true },
    { value: `${active}`, label: '待完成' },
  ]
})

// ---- 1C. Resources ----
const KINDS = { week: '周', month: '月', version: '版本' }
function periodLabel(kind, period) {
  const text = String(period ?? '')
  const month = kind === 'month' && /^(\d{4})(0[1-9]|1[0-2])$/.exec(text)
  if (month) return `${month[1]} 年 ${Number(month[2])} 月`
  if (kind === 'version' && /^\d+\.\d+$/.test(text)) return `${text} 版本`
  return `${KINDS[kind] || '当前'}周期 ${text}`.trim()
}
const periodsList = computed(() =>
  Object.entries(KINDS).flatMap(([kind, kindName]) =>
    list(payload.value?.periods?.[kind])
      .filter(p => p.period != null)
      .map(p => ({ ...p, kind, kindName })),
  ),
)
const resCurrent = computed(() => payload.value?.current || null)
const resSelected = computed(() =>
  periodsList.value.find(p => p.kind === resCurrent.value?.kind && String(p.period) === String(resCurrent.value?.period)) || null,
)
const resTitle = computed(() => {
  if (!resCurrent.value?.data) return '资源周期统计'
  return resSelected.value?.title || periodLabel(resCurrent.value.kind, resCurrent.value.period)
})
const resRange = computed(() => {
  const sel = resSelected.value
  if (!sel) return ''
  const when = v => sourceDateTime(v) ?? v
  const start = sel.start_time || sel.start_date
  const end = sel.end_time || sel.end_date
  if (!start && !end) return ''
  return `${when(start) || '未知'} — ${when(end) || '未知'}`
})
const resErrorText = computed(() => {
  const err = payload.value?.error
  return err ? friendlyDataError(err, snap.value?.state) : ''
})
function trendClass(v) {
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v ?? ''))
  return !Number.isFinite(n) || n === 0 ? '' : n > 0 ? 'is-up' : 'is-down'
}
function trendText(v) {
  if (v == null || v === '') return '环比 —'
  const s = String(v)
  return s.startsWith('环比') ? s : `环比 ${s}`
}
const resCurrencies = computed(() => {
  const data = resCurrent.value?.data || {}
  return [
    ['star_list', '星声收入', data.total_star, data.star_inc, true],
    ['coin_list', '贝币收入', data.total_coin, data.coin_inc, false],
  ].map(([key, name, totalVal, inc, featured]) => {
    const shares = sourceShares(data[key], 6)
    const knownSum = shares.reduce((s, p) => s + (typeof p.value === 'number' && p.value > 0 ? p.value : 0), 0)
    const maxVal = shares.reduce((m, p) => (typeof p.value === 'number' && p.value > m ? p.value : m), 0)
    return {
      key,
      name,
      featured,
      total: totalVal,
      inc,
      trend: trendClass(inc),
      trendLabel: trendText(inc),
      knownSum,
      parts: shares.map((part, i) => ({
        ...part,
        color: CHART_COLORS[i % CHART_COLORS.length],
        sharePct: part.value != null && knownSum > 0 ? Math.round((part.value / knownSum) * 100) : null,
        barWidth: part.value != null && maxVal > 0 ? Math.max(4, Math.round((part.value / maxVal) * 100)) : 0,
      })),
    }
  })
})

// ---- 1D. Combat ----
function resolveRoleChip(role) {
  const ident = roleIdentity('wuthering_waves', role || {})
  const name = ident.name || '名称未提供'
  const id = role?.role_id ?? role?.id
  const icon = resolveWuwaIcon(name, id, role?.role_icon_url || role?.icon_url || ident.icon)
  return {
    name,
    icon,
    level: role?.role_level ?? role?.level ?? null,
  }
}

const towerData = computed(() => payload.value?.tower?.data || null)
const towerZones = computed(() => list(towerData.value?.difficulty_list))
const activeTowerZone = computed(() => deepZone(towerZones.value) || towerZones.value.find(z => list(z.tower_area_list).length) || towerZones.value[0] || null)
const towerOtherZones = computed(() => otherZoneStars(towerZones.value))
const towerActiveTotals = computed(() => towerTotals(activeTowerZone.value?.tower_area_list))
const towerSeasonMeta = computed(() =>
  towerData.value?.season_end_at ? `周期结束 ${stamp(towerData.value.season_end_at)}` : '',
)
function starGlyphs(floor) {
  const got = Number(floor?.star)
  const capVal = Number(floor?.max_star)
  return floor?.star != null && Number.isInteger(got) && Number.isInteger(capVal) && capVal > 0 && capVal <= 6 && got >= 0 && got <= capVal
    ? { got, cap: capVal }
    : null
}

const hologramData = computed(() => payload.value?.hologram?.data || null)
const hologramBosses = computed(() => {
  const out = []
  for (const [, records] of Object.entries(hologramData.value?.challenge_info || {})) {
    const tried = list(records).filter(r => Number(r.pass_time) > 0 || list(r.roles).length || r.attempted === true)
    if (!tried.length) continue
    const best = tried.reduce((a, b) => (Number(b.difficulty) > Number(a.difficulty) ? b : a))
    out.push({
      bossName: best.boss_name || '未知首领',
      difficulty: best.difficulty,
      bossLevel: best.boss_level,
      passTime: Number(best.pass_time) > 0 ? `${best.pass_time} 秒` : '已挑战',
      roles: list(best.roles).map(resolveRoleChip),
    })
  }
  return out
})

const slashData = computed(() => payload.value?.slash?.data || null)
const slashZones = computed(() =>
  list(slashData.value?.difficulty_list).map((z, idx) => {
    const ratio = share(z.all_score, z.max_score)
    const pct = ratio == null ? null : Math.round(ratio * 100)
    const isSea = typeof z.difficulty_name === 'string' && z.difficulty_name.startsWith('再生海域')
    const challenges = isSea
      ? list(z.challenge_list).map((ch, cIdx) => {
          const halves = list(ch.half_list)
          const halfKnown = halves.filter(h => typeof h.score === 'number' && h.score > 0).length
          return {
            key: cIdx,
            name: ch.challenge_name || `海域关卡 ${cIdx + 1}`,
            score: ch.score,
            rank: ch.rank,
            showBar: halfKnown > 1,
            halves: halves.map((h, hIdx) => ({
              key: hIdx,
              name: h.half_name || `${hIdx === 0 ? '上' : '下'}半场`,
              score: h.score,
              shareFlex: typeof h.score === 'number' && h.score > 0 ? h.score : 0,
              color: CHART_COLORS[hIdx % CHART_COLORS.length],
              roles: list(h.role_list).map(resolveRoleChip),
            })),
          }
        })
      : []
    return {
      key: idx,
      name: z.difficulty_name || `难度 ${value(z.difficulty)}`,
      allScore: z.all_score,
      maxScore: z.max_score,
      pct,
      bestRank: bestRank(z.challenge_list),
      challenges,
    }
  }),
)
</script>

<template>
  <div class="ov-ds-sheet ov-wuwa-data">
    <p v-if="authError" class="ov-alert">{{ authError }}</p>

    <!-- 1A. Exploration -->
    <template v-if="cap === 'exploration'">
      <p v-if="!countryGroups.length && detections?.total == null" class="ov-empty">暂无探索数据</p>
      <template v-else>
        <section class="ao-section">
          <OverviewSectionHead title="探索总览" />
          <OverviewStatGrid :stats="exploreStats" :columns="4" />
        </section>

        <section v-if="countryGroups.length" class="ao-section">
          <OverviewSectionHead title="大区探索度" :meta="`${countryGroups.length} 个地区`" />
          <div class="ov-ds-grid-2">
            <article v-for="g in countryGroups" :key="g.key" class="ov-ds-card ww-explore-card">
              <header class="ov-ds-card-head">
                <h3 class="ov-ds-card-title">{{ g.name }}</h3>
                <strong class="ww-pct-badge" :class="{ 'is-full': g.progress != null && g.progress >= 100 }">{{ g.pctText }}</strong>
              </header>
              <div v-if="g.progress != null" class="ov-bar-track">
                <i class="ov-bar-fill" :style="{ width: `${Math.max(0, Math.min(100, g.progress))}%` }" />
              </div>
              <span v-else class="ov-meter-none" aria-hidden="true" />
              <ul v-if="g.areas.length" class="ww-subareas">
                <li v-for="area in g.areas" :key="area.key" class="ww-subarea-item">
                  <div class="ww-subarea-top">
                    <span class="ww-subarea-name">{{ area.name }}</span>
                    <strong class="ww-subarea-pct" :class="{ 'is-full': area.progress != null && area.progress >= 100 }">{{ area.pctText }}</strong>
                  </div>
                  <div v-if="area.progress != null" class="ov-bar-track is-thin">
                    <i class="ov-bar-fill" :style="{ width: `${Math.max(0, Math.min(100, area.progress))}%` }" />
                  </div>
                </li>
              </ul>
            </article>
          </div>
        </section>

        <section v-if="detections?.total != null" class="ao-section">
          <OverviewSectionHead title="残象探寻收录" :meta="`共 ${count(detections.total)} 只`" />
          <div class="ov-ds-card ww-detect-card">
            <div v-if="detectionLevels.length" class="ov-stack-bar" aria-hidden="true">
              <i
                v-for="lvl in detectionLevels"
                v-show="lvl.count > 0"
                :key="lvl.name"
                :style="{ flex: lvl.count, background: lvl.color }"
              />
            </div>
            <div class="ww-detect-grid">
              <div v-for="lvl in detectionLevels" :key="lvl.name" class="ww-detect-cell">
                <span class="ww-detect-lbl">
                  <i class="ov-legend-dot" :style="{ background: lvl.color }" aria-hidden="true" />
                  {{ lvl.name }}
                </span>
                <strong class="ww-detect-val">{{ lvl.count != null ? count(lvl.count) : '未知' }}</strong>
                <span v-if="lvl.pct != null" class="ww-detect-pct">{{ lvl.pct }}%</span>
              </div>
            </div>
          </div>
        </section>
      </template>
    </template>

    <!-- 1B. Progress -->
    <template v-else-if="cap === 'progress'">
      <p v-if="!progressRows.length" class="ov-empty">暂无周期进度数据</p>
      <template v-else>
        <section class="ao-section">
          <OverviewSectionHead title="周期进度总览" :meta="`共 ${progressRows.length} 项`" />
          <OverviewStatGrid :stats="progressStats" :columns="3" />
        </section>

        <section class="ao-section">
          <OverviewSectionHead title="周期任务明细" />
          <div class="ov-ds-grid-2">
            <article v-for="row in progressRows" :key="row.key" class="ov-ds-card ww-prog-card" :class="{ 'is-done': row.done }">
              <header class="ov-ds-card-head">
                <h3 class="ov-ds-card-title">{{ row.label }}</h3>
                <span class="ov-pill" :class="{ 'is-ok': row.done }">{{ row.statusText }}</span>
              </header>
              <div class="ww-prog-vals">
                <strong class="ww-prog-cur">
                  {{ row.cur != null ? count(row.cur) : '未知' }}<span v-if="row.total != null" class="ww-prog-max"> / {{ count(row.total) }}</span>
                </strong>
                <span v-if="row.pct != null" class="ww-pct-badge" :class="{ 'is-full': row.done }">{{ row.pct }}%</span>
              </div>
              <div v-if="row.total != null && row.pct != null" class="ov-bar-track">
                <i class="ov-bar-fill" :style="{ width: `${row.pct}%` }" />
              </div>
              <p v-if="row.note" class="ww-prog-note">{{ row.note }}</p>
            </article>
          </div>
        </section>
      </template>
    </template>

    <!-- 1C. Resources -->
    <template v-else-if="cap === 'resources'">
      <p v-if="resErrorText" class="ov-alert">{{ resErrorText }}</p>
      <p v-if="!resCurrent?.data" class="ov-empty">暂无资源简报，请刷新数据。</p>
      <template v-else>
        <section class="ao-section">
          <OverviewSectionHead :title="`${resTitle} · 期间获取`" :meta="resRange" />
          <div class="ov-ds-grid-2 ww-res-currencies">
            <article v-for="cur in resCurrencies" :key="cur.key" class="ov-ds-card ww-res-card" :class="{ 'is-featured': cur.featured }">
              <header class="ww-res-head">
                <div>
                  <span class="ww-res-lbl">{{ cur.name }}</span>
                  <strong class="ww-res-total">{{ count(cur.total) }}</strong>
                </div>
                <span class="ov-pill ww-delta-pill" :class="cur.trend">{{ cur.trendLabel }}</span>
              </header>
              <div v-if="cur.parts.length && cur.knownSum > 0" class="ov-stack-bar" aria-hidden="true">
                <i
                  v-for="part in cur.parts"
                  v-show="part.value > 0"
                  :key="part.label"
                  :style="{ flex: part.value, background: part.color }"
                />
              </div>
              <ul v-if="cur.parts.length" class="ww-src-list">
                <li v-for="part in cur.parts" :key="part.label" class="ww-src-row">
                  <span class="ww-src-name">
                    <i class="ov-legend-dot" :style="{ background: part.color }" aria-hidden="true" />
                    {{ part.label }}
                  </span>
                  <span class="ov-bar-track is-mini" aria-hidden="true">
                    <i v-if="part.barWidth" class="ov-bar-fill" :style="{ width: `${part.barWidth}%`, background: part.color }" />
                  </span>
                  <strong class="ww-src-val">
                    {{ part.value != null ? count(part.value) : '未知' }}
                    <span v-if="part.sharePct != null" class="ww-src-pct">({{ part.sharePct }}%)</span>
                  </strong>
                </li>
              </ul>
              <p v-else class="ov-muted-note">未提供来源明细</p>
            </article>
          </div>
        </section>

        <section v-if="resCurrent.data.copy_writing || resCurrent.data.recommend" class="ao-section">
          <OverviewSectionHead title="简报说明" />
          <div class="ov-ds-card ww-res-notes">
            <p v-if="resCurrent.data.copy_writing" class="ww-note-text">{{ resCurrent.data.copy_writing }}</p>
            <div v-if="resCurrent.data.recommend" class="ww-rec-box">
              <strong v-if="resCurrent.data.recommend.post_title" class="ww-rec-title">{{ resCurrent.data.recommend.post_title }}</strong>
              <p v-if="resCurrent.data.recommend.content" class="ww-note-text">{{ resCurrent.data.recommend.content }}</p>
            </div>
          </div>
        </section>
      </template>
    </template>

    <!-- 1D. Combat -->
    <template v-else-if="cap === 'combat'">
      <!-- Tower -->
      <section class="ao-section">
        <OverviewSectionHead title="逆境深塔" :meta="towerSeasonMeta" />
        <p v-if="!towerData" class="ov-empty">深塔数据暂不可用</p>
        <p v-else-if="towerData.is_unlock === false" class="ov-empty">逆境深塔尚未解锁</p>
        <template v-else>
          <div class="ww-tower-summary">
            <div v-if="activeTowerZone" class="ov-pill is-accent">
              {{ activeTowerZone.difficulty_name || `分区 ${activeTowerZone.difficulty}` }}
              · {{ towerActiveTotals.got != null ? `${towerActiveTotals.got}${towerActiveTotals.cap != null ? ` / ${towerActiveTotals.cap}` : ''} ★` : '星数未知' }}
            </div>
            <span v-for="oz in towerOtherZones" :key="oz.name" class="ov-pill">
              {{ oz.name }} · {{ oz.got }}{{ oz.cap != null ? ` / ${oz.cap}` : '' }} ★
            </span>
          </div>
          <div v-if="activeTowerZone && list(activeTowerZone.tower_area_list).length" class="ww-tower-areas">
            <article v-for="(area, aIdx) in list(activeTowerZone.tower_area_list)" :key="aIdx" class="ov-ds-card ww-tower-area">
              <header class="ov-ds-card-head">
                <h3 class="ov-ds-card-title">{{ area.area_name || `区域 ${aIdx + 1}` }}</h3>
                <strong class="ww-star-total">
                  <template v-if="area.max_star != null">{{ value(area.star) }} / {{ value(area.max_star) }} ★</template>
                  <template v-else-if="area.star != null">已得 {{ value(area.star) }} ★</template>
                  <template v-else>星数未知</template>
                </strong>
              </header>
              <div v-if="area.max_star != null && area.star != null" class="ov-bar-track is-thin">
                <i class="ov-bar-fill" :style="{ width: `${Math.round((share(area.star, area.max_star) || 0) * 100)}%` }" />
              </div>
              <div v-if="list(area.floor_list).length" class="ww-floor-list">
                <div v-for="(floor, fIdx) in list(area.floor_list)" :key="fIdx" class="ww-floor-row">
                  <span class="ww-floor-num">第 {{ value(floor.floor ?? floor.floor_index) }} 层</span>
                  <span class="ww-floor-stars">
                    <template v-if="starGlyphs(floor)">
                      <span
                        v-for="n in starGlyphs(floor).cap"
                        :key="n"
                        class="ww-star-glyph"
                        :class="{ off: n > starGlyphs(floor).got }"
                      >★</span>
                    </template>
                    <template v-else-if="floor.max_star != null">{{ value(floor.star) }} / {{ value(floor.max_star) }} ★</template>
                    <template v-else>已得 {{ value(floor.star) }} ★</template>
                  </span>
                  <div v-if="list(floor.role_list || floor.roles).length" class="ov-role-chips">
                    <span v-for="(role, rIdx) in list(floor.role_list || floor.roles).map(resolveRoleChip)" :key="rIdx" class="ov-role-chip">
                      <img
                          v-if="safeImg(role.icon)"
                          :src="safeImg(role.icon)"
                          :alt="role.name"
                          class="ov-role-chip-img"
                          @error="onImgError(role.icon)"
                        />
                      <span>{{ role.name }}</span>
                      <span v-if="role.level != null" class="ov-role-chip-lv">Lv.{{ role.level }}</span>
                    </span>
                  </div>
                  <span v-else class="ov-muted-inline">阵容未提供</span>
                </div>
              </div>
              <p v-else class="ov-muted-note">未提供分层数据</p>
            </article>
          </div>
          <p v-else class="ov-empty">未提供深塔分区记录</p>
        </template>
      </section>

      <!-- Hologram -->
      <section class="ao-section">
        <OverviewSectionHead title="战术全息" :meta="hologramBosses.length ? `已挑战 ${hologramBosses.length} 位首领` : ''" />
        <p v-if="hologramData?.is_unlock === false" class="ov-empty">战术全息尚未解锁</p>
        <div v-else-if="hologramBosses.length" class="ov-ds-grid-2">
          <article v-for="(boss, bIdx) in hologramBosses" :key="bIdx" class="ov-ds-card ww-boss-card">
            <header class="ov-ds-card-head">
              <h3 class="ov-ds-card-title">{{ boss.bossName }}</h3>
              <span class="ov-pill is-accent">难度 {{ value(boss.difficulty) }}</span>
            </header>
            <div class="ww-boss-meta">
              <span>首领等级 Lv.{{ value(boss.bossLevel) }}</span>
              <strong>{{ boss.passTime }}</strong>
            </div>
            <div v-if="boss.roles.length" class="ov-role-chips">
              <span v-for="(role, rIdx) in boss.roles" :key="rIdx" class="ov-role-chip">
                <img
                          v-if="safeImg(role.icon)"
                          :src="safeImg(role.icon)"
                          :alt="role.name"
                          class="ov-role-chip-img"
                          @error="onImgError(role.icon)"
                        />
                <span>{{ role.name }}</span>
                <span v-if="role.level != null" class="ov-role-chip-lv">Lv.{{ role.level }}</span>
              </span>
            </div>
            <p v-else class="ov-muted-note">队伍未提供</p>
          </article>
        </div>
        <p v-else class="ov-empty">未提供战术全息挑战记录</p>
      </section>

      <!-- Slash -->
      <section class="ao-section">
        <OverviewSectionHead title="冥歌海墟" />
        <p v-if="slashData?.is_unlock === false" class="ov-empty">冥歌海墟尚未解锁</p>
        <p v-else-if="!slashZones.length" class="ov-empty">未提供海墟记录</p>
        <template v-else>
          <div class="ww-slash-zones">
            <article v-for="zone in slashZones" :key="zone.key" class="ov-ds-card ww-slash-zone-card">
              <header class="ov-ds-card-head">
                <h3 class="ov-ds-card-title">{{ zone.name }}</h3>
                <span v-if="zone.bestRank" class="ww-rank-pill">{{ zone.bestRank }}</span>
              </header>
              <div class="ww-prog-vals">
                <strong class="ww-prog-cur">{{ count(zone.allScore) }}<span class="ww-prog-max"> / {{ count(zone.maxScore) }}</span></strong>
                <span v-if="zone.pct != null" class="ww-pct-badge">{{ zone.pct }}%</span>
              </div>
              <div v-if="zone.pct != null" class="ov-bar-track is-thin">
                <i class="ov-bar-fill" :style="{ width: `${zone.pct}%` }" />
              </div>

              <div v-if="zone.challenges.length" class="ww-slash-challenges" :class="{ 'is-two-col': zone.challenges.length >= 2 }">
                <div v-for="ch in zone.challenges" :key="ch.key" class="ww-slash-ch">
                  <div class="ww-slash-ch-head">
                    <strong class="ww-slash-ch-name">{{ ch.name }}</strong>
                    <span class="ww-slash-ch-score">{{ count(ch.score) }}</span>
                    <span v-if="ch.rank" class="ww-rank-pill">{{ ch.rank }}</span>
                  </div>
                  <div v-if="ch.showBar" class="ov-stack-bar is-thin" aria-hidden="true">
                    <i
                      v-for="h in ch.halves"
                      v-show="h.shareFlex > 0"
                      :key="h.key"
                      :style="{ flex: h.shareFlex, background: h.color }"
                    />
                  </div>
                  <div class="ww-halves">
                    <div v-for="h in ch.halves" :key="h.key" class="ww-half-row">
                      <div class="ww-half-top">
                        <span class="ww-half-name">
                          <i class="ov-legend-dot" :style="{ background: h.color }" aria-hidden="true" />
                          {{ h.name }}
                        </span>
                        <strong class="ww-half-score">{{ count(h.score) }} 分</strong>
                      </div>
                      <div v-if="h.roles.length" class="ov-role-chips">
                        <span v-for="(role, rIdx) in h.roles" :key="rIdx" class="ov-role-chip">
                          <img
                          v-if="safeImg(role.icon)"
                          :src="safeImg(role.icon)"
                          :alt="role.name"
                          class="ov-role-chip-img"
                          @error="onImgError(role.icon)"
                        />
                          <span>{{ role.name }}</span>
                        </span>
                      </div>
                      <span v-else class="ov-muted-inline">队伍未提供</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>
          </div>
        </template>
      </section>
    </template>
  </div>
</template>
