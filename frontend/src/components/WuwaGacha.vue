<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { value, list, stamp } from '../wuwa-display.js'
import WuwaDrawTable from './WuwaDrawTable.vue'
import InfoHint from './InfoHint.vue'
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
  try {
    if (chosen.size > 2 * 1024 * 1024) throw new Error()
    const records = JSON.parse(await chosen.text())
    if (version !== fileGeneration) return
    await perform({ records })
  } catch {
    if (version !== fileGeneration) return
    error.value =
      '文件无法导入：请选择不超过 2 MiB、含当前账号标识的有效 JSON 文件'
    busy.value = false
  }
}
onMounted(() => load())
watch(
  () => props.accountKey,
  () => {
    importDecided = false
    load()
  },
)
// The import form opens by itself only when the first archive read for an
// account is empty; after that it stays as the user left it, so a successful
// import does not fold it away mid-use.
const importOpen = ref(false)
let importDecided = false
watch(archive, (loaded) => {
  if (importDecided || !loaded) return
  importDecided = true
  importOpen.value = loaded.state === 'need_import' || !loaded.total
})
const poolNames = computed(() =>
  Object.fromEntries(
    list(archive.value?.pools)
      .filter((p) => p.pool != null && p.name)
      .map((p) => [p.pool, p.name]),
  ),
)
// Coverage bounds are record times in the source time zone: reformat, never convert.
const SOURCE_TIME = /^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})/
function sourceTime(v) {
  const match = typeof v === 'string' ? v.match(SOURCE_TIME) : null
  return match ? `${match[1]} ${match[2]}` : value(v)
}
const RARITY_SERIES = {
  3: 'var(--text-faint)',
  4: 'var(--chart-5)',
  5: 'var(--game-wuwa)',
}
function rarities(pool) {
  return Object.entries(pool.rarity_distribution || {})
    .map(([rarity, count]) => ({
      rarity,
      count,
      label: rarity === 'unknown' ? '稀有度未知' : `${rarity} 星`,
      size: typeof count === 'number' && count > 0 ? count : 0,
      series: RARITY_SERIES[rarity] || 'var(--border-strong)',
    }))
    .sort(
      (a, b) =>
        (a.rarity === 'unknown') - (b.rarity === 'unknown') ||
        Number(a.rarity) - Number(b.rarity),
    )
}
</script>
<template>
  <section class="wuwa-panel">
    <header class="cap-title">
      <h2>抽卡历史</h2>
      <InfoHint
        text="由你决定何时导入。打开此页只读取本地档案；链接仅在点击导入时使用，用后清空。文件在本机解析后交给本地服务。"
      />
    </header>
    <details class="wuwa-import" :open="importOpen" @toggle="importOpen = $event.target.open">
      <summary>导入记录</summary>
      <div class="wuwa-import-body">
        <form class="toolbar wuwa-import-row" @submit.prevent="importUrl">
          <input
            class="grow"
            type="password"
            autocomplete="off"
            spellcheck="false"
            aria-label="官方记录授权链接"
            :value="url"
            @input="url = $event.target.value"
            placeholder="粘贴官方记录授权链接，不保存到浏览器"
          /><button
            type="submit"
            class="ui-button small-button primary"
            :disabled="busy || !url.trim()"
            @click.prevent="importUrl"
          >
            导入链接
          </button>
        </form>
        <div class="toolbar wuwa-import-row">
          <input
            ref="fileInput"
            class="wuwa-file"
            type="file"
            accept=".json,application/json"
            aria-label="本地导出 JSON"
            :disabled="busy"
            @change="file = $event.target.files?.[0] || null"
          /><button
            type="button"
            class="ui-button small-button"
            :disabled="busy || !file"
            @click="importFile"
          >
            导入文件</button
          ><InfoHint
            label="文件说明"
            text="支持带 UID 的 WWUID 或规范化导出；最大 2 MiB。"
          />
        </div>
      </div>
    </details>
    <p v-if="busy" role="status" class="wuwa-meta">正在读取 / 导入，请稍候…</p>
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
      <p class="wuwa-coverage">
        <span class="wuwa-meta" role="heading" aria-level="3">覆盖范围</span>
        <span class="badge badge-stale">不完整历史</span>
        <span class="wuwa-range"
          >{{ sourceTime(archive.coverage?.earliest) }} —
          {{ sourceTime(archive.coverage?.latest) }}</span
        >
        <InfoHint
          :text="`${
            archive.coverage?.message ||
            '仅代表已导入窗口，未导入或已过保留期的记录未知；无保底推断。'
          }（记录采用来源时区）`"
        />
        <span class="wuwa-meta wuwa-coverage-end"
          >最近导入 {{ stamp(archive.coverage?.imported_at) }} · 来源
          {{
            archive.coverage?.source === 'official_query'
              ? '官方记录查询'
              : archive.coverage?.source === 'json_import'
                ? '本地 JSON'
                : '未导入'
          }}</span
        >
        <span
          v-if="list(archive.coverage?.failed_pools).length"
          class="badge badge-danger"
          >未完整获取卡池 {{ archive.coverage.failed_pools.join('、') }}</span
        >
      </p>
      <section class="wuwa-section">
        <h3 class="wuwa-subhead">
          各池统计<span class="wuwa-meta"
            >全档案 {{ value(archive.total) }} 抽 · 按记录条数计算</span
          >
        </h3>
        <div v-if="list(archive.pools).length" class="wuwa-tiles wuwa-pools">
          <article
            v-for="pool in list(archive.pools)"
            :key="pool.pool"
            class="wuwa-tile"
          >
            <header class="wuwa-tile-head">
              <h4>{{ pool.name || `卡池 ${pool.pool}` }}</h4>
              <span class="wuwa-tile-end wuwa-pool-total"
                ><b>{{ value(pool.total) }}</b> 抽</span
              >
            </header>
            <template v-if="rarities(pool).length">
              <div class="stack-bar" aria-hidden="true">
                <i
                  v-for="r in rarities(pool)"
                  v-show="r.size"
                  :key="r.rarity"
                  :style="{ flex: r.size, '--series': r.series }"
                ></i>
              </div>
              <ul class="legend">
                <li
                  v-for="r in rarities(pool)"
                  :key="r.rarity"
                  :style="{ '--series': r.series }"
                >
                  {{ r.label }} <b>{{ r.count }}</b>
                </li>
              </ul>
            </template>
          </article>
        </div>
      </section>
      <section class="wuwa-section">
        <h3 class="wuwa-subhead">
          五星记录<span class="wuwa-meta"
            >共 {{ value(archive.gold_total) }} 条</span
          >
        </h3>
        <WuwaDrawTable :rows="list(archive.gold)" :pool-names="poolNames" />
      </section>
      <details open class="wuwa-section wuwa-records-all">
        <summary>全部记录（当前页）</summary>
        <WuwaDrawTable :rows="list(archive.items)" :pool-names="poolNames" />
      </details>
      <nav class="wuwa-pager" aria-label="抽卡档案分页">
        <button
          type="button"
          class="ui-button small-button"
          :disabled="busy || offset === 0"
          @click="load(Math.max(0, offset - 50))"
        >
          上一页</button
        ><span
          >第 {{ Math.floor(offset / 50) + 1 }} 页<InfoHint
            text="五星记录与全部记录两个列表分别分页。"
        /></span
        ><button
          type="button"
          class="ui-button small-button"
          :disabled="
            busy ||
            offset + 50 >= Math.max(archive.total || 0, archive.gold_total || 0)
          "
          @click="load(offset + 50)"
        >
          下一页
        </button>
      </nav></template
    ><button
      v-else-if="!busy"
      type="button"
      class="ui-button small-button"
      @click="load()"
    >
      重试读取档案
    </button>
  </section>
</template>
