<script setup>
import { computed } from 'vue'
import { fetchedLabel } from '../time.js'
import { pityParts, pullDay } from '../endfield-gacha-api.js'
import {
  bannerGroups,
  gachaPools,
  kindSummary,
  poolCategories,
  poolPace,
  pullRuler,
  rarityShares,
  sixPullsParts,
  syncStatus,
} from '../endfield-gacha-summary.js'
import { gachaArtwork } from '../endfield-reports.js'
import EndfieldArtwork from '../components/EndfieldArtwork.vue'
import OverviewSectionHead from './OverviewSectionHead.vue'
import { asset } from './models.js'

const props = defineProps({
  input: { type: Object, required: true },
})

const panel = computed(() => (props.input?.snapshot?.display_data?.panels || []).find(p => p.capability === 'gacha') || null)
const gachaSnap = computed(() => panel.value?.snapshot || null)
const summary = computed(() => (gachaSnap.value?.payload?.schema_version === 1 ? gachaSnap.value.payload : null))
const report = computed(() => (summary.value?.report?.schema_version === 1 ? summary.value.report : null))

const show = value => (value == null || value === '' ? '未知' : value)
const pools = computed(() => gachaPools(summary.value))
const categories = computed(() => poolCategories(pools.value))
const fetchedAt = computed(() => fetchedLabel(gachaSnap.value?.fetched_at))

// Operator headhunting and weapon requisition use distinct currencies and rules: never sum them.
const kinds = computed(() => ['character', 'weapon'].map(kind => kindSummary(pools.value, kind)).filter(Boolean))
const unverifiedRecords = computed(() => kinds.value.reduce((sum, kind) => sum + kind.unverified_records, 0))
const failures = computed(() =>
  (Array.isArray(summary.value?.errors) ? summary.value.errors : []).filter(item => item && typeof item.label === 'string'),
)
const status = computed(() => syncStatus(summary.value, report.value))

const rulers = computed(() => ({
  character: pullRuler(pools.value, 'character'),
  weapon: pullRuler(pools.value, 'weapon'),
}))
const dayRange = item =>
  Number.isFinite(item?.oldest_at) && Number.isFinite(item?.newest_at) ? `${pullDay(item.oldest_at)} – ${pullDay(item.newest_at)}` : ''

const views = computed(() =>
  categories.value.map(category => {
    const banners = bannerGroups(category)
    const split = banners.length > 1
    const shares = rarityShares(category).filter(part => part.field !== 'unknown_rarity' || part.count !== 0)
    const counted = shares.reduce((sum, part) => sum + (part.count ?? 0), 0)
    const pulls = Number(category.total)
    return {
      category,
      split,
      pace: poolPace(category),
      ruler: rulers.value[category.kind === 'weapon' ? 'weapon' : 'character'],
      shares,
      rest: Number.isFinite(pulls) && pulls > counted ? pulls - counted : 0,
      banners: split ? banners : [{ ...banners[0], key: 'all', history: category.history }],
      range: dayRange(category),
    }
  }),
)

const pity = pool => pityParts(pool?.since_last_six)
const categoryPity = category => pity(category.kind === 'weapon' ? category.latest : category)
const percent = share => `${(share * 100).toFixed(share < 0.1 ? 1 : 0)}%`
const barWidth = (item, ruler) => {
  const parts = sixPullsParts(item)
  return parts && ruler ? `${Math.min(100, Math.round((parts.count / ruler) * 10000) / 100)}%` : '0%'
}
const tag = (item, pace) =>
  item === pace.fastest ? { label: '最欧', tone: 'lucky' } : item === pace.slowest ? { label: '最非', tone: 'unlucky' } : null

const padIdx = n => String(n).padStart(2, '0')
const RARITY_COLOR = {
  six_star: '#d95926',
  five_star: '#dba11c',
  four_star: '#7b74b0',
  unknown_rarity: '#5e6670',
}
</script>

<template>
  <section class="endfield-gacha ov-ef-gacha" aria-label="终末地寻访战报">
    <OverviewSectionHead title="寻访汇总" en="OVERVIEW" :index="1" :meta="status.label" />

    <div class="ov-ef-card ef-gc-hero">
      <div class="ef-gc-hero-bar">
        <span class="ef-gc-status" :class="`is-${status.tone}`">
          <i class="ef-gc-dot" aria-hidden="true" />
          {{ status.label }}
        </span>
        <span v-if="gachaSnap?.stale" class="ov-gc-badge is-warn">待更新</span>
        <span v-if="summary && fetchedAt" class="ef-gc-sync num-nowrap">同步于 {{ fetchedAt }}</span>
      </div>

      <p v-if="!summary" class="ov-empty" style="padding: 16px 0">
        尚未同步寻访记录，请在云端看板刷新后查看。
      </p>

      <template v-else>
        <div v-if="kinds.length" class="ef-gc-kinds" :class="{ 'is-pair': kinds.length === 2 }">
          <section v-for="kind in kinds" :key="kind.kind" class="ef-gc-kind-block">
            <div class="ef-gc-kind-head">
              <h3>{{ kind.label }}</h3>
              <span class="ef-gc-kind-sub">独立货币体系</span>
            </div>
            <div class="ef-gc-kind-body">
              <p class="ef-gc-kind-total num-nowrap">
                {{ show(kind.total) }}<small v-if="kind.total != null">抽</small>
              </p>
              <div class="ef-gc-kind-metrics">
                <div class="ef-gc-km is-six">
                  <span>6★</span>
                  <b class="num-nowrap">{{ show(kind.six_star) }}</b>
                </div>
                <div class="ef-gc-km is-five">
                  <span>5★</span>
                  <b class="num-nowrap">{{ show(kind.five_star) }}</b>
                </div>
                <div class="ef-gc-km">
                  <span>平均 6★</span>
                  <b class="num-nowrap">
                    <template v-if="kind.pace.average != null">{{ kind.pace.average }}<small>抽</small></template>
                    <template v-else>—</template>
                  </b>
                </div>
              </div>
            </div>
          </section>
        </div>

        <p v-if="failures.length" class="ef-gc-notice is-warn">
          本次未能读取：<template v-for="(item, index) in failures" :key="item.key"><template v-if="index">、</template><b>{{ item.label }}</b>（{{ item.message || '原因未知' }}）</template>。其他卡池已正常同步。
        </p>
        <p v-if="unverifiedRecords > 0" class="ef-gc-notice is-warn">
          另有 {{ unverifiedRecords }} 条武器记录类型不明确，暂不计入统计。
        </p>
        <p v-if="kinds.some(kind => kind.gifts > 0)" class="ef-gc-notice">
          额外奖励保留在逐条记录中，不计入抽数、出货和垫抽。
        </p>
        <p v-if="summary.complete === false" class="ef-gc-notice is-warn">
          还有记录未同步完，下次刷新会接着同步。
        </p>
      </template>
    </div>

    <template v-if="summary">
      <div v-if="!pools.length" class="ov-ef-card">
        <p class="ov-empty" style="padding: 16px 0">暂无寻访记录。</p>
      </div>

      <article v-for="(view, idx) in views" :key="view.category.key" class="ov-ef-card pool-detail">
        <header class="detail-head">
          <span class="ef-gc-idx">{{ padIdx(idx + 2) }} /</span>
          <h3>{{ view.category.label }}</h3>
          <span class="ef-gc-chip">{{ view.category.kind === 'weapon' ? '武器申领' : '干员寻访' }}</span>
          <span v-if="view.category.gaps || view.category.pending" class="ef-gc-chip is-warn">
            {{ view.category.pending ? '部分待同步' : '记录有缺口' }}
          </span>
          <span v-if="view.range" class="detail-range num-nowrap">{{ view.range }}</span>
        </header>

        <div class="detail-top">
          <div class="pity-block">
            <span class="pity-k">{{ view.category.kind === 'weapon' ? '当期已垫' : '已垫' }}</span>
            <strong class="pity-val num-nowrap">
              <template v-if="categoryPity(view.category)">{{ categoryPity(view.category).prefix }}{{ categoryPity(view.category).count }}<small>{{ categoryPity(view.category).unit }}</small></template>
              <template v-else>未知</template>
            </strong>
            <span class="pity-sub"><template v-if="view.category.kind === 'weapon'">{{ view.category.latest.label }}<br /></template>距上次 6★</span>
          </div>

          <div class="detail-stats">
            <div class="ef-gc-stat">
              <span class="ef-gc-stat-k">总抽数</span>
              <span class="ef-gc-stat-v num-nowrap">{{ show(view.category.total) }}<small v-if="view.category.total != null">抽</small></span>
              <span v-if="view.category.free" class="ef-gc-stat-sub">含免费 {{ view.category.free }}</span>
            </div>
            <div class="ef-gc-stat is-six">
              <span class="ef-gc-stat-k">6★</span>
              <span class="ef-gc-stat-v num-nowrap">{{ show(view.category.six_star) }}</span>
            </div>
            <div class="ef-gc-stat is-five">
              <span class="ef-gc-stat-k">5★</span>
              <span class="ef-gc-stat-v num-nowrap">{{ show(view.category.five_star) }}</span>
            </div>
            <div class="ef-gc-stat">
              <span class="ef-gc-stat-k">平均出 6★</span>
              <span class="ef-gc-stat-v num-nowrap">
                <template v-if="view.pace.average != null">{{ view.pace.average }}<small>抽</small></template>
                <template v-else>—</template>
              </span>
            </div>
            <div class="ef-gc-stat">
              <span class="ef-gc-stat-k">最欧</span>
              <span class="ef-gc-stat-v num-nowrap">
                <template v-if="view.pace.fastest">{{ view.pace.fastest.pulls }}<small>抽</small></template>
                <template v-else>—</template>
              </span>
              <span v-if="view.pace.fastest" class="ef-gc-stat-sub">{{ view.pace.fastest.name || '未知' }}</span>
            </div>
            <div class="ef-gc-stat">
              <span class="ef-gc-stat-k">最非</span>
              <span class="ef-gc-stat-v num-nowrap">
                <template v-if="view.pace.slowest">{{ view.pace.slowest.pulls }}<small>抽</small></template>
                <template v-else>—</template>
              </span>
              <span v-if="view.pace.slowest" class="ef-gc-stat-sub">{{ view.pace.slowest.name || '未知' }}</span>
            </div>
          </div>
        </div>

        <div class="rarity">
          <div class="ov-ds-stack-bar">
            <i
              v-for="part in view.shares.filter(part => part.count)"
              :key="part.field"
              :style="{ flex: part.count, backgroundColor: RARITY_COLOR[part.field] || '#5e6670' }"
            />
            <i v-if="view.rest" class="ef-gc-stack-rest" :style="{ flex: view.rest }" />
          </div>
          <div class="ov-ds-legend">
            <span v-for="part in view.shares" :key="part.field" class="ov-ds-legend-item">
              <i class="ov-ds-dot" :style="{ backgroundColor: RARITY_COLOR[part.field] || '#5e6670' }" />
              <span>{{ part.label }}</span>
              <b class="num-nowrap">{{ part.count ?? '未知' }}</b>
              <span v-if="part.share != null" class="ov-ds-muted num-nowrap">{{ percent(part.share) }}</span>
            </span>
          </div>
        </div>

        <div class="six-head">
          <h4>{{ view.split ? '按期统计' : '6★ 出货记录' }}</h4>
          <span class="num-nowrap">{{ view.split ? `${view.banners.length} 期` : `${view.category.history_total ?? view.category.history.length} 次` }}</span>
          <span v-if="view.ruler" class="ef-gc-ruler num-nowrap">标尺 {{ view.ruler }} 抽</span>
        </div>

        <p v-if="!view.split && !view.category.history.length" class="ef-gc-banner-empty">该卡池暂无 6★ 记录。</p>
        <div v-else class="banners">
          <section v-for="group in view.banners" :key="group.key" class="banner" :class="{ plain: !view.split }">
            <header v-if="view.split" class="banner-head">
              <strong>{{ group.name || '未命名卡池' }}</strong>
              <span v-if="dayRange(group)" class="banner-range num-nowrap">{{ dayRange(group) }}</span>
              <span class="banner-meta num-nowrap">
                <template v-if="group.pity && pity(group)">已垫 <b>{{ pity(group).prefix }}{{ pity(group).count }}</b> · </template>
                <b>{{ show(group.total) }}</b> 抽 · 6★ <b>{{ show(group.six_star) }}</b> · 5★ <b>{{ show(group.five_star) }}</b>
              </span>
            </header>

            <ol v-if="group.history.length" class="pull-list">
              <li
                v-for="(item, index) in group.history"
                :key="index"
                class="pull-row"
                :class="{ lower: item.status === 'lower_bound' }"
              >
                <EndfieldArtwork
                  class="pull-art"
                  :src="asset(gachaArtwork(item, view.category.kind))"
                  :name="item.name || '未知'"
                />
                <div class="pull-who">
                  <strong>{{ item.name || '未知' }}</strong>
                </div>
                <div class="pull-track">
                  <i class="pull-fill" :style="{ width: barWidth(item, view.ruler) }" />
                  <span class="pull-value num-nowrap">
                    <template v-if="sixPullsParts(item)">{{ sixPullsParts(item).prefix }}{{ sixPullsParts(item).count }}<small>{{ sixPullsParts(item).unit }}</small></template>
                    <template v-else>抽数未知</template>
                  </span>
                  <span v-if="tag(item, view.pace)" class="pull-tag" :class="tag(item, view.pace).tone">
                    {{ tag(item, view.pace).label }}
                  </span>
                </div>
              </li>
            </ol>

            <p v-else-if="view.split" class="ef-gc-banner-empty">{{ group.six_star ? '本期 6★ 不在已展示的历史中。' : '本期未出 6★。' }}</p>
            <p v-if="view.split && group.history.length && group.six_star > group.history.length" class="ef-gc-banner-empty">
              另有 {{ group.six_star - group.history.length }} 次 6★ 不在已展示的历史中。
            </p>
          </section>
        </div>

        <p v-if="view.category.history_truncated === true" class="ef-gc-notice">
          仅显示最近 {{ view.category.history_available }} 次 6★（账本共 {{ view.category.history_total }} 次）；完整记录请在网页查看。
        </p>
        <p v-else-if="view.category.kind !== 'weapon' && view.category.history_truncated == null" class="ef-gc-notice">
          6★ 历史的覆盖范围未知。
        </p>
      </article>

      <p v-if="pools.length" class="ov-ds-note-line">≥ 表示含未计入的免费抽或记录断档。</p>
    </template>
  </section>
</template>
