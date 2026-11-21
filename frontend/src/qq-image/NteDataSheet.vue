<script setup>
import { computed, reactive } from 'vue'
import { friendlyDataError } from '../cloud-display.js'
import { percentOf } from '../dashboard.js'
import { displayRoleValue } from '../nte-roles.js'
import { displayNteText, displayVehicleStat, imageTeams, vehicleDecorationType } from '../nte-display.js'
import { nteAssetImage } from '../nte-artwork.js'
import { GLYPHS, catalogRole } from '../nte-charts.js'
import nteIcons from '../nte-icon-catalog.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import { asset, knownRoles } from './models.js'
import { resolveNteIcon } from './role-meta.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const panel = computed(() => (props.input?.snapshot?.display_data?.panels || [])[0] || null)
const cap = computed(() => panel.value?.capability || '')
const snap = computed(() => panel.value?.snapshot || null)
const payload = computed(() => snap.value?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => (legacy.value ? {} : payload.value ?? {}))
const authError = computed(() => (snap.value?.state === 'auth_expired' ? friendlyDataError('', snap.value.state) : ''))

const list = v => (Array.isArray(v) ? v : [])
const failedUrls = reactive(new Set())
const safeImg = url => (url && !failedUrls.has(url) ? url : '')
const onImgError = url => {
  if (url) failedUrls.add(url)
}
const displayVal = v => displayRoleValue(v, '未知')
const measurable = (cur, total) => percentOf(cur, total) != null
const pctInt = (cur, total) => (measurable(cur, total) ? Math.round(percentOf(cur, total)) : null)
const pctText = (cur, total) => (measurable(cur, total) ? `${Math.round(percentOf(cur, total))}%` : null)
const exceedsTarget = (cur, total) => measurable(cur, total) && Number(cur) > Number(total)

const stateText = v => (v === true ? '已拥有' : v === false ? '未拥有' : '拥有状态未知')
const stateShort = v => (v === true ? '已拥有' : v === false ? '未拥有' : '未知')
const stateCls = v => (v === true ? 'is-owned' : v === false ? 'is-unowned' : 'is-unknown')

const roleMap = computed(() => new Map(knownRoles('nte').map(r => [String(r.id), r])))
const allKnownRoleNames = computed(() => [
  ...knownRoles('nte').map(r => r.name),
  ...Object.keys(nteIcons.roles || {}),
])
function residentInfo(id) {
  const rec = roleMap.value.get(String(id)) || catalogRole(id)
  const name = rec?.name || '名称未提供'
  const icon = resolveNteIcon(name, id, rec?.icon_url || rec?.icon)
  return { id: String(id), name, icon }
}

// ---- 2A. Exploration ----
const areas = computed(() => list(data.value.areas))
const exploreStats = computed(() => {
  let sumCur = 0
  let sumTotal = 0
  let anyMeasurable = false
  let fullCount = 0
  for (const a of areas.value) {
    if (measurable(a.current, a.total)) {
      anyMeasurable = true
      sumCur += Number(a.current)
      sumTotal += Number(a.total)
      if (Number(a.current) >= Number(a.total)) fullCount++
    }
  }
  const rate = anyMeasurable && sumTotal > 0 ? `${Math.round((sumCur / sumTotal) * 100)}%` : '—'
  return [
    { value: `${areas.value.length}`, label: '探索区域' },
    { value: anyMeasurable ? `${sumCur} / ${sumTotal}` : '未知', label: '合计收集', accent: true },
    { value: `${fullCount}`, label: `满探索 (${rate})`, accent: true },
  ]
})

// ---- 2B. Progress ----
const categories = computed(() => list(data.value.categories))
const progressPct = computed(() => pctText(data.value.completed, data.value.total))
const progressPctNum = computed(() => pctInt(data.value.completed, data.value.total))
const progressStats = computed(() => [
  { value: `${displayVal(data.value.completed)} / ${displayVal(data.value.total)}`, label: '已达成成就', accent: true },
  { value: progressPct.value || '—', label: '总完成率', accent: true },
  { value: `${displayVal(data.value.gold)}`, label: '金奖章', tone: 'gold' },
  { value: `${displayVal(data.value.silver)}`, label: '银奖章', tone: 'silver' },
  { value: `${displayVal(data.value.bronze)}`, label: '铜奖章', tone: 'bronze' },
])
const medalTotal = computed(() => {
  const nums = [data.value.gold, data.value.silver, data.value.bronze].filter(v => typeof v === 'number' && Number.isFinite(v) && v >= 0)
  return nums.length ? nums.reduce((a, b) => a + b, 0) : 0
})
const medalSegments = computed(() => [
  { key: 'gold', label: '金奖章', value: data.value.gold, color: 'linear-gradient(90deg, #f8d46c 0%, #dca02e 100%)' },
  { key: 'silver', label: '银奖章', value: data.value.silver, color: 'linear-gradient(90deg, #e2eaf8 0%, #9fb0c8 100%)' },
  { key: 'bronze', label: '铜奖章', value: data.value.bronze, color: 'linear-gradient(90deg, #e59e6a 0%, #b86c3b 100%)' },
])

// ---- 2C & 2D. Realestate / Vehicles ----
const assetEntries = computed(() => list(data.value.entries).filter(e => e && e.owned !== false))
const ownedSharePct = computed(() => pctText(data.value.owned_count, data.value.total))
const assetStats = computed(() => [
  { value: `${displayVal(data.value.owned_count)} / ${displayVal(data.value.total)}`, label: cap.value === 'vehicles' ? '拥有载具' : '拥有房产', accent: true },
  { value: ownedSharePct.value || '—', label: '图鉴收集率', accent: true },
  { value: `${assetEntries.value.length}`, label: '本页展示' },
])
function assetCover(entry) {
  return asset(nteAssetImage(cap.value, entry?.id))
}
function isShowcaseVehicle(entry) {
  if (cap.value !== 'vehicles') return false
  if (data.value.show_id != null && String(entry?.id) === String(data.value.show_id)) return true
  if (data.value.show_name && entry?.name === data.value.show_name) return true
  return false
}

// ---- 2E. Teams ----
const teamEntries = computed(() =>
  imageTeams(list(data.value.entries), list(data.value.owned_role_names), allKnownRoleNames.value),
)
function teamIcon(entry) {
  return asset(entry?.icon_url)
}
function teamDiagrams(entry) {
  return list(entry?.image_urls)
    .filter(url => /peidui|2team_rec/i.test(url))
    .map(url => asset(url))
    .filter(Boolean)
}
</script>

<template>
  <div class="ov-ds-sheet ov-nte-data">
    <p v-if="authError" class="ov-alert">{{ authError }}</p>
    <p v-if="payload === null" class="ov-empty">暂无数据，请刷新后查看</p>
    <p v-else-if="legacy" class="ov-empty">数据格式已更新，请刷新</p>

    <!-- 2A. Exploration -->
    <template v-else-if="cap === 'exploration'">
      <section class="ao-section">
        <OverviewSectionHead title="区域探索总览" :meta="`共 ${areas.length} 个区域`" />
        <OverviewStatGrid :stats="exploreStats" :columns="3" />
      </section>

      <section class="ao-section">
        <OverviewSectionHead title="分区探索明细" />
        <p v-if="!areas.length" class="ov-empty">暂无探索数据</p>
        <div v-else class="ov-ds-grid-2">
          <article v-for="(area, i) in areas" :key="area.id ?? i" class="ov-ds-card nte-area-card">
            <header class="ov-ds-card-head">
              <h3 class="ov-ds-card-title">{{ displayVal(area.name) }}</h3>
              <div class="nte-area-head-right">
                <strong class="nte-pair-val">
                  {{ displayVal(area.current) }}<span class="nte-pair-max"> / {{ displayVal(area.total) }}</span>
                </strong>
                <span v-if="pctText(area.current, area.total)" class="ov-pill is-accent">{{ pctText(area.current, area.total) }}</span>
              </div>
            </header>
            <div v-if="measurable(area.current, area.total)" class="ov-bar-track nte-bar">
              <i class="ov-bar-fill" :style="{ width: `${pctInt(area.current, area.total)}%` }" />
            </div>
            <span v-else class="ov-meter-none" aria-hidden="true" />
            <span v-if="exceedsTarget(area.current, area.total)" class="target-met">已达目标</span>

            <ul v-if="list(area.details).length" class="nte-area-details">
              <li v-for="(entry, dIdx) in list(area.details)" :key="entry.id ?? dIdx" class="nte-detail-row">
                <span class="nte-detail-k">{{ displayVal(entry.name) }}</span>
                <div class="nte-detail-bar">
                  <div v-if="measurable(entry.current, entry.total)" class="ov-bar-track is-thin nte-bar">
                    <i class="ov-bar-fill" :style="{ width: `${pctInt(entry.current, entry.total)}%` }" />
                  </div>
                  <span v-else class="ov-meter-none" aria-hidden="true" />
                </div>
                <span class="nte-detail-v">
                  <span class="nte-detail-nums">
                    {{ displayVal(entry.current) }} / {{ displayVal(entry.total) }}<template v-if="pctText(entry.current, entry.total)"> · {{ pctText(entry.current, entry.total) }}</template>
                  </span>
                  <span v-if="exceedsTarget(entry.current, entry.total)" class="target-met">已达目标</span>
                </span>
              </li>
            </ul>
          </article>
        </div>
      </section>
    </template>

    <!-- 2B. Progress (preserves .nte-card, .categories, .target-met, and aligned native <progress>) -->
    <template v-else-if="cap === 'progress'">
      <div class="ov-nte-progress nte-card">
        <section class="ao-section">
          <OverviewSectionHead title="成就总览" :meta="progressPct || ''" />
          <OverviewStatGrid :stats="progressStats" :columns="5" />
          <div class="ov-ds-card nte-prog-bars-card">
            <div class="nte-overall-row">
              <span class="nte-overall-lbl">成就收集总进度</span>
              <div class="ov-bar-track nte-bar">
                <i class="ov-bar-fill" :style="{ width: `${progressPctNum ?? 0}%` }" />
              </div>
              <strong class="nte-pair-val">{{ displayVal(data.completed) }} / {{ displayVal(data.total) }}</strong>
            </div>
            <div v-if="medalTotal > 0" class="nte-medal-bar-row">
              <span class="nte-overall-lbl">金 / 银 / 铜占比</span>
              <div class="ov-stack-bar" aria-hidden="true">
                <i
                  v-for="m in medalSegments"
                  v-show="typeof m.value === 'number' && m.value > 0"
                  :key="m.key"
                  :style="{ flex: m.value, background: m.color }"
                />
              </div>
              <div class="nte-medal-dots">
                <span v-for="m in medalSegments" :key="m.key" class="nte-medal-tag">
                  <i class="ov-legend-dot" :style="{ background: m.color }" aria-hidden="true" />
                  {{ m.label }} {{ displayVal(m.value) }}
                </span>
              </div>
            </div>
          </div>
        </section>

        <section class="ao-section">
          <OverviewSectionHead title="成就分类明细" :meta="`${categories.length} 个分类`" />
          <div v-if="categories.length" class="ov-ds-card nte-cats-card">
            <ul class="nte-cat-list categories">
              <li v-for="(cat, i) in categories" :key="cat.id ?? i" class="nte-cat-row">
                <span class="nte-cat-name">{{ displayVal(cat.name) }}</span>
                <progress
                  v-if="measurable(cat.current, cat.total)"
                  class="nte-progress"
                  :value="cat.current"
                  :max="cat.total"
                  :aria-label="cat.name || '成就分类'"
                />
                <span v-else class="ov-meter-none" aria-hidden="true" />
                <span class="nte-cat-val">
                  <span class="nte-cat-nums">{{ displayVal(cat.current) }} / {{ displayVal(cat.total) }}</span>
                  <span v-if="exceedsTarget(cat.current, cat.total)" class="target-met">已达目标</span>
                </span>
              </li>
            </ul>
          </div>
          <p v-else class="ov-empty">暂无分类明细</p>
        </section>
      </div>
    </template>

    <!-- 2C & 2D. Realestate / Vehicles (preserves .asset-grid .asset, .asset-cover >= 100px, .asset-name beside cover) -->
    <template v-else-if="cap === 'realestate' || cap === 'vehicles'">
      <section class="ao-section">
        <OverviewSectionHead
          :title="cap === 'vehicles' ? '载具总览' : '房产总览'"
          :meta="cap === 'vehicles' && (data.show_name || data.show_id) ? `展示载具：${data.show_name || data.show_id}` : ''"
        />
        <OverviewStatGrid :stats="assetStats" :columns="3" />
      </section>

      <section class="ao-section">
        <OverviewSectionHead :title="cap === 'vehicles' ? '载具明细' : '房产明细'" :meta="`${assetEntries.length} 项`" />
        <p v-if="!assetEntries.length" class="ov-empty">
          {{ list(data.entries).length ? '暂无已拥有的条目' : '暂无资产明细' }}
        </p>
        <div v-else class="asset-grid nte-asset-grid" :class="{ 'is-single': assetEntries.length === 1 }">
          <article v-for="(entry, idx) in assetEntries" :key="`${entry.id}-${idx}`" class="asset ov-ds-card nte-asset-card">
            <header class="nte-asset-head">
              <span class="asset-cover nte-asset-cover" aria-hidden="true">
                <img
                  v-if="safeImg(assetCover(entry))"
                  :src="safeImg(assetCover(entry))"
                  alt=""
                  @error="onImgError(assetCover(entry))"
                />
                <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
                  <path :d="cap === 'vehicles' ? GLYPHS.car : GLYPHS.house" />
                </svg>
              </span>
              <div class="nte-asset-title-col">
                <strong class="asset-name nte-asset-name">{{ entry.name || `${cap === 'vehicles' ? '载具' : '房产'} ${entry.id}` }}</strong>
                <div class="nte-asset-pills">
                  <span class="ov-pill" :class="stateCls(entry.owned)">{{ stateText(entry.owned) }}</span>
                  <span v-if="isShowcaseVehicle(entry)" class="ov-pill is-accent">展示载具</span>
                  <span v-if="cap === 'realestate' && list(entry.resident_ids).length" class="ov-pill">
                    入住 {{ list(entry.resident_ids).length }}
                  </span>
                  <span v-if="cap === 'realestate' && list(entry.furniture).length" class="ov-pill">
                    家具 {{ list(entry.furniture).length }}
                  </span>
                </div>
              </div>
            </header>

            <template v-if="cap === 'realestate'">
              <div class="nte-asset-subblock">
                <h4 class="nte-sub-title">入住角色</h4>
                <ul v-if="list(entry.resident_ids).length" class="nte-residents">
                  <li v-for="(id, rIdx) in entry.resident_ids" :key="`${id}-${rIdx}`" class="ov-role-chip">
                    <img
                      v-if="safeImg(residentInfo(id).icon)"
                      :src="safeImg(residentInfo(id).icon)"
                      :alt="residentInfo(id).name"
                      class="ov-role-chip-img"
                      @error="onImgError(residentInfo(id).icon)"
                    />
                    <span>{{ residentInfo(id).name }}</span>
                  </li>
                </ul>
                <p v-else class="ov-muted-note">未提供入住角色</p>
              </div>

              <div class="nte-asset-subblock">
                <h4 class="nte-sub-title">家具清单</h4>
                <ul v-if="list(entry.furniture).length" class="nte-furniture-list">
                  <li v-for="(item, fIdx) in entry.furniture" :key="fIdx" class="nte-furniture-row">
                    <span class="nte-furniture-name">{{ item.name || `家具 ${item.id}` }}</span>
                    <span class="ov-pill" :class="stateCls(item.owned)">{{ stateShort(item.owned) }}</span>
                  </li>
                </ul>
                <p v-else class="ov-muted-note">暂无家具明细</p>
              </div>
            </template>

            <template v-else>
              <div class="nte-asset-subblock">
                <h4 class="nte-sub-title">基础属性</h4>
                <div v-if="list(entry.base).length" class="nte-veh-base">
                  <div v-for="(stat, bIdx) in entry.base" :key="bIdx" class="nte-veh-stat">
                    <span class="nte-veh-k">{{ stat.name || '未命名属性' }}</span>
                    <strong class="nte-veh-v">{{ displayVehicleStat(stat) }}</strong>
                  </div>
                </div>
                <p v-else class="ov-muted-note">未提供基础属性</p>
              </div>

              <div class="nte-asset-subblock">
                <h4 class="nte-sub-title">进阶属性</h4>
                <ul v-if="list(entry.advanced).length" class="nte-veh-adv">
                  <li v-for="(stat, aIdx) in entry.advanced" :key="aIdx" class="nte-veh-adv-row">
                    <span class="nte-veh-adv-k">{{ stat.name || '未命名属性' }}</span>
                    <div class="nte-veh-adv-bar">
                      <div v-if="percentOf(stat.value, stat.maximum) !== null" class="ov-bar-track is-thin nte-bar">
                        <i class="ov-bar-fill" :style="{ width: `${Math.round(percentOf(stat.value, stat.maximum))}%` }" />
                      </div>
                      <span v-else class="ov-meter-none" aria-hidden="true" />
                    </div>
                    <strong class="nte-veh-adv-v">{{ displayVehicleStat(stat) }} / {{ displayVal(stat.maximum) }}</strong>
                  </li>
                </ul>
                <p v-else class="ov-muted-note">未提供进阶属性</p>
              </div>

              <div v-if="list(entry.models).length" class="nte-asset-subblock">
                <h4 class="nte-sub-title">装饰 / 涂装</h4>
                <div class="nte-deco-chips">
                  <span v-for="(model, mIdx) in entry.models" :key="mIdx" class="ov-pill">
                    {{ vehicleDecorationType(model.type) }}
                  </span>
                </div>
              </div>
            </template>
          </article>
        </div>
      </section>
    </template>

    <!-- 2E. Teams -->
    <template v-else-if="cap === 'teams'">
      <section class="ao-section">
        <OverviewSectionHead title="官方配队推荐" :meta="`共 ${teamEntries.length} 套配队`" />
        <p v-if="!teamEntries.length" class="ov-empty">暂无官方配队推荐</p>
        <div v-else class="nte-teams-list">
          <article v-for="(entry, idx) in teamEntries" :key="`${entry.id}-${idx}`" class="ov-ds-card nte-team-card">
            <header class="nte-team-head">
              <img
                v-if="safeImg(teamIcon(entry))"
                :src="safeImg(teamIcon(entry))"
                :alt="entry.name || '配队'"
                class="nte-team-icon"
                @error="onImgError(teamIcon(entry))"
              />
              <div class="nte-team-title-wrap">
                <h3 class="ov-ds-card-title">{{ entry.name || `推荐配队 ${entry.id ?? idx + 1}` }}</h3>
                <span class="ov-pill is-accent">官方推荐</span>
              </div>
            </header>
            <p class="nte-team-desc">{{ displayNteText(entry.description) || '未提供推荐说明' }}</p>
            <div v-if="teamDiagrams(entry).some(u => safeImg(u))" class="nte-team-diagrams">
              <img
                v-for="(url, uIdx) in teamDiagrams(entry).filter(u => safeImg(u))"
                :key="uIdx"
                :src="safeImg(url)"
                :alt="`${entry.name || '配队推荐'}配队图 ${uIdx + 1}`"
                class="nte-team-diagram-img"
                @error="onImgError(url)"
              />
            </div>
          </article>
        </div>
      </section>
    </template>
  </div>
</template>
