<script setup>
import { computed, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { list, value } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
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
</script>
<template>
  <section class="wuwa-panel">
    <p class="wuwa-kicker">RESOURCE REPORT</p>
    <h2>资源简报</h2>
    <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    <p class="wuwa-muted">
      期间获取量，非当前钱包余额。仅可查询来源返回的周期。
    </p>
    <div class="wuwa-periods">
      <fieldset v-for="(name, kind) in kinds" :key="kind">
        <legend>{{ name }}报告</legend>
        <button
          v-for="p in periods.filter((p) => p.kind === kind)"
          :key="p.period"
          :aria-pressed="
            current?.kind === kind &&
            String(current?.period) === String(p.period)
          "
          @click="select(p)"
        >
          {{ p.title || `${name} ${p.period}` }}</button
        ><span v-if="!periods.some((p) => p.kind === kind)" class="wuwa-muted"
          >无可用周期</span
        >
      </fieldset>
    </div>
    <p v-if="pending" role="status">正在读取所选周期…</p>
    <p v-if="error || snap?.payload?.error" role="alert" class="wuwa-error">
      {{ error || snap?.payload?.error }}
    </p>
    <template v-if="current?.data"
      ><h3>
        {{
          selected?.title ||
          `${kinds[current.kind] || '未知'}周期 ${current.period}`
        }}
        · 期间获取
      </h3>
      <p
        class="wuwa-meta"
        v-if="
          selected?.start_time ||
          selected?.start_date ||
          selected?.end_time ||
          selected?.end_date
        "
      >
        {{ selected.start_time || selected.start_date || '开始日期未提供' }} —
        {{ selected.end_time || selected.end_date || '结束日期未提供' }}
      </p>
      <p v-if="pending || error" class="wuwa-warning">
        仍显示上方标明周期的报告，尚未切换为新结果。
      </p>
      <div class="wuwa-metrics">
        <div>
          <span>贝币</span><strong>{{ value(current.data.total_coin) }}</strong
          ><small>环比 {{ value(current.data.coin_inc) }}</small>
        </div>
        <div>
          <span>星声</span><strong>{{ value(current.data.total_star) }}</strong
          ><small>环比 {{ value(current.data.star_inc) }}</small>
        </div>
      </div>
      <div class="wuwa-grid">
        <section
          v-for="[key, title] in [
            ['coin_list', '贝币来源'],
            ['star_list', '星声来源'],
          ]"
          :key="key"
          class="wuwa-inset"
        >
          <h3>{{ title }}</h3>
          <dl>
            <div v-for="(entry, i) in list(current.data[key])" :key="i">
              <dt>{{ entry.type || '未知来源' }}</dt>
              <dd>{{ value(entry.num) }}</dd>
            </div>
          </dl>
          <p v-if="!list(current.data[key]).length">未提供明细</p>
        </section>
      </div>
      <details v-if="list(current.data.item_list).length">
        <summary>全部资源类别与明细</summary>
        <WuwaFields :data="current.data.item_list" />
      </details>
      <p class="wuwa-description">{{ current.data.copy_writing }}</p>
      <details v-if="current.data.recommend">
        <summary>
          {{ current.data.recommend.post_title || '来源推荐说明' }}
        </summary>
        <p class="wuwa-description">{{ current.data.recommend.content }}</p>
      </details>
      <WuwaStatus :snap="current"
    /></template>
    <p v-else class="wuwa-muted">暂无可用报告，请选择可用周期。</p>
  </section>
</template>
