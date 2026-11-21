<script setup>
import { computed, reactive } from 'vue'
import { aggregateKind, gachaSource, pityText } from '../wuwa-gacha.js'
import { pityGauge, rarityTotals } from '../wuwa-charts.js'
import { gachaItemIcon } from '../wuwa-icons.js'
import { list, stamp, value } from '../wuwa-display.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import OverviewStatGrid from './OverviewStatGrid.vue'
import { asset } from './models.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const failedUrls = reactive(new Set())
const safeImg = url => (url && !failedUrls.has(url) ? url : '')
const onImgError = url => {
  if (url) failedUrls.add(url)
}
const itemIcon = row => safeImg(asset(gachaItemIcon(row)))

const snap = computed(() => props.input?.snapshot || {})
const archive = computed(() => {
  if (snap.value.kind === 'wuwa_gacha') return snap.value.display_data?.archive || null
  const panel = (snap.value.display_data?.panels || []).find(p => p.capability === 'gacha')
  return panel?.snapshot?.payload || null
})

const pools = computed(() => list(archive.value?.pools))
const poolNames = computed(() =>
  Object.fromEntries(
    pools.value
      .filter(p => p.pool != null && p.name)
      .map(p => [String(p.pool), p.name]),
  ),
)

const goldShare = computed(() => {
  const total = archive.value?.total
  const gold = archive.value?.gold_total
  if (typeof total === 'number' && total > 0 && typeof gold === 'number') {
    return `${((gold / total) * 100).toFixed(1)}%`
  }
  return '—'
})

const summaryStats = computed(() => [
  { value: value(archive.value?.total), label: '已录总抽' },
  { value: value(archive.value?.gold_total), label: '五星总数', accent: true },
  { value: goldShare.value, label: '五星占比' },
  { value: `${pools.value.length}`, label: '统计卡池' },
])

const RARITY_COLOR = {
  5: '#e6c98f',
  4: '#b288ff',
  3: '#738296',
  unknown: '#5b6472',
}

function raritiesOf(distribution) {
  return Object.entries(distribution || {})
    .map(([rarity, count]) => ({
      rarity,
      count,
      label: rarity === 'unknown' ? '稀有度未知' : `${rarity} 星`,
      size: typeof count === 'number' && count > 0 ? count : 0,
      color: RARITY_COLOR[rarity] || '#6b7280',
    }))
    .sort((a, b) => (a.rarity === 'unknown') - (b.rarity === 'unknown') || Number(b.rarity) - Number(a.rarity))
}

const totalRarityKnown = computed(() => rarityTotals(pools.value).reduce((sum, r) => sum + (Number(r.value) || 0), 0))
const globalRarities = computed(() =>
  rarityTotals(pools.value).map(({ rarity, value: count }) => ({
    rarity,
    count,
    label: rarity === 'unknown' ? '稀有度未知' : `${rarity} 星`,
    pct: totalRarityKnown.value > 0 ? `${((count / totalRarityKnown.value) * 100).toFixed(rarity === '5' ? 1 : 0)}%` : '',
    color: RARITY_COLOR[rarity] || '#6b7280',
  })),
)

const SOURCE_TIME = /^(\d{4})-(\d{2}-\d{2})[T ](\d{2}:\d{2})/
function sourceTime(v) {
  const m = typeof v === 'string' ? v.match(SOURCE_TIME) : null
  return m ? `${m[1]}-${m[2]} ${m[3]}` : value(v)
}
function shortTime(v) {
  const m = typeof v === 'string' ? v.match(SOURCE_TIME) : null
  return m ? `${m[2]} ${m[3]}` : value(v)
}

function groupByPool(rows) {
  const groups = new Map()
  for (const row of list(rows)) {
    const key = row.pool == null ? '' : String(row.pool)
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        name: poolNames.value[key] || (key ? `卡池 ${key}` : '未知卡池'),
        rows: [],
      })
    }
    groups.get(key).rows.push(row)
  }
  return [...groups.values()]
}

const goldGroups = computed(() => groupByPool(archive.value?.gold))
const aggregateItems = computed(() => list(archive.value?.aggregates?.items))
const recentItems = computed(() => list(archive.value?.items))
</script>

<template>
  <div class="ov-ww-gacha">
    <div v-if="!archive || archive.state === 'need_import'" class="ov-empty-card">
      <p class="ov-empty-title">{{ archive?.coverage?.message || '尚未导入可核验的鸣潮抽卡记录' }}</p>
      <p class="ov-empty-sub">请在云端看板通过官方记录链接或 JSON 文件导入后重试查询。</p>
    </div>

    <template v-else>
      <OverviewSectionHead title="抽卡总览" meta="逐抽统计" />
      <OverviewStatGrid :stats="summaryStats" :columns="4" />

      <div class="ov-gc-meta-strip">
        <span class="ov-gc-badge" :class="archive.coverage?.complete === true ? 'is-ok' : 'is-warn'">
          {{ archive.coverage?.complete === true ? '完整历史' : '部分历史 / 待核验' }}
        </span>
        <span v-if="archive.coverage?.earliest || archive.coverage?.latest" class="ov-gc-meta-item">
          记录范围 <b class="num-nowrap">{{ sourceTime(archive.coverage?.earliest) }}</b> — <b class="num-nowrap">{{ sourceTime(archive.coverage?.latest) }}</b>
        </span>
        <span v-if="archive.coverage?.source" class="ov-gc-meta-item">
          来源 {{ gachaSource(archive.coverage.source) }}
        </span>
        <span v-if="archive.coverage?.imported_at" class="ov-gc-meta-item">
          导入于 <b class="num-nowrap">{{ stamp(archive.coverage.imported_at) }}</b>
        </span>
        <span v-if="list(archive.coverage?.failed_pools).length" class="ov-gc-badge is-warn">
          未完整卡池：{{ archive.coverage.failed_pools.join('、') }}
        </span>
      </div>

      <div v-if="globalRarities.length" class="ov-ds-card">
        <div class="ov-ds-row-head">
          <span class="ov-ds-card-title">稀有度分布汇总</span>
          <span class="ov-ds-card-meta num-nowrap">共 {{ value(totalRarityKnown) }} 抽</span>
        </div>
        <div class="ov-ds-stack-bar" aria-hidden="true">
          <i
            v-for="r in globalRarities"
            :key="r.rarity"
            :style="{ flex: Math.max(1, r.count), backgroundColor: r.color }"
          />
        </div>
        <div class="ov-ds-legend">
          <span v-for="r in globalRarities" :key="r.rarity" class="ov-ds-legend-item">
            <i class="ov-ds-dot" :style="{ backgroundColor: r.color }" />
            <span>{{ r.label }}</span>
            <b class="num-nowrap">{{ r.count }}</b>
            <span v-if="r.pct" class="ov-ds-muted num-nowrap">({{ r.pct }})</span>
          </span>
        </div>
      </div>

      <template v-if="pools.length">
        <OverviewSectionHead title="各池水位与统计" :meta="`${pools.length} 个卡池`" />
        <div class="ov-ds-grid-2 ww-gc-pools">
          <article v-for="pool in pools" :key="pool.pool" class="ov-ds-card ww-gc-pool">
            <header class="ov-ds-row-head">
              <span class="ov-ds-card-title">{{ pool.name || `卡池 ${pool.pool}` }}</span>
              <span class="ww-gc-pool-total num-nowrap"><b>{{ value(pool.total) }}</b> 抽</span>
            </header>

            <div class="ww-gc-pity-box">
              <div class="ww-gc-pity-line">
                <span class="ww-gc-pity-main">{{ pityText(pool.pity) }}</span>
                <span v-if="pool.pity?.hard_pity_remaining != null" class="ww-gc-pity-rem num-nowrap">
                  距上限 {{ pool.pity.hard_pity_remaining }} 抽
                </span>
              </div>
              <div v-if="pityGauge(pool.pity)" class="ov-ds-track ww-gc-pity-track">
                <i v-if="pityGauge(pool.pity).max === 80" class="ww-gc-pity-tick" style="left: 81.25%" aria-hidden="true" />
                <i
                  class="ov-ds-fill"
                  :style="{ width: `${Math.min(100, Math.round((pityGauge(pool.pity).value / Math.max(1, pityGauge(pool.pity).max)) * 100))}%` }"
                />
              </div>
              <span class="ww-gc-pity-note">UP 保证未知</span>
            </div>

            <template v-if="raritiesOf(pool.rarity_distribution).length">
              <div class="ov-ds-stack-bar" aria-hidden="true">
                <i
                  v-for="r in raritiesOf(pool.rarity_distribution)"
                  v-show="r.size"
                  :key="r.rarity"
                  :style="{ flex: r.size, backgroundColor: r.color }"
                />
              </div>
              <div class="ov-ds-legend">
                <span v-for="r in raritiesOf(pool.rarity_distribution)" :key="r.rarity" class="ov-ds-legend-item">
                  <i class="ov-ds-dot" :style="{ backgroundColor: r.color }" />
                  <span>{{ r.label }}</span>
                  <b class="num-nowrap">{{ r.count }}</b>
                </span>
              </div>
            </template>
          </article>
        </div>
      </template>

      <template v-if="archive.aggregates?.total && aggregateItems.length">
        <OverviewSectionHead title="第三方五星汇总" :meta="`${archive.aggregates.total} 条`" />
        <div class="ov-ds-card">
          <p class="ov-ds-muted" style="margin: 0 0 10px">五星汇总记录，未计入逐抽统计。</p>
          <div class="ov-ds-grid-2">
            <div v-for="(item, idx) in aggregateItems" :key="idx" class="ww-gc-agg-item">
              <div class="ww-gc-item-icon">
                <img v-if="itemIcon(item)" :src="itemIcon(item)" :alt="item.name || '五星'" @error="onImgError(itemIcon(item))" />
                <span v-else>{{ (item.name || '金').slice(0, 1) }}</span>
              </div>
              <div class="ww-gc-agg-body">
                <strong>{{ item.name || '当前垫抽标记' }}</strong>
                <span>{{ poolNames[String(item.pool)] || `卡池 ${item.pool}` }} · {{ aggregateKind(item) }}</span>
              </div>
              <span class="ww-gc-agg-cnt num-nowrap">{{ value(item.period_count) }} 抽</span>
            </div>
          </div>
        </div>
      </template>

      <OverviewSectionHead title="五星出货记录" :meta="`共 ${value(archive.gold_total)} 条`" />
      <div v-if="goldGroups.length" class="ww-gc-gold-groups">
        <section v-for="group in goldGroups" :key="group.key" class="ov-ds-card ww-gc-gold-group">
          <header class="ov-ds-row-head">
            <span class="ov-ds-card-title">{{ group.name }}</span>
            <span class="ov-ds-card-meta num-nowrap">{{ group.rows.length }} 条五星</span>
          </header>
          <div class="ww-gc-gold-grid">
            <article v-for="(row, i) in group.rows" :key="row.draw_id || i" class="ww-gc-gold-tile">
              <div class="ww-gc-item-icon is-gold">
                <img v-if="itemIcon(row)" :src="itemIcon(row)" :alt="row.name || '五星'" @error="onImgError(itemIcon(row))" />
                <span v-else>{{ (row.name || '金').slice(0, 1) }}</span>
              </div>
              <div class="ww-gc-gold-info">
                <strong>{{ row.name || '名称未知' }}</strong>
                <div class="ww-gc-gold-meta">
                  <span v-if="row.resource_type" class="ww-gc-type-pill">{{ row.resource_type }}</span>
                  <span class="ww-gc-time num-nowrap">{{ shortTime(row.time) }}</span>
                </div>
              </div>
            </article>
          </div>
        </section>
      </div>
      <div v-else class="ov-ds-card">
        <p class="ov-ds-muted" style="margin: 0">暂无五星记录</p>
      </div>

      <template v-if="recentItems.length">
        <OverviewSectionHead title="最近抽卡明细" :meta="`本次读取 ${recentItems.length} 条`" />
        <div class="ov-ds-card ww-gc-records-card">
          <div class="ww-gc-draw-list">
            <div
              v-for="(row, idx) in recentItems"
              :key="row.draw_id || idx"
              class="ww-gc-draw-row"
              :class="`is-rarity-${String(row.rarity || 'other')}`"
            >
              <div class="ww-gc-item-icon is-sm">
                <img v-if="itemIcon(row)" :src="itemIcon(row)" :alt="row.name || '物品'" @error="onImgError(itemIcon(row))" />
                <span v-else>{{ (row.name || '?').slice(0, 1) }}</span>
              </div>
              <div class="ww-gc-draw-main">
                <strong>{{ row.name || '名称未知' }}</strong>
                <span v-if="row.resource_type" class="ww-gc-type-pill">{{ row.resource_type }}</span>
              </div>
              <span class="ww-gc-draw-pool">{{ poolNames[String(row.pool)] || value(row.pool) }}</span>
              <span class="ww-gc-rarity-pill num-nowrap">{{ row.rarity ? `${row.rarity}★` : '—' }}</span>
              <span class="ww-gc-draw-time num-nowrap">{{ shortTime(row.time) }}</span>
            </div>
          </div>
        </div>
      </template>
      <p v-else class="ov-ds-note-line">
        已导入记录 {{ value(archive.total) }} 抽；完整逐抽明细可在云端看板查看。
      </p>
    </template>
  </div>
</template>
