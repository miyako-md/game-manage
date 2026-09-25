<script setup>
import { computed, ref, watch } from 'vue'
import { displayBeijing } from '../time.js'
import { exportRecords, getRecords, pityText, pullDate, rarityLabel } from '../endfield-gacha-api.js'

const props = defineProps({ snap: { type: Object, default: null }, accountId: { type: String, default: '' } })
const summary = computed(() => props.snap?.payload?.schema_version === 1 ? props.snap.payload : null)
const pools = computed(() => Array.isArray(summary.value?.pools) ? summary.value.pools : [])
const fetched = computed(() => props.snap?.fetched_at ? displayBeijing(props.snap.fetched_at) : '未同步')
const opened = ref(false), recordPool = ref(''), records = ref([]), total = ref(0), offset = ref(0), busy = ref(false), message = ref('')
const PAGE = 50
let generation = 0

async function load(start = 0) {
  if (!props.accountId) return
  const request = ++generation
  busy.value = true; message.value = ''
  try {
    const page = await getRecords(recordPool.value, start, PAGE)
    if (request !== generation) return
    records.value = page.records || []; total.value = page.total || 0; offset.value = start
  } catch (error) {
    if (request === generation) message.value = error.message
  } finally {
    if (request === generation) busy.value = false
  }
}
// 逐条记录只在展开时读取本机账本。
watch(() => [props.accountId, recordPool.value, opened.value], () => { records.value = []; total.value = 0; if (opened.value) load(0) })

async function download() {
  busy.value = true; message.value = ''
  try {
    const data = await exportRecords()
    const url = URL.createObjectURL(new Blob([JSON.stringify(data)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = `endfield-gacha-${props.accountId}.json`; link.click(); URL.revokeObjectURL(url)
    message.value = `已导出 ${data.records?.length || 0} 条记录。`
  } catch (error) {
    message.value = error.message
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="endfield-gacha" aria-labelledby="endfield-gacha-title">
    <header class="gacha-head">
      <div><p class="eyebrow">HEADHUNTING RECORDS</p><h2 id="endfield-gacha-title">寻访记录</h2>
        <p class="muted">官方只能查到约 90 天的记录，本工具从第一次同步开始在本机长期保存。</p></div>
      <button type="button" :disabled="busy || !accountId" @click="download">导出记录</button>
    </header>
    <p v-if="!accountId" class="empty">登录终末地后，点「刷新数据」开始同步寻访记录。</p>
    <p v-else-if="!summary" class="empty">尚未同步寻访记录，点「刷新数据」开始同步。</p>
    <template v-else>
      <p class="sync-note">共 {{ summary.total }} 抽 · 最近同步 {{ fetched }}<span v-if="!summary.complete" class="warn"> · 还有未同步完的记录，下次刷新会接着同步</span></p>
      <p v-if="!pools.length" class="empty">近 90 天没有寻访记录。</p>
      <div v-else class="pool-grid">
        <article v-for="pool in pools" :key="pool.key" class="pool-card">
          <h3>{{ pool.label }}</h3>
          <p class="pity"><span>距上次 6★</span><strong>{{ pityText(pool.since_last_six) }}</strong></p>
          <p class="counts">{{ pool.total }} 抽 · 6★ {{ pool.six_star }} · 5★ {{ pool.five_star }}<span v-if="pool.free"> · 免费 {{ pool.free }}</span></p>
          <p v-if="pool.gaps" class="warn">{{ pool.pending ? '有未同步完的区段' : '有官方已无法查到的缺口' }}，跨过缺口的抽数只给最少值</p>
          <ol v-if="pool.history.length" class="six-list">
            <li v-for="(item, index) in pool.history" :key="index"><strong>{{ item.name || '未知' }}</strong><span>{{ item.status === 'exact' ? `${item.pulls} 抽` : `至少 ${item.pulls} 抽` }}</span><small>{{ item.pool_name || '' }} · {{ pullDate(item.obtained_at) }}</small></li>
          </ol>
        </article>
      </div>
      <details class="record-list" @toggle="opened = $event.target.open">
        <summary>逐条记录</summary>
        <label>卡池 <select v-model="recordPool" :disabled="busy"><option value="">全部</option><option v-for="pool in pools" :key="pool.key" :value="pool.key">{{ pool.label }}</option></select></label>
        <ol class="records">
          <li v-for="row in records" :key="`${row.pool_key}-${row.seq_id}`" :class="{ six: row.rarity === 6 }"><strong>{{ row.name || '未知' }}</strong><span>{{ rarityLabel(row.rarity) }}</span><small>{{ row.pool_name || '' }}{{ row.is_free ? ' · 免费' : '' }} · {{ pullDate(row.gacha_ts) }}</small></li>
        </ol>
        <p v-if="!records.length && !busy" class="empty">暂无记录。</p>
        <nav class="pager"><button type="button" :disabled="busy || offset === 0" @click="load(Math.max(0, offset - PAGE))">上一页</button><span>{{ total ? `${offset + 1}–${Math.min(offset + PAGE, total)} / ${total}` : '0' }}</span><button type="button" :disabled="busy || offset + PAGE >= total" @click="load(offset + PAGE)">下一页</button></nav>
      </details>
    </template>
    <p v-if="message" class="message" role="status">{{ message }}</p>
  </section>
</template>

<style scoped>
.endfield-gacha { display:grid; gap:16px; min-width:0; }
.gacha-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
.gacha-head h2 { margin:4px 0; }
.sync-note, .counts, .muted, small { color:var(--text-muted); font-size:12px; }
.warn { color:var(--stale-text); font-size:12px; }
.pool-grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fill, minmax(240px, 1fr)); }
.pool-card { border:1px solid var(--border); border-radius:8px; padding:14px; background:var(--card-bg); min-width:0; }
.pool-card h3 { margin:0 0 10px; font-size:14px; }
.pity { display:flex; justify-content:space-between; align-items:baseline; margin:0 0 6px; }
.pity strong { font-size:22px; font-weight:500; }
.six-list, .records { list-style:none; margin:10px 0 0; padding:0; display:grid; gap:6px; }
.six-list li, .records li { display:grid; grid-template-columns:1fr auto; gap:2px 10px; font-size:12px; }
.six-list small, .records small { grid-column:1 / -1; }
.records li.six strong { color:var(--accent); }
.record-list > summary { cursor:pointer; color:var(--text-muted); font-size:13px; padding:10px 0; }
.pager { display:flex; gap:12px; align-items:center; margin-top:10px; font-size:12px; }
.empty, .message { font-size:13px; color:var(--text-muted); }
</style>
