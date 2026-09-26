<script setup>
import { computed, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { list, value, sourceDateTime } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
import InfoHint from './InfoHint.vue'
const props = defineProps({
  snap: { default: null },
  accountKey: { type: String, default: '' },
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
watch(
  () => props.snap,
  () => {
    if (!pending.value) report.value = null
  },
)
async function select(period) {
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
const totals = computed(() => {
  const data = current.value?.data || {}
  return [
    ['coin_list', '贝币', data.total_coin, data.coin_inc, '贝币来源'],
    ['star_list', '星声', data.total_star, data.star_inc, '星声来源'],
  ].map(([key, name, total, inc, title], n) => {
    const rows = list(data[key])
    const sum = rows.reduce(
      (acc, r) => acc + (typeof r?.num === 'number' ? r.num : 0),
      0,
    )
    const base = typeof total === 'number' && total > 0 ? total : sum
    return {
      key,
      name,
      total,
      inc,
      title,
      rows: rows.map((r, i) => ({
        type: r.type || '未知来源',
        num: r.num,
        pct:
          typeof r.num === 'number' && base > 0
            ? Math.max(0, Math.min(100, Math.round((r.num / base) * 100)))
            : null,
        series: `var(--chart-${(i + n * 3) % 6 + 1})`,
      })),
    }
  })
})
</script>
<template>
  <section class="wuwa-panel">
    <header class="cap-title">
      <h2>资源简报</h2>
      <InfoHint text="期间获取量，非当前钱包余额。仅可查询来源返回的周期。" />
      <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    </header>
    <div class="wuwa-periods">
      <div
        v-for="(name, kind) in kinds"
        :key="kind"
        class="wuwa-period-group"
        role="group"
        :aria-label="`${name}报告`"
      >
        <span class="wuwa-period-label" aria-hidden="true">{{ name }}报告</span
        ><button
          v-for="p in periods.filter((p) => p.kind === kind)"
          :key="p.period"
          type="button"
          class="wuwa-chip-button"
          :aria-pressed="
            current?.kind === kind &&
            String(current?.period) === String(p.period)
          "
          @click="select(p)"
        >
          {{ p.title || `${name} ${p.period}` }}</button
        ><span v-if="!periods.some((p) => p.kind === kind)" class="wuwa-meta"
          >无可用周期</span
        >
      </div>
    </div>
    <p v-if="pending" role="status" class="wuwa-meta">正在读取所选周期…</p>
    <p v-if="error || snap?.payload?.error" role="alert" class="wuwa-error">
      {{ error || snap?.payload?.error }}
    </p>
    <template v-if="current?.data">
      <header class="wuwa-report-head">
        <h3>
          {{
            selected?.title ||
            `${kinds[current.kind] || '未知'}周期 ${current.period}`
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
      <p v-if="pending || error" class="wuwa-warning wuwa-meta">
        仍显示上方标明周期的报告，尚未切换为新结果。
      </p>
      <div class="wuwa-tiles wuwa-currencies">
        <section v-for="c in totals" :key="c.key" class="wuwa-currency wuwa-cq">
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
          <ul v-if="c.rows.length" class="bar-list wuwa-bars with-note">
            <li v-for="(r, i) in c.rows" :key="i" class="bar-row has-note">
              <span class="k">{{ r.type }}</span
              ><span class="meter"
                ><i :style="{ '--pct': (r.pct ?? 0) + '%', '--series': r.series }"></i></span
              ><span class="v">{{ amount(r.num) }}</span
              ><span class="note">{{ r.pct == null ? '' : `${r.pct}%` }}</span>
            </li>
          </ul>
          <p v-else class="wuwa-muted">未提供明细</p>
        </section>
      </div>
      <p v-if="current.data.copy_writing" class="wuwa-note">
        {{ current.data.copy_writing }}
      </p>
      <details
        v-if="list(current.data.item_list).length"
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
          {{ current.data.recommend.post_title || '来源推荐说明' }}
        </summary>
        <p class="wuwa-description">{{ current.data.recommend.content }}</p>
      </details>
    </template>
    <p v-else class="wuwa-muted">暂无可用报告，请选择可用周期。</p>
  </section>
</template>
