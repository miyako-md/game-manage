<script setup>
import { onMounted, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { list, stamp, label, value } from '../wuwa-display.js'
import WuwaTower from './WuwaTower.vue'
import WuwaFields from './WuwaFields.vue'
import WuwaRoleDetail from './WuwaRoleDetail.vue'
const props = defineProps({
  roleNames: { type: Object, default: () => ({}) },
  accountKey: { type: String, default: '' },
})
const kind = ref('tower'),
  archive = ref(null),
  offset = ref(0),
  busy = ref(false),
  error = ref(''),
  outcome = ref(null)
function reset() {
  archive.value = null
  offset.value = 0
  busy.value = false
  error.value = ''
  outcome.value = null
}
const request = useWuwaRequest(() => props.accountKey, reset)
async function load(page = 0) {
  busy.value = true
  error.value = ''
  try {
    const result = await request.run(
      `history?kind=${kind.value}&limit=50&offset=${page}`,
    )
    if (!result) return
    archive.value = result
    offset.value = page
    busy.value = false
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
function change(next) {
  request.cancel()
  kind.value = next
  archive.value = null
  return load()
}
async function backfill() {
  busy.value = true
  error.value = ''
  try {
    const result = await request.run('history/backfill', {})
    if (!result) return
    outcome.value = result
    await load()
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
onMounted(() => load())
watch(
  () => props.accountKey,
  () => {
    kind.value = 'tower'
    load()
  },
)
</script>
<template>
  <section class="wuwa-panel">
    <header class="wuwa-heading">
      <div>
        <p class="wuwa-kicker">OBSERVATION HISTORY</p>
        <h2>成长记录</h2>
      </div>
      <button :disabled="busy" @click="backfill">回补本地快照</button>
    </header>
    <p class="wuwa-muted">
      从成功观测开始记录。同一角色首次记录是基线，不计作练度提升；一次观测不能说明趋势。完整详情仅在你打开角色面板后记录。
    </p>
    <nav class="wuwa-tabs" aria-label="历史类型">
      <button
        v-for="[key, name] in [
          ['tower', '跨期深塔'],
          ['roles', '角色练度变化'],
          ['role_detail', '完整面板变化'],
        ]"
        :key="key"
        :aria-pressed="kind === key"
        @click="change(key)"
      >
        {{ name }}
      </button>
    </nav>
    <p v-if="busy" role="status">正在读取历史…</p>
    <p v-if="error" class="wuwa-error" role="alert">{{ error }}</p>
    <p v-if="outcome" class="wuwa-notice">
      回补新增 {{ value(outcome.inserted) }} 条。{{ outcome.message }}
    </p>
    <template v-if="archive"
      ><p class="wuwa-meta">
        开始记录：{{ stamp(archive.archive_started_at) }}（北京时间） ·
        {{ value(archive.total) }} 条观测，非变化次数
      </p>
      <p>{{ archive.coverage || '仅保存成功观测；首次记录之前未知。' }}</p>
      <p v-if="!list(archive.items).length" class="wuwa-notice">
        尚无此类历史。官方旧成绩不可用不代表没有成绩；可尝试回补已有同账号快照。
      </p>
      <div class="wuwa-stack">
        <article
          v-for="item in list(archive.items)"
          :key="item.id"
          class="wuwa-inset"
        >
          <header class="wuwa-heading">
            <h3 v-if="kind === 'tower'">
              赛季结束 {{ stamp(item.season) }}（北京时间）
            </h3>
            <h3 v-else>
              {{
                item.payload?.name ||
                item.payload?.data?.role?.role_name ||
                item.payload?.role?.role_name ||
                `角色 ${item.subject}`
              }}
            </h3>
            <span class="wuwa-tag">{{
              item.delta == null ? '首次观测 · 基线' : '观测到变化'
            }}</span>
          </header>
          <p class="wuwa-meta">
            来源时间 {{ stamp(item.source_at) }} · 观测
            {{ stamp(item.observed_at) }} · 入档
            {{ stamp(item.archived_at) }}（北京时间）
          </p>
          <div v-if="item.delta" class="wuwa-stack">
            <details v-for="(delta, key) in item.delta" :key="key" open>
              <summary>{{ label(key) }}</summary>
              <div class="wuwa-grid">
                <section>
                  <h4>之前</h4>
                  <WuwaFields :data="delta.before" />
                </section>
                <section>
                  <h4>之后</h4>
                  <WuwaFields :data="delta.after" />
                </section>
              </div>
              <p v-if="delta.delta != null">变化量 {{ delta.delta }}</p>
            </details>
          </div>
          <details>
            <summary>查看本次观测详情</summary>
            <WuwaTower
              v-if="kind === 'tower'"
              :data="item.payload"
              :role-names="roleNames"
            /><WuwaRoleDetail
              v-else-if="kind === 'role_detail'"
              :data="item.payload?.data || item.payload"
            /><WuwaFields v-else :data="item.payload" />
          </details>
        </article>
      </div>
      <nav class="wuwa-pager" aria-label="历史分页">
        <button
          :disabled="busy || offset === 0"
          @click="load(Math.max(0, offset - 50))"
        >
          上一页</button
        ><span>第 {{ Math.floor(offset / 50) + 1 }} 页</span
        ><button
          :disabled="busy || offset + 50 >= archive.total"
          @click="load(offset + 50)"
        >
          下一页
        </button>
      </nav></template
    ><button v-else-if="!busy" @click="load()">重试读取历史</button>
  </section>
</template>
