<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { count, list, stamp, value } from '../wuwa-display.js'
import { deepStars, seasonDelta } from '../wuwa-charts.js'
// The 成长记录 card before it is opened: this season's stars from the loaded snapshot,
// and one small tower-history read for the archive's size, last record and start.
const props = defineProps({ accountKey: { type: String, default: '' }, combat: { default: null } })
const archive = ref(null), busy = ref(false), error = ref('')
function reset() { archive.value = null; busy.value = false; error.value = '' }
const request = useWuwaRequest(() => props.accountKey, reset)
async function load() {
  if (!props.accountKey) return
  busy.value = true
  error.value = ''
  try {
    const result = await request.run('history?kind=tower&limit=10&offset=0')
    if (!result) return
    archive.value = result
  } catch (e) {
    error.value = e.message
  }
  busy.value = false
}
onMounted(load)
watch(() => props.accountKey, load)
const stars = computed(() => deepStars(props.combat?.payload?.tower?.data))
const items = computed(() => list(archive.value?.items))
const empty = computed(() => archive.value != null && !items.value.length)
const delta = computed(() => seasonDelta(items.value))
const signed = n => (n > 0 ? `+${n}` : String(n))
</script>
<template>
  <div class="history-summary">
    <dl class="wuwa-stats">
      <div class="wuwa-stat"><dt>本期深境区</dt><dd>{{ value(stars.got) }}<small v-if="stars.cap != null"> / {{ stars.cap }}</small><small> 星</small></dd></div>
      <template v-if="archive && !empty">
        <div class="wuwa-stat"><dt>深塔记录</dt><dd>{{ count(archive.total) }}<small> 条</small></dd></div>
        <div class="wuwa-stat"><dt>最近记录</dt><dd class="is-time">{{ stamp(items[0].observed_at) }}</dd></div>
        <div class="wuwa-stat"><dt>记录起点</dt><dd class="is-time">{{ stamp(archive.archive_started_at) }}</dd></div>
      </template>
    </dl>
    <p v-if="delta != null" class="history-delta">较上期 <b>{{ signed(delta) }}</b> 星</p>
    <p v-if="busy" role="status" class="wuwa-meta">正在读取记录摘要…</p>
    <p v-else-if="error" class="wuwa-meta">记录摘要暂不可用（{{ error }}），仍可打开查看完整记录。</p>
    <p v-else-if="empty" class="wuwa-launcher-copy">尚未开始记录；打开后可回补本人快照</p>
    <p v-else-if="archive" class="wuwa-meta">时间为北京时间；每次刷新数据后留存角色与玩法记录。</p>
  </div>
</template>
