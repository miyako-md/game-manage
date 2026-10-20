<script setup>
import { computed, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { friendlyDataError } from '../cloud-display.js'
import { list, value, sourceDateTime } from '../wuwa-display.js'
import { sourceShares } from '../wuwa-charts.js'
import { vGlide, vReveal } from '../motion.js'
import DonutChart from './DonutChart.vue'
import HRail from './HRail.vue'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
const props = defineProps({
  snap: { default: null },
  accountKey: { type: String, default: '' },
  imageMode: Boolean,
})
const report = ref(null),
  pending = ref(''),
  error = ref('')
const request = useWuwaRequest(
  () => props.accountKey,
  () => {
    report.value = null
    pending.value = ''
    error.value = ''
  },
)
const kinds = { week: '周', month: '月', version: '版本' }
// A month period is YYYYMM; other kinds keep the source wording unless their format is known.
function periodLabel(kind, period) {
  const text = String(period ?? '')
  const month = kind === 'month' && /^(\d{4})(0[1-9]|1[0-2])$/.exec(text)
  if (month) return `${month[1]} 年 ${Number(month[2])} 月`
  if (kind === 'version' && /^\d+\.\d+$/.test(text)) return `${text} 版本`
  return `${kinds[kind] || '未知'}周期 ${period}`
}
const periods = computed(() =>
  Object.entries(kinds).flatMap(([kind, name]) =>
    list(props.snap?.payload?.periods?.[kind])
      .filter((p) => p.period != null)
      .map((p) => ({ ...p, kind, kindName: name })),
  ),
)
const current = computed(() => report.value || props.snap?.payload?.current)
const selected = computed(() =>
  periods.value.find(
    (p) =>
      p.kind === current.value?.kind &&
      String(p.period) === String(current.value?.period),
  ),
)
// Polling hands over a new snapshot object every minute. Only a newer fetch of
// the period on display makes the loaded report stale; another chosen period stays.
watch(
  () => props.snap?.fetched_at,
  () => {
    const fresh = props.snap?.payload?.current
    if (
      !pending.value &&
      report.value?.kind === fresh?.kind &&
      String(report.value?.period) === String(fresh?.period)
    )
      report.value = null
  },
)
async function select(period) {
  if (props.imageMode) return
  pending.value = `${period.kind}:${period.period}`
  error.value = ''
  try {
    const result = await request.run(
      `resources/${period.kind}/${encodeURIComponent(period.period)}`,
    )
    if (!result) return
    report.value = {
      ...result.payload,
      state: 'ok',
      fetched_at: result.fetched_at || result.payload.provenance?.fetched_at,
    }
    pending.value = ''
  } catch (e) {
    error.value = e.message
    pending.value = ''
  }
}
const amount = (v) => (typeof v === 'number' ? v.toLocaleString('zh-CN') : value(v))
// item_list rows shaped { type, num, detail: [{ type, num }] } read as a table;
// anything else falls back to the generic field view.
const only = (obj, keys) =>
  obj && typeof obj === 'object' && !Array.isArray(obj) &&
  Object.keys(obj).every((k) => keys.includes(k))
const itemRows = computed(() => {
  const rows = list(current.value?.data?.item_list)
  return rows.length &&
    rows.every(
      (r) =>
        only(r, ['type', 'num', 'detail']) &&
        (r.detail == null || list(r.detail).every((d) => only(d, ['type', 'num']))),
    )
    ? rows
    : null
})
const when = (v) => sourceDateTime(v) ?? v
// 环比 comes as "+12%" / "-15%" or a number: the sign picks the chip colour.
function trend(v) {
  const n = typeof v === 'number' ? v : Number.parseFloat(String(v ?? ''))
  return !Number.isFinite(n) || n === 0 ? '' : n > 0 ? 'is-up' : 'is-down'
}
// Each currency: the total, its change on the last report, and the sources as parts of a whole.
const totals = computed(() => {
  const data = current.value?.data || {}
  return [
    ['coin_list', '贝币', data.total_coin, data.coin_inc, '贝币来源'],
    ['star_list', '星声', data.total_star, data.star_inc, '星声来源'],
  ].map(([key, name, total, inc, title]) => ({
    key,
    name,
    total,
    inc,
    title,
    segments: sourceShares(data[key]).map((part, i) => ({ ...part, color: `var(--chart-${i + 1})` })),
  }))
})
</script>
<template>
  <section class="wuwa-board">
    <header class="wuwa-board-head">
      <h2>资源简报</h2>
      <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    </header>
    <div class="wuwa-panel wuwa-report" :class="{ 'is-hero': current?.data }">
      <header v-if="current?.data" class="wuwa-report-head">
        <h3>
          {{
            selected?.title || periodLabel(current.kind, current.period)
          }}
          · 期间获取
        </h3>
        <span
          v-if="
            selected?.start_time ||
            selected?.start_date ||
            selected?.end_time ||
            selected?.end_date
          "
          class="wuwa-meta"
        >
          {{ when(selected.start_time || selected.start_date) || '开始日期未提供' }}
          —
          {{ when(selected.end_time || selected.end_date) || '结束日期未提供' }}
        </span>
        <WuwaStatus :snap="current" />
      </header>
      <HRail v-if="!imageMode" label="资源报告周期" class="wuwa-periods">
        <div
          v-for="(name, kind) in kinds"
          :key="kind"
          class="wuwa-period-group"
          role="group"
          :aria-label="`${name}报告`"
        >
          <span class="wuwa-period-label" aria-hidden="true">{{ name }}报告</span
          ><span v-if="!periods.some((p) => p.kind === kind)" class="wuwa-meta"
            >无可用周期</span
          ><div v-else v-glide class="segmented">
            <button
              v-for="p in periods.filter((p) => p.kind === kind)"
              :key="p.period"
              type="button"
              :aria-pressed="
                current?.kind === kind &&
                String(current?.period) === String(p.period)
              "
              @click="select(p)"
            >
              {{ p.title || `${name} ${p.period}` }}
            </button>
          </div>
        </div>
      </HRail>
      <p v-if="pending" role="status" class="wuwa-meta">正在读取所选周期…</p>
      <p v-if="error || snap?.payload?.error" role="alert" class="wuwa-error">
        {{ imageMode ? friendlyDataError(error || snap?.payload?.error,snap?.state) : error || snap?.payload?.error }}
      </p>
      <p v-if="current?.data && (pending || error)" class="wuwa-warning wuwa-meta">
        当前仍显示上一份报告。
      </p>
      <p v-if="!current?.data" class="wuwa-muted">{{ periods.length ? '暂无报告，请选择其他周期。' : '暂无报告，请刷新数据。' }}</p>
    </div>
    <template v-if="current?.data">
      <div class="wuwa-bento">
        <section v-for="c in totals" :key="c.key" v-reveal class="wuwa-panel span-6 wuwa-currency">
          <dl class="wuwa-total">
            <dt>{{ c.name }}</dt>
            <dd>
              <b>{{ amount(c.total) }}</b>
              <span class="wuwa-delta" :class="trend(c.inc)"
                >环比 {{ value(c.inc) }}</span
              >
            </dd>
          </dl>
          <h4 class="sr-only">{{ c.title }}</h4>
          <DonutChart v-if="c.segments.length" :segments="c.segments" :label="c.title" :size="132" :stroke="16">
            <small class="ring-cap">来源</small>
            <b class="donut-total">{{ c.segments.length }}</b>
          </DonutChart>
          <p v-else class="wuwa-muted">未提供明细</p>
        </section>
      </div>
      <!-- The bot image skips the category dump: the two donuts above already carry it. -->
      <section v-if="current.data.copy_writing || (!imageMode && list(current.data.item_list).length) || current.data.recommend" class="wuwa-panel">
        <p v-if="current.data.copy_writing" class="wuwa-note">
          {{ current.data.copy_writing }}
        </p>
        <details
          v-if="!imageMode && list(current.data.item_list).length"
          class="wuwa-supplement"
        >
          <summary>全部资源类别与明细</summary>
          <table v-if="itemRows" class="data-table wuwa-items">
            <thead>
              <tr>
                <th>类别</th>
                <th class="num">数量</th>
                <th>来源明细</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in itemRows" :key="i">
                <td>{{ r.type || '未知类别' }}</td>
                <td class="num">{{ amount(r.num) }}</td>
                <td>
                  <ul v-if="list(r.detail).length" class="chip-list">
                    <li v-for="(d, j) in list(r.detail)" :key="j" class="chip">
                      {{ d.type || '未知来源' }} <b>{{ amount(d.num) }}</b>
                    </li>
                  </ul>
                  <span v-else class="wuwa-muted">暂无条目</span>
                </td>
              </tr>
            </tbody>
          </table>
          <WuwaFields v-else :data="current.data.item_list" />
        </details>
        <details v-if="current.data.recommend" class="wuwa-supplement">
          <summary>
            {{ current.data.recommend.post_title || '推荐说明' }}
          </summary>
          <p class="wuwa-description">{{ current.data.recommend.content }}</p>
        </details>
      </section>
    </template>
  </section>
</template>
