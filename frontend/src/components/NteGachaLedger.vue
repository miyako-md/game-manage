<script setup>
import { ref, watch } from 'vue'
import { getLedgerSummary, getLedgerRecords, previewLedger, importLedger, getLedgerRules, saveLedgerRule, exportLedger, pityLabel, ledgerDate, poolLabel, requirementLabel, resultLabel } from '../nte-gacha-api.js'

const props = defineProps({ accountId: { type: String, default: '' } })
const summary = ref(null), records = ref([]), recordTotal = ref(0), rules = ref([])
const pool = ref(''), offset = ref(0), busy = ref(false), error = ref(''), message = ref('')
const documentData = ref(null), fileName = ref(''), preview = ref(null)
const latest = ref(false), continuous = ref(false), identity = ref(false)
const rulePool = ref(''), ruleLimit = ref(''), ruleType = ref('character'), ruleNote = ref(''), ruleConfirmed = ref(false)
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
  if (!props.accountId) return
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
  load()
}, { immediate: true })
watch([pool, offset], () => { if (props.accountId) loadRecords() })
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
    message.value = '卡池规则已保存，按用户设置计算'; await load()
  } catch (e) { if (id === generation) error.value = e.message }
  finally { if (id === generation) busy.value = false }
}
function selectRule(value) {
  rulePool.value = value
  const existing = rules.value.find(r => r.pool_id === value)
  ruleLimit.value = existing?.s_hard_pity || ''; ruleType.value = existing?.reset_reward_type || 'character'
  ruleNote.value = existing?.source_note || ''; ruleConfirmed.value = false
}
function nextExport() { exportStart.value = exportNext.value + 1; download() }
</script>

<template>
  <section class="cap-card ledger" aria-label="本地逐抽账本">
    <header class="ledger-head"><div><p class="eyebrow">LOCAL PULL HISTORY</p><h2>逐抽账本</h2><p class="muted">逐条保存真实记录。导入覆盖范围与社区统计分别计算。</p></div><button type="button" :disabled="busy || !accountId" @click="download">导出记录</button></header>
    <p v-if="!accountId" class="notice">请先在社区账号登录异环并刷新账号资料，账本按游戏角色独立保存。</p>
    <template v-else>
      <p v-if="error" role="alert" class="notice error">{{ error }}</p><p v-if="message" role="status" class="notice">{{ message }}</p>
      <div class="ledger-summary"><strong>{{ summary?.total_records ?? 0 }}</strong><span>条已保存记录</span><span class="muted">· 截至导入文件时间，不代表已经覆盖账号全部历史</span><button :disabled="busy" @click="load">刷新账本</button></div>
      <div class="export-controls"><label><input type="checkbox" v-model="segmented" :disabled="busy" />分段导出大账本</label><label v-if="segmented">从第 <input type="number" v-model="exportStart" min="1" :disabled="busy" /> 条开始</label><button v-if="segmented && exportNext != null" :disabled="busy" @click="nextExport">下载下一段</button><p v-if="segmented" class="muted">每段最多 2,000 条，过大时自动缩小；请按提示下载全部分段，期间不要导入新记录。分段恢复保留流水，垫抽范围需原始连续记录重新证明。</p></div>
      <details class="import-panel" open><summary>导入逐抽记录</summary>
        <p class="muted">支持 nte-history-export v1 和本账本导出的 JSON；最大 8 MB / 50,000 条。塔吉多出 S 汇总不能作为逐抽历史导入。</p>
        <label class="file-picker">选择 JSON 文件<input type="file" accept=".json,application/json" :disabled="busy" @change="chooseFile" /></label><p v-if="fileName" class="muted">{{ fileName }}</p>
        <div class="coverage"><label><input type="checkbox" v-model="latest" :disabled="busy" />记录包含截至导出时该卡池最新的一抽</label><label><input type="checkbox" v-model="continuous" :disabled="busy" />已核对所导入记录连续，没有漏页或缺行</label><label><input type="checkbox" v-model="identity" :disabled="busy" />文件未标明 UID 时，我确认它属于当前角色</label></div>
        <p class="muted">这些确认仅说明你核对过的范围。文件自带缺页或解码失败警告时，垫抽仍会标记未知。</p>
        <button :disabled="busy || !documentData" @click="inspect">校验并预览</button>
        <div v-if="preview" class="preview" role="status"><strong>预览：{{ preview.record_count }} 条 · 新增 {{ preview.new_records }} · 重复 {{ preview.duplicates }}</strong>
          <p v-if="preview.imported_rules?.length">将同时恢复文件中的 {{ preview.imported_rules.length }} 条用户设置规则。</p>
          <p v-if="preview.identity_confirmation_required">文件缺少角色身份，请勾选归属确认后重新预览。</p>
          <ul v-if="preview.warnings?.length"><li v-for="(note, index) in preview.warnings" :key="index">{{ requirementLabel(note) }}</li></ul>
          <ul v-if="preview.missing_requirements?.length"><li v-for="(note, index) in preview.missing_requirements" :key="index">{{ requirementLabel(note) }}</li></ul>
          <button :disabled="busy || (preview.identity_confirmation_required && !identity)" @click="commitImport">确认导入到本机</button>
        </div>
        <details class="source-help"><summary>文件从哪里来？还缺哪些接口？</summary><p>现有社区接口不含全部逐抽。可使用真实游戏历史导出文件；记录只能覆盖已捕获、已翻阅的范围。</p><p><a href="https://github.com/Golumpa/nte-exporter" target="_blank" rel="noopener noreferrer">nte-exporter 格式与使用说明 ↗</a>：游戏历史通信导出，国服兼容尚未实测。国服截图 OCR 导出目前需要转换成账本规范并核对识别结果。</p><p>仍缺：经验证的国服全量历史接口及分页方式、历史保留期限、不同卡池继承和 UP 规则。没有这些证据时不会宣称自动全量同步或必出 UP。</p></details>
      </details>
      <div v-if="summary?.pools?.length" class="pool-grid"><article v-for="item in summary.pools" :key="item.pool_id" class="pool-card"><h3>{{ poolLabel(item.pool_id) }}</h3><p class="muted">已导入 {{ item.total_pulls }} 次计数抽取</p><div class="pity"><span>当前垫抽</span><strong>{{ pityLabel(item.pity) }}</strong></div><p class="muted">{{ requirementLabel(item.pity?.basis) }}</p><p v-if="item.pity?.as_of" class="muted">记录范围：{{ ledgerDate(item.pity.latest_record_at || item.pity.as_of) }}</p><p>距所设 S 保底：{{ item.pity?.hard_pity_remaining == null ? '未知' : `${item.pity.hard_pity_remaining} 抽` }}</p><p v-if="item.pity?.rule_basis === 'user_configured'" class="muted">按用户设置的规则计算，不表示已核实官方规则或必出 UP。</p><ul class="requirements"><li v-for="(note, index) in item.pity?.missing_requirements || []" :key="index">{{ requirementLabel(note) }}</li></ul><button @click="selectRule(item.pool_id)">设置此池规则</button></article></div>
      <details class="rule-editor" :open="!!rulePool"><summary>卡池规则</summary><p class="muted">只有记录完整性和奖励语义满足条件，才计算所设保底剩余。请核对游戏内对应卡池规则。</p><form @submit.prevent="saveRule"><label>卡池<select v-model="rulePool" required @change="selectRule(rulePool)"><option value="">选择卡池</option><option v-for="item in summary?.pools || []" :key="item.pool_id" :value="item.pool_id">{{ poolLabel(item.pool_id) }}</option></select></label><label>S 硬保底抽数<input v-model="ruleLimit" type="number" min="1" max="1000" required /></label><label>重置奖励<select v-model="ruleType"><option value="character">S 角色</option><option value="arc">S 弧盘</option></select></label><label class="wide">规则依据<input v-model="ruleNote" maxlength="200" required placeholder="例如：游戏内某卡池规则及核对日期" /></label><label class="wide check"><input type="checkbox" v-model="ruleConfirmed" required />我已核对这项卡池规则，按我的设置计算</label><button :disabled="busy || !rulePool || !ruleConfirmed">保存规则</button></form></details>
      <div class="records-toolbar"><h3>逐抽记录</h3><label>卡池<select v-model="pool" @change="offset = 0"><option value="">全部卡池</option><option v-for="item in summary?.pools || []" :key="item.pool_id" :value="item.pool_id">{{ poolLabel(item.pool_id) }}</option></select></label><span class="muted">{{ recordTotal }} 条</span></div>
      <p v-if="!records.length" class="notice">暂无逐抽记录。导入后即可查看；这里不会用社区出 S 明细补造历史。</p>
      <div v-else class="records-table"><table><thead><tr><th>时间（源文件）</th><th>卡池</th><th>物品</th><th>品质</th><th>数量</th><th>计数信息</th></tr></thead><tbody><tr v-for="row in records" :key="row.uid"><td>{{ ledgerDate(row.timestamp) }}</td><td>{{ poolLabel(row.pool_group_id) }}</td><td>{{ row.reward_name || row.reward_id }}</td><td>{{ row.reward_rank || '未知' }}</td><td>{{ row.quantity ?? '未知' }}</td><td>{{ resultLabel(row.result_type) }}</td></tr></tbody></table></div>
      <nav v-if="recordTotal > 100" class="pagination" aria-label="抽卡记录分页"><button :disabled="offset === 0 || busy" @click="offset = Math.max(0, offset - 100)">上一页</button><span>{{ Math.floor(offset / 100) + 1 }} / {{ Math.ceil(recordTotal / 100) }}</span><button :disabled="offset + 100 >= recordTotal || busy" @click="offset += 100">下一页</button></nav>
    </template>
  </section>
</template>

<style scoped>
.export-controls { display:flex; gap:14px; flex-wrap:wrap; align-items:center; font-size:12px; }.export-controls input[type=number] { width:90px; }.export-controls p { flex-basis:100%; }
.ledger { display:grid; gap:20px; min-width:0; }.ledger h2 { font-size:22px; }.ledger h3 { font-size:14px; }.ledger-head,.ledger-summary,.records-toolbar,.pagination { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }.ledger-head { justify-content:space-between; }.ledger-head .muted { margin-top:8px; }.ledger .eyebrow { color:var(--accent); font-size:10px; letter-spacing:.15em; margin-bottom:8px; }.muted,.requirements { color:var(--text-muted); font-size:12px; line-height:1.7; }.ledger-summary>strong { font-size:28px; color:var(--accent); }.ledger button { padding:8px 12px; background:#d8bb8412; color:var(--accent); border:1px solid var(--border); border-radius:7px; cursor:pointer; font:inherit; font-size:12px; }.ledger button:disabled { opacity:.45; cursor:default; }.ledger input:not([type=checkbox]),.ledger select { color:var(--text); background:var(--bg); border:1px solid var(--border); padding:8px; border-radius:6px; max-width:100%; }.ledger input[type=checkbox] { accent-color:var(--accent); }.notice,.preview { padding:14px; background:#d8bb840b; border:1px solid var(--border); border-radius:8px; font-size:12px; line-height:1.7; }.error { color:#efb2a0; }.import-panel,.rule-editor { padding:16px; border:1px solid var(--border); border-radius:9px; }.ledger summary { cursor:pointer; color:var(--text); font-weight:550; margin-bottom:12px; }.file-picker { display:block; margin:14px 0; font-size:12px; }.file-picker input { display:block; margin-top:8px; }.coverage { display:grid; gap:9px; font-size:12px; margin:16px 0; }.preview { margin-top:16px; }.preview ul { padding-left:20px; margin:8px 0; }.source-help { margin-top:16px; font-size:12px; line-height:1.8; }.source-help a { color:var(--accent); }.pool-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }.pool-card { border:1px solid var(--border); border-radius:10px; padding:17px; display:grid; gap:9px; font-size:12px; overflow-wrap:anywhere; }.pity { display:flex; align-items:center; justify-content:space-between; }.pity strong { font-size:23px; color:var(--accent); }.requirements { padding-left:15px; }.rule-editor form { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }.rule-editor label { display:grid; gap:7px; font-size:12px; }.rule-editor .wide { grid-column:1/-1; }.rule-editor .check { display:flex; align-items:center; }.records-toolbar label { margin-left:auto; font-size:12px; }.records-toolbar select { margin-left:8px; }.records-table { overflow:auto; }.records-table table { width:100%; border-collapse:collapse; text-align:left; font-size:12px; }.records-table td,.records-table th { border-bottom:1px solid var(--border); padding:11px 10px; white-space:nowrap; }.records-table th { color:var(--text-muted); font-weight:500; }.pagination { justify-content:center; font-size:12px; }@media(max-width:650px){.rule-editor form{grid-template-columns:1fr}.ledger-head{align-items:start}.pool-grid{grid-template-columns:1fr}}
</style>
