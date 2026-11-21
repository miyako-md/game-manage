<script setup>
import { computed, reactive } from 'vue'
import { nteItemLabel } from '../nte-display.js'
import { displayBeijing } from '../time.js'
import { safeUrl } from '../calendar.js'
import { finiteValue } from '../dashboard.js'
import { gachaRating, gachaTone, luckTone, officialPullIcon, pullTime } from '../nte-charts.js'
import { nteRewardIcon } from '../nte-icons.js'
import { ledgerDate, pityLabel, poolLabel, resultLabel } from '../nte-gacha-api.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import { asset, knownRoles } from './models.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const failedImages = reactive(new Set())
const markFailed = url => {
  if (url) failedImages.add(url)
}

const snap = computed(() => props.input?.snapshot || {})
const displayData = computed(() => snap.value.display_data || {})
const gachaSnap = computed(() => {
  if (snap.value.kind === 'nte_gacha') return displayData.value.snapshot || null
  const panel = (displayData.value.panels || []).find(p => p.capability === 'gacha')
  return panel?.snapshot || null
})
const ledger = computed(() => displayData.value.ledger || null)
const roles = computed(() => {
  const list = displayData.value.roles
  return Array.isArray(list) && list.length ? list : knownRoles('nte')
})

const payload = computed(() => gachaSnap.value?.payload || null)
const legacy = computed(() => Boolean(payload.value && payload.value.schema_version !== 1))
const pools = computed(() => (!legacy.value && Array.isArray(payload.value?.pools) ? payload.value.pools : []))

const known = value => finiteValue(value) !== null && value >= 0
const show = value => (known(value) ? value : '未知')
const average = value => (known(value) ? Number(value.toFixed(1)) : '未知')
const scale = pool => (known(pool?.guarantee) && pool.guarantee > 0 ? pool.guarantee : null)

const officialTitle = computed(() =>
  !legacy.value && typeof payload.value?.luck_title === 'string' ? payload.value.luck_title : '',
)
const titleTone = computed(() => luckTone(payload.value?.luck_type))
const fetched = computed(() => (gachaSnap.value?.fetched_at ? displayBeijing(gachaSnap.value.fetched_at) : '未提供'))

const totalDraws = computed(() => pools.value.reduce((sum, p) => sum + (known(p.total_draws) ? p.total_draws : 0), 0))
const totalS = computed(() => pools.value.reduce((sum, p) => sum + (known(p.s_count) ? p.s_count : 0), 0))

const summaryStats = computed(() => {
  const stats = [
    { value: `${pools.value.length}`, label: '统计卡池' },
    { value: `${totalDraws.value}`, label: '总抽数' },
    { value: `${totalS.value}`, label: '出 S 总数', accent: true },
  ]
  if (ledger.value) {
    stats.push({ value: `${ledger.value.total_records ?? 0}`, label: '逐抽账本', accent: true })
  }
  return stats
})

const historyGroups = computed(() =>
  pools.value
    .map(pool => ({ pool, entries: Array.isArray(pool.details) ? pool.details : null }))
    .filter(group => group.entries),
)

const roleIcons = computed(() => new Map(roles.value.map(role => [String(role.id), role.icon_url])))
function pullIconUrl(entry) {
  const id = String(entry.item_id || '')
  for (const raw of [roleIcons.value.get(id), nteRewardIcon({ id, name: entry.name }), officialPullIcon(id)]) {
    const allowed = asset(raw)
    const url = safeUrl(allowed) || (allowed && allowed.startsWith('/') ? allowed : '')
    if (url && !failedImages.has(raw) && !failedImages.has(url)) return url
  }
  return null
}

function ledgerIconUrl(row) {
  const raw = nteRewardIcon({ id: row.reward_id, name: row.reward_name, type: row.reward_type })
  const url = asset(raw)
  return url && !failedImages.has(url) ? url : ''
}

function barStyle(entry, pool) {
  const limit = scale(pool)
  if (!known(entry.pity) || !limit) return { width: '0%' }
  return { width: `${Math.min(100, (entry.pity / limit) * 100)}%` }
}

function obtained(value) {
  const time = pullTime(value)
  return time == null ? '时间未提供' : displayBeijing(time)
}

const ledgerPools = computed(() => (Array.isArray(ledger.value?.pools) ? ledger.value.pools : []))
const ledgerRecords = computed(() => (Array.isArray(ledger.value?.records) ? ledger.value.records : []))
</script>

<template>
  <div class="cloud-gacha ov-nte-gacha">
    <div v-if="!payload" class="ov-empty-card">
      <p class="ov-empty-title">暂无抽卡数据，请刷新后查看。</p>
    </div>
    <div v-else-if="legacy" class="ov-empty-card">
      <p class="ov-empty-title">抽卡数据格式已升级，请刷新后查看。</p>
    </div>
    <template v-else>
      <OverviewSectionHead title="社区抽卡统计" meta="塔吉多近期统计" />

      <div class="nte-gc-banner">
        <span class="nte-gc-source-tag">社区统计</span>
        <span v-if="officialTitle" class="luck-title" :class="titleTone">
          <small>近期评价</small>
          <strong>{{ officialTitle }}</strong>
        </span>
        <span v-if="gachaSnap?.stale" class="ov-gc-badge is-warn">待更新</span>
        <span class="nte-gc-fetched num-nowrap">更新于 {{ fetched }}</span>
      </div>

      <OverviewStatGrid v-if="pools.length" :stats="summaryStats" :columns="summaryStats.length >= 4 ? 4 : 3" />

      <p v-if="!pools.length" class="ov-empty">暂无卡池统计。</p>
      <div v-else class="pool-overview nte-gc-pools" :class="`cols-${Math.min(3, Math.max(1, pools.length))}`">
        <article v-for="(pool, index) in pools" :key="index" class="pool-stat nte-gc-pool-card">
          <h3>{{ pool.name || '未命名卡池' }}</h3>
          <p class="draw-total"><strong class="num-nowrap">{{ show(pool.total_draws) }}</strong><span>抽</span></p>
          <div class="nte-gc-pool-kvs">
            <div class="nte-gc-kv">
              <span>出 S 数量</span>
              <b class="num-nowrap">{{ show(pool.s_count) }}</b>
            </div>
            <div class="nte-gc-kv">
              <span>S 级平均</span>
              <b class="num-nowrap">{{ average(pool.average) }}</b>
            </div>
            <div v-if="scale(pool)" class="nte-gc-kv">
              <span>本池标尺</span>
              <b class="num-nowrap">{{ scale(pool) }} 抽</b>
            </div>
          </div>
        </article>
      </div>

      <section v-for="(group, groupIndex) in historyGroups" :key="groupIndex" class="nte-gc-history">
        <OverviewSectionHead
          :title="`${group.pool.name || '未命名卡池'} · 已出 S 记录`"
          :meta="group.entries ? `${group.entries.length} 条` : '未提供'"
        />
        <div class="ov-ds-card">
          <p v-if="!group.entries.length" class="ov-ds-muted" style="margin: 0">该卡池暂无已出 S 明细。</p>
          <ol v-else class="pull-list">
            <li
              v-for="(entry, index) in group.entries"
              :key="`${groupIndex}-${entry.item_id}-${index}`"
              class="pull-row"
            >
              <div class="reward-icon">
                <img
                  v-if="pullIconUrl(entry)"
                  :src="pullIconUrl(entry)"
                  :alt="nteItemLabel(entry.item_id, entry.name)"
                  @error="markFailed(pullIconUrl(entry))"
                />
                <span v-else aria-hidden="true">{{ nteItemLabel(entry.item_id, entry.name).slice(0, 2) }}</span>
              </div>
              <strong class="pull-name">{{ nteItemLabel(entry.item_id, entry.name) }}</strong>
              <div class="bar-track" :aria-label="known(entry.pity) ? `本次出 S：${entry.pity} 抽` : '本次抽数未提供'">
                <div class="pull-bar" :class="gachaTone(entry)" :style="barStyle(entry, group.pool)" />
                <div class="bar-values">
                  <template v-if="known(entry.pity)">
                    <strong class="num-nowrap">{{ entry.pity }}</strong>
                    <span>抽</span>
                  </template>
                  <span v-else>本次抽数未提供</span>
                  <span v-if="gachaRating(entry)" class="rating" :class="gachaTone(entry)">
                    {{ gachaRating(entry) }}
                  </span>
                </div>
              </div>
              <time class="pull-time num-nowrap">{{ obtained(entry.obtained_at) }}</time>
            </li>
          </ol>
          <footer v-if="group.entries.length" class="bar-legend">
            <span><i class="short" />欧 / 超欧</span>
            <span><i class="medium" />普通 / 非</span>
            <span><i class="long" />超非</span>
            <span v-if="scale(group.pool)" class="num-nowrap">本池标尺 {{ scale(group.pool) }} 抽</span>
          </footer>
        </div>
      </section>

      <p class="ov-ds-note-line">
        横条表示当期出 S 的抽数与社区评价，不表示当前垫抽；未提供标尺时不绘制比例。
      </p>

      <template v-if="ledger">
        <OverviewSectionHead title="本人逐抽账本" :meta="`${ledger.total_records ?? 0} 条已保存记录`" />

        <div v-if="ledgerPools.length" class="ov-ds-grid-2">
          <article v-for="item in ledgerPools" :key="item.pool_id" class="ov-ds-card nte-gc-ledger-pool">
            <header class="ov-ds-row-head">
              <span class="ov-ds-card-title">{{ poolLabel(item.pool_id) }}</span>
              <span v-if="item.pity?.rule_basis === 'user_configured'" class="nte-gc-chip">按用户规则</span>
            </header>
            <div class="nte-gc-pity-grid">
              <div class="nte-gc-pity-cell">
                <span>当前垫抽</span>
                <strong class="num-nowrap">{{ pityLabel(item.pity) }}</strong>
              </div>
              <div class="nte-gc-pity-cell">
                <span>距所设 S 保底</span>
                <strong class="num-nowrap">{{ item.pity?.hard_pity_remaining == null ? '未知' : `${item.pity.hard_pity_remaining} 抽` }}</strong>
              </div>
            </div>
            <p class="nte-gc-ledger-meta">
              已导入 <b class="num-nowrap">{{ item.total_pulls }}</b> 次计数抽取
              <template v-if="item.pity?.as_of">
                · 记录范围：<span class="num-nowrap">{{ ledgerDate(item.pity.latest_record_at || item.pity.as_of) }}</span>
              </template>
            </p>
          </article>
        </div>

        <div v-if="ledgerRecords.length" class="ov-ds-card nte-gc-ledger-records">
          <div class="ov-ds-row-head" style="margin-bottom: 10px">
            <span class="ov-ds-card-title">逐抽记录</span>
            <span class="ov-ds-card-meta num-nowrap">展示 {{ ledgerRecords.length }} / {{ ledger.total_records ?? ledgerRecords.length }} 条</span>
          </div>
          <div class="nte-gc-ledger-list">
            <div v-for="row in ledgerRecords" :key="row.uid" class="nte-gc-ledger-row">
              <div class="reward-icon is-sm">
                <img
                  v-if="ledgerIconUrl(row)"
                  :src="ledgerIconUrl(row)"
                  :alt="row.reward_name || row.reward_id"
                  @error="markFailed(ledgerIconUrl(row))"
                />
                <span v-else aria-hidden="true">{{ String(row.reward_name || row.reward_id || '?').slice(0, 2) }}</span>
              </div>
              <div class="nte-gc-ledger-item">
                <strong>{{ row.reward_name || row.reward_id }}</strong>
                <span>{{ poolLabel(row.pool_group_id) }} · {{ resultLabel(row.result_type) }}</span>
              </div>
              <span class="nte-gc-rank-pill">{{ row.reward_rank || '未知' }}</span>
              <span class="nte-gc-qty num-nowrap">×{{ row.quantity ?? '未知' }}</span>
              <time class="pull-time num-nowrap">{{ ledgerDate(row.timestamp) }}</time>
            </div>
          </div>
        </div>
        <p v-else-if="ledger.total_records > 0" class="ov-ds-note-line">
          逐条记录未加载；账本已导入 {{ ledger.total_records }} 条，可在网页查看完整列表。
        </p>
        <p v-else class="ov-ds-note-line">暂无逐抽记录。</p>
      </template>
    </template>
  </div>
</template>
