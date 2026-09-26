<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { value, list, stamp } from '../wuwa-display.js'
import WuwaDrawTable from './WuwaDrawTable.vue'
const props = defineProps({ accountKey: { type: String, default: '' } })
const archive = ref(null),
  url = ref(''),
  file = ref(null),
  fileInput = ref(null),
  outcome = ref(null),
  error = ref(''),
  busy = ref(false),
  offset = ref(0)
let fileGeneration = 0
onBeforeUnmount(() => {
  fileGeneration++
  clearInput()
})
function clearInput() {
  url.value = ''
  file.value = null
  if (fileInput.value) fileInput.value.value = ''
}
function reset() {
  fileGeneration++
  clearInput()
  archive.value = null
  outcome.value = null
  error.value = ''
  busy.value = false
  offset.value = 0
}
const request = useWuwaRequest(() => props.accountKey, reset)
async function load(page = 0) {
  busy.value = true
  error.value = ''
  try {
    const result = await request.run(`gacha?limit=50&offset=${page}`)
    if (!result) return
    archive.value = result
    offset.value = page
    busy.value = false
  } catch (e) {
    error.value = e.message
    busy.value = false
  }
}
async function perform(body) {
  try {
    const result = await request.run('gacha/import', body)
    if (!result) return
    outcome.value = result
    await load(0)
  } catch (e) {
    error.value = e.message
    busy.value = false
  } finally {
    clearInput()
  }
}
function importUrl() {
  if (busy.value || !url.value.trim()) return
  const submitted = url.value.trim()
  clearInput()
  outcome.value = null
  error.value = ''
  busy.value = true
  return perform({ url: submitted })
}
async function importFile() {
  if (busy.value || !file.value) return
  const chosen = file.value,
    version = ++fileGeneration
  clearInput()
  outcome.value = null
  error.value = ''
  busy.value = true
  let records
  try {
    if (chosen.size > 2 * 1024 * 1024) throw new Error()
    records = JSON.parse(await chosen.text())
  } catch {
    if (version !== fileGeneration) return
    error.value =
      '文件无法导入：请选择不超过 2 MiB、含当前账号标识的有效 JSON 文件'
    busy.value = false
    return
  }
  if (version !== fileGeneration) return
  await perform({ records })
}
onMounted(() => load())
watch(
  () => props.accountKey,
  () => load(),
)
</script>
<template>
  <section class="wuwa-panel">
    <p class="wuwa-kicker">LOCAL GACHA ARCHIVE</p>
    <h2>抽卡历史</h2>
    <p class="wuwa-muted">
      由你决定何时导入。打开此页只读取本地档案；链接仅在点击导入时使用，用后清空。文件在本机解析后交给本地服务。
    </p>
    <div class="wuwa-grid">
      <form class="wuwa-inset" @submit.prevent="importUrl">
        <label
          >官方记录授权链接<input
            type="password"
            autocomplete="off"
            spellcheck="false"
            :value="url"
            @input="url = $event.target.value"
            placeholder="粘贴链接，不保存到浏览器" /></label
        ><button
          type="submit"
          :disabled="busy || !url.trim()"
          @click.prevent="importUrl"
        >
          导入链接
        </button>
      </form>
      <div class="wuwa-inset">
        <label
          >本地导出 JSON<input
            ref="fileInput"
            type="file"
            accept=".json,application/json"
            :disabled="busy"
            @change="file = $event.target.files?.[0] || null"
        /></label>
        <p class="wuwa-meta">支持带 UID 的 WWUID 或规范化导出；最大 2 MiB。</p>
        <button :disabled="busy || !file" @click="importFile">导入文件</button>
      </div>
    </div>
    <p v-if="busy" role="status">正在读取 / 导入，请稍候…</p>
    <p v-if="error" class="wuwa-error" role="alert">{{ error }}</p>
    <div v-if="outcome" class="wuwa-notice" role="status">
      <p>
        收到 {{ value(outcome.received) }} 条 · 新增
        {{ value(outcome.inserted) }} 条（重复记录不会重复计数）
      </p>
      <p v-if="outcome.state === 'need_import'">
        本次未获得记录；已有档案保持不变。
      </p>
      <p v-if="list(outcome.failed_pools).length" class="wuwa-warning">
        部分卡池导入失败：{{
          outcome.failed_pools.join('、')
        }}。仅保存成功部分。
      </p>
    </div>
    <template v-if="archive"
      ><p v-if="archive.state === 'need_import'" class="wuwa-notice">
        尚无已导入记录。导入前的账号抽卡历史未知。
      </p>
      <section class="wuwa-inset">
        <h3>覆盖范围 · 不完整历史</h3>
        <p>
          {{ value(archive.coverage?.earliest) }} —
          {{ value(archive.coverage?.latest) }}（记录采用来源时区）
        </p>
        <p class="wuwa-meta">
          最近导入 {{ stamp(archive.coverage?.imported_at) }} · 来源
          {{
            archive.coverage?.source === 'official_query'
              ? '官方记录查询'
              : archive.coverage?.source === 'json_import'
                ? '本地 JSON'
                : '未导入'
          }}
        </p>
        <p>
          {{
            archive.coverage?.message ||
            '仅代表已导入窗口，未导入或已过保留期的记录未知；无保底推断。'
          }}
        </p>
        <p
          v-if="list(archive.coverage?.failed_pools).length"
          class="wuwa-warning"
        >
          未完整获取卡池 {{ archive.coverage.failed_pools.join('、') }}
        </p>
      </section>
      <h3>
        各池统计
        <span class="wuwa-meta"
          >全档案 {{ value(archive.total) }} 抽 · 按记录条数计算</span
        >
      </h3>
      <div class="wuwa-grid">
        <article
          v-for="pool in list(archive.pools)"
          :key="pool.pool"
          class="wuwa-inset"
        >
          <h4>{{ pool.name || `卡池 ${pool.pool}` }}</h4>
          <strong class="wuwa-big">{{ value(pool.total) }} 抽</strong>
          <p v-for="(count, rarity) in pool.rarity_distribution" :key="rarity">
            {{ rarity === 'unknown' ? '稀有度未知' : `${rarity} 星` }} ·
            {{ count }}
          </p>
        </article>
      </div>
      <h3>
        五星记录
        <span class="wuwa-meta">共 {{ value(archive.gold_total) }} 条</span>
      </h3>
      <WuwaDrawTable :rows="list(archive.gold)" />
      <details open>
        <summary>全部记录（当前页）</summary>
        <WuwaDrawTable :rows="list(archive.items)" />
      </details>
      <nav class="wuwa-pager" aria-label="抽卡档案分页">
        <button
          :disabled="busy || offset === 0"
          @click="load(Math.max(0, offset - 50))"
        >
          上一页</button
        ><span>第 {{ Math.floor(offset / 50) + 1 }} 页 · 两个列表分别分页</span
        ><button
          :disabled="
            busy ||
            offset + 50 >= Math.max(archive.total || 0, archive.gold_total || 0)
          "
          @click="load(offset + 50)"
        >
          下一页
        </button>
      </nav></template
    ><button v-else-if="!busy" @click="load()">重试读取档案</button>
  </section>
</template>
