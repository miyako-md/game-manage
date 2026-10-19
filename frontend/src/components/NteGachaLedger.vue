<script setup>
import { computed, ref, watch } from 'vue'
import { isCloudMode } from '../http-client.js'
const cloudMode = isCloudMode()
import { getLedgerSummary, getLedgerRecords, previewLedger, importLedger, getLedgerRules, saveLedgerRule, exportLedger, pityLabel, ledgerDate, poolLabel, requirementLabel, resultLabel } from '../nte-gacha-api.js'
import { gauge } from '../nte-charts.js'
import AppIcon from './AppIcon.vue'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'
import RingGauge from './RingGauge.vue'
import NteIcon from './NteIcon.vue'
import { nteRewardIcon } from '../nte-icons.js'

const props = defineProps({ accountId: { type: String, default: '' }, snapshot:{type:Object,default:null}, imageMode:{type:Boolean,default:false} })
const summary = ref(null), records = ref([]), recordTotal = ref(0), rules = ref([])
const rewardIcon = row => nteRewardIcon({ id: row.reward_id, name: row.reward_name, type: row.reward_type })
const pool = ref(''), offset = ref(0), busy = ref(false), error = ref(''), message = ref('')
const documentData = ref(null), fileName = ref(''), preview = ref(null)
const latest = ref(false), continuous = ref(false), identity = ref(false)
const rulePool = ref(''), ruleLimit = ref(''), ruleNote = ref(''), ruleConfirmed = ref(false)
// The backend fixes the reset reward per pool and refuses mystery-box rules (no per-round identity or reset rule).
const ruleType = computed(() => rulePool.value === 'Arc_MiracleBox' ? 'arc' : 'character')
const ruleable = pool => pool !== 'Gashapon_MysteryBox'
const segmented = ref(false), exportStart = ref(1), exportNext = ref(null)
let generation = 0, listRequest = 0, fileRequest = 0
function importBody() { return { document: documentData.value, latest_confirmed: latest.value, continuity_confirmed: continuous.value, identity_confirmed: identity.value } }
async function loadRecords() {
  const id = generation, request = ++listRequest
  try {
    const data = await getLedgerRecords(pool.value, offset.value)
    if (id !== generation || request !== listRequest) return
    records.value = data.records || []; recordTotal.value = data.total || 0
  } catch (e) { if (id === generation && request === listRequest) error.value = e.message }
}
async function load() {
  const id = generation
  if (!props.accountId || props.imageMode) return
  busy.value = true; error.value = ''
  try {
    const [data, ruleData] = await Promise.all([getLedgerSummary(), getLedgerRules()])
    if (id !== generation) return
    summary.value = data; rules.value = ruleData.rules || []
    await loadRecords()
  } catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
watch(() => props.accountId, () => {
  generation++; listRequest++; fileRequest++; summary.value = null; records.value = []; rules.value = []; pool.value = ''; offset.value = 0
  documentData.value = null; fileName.value = ''; preview.value = null; latest.value = continuous.value = identity.value = false
  rulePool.value = ''; ruleLimit.value = ''; ruleNote.value = ''; ruleConfirmed.value = false; error.value = ''; message.value = ''; busy.value = false
  segmented.value = false; exportStart.value = 1; exportNext.value = null
  if (props.imageMode) { summary.value = props.snapshot; records.value = props.snapshot?.records || []; recordTotal.value = props.snapshot?.total_records || 0 }
  else load()
}, { immediate: true })
watch([pool, offset], () => { if (props.accountId && !props.imageMode) loadRecords() })
watch(pool, () => { exportStart.value = 1; exportNext.value = null })
watch([latest, continuous, identity], () => { preview.value = null })
async function chooseFile(event) {
  const file = event.target.files?.[0], id = generation, request = ++fileRequest
  documentData.value = null; preview.value = null; error.value = ''; message.value = ''; fileName.value = file?.name || ''
  latest.value = continuous.value = identity.value = false
  if (!file) return
  if (file.size > 8 * 1024 * 1024) { error.value = '文件超过 8 MB，请分批导入'; return }
  try {
    const value = JSON.parse(await file.text())
    if (id !== generation || request !== fileRequest) return
    documentData.value = value
  } catch { if (id === generation && request === fileRequest) error.value = '文件不是有效 JSON，请导出原始记录文件后重试' }
}
async function inspect() {
  const id = generation
  busy.value = true; error.value = ''; message.value = ''
  try { const result = await previewLedger(importBody()); if (id === generation) preview.value = result }
  catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
async function commitImport() {
  const id = generation, value = preview.value
  if (!value) return
  busy.value = true; error.value = ''
  try {
    const result = await importLedger({ ...importBody(), preview_id: value.preview_id })
    if (id !== generation) return
    message.value = `导入完成：新增 ${result.imported ?? 0} 条，重复 ${result.duplicates ?? 0} 条`
    preview.value = null; await load()
  } catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
async function download() {
  const id = generation
  busy.value = true; error.value = ''
  try {
    const start = Math.max(0, Number(exportStart.value || 1) - 1)
    const data = await exportLedger(pool.value, segmented.value ? start : null)
    if (id !== generation) return
    const blob = new Blob([JSON.stringify(data)], { type: 'application/json' })
    const url = URL.createObjectURL(blob), link = document.createElement('a')
    link.href = url; link.download = `nte-gacha-${props.accountId}${segmented.value ? `-from-${start + 1}` : ''}.json`; link.click(); URL.revokeObjectURL(url)
    exportNext.value = data.export_page?.next_offset ?? null
    if (segmented.value) message.value = `已导出本段 ${data.records?.length || 0} 条。${exportNext.value == null ? '已到末尾。' : `下一段从第 ${exportNext.value + 1} 条开始。`}`
  } catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
async function saveRule() {
  const id = generation
  busy.value = true; error.value = ''
  try {
    await saveLedgerRule({ pool_id: rulePool.value, s_hard_pity: Number(ruleLimit.value), reset_reward_type: ruleType.value,
      source_note: ruleNote.value, confirmed: ruleConfirmed.value })
    if (id !== generation) return
    message.value = '自定义规则已保存'; await load()
  } catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
function selectRule(value) {
  rulePool.value = value
  const existing = rules.value.find(r => r.pool_id === value)
  ruleLimit.value = existing?.s_hard_pity || ''
  ruleNote.value = existing?.source_note || ''; ruleConfirmed.value = false
}
function nextExport() { exportStart.value = exportNext.value + 1; download() }
// How far the current pity is towards the hard pity the reader set; unknown without a rule and a complete record.
function pityGauge(item) {
  const count = item.pity?.count, left = item.pity?.hard_pity_remaining
  return Number.isInteger(count) && Number.isInteger(left) && left >= 0 && count + left > 0 ? gauge(count, count + left) : null
}
</script>

<template>
  <section class="cap-card ledger" :aria-label="cloudMode ? '本人逐抽账本' : '本地逐抽账本'">
    <header class="cap-title ledger-head">
      <h2>逐抽账本</h2>
      <InfoHint text="导入的逐条抽卡记录与社区统计分别计算。" />
      <span v-if="accountId" class="saved-count"><b>{{ summary?.total_records ?? 0 }}</b>条已保存记录</span>
      <span v-if="!imageMode" class="head-actions">
        <label v-if="accountId" class="check"><input type="checkbox" v-model="segmented" :disabled="busy" />分段导出大账本</label>
        <button v-if="accountId" type="button" class="ui-button small-button" :disabled="busy" @click="load">刷新账本</button>
        <button type="button" class="ui-button small-button" :disabled="busy || !accountId" @click="download">导出记录</button>
      </span>
    </header>
    <p v-if="!accountId && !imageMode" class="notice">请先在社区账号登录异环并刷新账号资料，账本按游戏角色独立保存。</p>
    <template v-else>
      <div v-if="segmented" class="toolbar export-controls">
        <label>从第 <input type="number" v-model="exportStart" min="1" :disabled="busy" /> 条开始</label>
        <button v-if="exportNext != null" type="button" class="ui-button small-button" :disabled="busy" @click="nextExport">下载下一段</button>
        <InfoHint align="end" text="每段最多 2,000 条。恢复后需重新确认记录连续，才能计算垫抽。" />
        <p class="export-warning">请按提示下载全部分段，期间不要导入新记录。</p>
      </div>
      <p v-if="error" role="alert" class="notice error">{{ error }}</p><p v-if="message" role="status" class="notice">{{ message }}</p>
      <details v-if="!imageMode" class="panel import-panel"><summary>导入逐抽记录<AppIcon name="chevron" :size="14" class="t-disclosure" /></summary>
        <div class="panel-body">
          <div class="file-row">
            <label class="file-picker">选择 JSON 文件<input type="file" accept=".json,application/json" :disabled="busy" @change="chooseFile" /></label>
            <span v-if="fileName" class="file-name">{{ fileName }}</span>
            <InfoHint align="end" text="支持本账本和 nte-history-export v1 文件，最多 8 MB、50,000 条。" />
          </div>
          <div class="coverage"><label><input type="checkbox" v-model="latest" :disabled="busy" />包含导出时该卡池的最新一抽</label><label><input type="checkbox" v-model="continuous" :disabled="busy" />记录连续，无漏页或缺行</label><label><input type="checkbox" v-model="identity" :disabled="busy" />文件未标明角色编号时，确认属于当前角色</label></div>
          <div class="panel-actions"><button type="button" class="ui-button small-button" :disabled="busy || !documentData" @click="inspect">校验并预览</button><InfoHint text="文件有缺页或读取错误时，需补全记录才能计算垫抽。" /></div>
          <div v-if="preview" class="preview" role="status">
            <p class="preview-head"><strong>预览</strong><span class="chip"><b>{{ preview.record_count }}</b> 条</span><span class="chip">新增 <b>{{ preview.new_records }}</b></span><span class="chip">重复 <b>{{ preview.duplicates }}</b></span></p>
            <p v-if="preview.imported_rules?.length">同时恢复文件中的 {{ preview.imported_rules.length }} 条自定义规则。</p>
            <p v-if="preview.identity_confirmation_required" class="warn">文件未标明角色，请勾选“确认属于当前角色”后重新预览。</p>
            <ul v-if="preview.warnings?.length"><li v-for="(note, index) in preview.warnings" :key="index">{{ requirementLabel(note) }}</li></ul>
            <ul v-if="preview.missing_requirements?.length"><li v-for="(note, index) in preview.missing_requirements" :key="index">{{ requirementLabel(note) }}</li></ul>
            <button type="button" class="ui-button small-button primary" :disabled="busy || (preview.identity_confirmation_required && !identity)" @click="commitImport">{{ cloudMode ? '确认导入到当前账号' : '确认导入到本机' }}</button>
          </div>
          <details class="source-help"><summary>导入文件说明</summary><p>使用逐抽历史导出文件，或本账本导出的备份。社区出 S 汇总无法导入。</p><p><a href="https://github.com/Golumpa/nte-exporter" target="_blank" rel="noopener noreferrer">nte-exporter 文件格式说明 ↗</a></p></details>
        </div>
      </details>
      <div v-if="summary?.pools?.length" class="pool-grid">
        <article v-for="item in summary.pools" :key="item.pool_id" class="pool-card">
          <header class="pool-card-head"><h3>{{ poolLabel(item.pool_id) }}</h3><span v-if="item.pity?.rule_basis === 'user_configured'" class="chip">按用户规则</span><button type="button" v-if="!imageMode && ruleable(item.pool_id)" class="ui-button ghost small-button" @click="selectRule(item.pool_id)">设置此池规则</button></header>
          <span v-if="!imageMode && pityGauge(item)" class="pity-ring" aria-hidden="true"><RingGauge :value="pityGauge(item).current" :max="pityGauge(item).total" label="垫抽进度" :size="84" :stroke="9" color="var(--game-vivid)"><b class="ring-pct">{{ Math.round(pityGauge(item).pct) }}%</b></RingGauge></span>
          <dl class="kv-grid pity-kv"><div><dt>当前垫抽</dt><dd>{{ pityLabel(item.pity) }}</dd></div><div><dt>距所设 S 保底</dt><dd>{{ item.pity?.hard_pity_remaining == null ? '未知' : `${item.pity.hard_pity_remaining} 抽` }}</dd></div></dl>
          <p class="muted">已导入 {{ item.total_pulls }} 次计数抽取<template v-if="item.pity?.as_of"><span class="sep" aria-hidden="true" />记录范围：{{ ledgerDate(item.pity.latest_record_at || item.pity.as_of) }}</template></p>
          <details v-if="!imageMode && (item.pity?.basis || item.pity?.missing_requirements?.length)" data-render-collapsed><summary>计算详情</summary><p v-if="item.pity?.basis" class="muted">{{ requirementLabel(item.pity.basis) }}</p><ul v-if="item.pity?.missing_requirements?.length" class="requirements"><li v-for="(note, index) in item.pity.missing_requirements" :key="index">{{ requirementLabel(note) }}</li></ul></details>
        </article>
      </div>
      <details v-if="!imageMode" class="panel rule-editor" :open="!!rulePool"><summary>卡池规则<AppIcon name="chevron" :size="14" class="t-disclosure" /></summary>
        <form class="panel-body rule-form" @submit.prevent="saveRule">
          <div class="field">卡池<MenuSelect :model-value="rulePool" label="卡池" :options="[{ value: '', label: '选择卡池' }, ...(summary?.pools || []).filter(item => ruleable(item.pool_id)).map(item => ({ value: item.pool_id, label: poolLabel(item.pool_id) }))]" @change="selectRule" /></div>
          <label>S 硬保底抽数<input v-model="ruleLimit" type="number" min="1" max="1000" required /></label>
          <div class="field">重置奖励<span class="rule-reward">{{ !rulePool ? '先选择卡池' : ruleType === 'arc' ? 'S 弧盘' : 'S 角色' }}</span></div>
          <label class="wide">规则依据<input v-model="ruleNote" maxlength="200" required placeholder="例如：游戏内某卡池规则及核对日期" /></label>
          <label class="wide check"><input type="checkbox" v-model="ruleConfirmed" required />已核对游戏内规则，按此设置计算</label>
          <div class="wide panel-actions"><button class="ui-button small-button" :disabled="busy || !rulePool || !ruleConfirmed">保存规则</button><InfoHint text="请填写对应卡池的游戏内规则。记录完整且奖励类型明确时，显示距所设 S 保底的抽数。" /></div>
        </form>
      </details>
      <div class="toolbar records-toolbar">
        <h3>逐抽记录</h3>
        <MenuSelect v-if="!imageMode" v-model="pool" label="卡池" :options="[{ value: '', label: '全部卡池' }, ...(summary?.pools || []).map(item => ({ value: item.pool_id, label: poolLabel(item.pool_id) }))]" @change="offset = 0" />
        <span class="count">{{ recordTotal }} 条</span>
      </div>
      <p v-if="imageMode && !records.length && summary?.total_records > 0" class="empty">逐条记录未加载；已导入 {{ summary.total_records }} 条，可在网页查看。</p>
      <p v-else-if="!records.length" class="empty">暂无逐抽记录</p>
      <div v-else class="records-table"><table class="data-table"><thead><tr><th>时间</th><th>卡池</th><th>物品</th><th>品质</th><th class="num">数量</th><th>计数信息</th></tr></thead><tbody><tr v-for="row in records" :key="row.uid"><td>{{ ledgerDate(row.timestamp) }}</td><td>{{ poolLabel(row.pool_group_id) }}</td><td><span v-if="imageMode" class="ledger-reward-image"><NteIcon v-if="rewardIcon(row)" :src="rewardIcon(row)" :name="row.reward_name || row.reward_id" size="large" /><span>{{ row.reward_name || row.reward_id }}</span></span><template v-else>{{ row.reward_name || row.reward_id }}</template></td><td>{{ row.reward_rank || '未知' }}</td><td class="num">{{ row.quantity ?? '未知' }}</td><td>{{ resultLabel(row.result_type) }}</td></tr></tbody></table></div>
      <nav v-if="!imageMode && recordTotal > 100" class="pagination" aria-label="抽卡记录分页"><button type="button" class="ui-button small-button" :disabled="offset === 0 || busy" @click="offset = Math.max(0, offset - 100)">上一页</button><span>{{ Math.floor(offset / 100) + 1 }} / {{ Math.ceil(recordTotal / 100) }}</span><button type="button" class="ui-button small-button" :disabled="offset + 100 >= recordTotal || busy" @click="offset += 100">下一页</button></nav>
    </template>
  </section>
</template>

<style scoped>
.ledger-reward-image { display:flex; align-items:center; gap:10px; min-width:0; }
.ledger-reward-image > span { overflow-wrap:anywhere; }
.ledger { display:grid; gap:12px; min-width:0; }
.ledger > * { min-width:0; }
.ledger h2 { font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.01em; }
.ledger h3 { font-size:14px; font-weight:600; }
.ledger-head { position:relative; margin-bottom:0; }
.saved-count { display:inline-flex; align-items:center; gap:4px; margin-left:4px; color:var(--text-muted); font-size:12px; font-weight:400; }
.saved-count b { color:var(--text); font-size:20px; line-height:24px; font-weight:550; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.head-actions { display:inline-flex; flex-wrap:wrap; align-items:center; gap:6px; margin-left:auto; }
.export-warning { flex-basis:100%; margin:0; color:var(--stale-text); font-size:12px; }
.check { display:inline-flex; align-items:center; gap:6px; color:var(--text-body); font-size:13px; font-weight:400; cursor:pointer; }
.ledger input[type=checkbox] { margin:0; accent-color:var(--accent); }
.ledger input:not([type=checkbox]):not([type=file]) { min-height:34px; max-width:100%; padding:4px 12px; border:1px solid var(--border); border-radius:var(--radius-control); background:var(--card-bg); color:var(--text); font-size:13px; }
.export-controls { position:relative; margin:0; font-size:13px; color:var(--text-body); }
.export-controls input[type=number] { width:88px; margin:0 4px; }
.notice { padding:10px 14px; border-radius:var(--radius-well); background:var(--surface-soft); color:var(--text-body); font-size:13px; line-height:1.6; }
.notice.error { background:var(--danger-bg); color:var(--danger); }
.muted { color:var(--text-muted); font-size:12px; line-height:1.6; }

/* Import and rule panels: collapsed one-line disclosures until needed, soft tiles with a hairline. */
.panel { border-radius:var(--radius-tile); background:var(--surface-soft); box-shadow:inset 0 0 0 1px var(--overlay-2); }
.panel > summary { display:flex; align-items:center; gap:8px; min-height:44px; padding:8px 14px 8px 16px; border-radius:var(--radius-tile); color:var(--text); font-size:14px; font-weight:600; list-style:none; cursor:pointer; }
.panel > summary::-webkit-details-marker { display:none; }
.panel > summary > svg { margin-left:auto; color:var(--text-faint); }
.panel > summary:focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:var(--radius-tile); }
@media (hover:hover) and (pointer:fine) { .panel > summary:hover { background:var(--hover-bg); } }
.panel-body { display:grid; gap:12px; padding:4px 16px 16px; font-size:13px; }
.file-row, .panel-actions { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; }
.file-picker { display:inline-flex; flex-wrap:wrap; align-items:center; gap:8px; color:var(--text-body); font-size:13px; }
.file-picker input { max-width:100%; color:var(--text-muted); font-size:13px; }
.file-picker input::file-selector-button { margin-right:8px; padding:4px 14px; border:1px solid var(--border-strong); border-radius:var(--radius-control); background:var(--card-bg); color:var(--text-body); font:inherit; cursor:pointer; }
.file-name { color:var(--text-muted); font-size:12px; }
.coverage { display:grid; gap:4px; }
.coverage label { display:flex; align-items:flex-start; gap:8px; color:var(--text-body); line-height:20px; }
.coverage input { margin-top:3px !important; }
.preview { display:grid; gap:6px; padding:10px 14px; border-radius:var(--radius-well); background:var(--card-bg); box-shadow:inset 0 0 0 1px var(--overlay-2); line-height:1.6; }
.preview-head { display:flex; flex-wrap:wrap; align-items:center; gap:6px; }
.preview-head strong { font-weight:600; }
.preview .warn { color:var(--warning-text); }
.preview ul { margin:0; padding-left:18px; list-style:disc; color:var(--text-muted); }
.preview > button { justify-self:start; }
.source-help { color:var(--text-muted); font-size:13px; line-height:1.7; }
.source-help > summary { width:fit-content; color:var(--accent); cursor:pointer; }
.source-help p { margin-top:4px; }
.source-help a { color:var(--accent); }

/* Pool cards: the ring towards the hard pity beside the pity numbers. */
.pool-grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(min(100%, 340px), 1fr)); gap:12px; }
.pool-card { display:grid; gap:8px; min-width:0; padding:16px 18px; border-radius:var(--radius-tile); background:var(--surface-soft); box-shadow:inset 0 0 0 1px var(--overlay-2); font-size:13px; overflow-wrap:anywhere; }
.pool-card:has(.pity-ring) { grid-template-columns:auto minmax(0, 1fr); column-gap:16px; }
.pool-card:has(.pity-ring) > :not(.pity-ring):not(.pity-kv) { grid-column:1 / -1; }
.pity-ring { grid-row:2 / span 1; align-self:center; }
.ring-pct { color:var(--text); font-size:15px; font-weight:600; letter-spacing:-.01em; }
.pool-card-head { position:relative; display:flex; flex-wrap:wrap; align-items:center; gap:4px 8px; }
.pool-card-head > button { margin-left:auto; }
.pity-kv { --kv-min:100px; }
.pity-kv dd { font-size:20px; line-height:26px; font-weight:550; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.pity-kv > div { padding:0; background:none; }
.sep::before { content:'·'; margin:0 6px; color:var(--text-faint); }
.requirements { margin:0; padding-left:16px; list-style:disc; color:var(--text-muted); font-size:12px; line-height:1.6; }

.rule-form { grid-template-columns:repeat(3, minmax(0, 1fr)); gap:10px 14px; }
.rule-form label,.rule-form .field { display:grid; gap:4px; color:var(--text-muted); font-size:12px; }
.rule-reward { color:var(--text); font-size:13px; line-height:34px; }
.rule-form .menu-select { display:flex; width:100%; }
.rule-form .wide { grid-column:1 / -1; }
.rule-form .check { display:flex; align-items:center; color:var(--text-body); font-size:13px; }

.records-toolbar { margin:6px 0 0; }
.records-toolbar h3 { margin-right:4px; }
.records-table { overflow-x:auto; }
.records-table td, .records-table th { white-space:nowrap; font-variant-numeric:tabular-nums; }
.empty { position:relative; display:flex; align-items:center; justify-content:center; gap:4px; padding:14px 0; color:var(--text-muted); font-size:13px; }
.pagination { display:flex; align-items:center; justify-content:center; gap:10px; color:var(--text-muted); font-size:13px; font-variant-numeric:tabular-nums; }
@media (max-width:650px) {
  .rule-form { grid-template-columns:1fr; }
  .head-actions { margin-left:0; flex-basis:100%; }
}
</style>
