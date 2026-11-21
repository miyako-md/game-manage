<script setup>
import { computed, reactive } from 'vue'
import { friendlyDataError } from '../cloud-display.js'
import {
  profileReport,
  rows,
  displayValue as display,
  sourceName as named,
  collectionTotals,
  medalCategoryParts,
  platedSummary,
} from '../endfield-reports.js'
import { shipPercent, trustStage } from '../endfield-ship.js'
import { challengeReport, CHALLENGE_KINDS, stageStates } from '../endfield-challenges.js'
import { displayBeijing } from '../time.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import { asset } from './models.js'
import { resolveEndfieldIcon } from './role-meta.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const EF_COLORS = ['#ffd100', '#72b8ff', '#6ee0b8', '#a6adb8', '#676d78']
const failedUrls = reactive(new Set())
const safeImg = url => (url && !failedUrls.has(url) ? url : '')
const onImgError = url => {
  if (url) failedUrls.add(url)
}

const panel = computed(() => (props.input?.snapshot?.display_data?.panels || [])[0] || null)
const cap = computed(() => panel.value?.capability || '')
const snap = computed(() => panel.value?.snapshot || null)
const payload = computed(() => snap.value?.payload ?? null)
const authError = computed(() => (snap.value?.state === 'auth_expired' ? friendlyDataError('', snap.value.state) : ''))

const report = computed(() => profileReport(payload.value))
const timeText = v => (typeof v === 'string' && v ? displayBeijing(v) : '未知')
const percentOf = (cur, total) =>
  typeof cur === 'number' && Number.isFinite(cur) && typeof total === 'number' && Number.isFinite(total) && total > 0
    ? Math.round(Math.max(0, Math.min(1, cur / total)) * 100)
    : null

// ---- 3A. Exploration (Regions) ----
const regions = computed(() => rows(report.value.regions?.items))
const regionsSummary = computed(() => report.value.regions?.summary || {})
function areaCollections(area) {
  if (Array.isArray(area.collections)) return area.collections
  return [
    ['puzzles', '醚质'],
    ['chests', '宝箱'],
    ['equipment_chests', '装备制造模板'],
    ['pieces', '维修灵感点'],
    ['blackboxes', '协议采录桩'],
  ].map(([key, label]) => ({ key, label, current: area[key]?.count, total: area[key]?.total }))
}
function regionTotals(region) {
  return collectionTotals(rows(region.areas || region.levels).map(areaCollections))
}
function settlementCount(region) {
  if (region.settlements_available === false) return null
  if (region.settlements_available === true || rows(region.settlements).length) return rows(region.settlements).length
  return null
}
function regionAreaCount(region) {
  return rows(region.areas || region.levels).length
}
const totalAreaCount = computed(() => regions.value.reduce((s, r) => s + regionAreaCount(r), 0))
const explorationStats = computed(() => [
  { value: display(regionsSummary.value.region_count ?? (regions.value.length || null)), label: '建设地区', accent: true },
  { value: display(regionsSummary.value.settlement_count), label: '据点总数' },
  { value: `${totalAreaCount.value}`, label: '下辖区域' },
])

// ---- 3B. Ship ----
const ship = computed(() => report.value.ship || {})
const rooms = computed(() => rows(ship.value.rooms))
const shipSummary = computed(() => ship.value.summary || {})
const shipStats = computed(() => [
  { value: display(shipSummary.value.room_count), label: '舱室总数', accent: true },
  { value: display(shipSummary.value.staffed_rooms), label: '有驻守舱室' },
  { value: display(shipSummary.value.operator_slots), label: '驻守席位' },
])
function residentName(op) {
  return op?.name || op?.id || op?.charId || '驻守干员'
}
function residentAvatar(op) {
  return resolveEndfieldIcon(residentName(op), op?.avatar_url, op)
}
function residentTrustStage(op) {
  return trustStage(op?.trust_percent, op?.trust_level_name)
}

// ---- 3C. Honor ----
const honor = computed(() => report.value.honor || { summary: { declared_count: payload.value?.achievements?.count }, items: [] })
const medals = computed(() => rows(honor.value.items))
const categoryParts = computed(() => medalCategoryParts(medals.value, 5))
const categoryTotal = computed(() => categoryParts.value.reduce((s, p) => s + p.value, 0))
const plating = computed(() => platedSummary(medals.value))
const honorStats = computed(() => {
  const list = [
    { value: display(honor.value.summary?.declared_count), label: '来源成就总数', accent: true },
    { value: display(honor.value.summary?.listed_count), label: '已记录奖章' },
  ]
  if (plating.value.listed && plating.value.known === plating.value.listed) {
    list.push({ value: `${plating.value.plated}`, label: '已镀层奖章', accent: true })
  }
  return list
})

// ---- 3D. Combat ----
const rawReports = computed(() => (Array.isArray(payload.value?.reports) ? payload.value.reports : []))
const challengeSections = computed(() =>
  rawReports.value.map((raw, idx) => {
    const kind = raw?.kind || ''
    const label = CHALLENGE_KINDS.find(([id]) => id === kind)?.[1] || '挑战'
    const normalized = challengeReport({ report: raw }, kind)
    const errText = typeof raw?.error === 'string' ? raw.error : ''
    const isStale = !!(normalized.stale || errText)
    const stats = [{ value: display(normalized.summary?.listed_count), label: '已记录', accent: true }]
    if (kind === 'crisis') {
      stats.push(
        { value: display(normalized.summary?.highest), label: '历史最高值', accent: true },
        { value: display(normalized.summary?.challenge_count), label: '挑战次数' },
      )
    }
    return {
      key: `${kind}-${idx}`,
      kind,
      label,
      report: normalized,
      isStale,
      stats,
    }
  }),
)
const passLabel = v => (v === true ? '已通关' : v === false ? '未通关' : '状态未知')
const stageSummaryLabel = group => {
  const st = stageStates([group])
  return `${st.passed}/${rows(group.stages).length} 通关`
}
</script>

<template>
  <div class="ov-ds-sheet ov-ef-data" :class="{ 'ov-ef-combat': cap === 'combat' }">
    <p v-if="authError" class="ov-alert">{{ authError }}</p>

    <!-- 3A. Exploration (Regions) — preserves .ef-region, .ef-totals > li; no .ef-settlement / .ef-subsection / .ring-gauge / 剩余 -->
    <template v-if="cap === 'exploration'">
      <section class="ao-section">
        <OverviewSectionHead
          title="地区建设"
          en="REGION CONSTRUCTION"
          index="01"
          :meta="`地区数 ${display(regionsSummary.region_count)}`"
        />
        <OverviewStatGrid :stats="explorationStats" :columns="3" />
      </section>

      <section class="ao-section">
        <OverviewSectionHead title="收集与建设明细" en="REGIONAL TOTALS" index="02" />
        <p v-if="!regions.length" class="ov-empty">尚无地区建设资料。</p>
        <div v-else class="ef-ds-regions">
          <section v-for="(region, rIdx) in regions" :key="region.id ?? rIdx" class="ef-region ov-ds-card ef-ds-card">
            <header class="ef-ds-card-head">
              <div class="ef-ds-title-group">
                <h3 class="ov-ds-card-title">{{ named(region) }}</h3>
                <span class="ef-ds-badge">等级 {{ display(region.level) }}</span>
              </div>
              <div class="ef-ds-region-facts">
                <div class="ef-ds-fact">
                  <span class="ef-ds-fact-k">地区调度券</span>
                  <strong class="ef-ds-fact-v">
                    {{ display(region.money?.current ?? region.money?.count) }}
                    <span class="ef-ds-fact-max">/ {{ display(region.money?.total) }}</span>
                  </strong>
                </div>
                <div class="ef-ds-fact">
                  <span class="ef-ds-fact-k">据点</span>
                  <strong class="ef-ds-fact-v">{{ display(settlementCount(region)) }}</strong>
                </div>
                <div class="ef-ds-fact">
                  <span class="ef-ds-fact-k">区域</span>
                  <strong class="ef-ds-fact-v">{{ regionAreaCount(region) }}</strong>
                </div>
              </div>
            </header>

            <ul v-if="regionTotals(region).length" class="ef-totals ef-ds-totals">
              <li v-for="item in regionTotals(region)" :key="item.key" class="ef-ds-total-row">
                <div class="ef-ds-total-top">
                  <span class="ef-ds-total-k">{{ item.label }}</span>
                  <strong class="ef-ds-total-v">
                    {{ display(item.current) }} / {{ display(item.total) }}<span v-if="item.partial" class="ef-ds-partial"> · 部分区域未知</span>
                  </strong>
                </div>
                <div v-if="item.percent != null" class="ov-bar-track ef-bar is-thin">
                  <i class="ov-bar-fill" :style="{ width: `${item.percent}%` }" />
                </div>
                <span v-else class="ov-meter-none" aria-hidden="true" />
              </li>
            </ul>
            <ul v-else class="ef-totals ef-ds-totals is-empty" aria-hidden="true" />
            <p v-if="!regionTotals(region).length" class="ov-muted-note">暂无下辖区域收集明细。</p>
          </section>
        </div>
      </section>
    </template>

    <!-- 3B. Ship — preserves .ef-resident .unknown-meter (width >= 120px), shows 0% & 未知 -->
    <template v-else-if="cap === 'ship'">
      <section class="ao-section">
        <OverviewSectionHead title="帝江号概览" en="SPACESHIP OVERVIEW" index="01" meta="快照换算" />
        <OverviewStatGrid :stats="shipStats" :columns="3" />
      </section>

      <section class="ao-section">
        <OverviewSectionHead title="舱室驻守" en="CABIN ROSTER" index="02" :meta="`${rooms.length} 间舱室`" />
        <p v-if="!rooms.length" class="ov-empty">尚无帝江号资料。</p>
        <div v-else class="ef-ds-rooms">
          <section v-for="(room, rIdx) in rooms" :key="room.id ?? rIdx" class="ov-ds-card ef-ds-card ef-ds-room">
            <header class="ef-ds-card-head">
              <h3 class="ov-ds-card-title">{{ room.name || '舱室' }}</h3>
              <span class="ef-ds-badge is-accent">LV. {{ display(room.level) }}</span>
            </header>

            <p v-if="!rows(room.operators).length" class="ov-muted-note">
              {{ room.operators_available === true ? '当前没有驻守干员记录。' : '尚未采集驻守干员资料。' }}
            </p>
            <div v-else class="ef-ds-residents">
              <article
                v-for="(op, oIdx) in rows(room.operators)"
                :key="op.id || op.charId || oIdx"
                class="ef-resident ef-ds-resident"
              >
                <div class="ef-ds-res-ident">
                  <span class="ef-ds-res-avatar">
                    <img
                      v-if="safeImg(residentAvatar(op))"
                      :src="safeImg(residentAvatar(op))"
                      :alt="residentName(op)"
                      @error="onImgError(residentAvatar(op))"
                    />
                    <span v-else aria-hidden="true">{{ [...residentName(op)][0] || '干' }}</span>
                  </span>
                  <strong class="ef-ds-res-name">{{ residentName(op) }}</strong>
                </div>

                <div class="ef-ds-res-meters">
                  <div class="ef-ds-res-meter">
                    <div class="ef-ds-meter-head">
                      <span class="ef-ds-meter-k">心情</span>
                      <strong class="ef-ds-meter-v">{{ shipPercent(op.mood_percent) }}</strong>
                    </div>
                    <div v-if="op.mood_percent != null" class="ov-bar-track ef-bar is-thin">
                      <i class="ov-bar-fill" :style="{ width: `${Math.max(0, Math.min(100, op.mood_percent))}%` }" />
                    </div>
                    <span v-else class="unknown-meter">
                      {{ op.mood_raw > 10000 ? '超出模型范围' : '观测值未知' }}
                    </span>
                  </div>

                  <div class="ef-ds-res-meter">
                    <div class="ef-ds-meter-head">
                      <span class="ef-ds-meter-k">信赖 · {{ op.trust_level_name || '阶段未知' }}</span>
                      <strong class="ef-ds-meter-v">{{ shipPercent(op.trust_percent) }}</strong>
                    </div>
                    <div v-if="residentTrustStage(op)" class="ov-bar-track ef-bar is-thin">
                      <i class="ov-bar-fill" :style="{ width: `${residentTrustStage(op).value}%` }" />
                    </div>
                    <span v-else class="unknown-meter">观测值未知</span>
                  </div>
                </div>
              </article>
            </div>
          </section>
        </div>
      </section>
    </template>

    <!-- 3C. Honor — icon wall with medal names, no per-medal category text -->
    <template v-else-if="cap === 'honor'">
      <section class="ao-section">
        <OverviewSectionHead title="光荣之路" en="HONOR ARCHIVE" index="01" :meta="medals.length ? `已录 ${medals.length} 枚` : ''" />
        <OverviewStatGrid :stats="honorStats" :columns="honorStats.length" />
      </section>

      <section v-if="categoryParts.length > 1" class="ao-section">
        <OverviewSectionHead title="奖章分类分布" en="CATEGORY SPLIT" index="02" :meta="`共 ${categoryParts.length} 类`" />
        <div class="ov-dist-panel">
          <div class="ov-stack-bar" aria-hidden="true">
            <i
              v-for="(part, idx) in categoryParts"
              v-show="part.value > 0"
              :key="part.label"
              :style="{ flex: part.value, background: EF_COLORS[idx % EF_COLORS.length] }"
            />
          </div>
          <ul class="ov-dist-legend">
            <li v-for="(part, idx) in categoryParts" :key="part.label">
              <i class="ov-legend-dot" :style="{ background: EF_COLORS[idx % EF_COLORS.length] }" aria-hidden="true" />
              <span>{{ part.label }}</span>
              <strong class="ov-legend-val">{{ part.value }}</strong>
              <span v-if="categoryTotal > 0">({{ Math.round((part.value / categoryTotal) * 100) }}%)</span>
            </li>
          </ul>
        </div>
      </section>

      <section class="ao-section">
        <OverviewSectionHead
          title="奖章陈列墙"
          en="MEDAL WALL"
          :index="categoryParts.length > 1 ? '03' : '02'"
          :meta="medals.length ? `${medals.length} 枚` : ''"
        />
        <p v-if="!medals.length" class="ov-empty">
          {{ honor.available === true ? '当前档案没有奖章记录。' : '尚未采集奖章详情，请刷新档案。' }}
        </p>
        <div v-else class="ef-ds-medal-wall">
          <figure
            v-for="(medal, mIdx) in medals"
            :key="medal.id ?? mIdx"
            class="ef-ds-medal"
            :class="{ 'is-plated': medal.is_plated === true }"
          >
            <div class="ef-ds-medal-frame">
              <img
                v-if="safeImg(asset(medal.icon_url))"
                :src="safeImg(asset(medal.icon_url))"
                :alt="medal.name || '奖章'"
                class="ef-ds-medal-img"
                @error="onImgError(asset(medal.icon_url))"
              />
              <span v-else class="ef-ds-medal-glyph" aria-hidden="true">{{ [...(medal.name || '奖')][0] }}</span>
            </div>
            <figcaption class="ef-ds-medal-name">{{ medal.name || '未命名奖章' }}</figcaption>
            <span v-if="medal.is_plated === true" class="ef-ds-plated-pill">已镀层</span>
          </figure>
        </div>
      </section>
    </template>

    <!-- 3D. Combat — preserves counter(ef-block) ticks/tick_titles, per-kind observation times, and 已有资料待更新 -->
    <template v-else-if="cap === 'combat'">
      <p v-if="!challengeSections.length" class="ov-empty">尚无挑战记录，请在看板读取后查看。</p>
      <template v-else>
        <section v-for="sec in challengeSections" :key="sec.key" class="ef-cb-section">
          <header class="ef-cb-head">
            <h2 class="ef-cb-title">{{ sec.label }} · 挑战记录</h2>
            <div class="ef-cb-status">
              <span v-if="sec.report.available && sec.stats.length === 1" class="ef-ds-badge is-accent">
                已记录 {{ sec.stats[0].value }}
              </span>
              <span class="ef-cb-time">{{ sec.label }}观测时间 {{ timeText(sec.report.fetched_at) }}（北京时间）</span>
              <span v-if="sec.report.available && sec.isStale" class="ef-cb-stale">已有资料待更新</span>
            </div>
          </header>

          <p v-if="sec.report.supported === false" class="ov-empty">当前账号暂不支持{{ sec.label }}挑战。</p>
          <p v-else-if="!sec.report.available" class="ov-empty">尚未采集{{ sec.label }}记录。</p>
          <template v-else>
            <OverviewStatGrid v-if="sec.stats.length > 1" :stats="sec.stats" :columns="sec.stats.length" />

            <p v-if="!sec.report.records.length" class="ov-empty">尚无已记录的{{ sec.label }}挑战。</p>
            <div v-else class="ef-cb-records" :class="{ 'is-two-col': sec.kind === 'crisis' && sec.report.records.length >= 2 }">
              <article
                v-for="(record, rIdx) in sec.report.records"
                :key="record.id ?? rIdx"
                class="ov-ds-card ef-ds-card ef-cb-record"
              >
              <header class="ef-cb-rec-head">
                <h3 class="ef-cb-rec-title">{{ record.name || (record.id != null ? `记录 ${record.id}` : `挑战记录 ${rIdx + 1}`) }}</h3>
                <span v-if="sec.kind === 'war'" class="ef-cb-result" :class="{ 'is-latest': rIdx === 0 }">{{ display(record.stars) }} 星</span>
                <span v-else-if="sec.kind === 'crisis'" class="ef-cb-result" :class="{ 'is-latest': rIdx === 0 }">{{ display(record.result) }}</span>
              </header>

              <p v-if="record.start_at || record.end_at" class="ef-cb-period">
                {{ timeText(record.start_at) }} — {{ timeText(record.end_at) }}
              </p>

              <!-- War Weeks -->
              <template v-if="sec.kind === 'war'">
                <p v-if="!rows(record.weeks).length" class="ov-muted-note">尚无轮换明细。</p>
                <div v-else class="ef-cb-weeks" :class="{ 'is-two-col': rows(record.weeks).length >= 2 }">
                  <article v-for="(week, wIdx) in rows(record.weeks)" :key="week.id ?? wIdx" class="ef-cb-week">
                    <header class="ef-cb-week-head">
                      <h4 class="ef-cb-week-title">{{ week.name || `轮换 ${wIdx + 1}` }}</h4>
                      <span class="ef-ds-badge is-accent">{{ display(week.stars) }} 星</span>
                    </header>
                    <div v-if="rows(week.groups).length" class="ef-cb-groups">
                      <div v-for="(group, gIdx) in rows(week.groups)" :key="gIdx" class="ef-cb-group">
                        <div class="ef-cb-group-head">
                          <strong class="ef-cb-group-name">{{ group.name || `关卡组 ${gIdx + 1}` }}</strong>
                          <span class="ef-cb-group-stars">★ {{ display(group.stars) }} · {{ stageSummaryLabel(group) }}</span>
                        </div>
                        <div v-if="rows(group.stages).length" class="ef-cb-pips" aria-hidden="true">
                          <i
                            v-for="(st, sIdx) in rows(group.stages)"
                            :key="sIdx"
                            :class="{ 'is-pass': st.passed === true, 'is-fail': st.passed === false }"
                          />
                        </div>
                        <ul v-if="rows(group.stages).length" class="ef-cb-stages">
                          <li v-for="(st, sIdx) in rows(group.stages)" :key="sIdx" class="ef-cb-stage">
                            <span class="ef-cb-diff">{{ st.difficulty || '未知' }}</span>
                            <span class="ef-cb-stage-name">{{ st.name || '未命名关卡' }}</span>
                            <span class="ef-cb-stage-state" :class="{ 'is-pass': st.passed === true, 'is-fail': st.passed === false }">
                              {{ passLabel(st.passed) }}
                            </span>
                          </li>
                        </ul>
                        <p v-else class="ov-muted-note">尚无关卡明细。</p>
                      </div>
                    </div>
                    <p v-else class="ov-muted-note">尚无关卡组明细。</p>
                  </article>
                </div>
              </template>

              <!-- Monument Groups -->
              <template v-else-if="sec.kind === 'monument'">
                <div v-if="rows(record.groups).length" class="ef-cb-groups" :class="{ 'is-two-col': rows(record.groups).length >= 2 }">
                  <div v-for="(group, gIdx) in rows(record.groups)" :key="gIdx" class="ef-cb-group">
                    <div class="ef-cb-group-head">
                      <strong class="ef-cb-group-name">{{ group.name || `关卡组 ${gIdx + 1}` }}</strong>
                      <span class="ef-cb-group-stars">★ {{ display(group.stars) }} · {{ stageSummaryLabel(group) }}</span>
                    </div>
                    <div v-if="rows(group.stages).length" class="ef-cb-pips" aria-hidden="true">
                      <i
                        v-for="(st, sIdx) in rows(group.stages)"
                        :key="sIdx"
                        :class="{ 'is-pass': st.passed === true, 'is-fail': st.passed === false }"
                      />
                    </div>
                    <ul v-if="rows(group.stages).length" class="ef-cb-stages">
                      <li v-for="(st, sIdx) in rows(group.stages)" :key="sIdx" class="ef-cb-stage">
                        <span class="ef-cb-diff">{{ st.difficulty || '未知' }}</span>
                        <span class="ef-cb-stage-name">{{ st.name || '未命名关卡' }}</span>
                        <span class="ef-cb-stage-state" :class="{ 'is-pass': st.passed === true, 'is-fail': st.passed === false }">
                          {{ passLabel(st.passed) }}
                        </span>
                      </li>
                    </ul>
                    <p v-else class="ov-muted-note">尚无关卡明细。</p>
                  </div>
                </div>
                <p v-else class="ov-muted-note">尚无关卡组明细。</p>
              </template>

              <!-- Crisis -->
              <div v-else class="ef-cb-crisis-row">
                <span class="ef-cb-crisis-k">通关状态</span>
                <strong class="ef-cb-stage-state" :class="{ 'is-pass': record.passed === true, 'is-fail': record.passed === false }">
                  {{ passLabel(record.passed) }}
                </strong>
              </div>
              </article>
            </div>

            <!-- War Honors -->
            <section v-if="sec.kind === 'war' && rows(sec.report.honors).length" class="ov-ds-card ef-ds-card ef-cb-honors-card">
              <header class="ef-cb-honor-head">
                <h3 class="ef-cb-honor-title">已有荣誉</h3>
                <span class="ef-ds-badge">{{ sec.report.honors.length }} 条</span>
              </header>
              <div class="ef-cb-honors-grid">
                <div v-for="(h, hIdx) in sec.report.honors" :key="hIdx" class="ef-cb-honor-tile">
                  <div class="ef-cb-honor-top">
                    <strong class="ef-cb-honor-name">{{ h.name || '未命名荣誉' }}</strong>
                    <span class="ef-ds-badge is-accent">{{ display(h.stars) }} 星</span>
                  </div>
                  <span class="ef-cb-honor-time">首次通关 {{ timeText(h.first_pass_at) }}</span>
                </div>
              </div>
            </section>
          </template>
        </section>
      </template>
    </template>
  </div>
</template>
