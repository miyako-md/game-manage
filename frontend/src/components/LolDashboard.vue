<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import SummaryMetrics from './SummaryMetrics.vue'
import AnnouncementList from './AnnouncementList.vue'
import AccountCard from './AccountCard.vue'
import MatchList from './MatchList.vue'
import LolTrend from './LolTrend.vue'
import { getLolAnalysis, collectLol, getLolMatch } from '../lol-api.js'
import { DAY_MS, beijingDayStart, formatBeijingDateTime } from '../calendar.js'

const props = defineProps({ snaps: { type: Object, default: () => ({}) } })
const emit = defineEmits(['refresh'])
const days = ref(90), queue = ref(''), section = ref('overview')
const periods = [[7, '近 7 天'], [30, '近 30 天'], [90, '近 90 天'], [365, '近 365 天'], [0, '全部归档']]
const queues = [['', '全部模式'], ['2400', '海克斯大乱斗'], ['450', '极地大乱斗'], ['420', '单双排位'], ['440', '灵活排位']]
const tabs = [['overview', '个人总览'], ['history', '对局记录'], ['hex', '海克斯'], ['announcement', '公告'], ['news', '资讯']]
const analysis = ref(null), loadedFilter = ref({ days: 90, queue: '' }), loading = ref(false), error = ref('')
const collecting = ref(false), collectError = ref(''), collectNote = ref('')
const expanded = ref(null), detail = ref(null), detailLoading = ref(false), detailError = ref('')
let generation = 0, analysisController, detailGeneration = 0, detailController, collectGeneration = 0, collectController, disposed = false
// The normalized summoner snapshot carries the stable LCU owner in extra.puuid.
const accountKey = computed(() => props.snaps.account?.payload?.extra?.puuid || '')
const val = value => Number.isFinite(value) ? Number(value.toFixed(1)) : '未知'
const percent = value => Number.isFinite(value) ? `${val(value)}%` : '未知'
const result = (win, remake = false) => remake ? '重开' : win === true ? '胜利' : win === false ? '失败' : '胜负未知'
const resultClass = row => row.remake ? 'remake' : row.win === true ? 'win' : row.win === false ? 'loss' : 'unknown'
const kda = row => `${val(row.kills)} / ${val(row.deaths)} / ${val(row.assists)}`
const fmt = formatBeijingDateTime
const overview = computed(() => analysis.value?.overview || {})
const coverage = computed(() => analysis.value?.coverage || {})
const hex = computed(() => analysis.value?.hextech || {})
const matches = computed(() => analysis.value?.matches || [])
const knownResults = computed(() => Number.isFinite(overview.value.wins) && Number.isFinite(overview.value.losses) ? overview.value.wins + overview.value.losses : null)
const hasArchive = computed(() => (coverage.value.archived_games ?? overview.value.games ?? 0) > 0)
const filterLabel = computed(() => `${periods.find(([key]) => key === loadedFilter.value.days)?.[1]} · ${queues.find(([key]) => key === loadedFilter.value.queue)?.[1]}`)
const metrics = computed(() => [
  { label: '对局场次', value: val(overview.value.games), note: `${val(overview.value.wins)} 胜 · ${val(overview.value.losses)} 负 · ${val(overview.value.unknown_results)} 未知 · ${val(overview.value.remakes)} 重开` },
  { label: '个人胜率', value: percent(overview.value.winrate), note: `有效胜负 ${val(knownResults.value)} 场；重开与未知胜负不计入` },
  { label: '平均参考评分', value: val(overview.value.average_score), note: `LOLhelper v3 · 3–16 分 · ${val(coverage.value.score_games)} 场可计算` },
  { label: '场均 K / D / A', value: `${val(overview.value.avg_kills)} / ${val(overview.value.avg_deaths)} / ${val(overview.value.avg_assists)}`, note: `已记录时长 ${val(overview.value.play_minutes)} 分钟` },
])
const heatDays = computed(() => {
  const count = loadedFilter.value.days || 365, end = beijingDayStart(), start = end - (count - 1) * DAY_MS
  const values = new Map((analysis.value?.heatmap || []).map(row => [row.date, row]))
  return Array.from({ length: count }, (_, i) => {
    const date = fmt(start + i * DAY_MS).slice(0, 10), row = values.get(date)
    return { date, games: row?.games ?? 0, wins: row?.wins ?? 0 }
  })
})
const heatMaximum = computed(() => Math.max(1, ...heatDays.value.map(row => row.games)))

function closeDetail() {
  detailGeneration++; detailController?.abort(); expanded.value = null; detail.value = null; detailLoading.value = false; detailError.value = ''
}
async function load() {
  const current = ++generation, filters = { days: days.value, queue: queue.value }
  analysisController?.abort(); analysisController = new AbortController()
  closeDetail(); loading.value = true; error.value = ''
  try {
    const next = await getLolAnalysis({ ...filters, signal: analysisController.signal })
    if (disposed || current !== generation) return
    if (next?.schema_version !== 1) throw new Error('本地分析数据版本不兼容，请更新服务后重试')
    analysis.value = next; loadedFilter.value = filters
  } catch (err) {
    if (!disposed && current === generation && err?.name !== 'AbortError') error.value = err.message
  } finally { if (!disposed && current === generation) loading.value = false }
}
async function collect() {
  if (collecting.value) return
  const current = ++collectGeneration
  collecting.value = true; collectError.value = ''; collectNote.value = ''; collectController = new AbortController()
  try {
    const data = await collectLol({ signal: collectController.signal })
    if (disposed || current !== collectGeneration) return
    collectNote.value = `本次采集 ${val(data.games)} 场，详情 ${val(data.details)} 场；详情未取得 ${val(data.failed_details)} 场。`
    await load()
    if (!disposed && current === collectGeneration) emit('refresh')
  } catch (err) { if (!disposed && current === collectGeneration && err?.name !== 'AbortError') collectError.value = err.message }
  finally { if (!disposed && current === collectGeneration) collecting.value = false }
}
async function toggleDetail(row) {
  if (expanded.value === row.match_id) { closeDetail(); return }
  closeDetail(); const current = ++detailGeneration
  expanded.value = row.match_id; detailLoading.value = true; detailController = new AbortController()
  try {
    const value = await getLolMatch(row.match_id, { signal: detailController.signal })
    if (!disposed && current === detailGeneration) detail.value = value.payload
  } catch (err) { if (!disposed && current === detailGeneration && err?.name !== 'AbortError') detailError.value = err.message }
  finally { if (!disposed && current === detailGeneration) detailLoading.value = false }
}
// Clear another owner's content synchronously; refreshes for the same owner may
// retain the last successful read. Generation guards also cover late transports.
watch(accountKey, () => {
  generation++; analysisController?.abort(); closeDetail()
  collectGeneration++; collectController?.abort()
  analysis.value = null; error.value = ''; collectError.value = ''; collectNote.value = ''; collecting.value = false
}, { flush: 'sync' })
watch([
  days, queue, accountKey,
  () => props.snaps.account?.fetched_at,
  () => props.snaps.match?.fetched_at,
  () => props.snaps.stats?.fetched_at,
], load, { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; analysisController?.abort(); collectController?.abort(); closeDetail() })
</script>

<template>
  <div class="lol-dashboard">
    <header class="lol-header">
      <div><span class="eyebrow">PERSONAL MATCH ARCHIVE</span><h2>{{ analysis?.account?.nickname || '我的英雄联盟' }}</h2><p>本机战绩档案<span v-if="analysis?.account"> · 等级 {{ val(analysis.account.level) }}</span> · 客户端关闭后仍可查看</p></div>
      <button type="button" class="collect-button" :disabled="collecting" @click="collect">{{ collecting ? '正在采集…' : '采集客户端战绩' }}</button>
    </header>
    <p v-if="collecting" class="lol-notice" role="status">正在读取客户端近期窗口与详情，最多等待 120 秒。</p>
    <p v-if="collectError" class="lol-error" role="alert">{{ collectError }}<span v-if="analysis">；已有分析数据仍保留。</span></p>
    <p v-if="collectNote" class="lol-notice" role="status">{{ collectNote }}</p>
    <div class="lol-toolbar">
      <nav class="detail-tabs" aria-label="英雄联盟数据分区"><button v-for="[key, label] in tabs" :key="key" type="button" :aria-pressed="section === key" @click="section = key">{{ label }}</button></nav>
      <div class="lol-filters"><label>时间<select :value="days" @change="days = Number($event.target.value)"><option v-for="[key, label] in periods" :key="key" :value="key">{{ label }}</option></select></label><label>模式<select :value="queue" @change="queue = $event.target.value"><option v-for="[key, label] in queues" :key="key" :value="key">{{ label }}</option></select></label><button class="reload-button" type="button" :disabled="loading" @click="load">重新读取</button></div>
    </div>
    <p v-if="loading" class="lol-notice" role="status">正在读取本地分析…<span v-if="analysis">暂时展示上次读取结果。</span></p>
    <p v-if="error" class="lol-error" role="alert">{{ error }}<span v-if="analysis">；保留上次成功读取的数据。</span></p>
    <details v-if="section === 'overview' && snaps.account?.payload" class="lol-panel"><summary>账号与排位快照{{ snaps.account.stale ? ' · 数据可能过期' : '' }}</summary><AccountCard :snap="snaps.account" /></details>
    <p v-if="analysis" class="coverage-line">当前展示：{{ filterLabel }} · 归档 {{ val(coverage.archived_games) }} 场 · 当前筛选 {{ val(overview.games) }} 场 · 有详情 {{ val(coverage.detail_games) }} 场<span v-if="analysis.collected_at"> · 采集于 {{ fmt(analysis.collected_at) }}（北京时间）</span></p>
    <template v-if="section === 'news' || section === 'announcement'"><AnnouncementList :snap="snaps[section]" :capability="section" /></template>
    <section v-else-if="!loading && !hasArchive" class="lol-empty">
      <div class="empty-symbol" aria-hidden="true">◈</div><h3>{{ analysis ? '本机尚无归档' : '本地档案暂不可用' }}</h3>
      <p>启动并登录英雄联盟客户端，点击上方「采集客户端战绩」建立个人档案。之后每次采集会补充、去重保存当前账号的近期战绩。</p>
      <p>客户端未运行时不能采集；已归档数据可以离线查看。客户端近期窗口通常最多 20 场，不代表完整历史。</p>
      <div v-if="section === 'history' && snaps.match?.payload?.length"><p>以下为升级前保留的近期对局快照，不计入新归档统计；实时详情需要客户端在线。</p><MatchList :snap="snaps.match" game-id="league_of_legends" /></div>
    </section>
    <template v-else-if="analysis && hasArchive">
      <template v-if="section === 'overview'">
        <SummaryMetrics :metrics="metrics" />
        <p class="method-note">评分为 LOLhelper v3 参考评分，非官方评分；仅完整队伍指标可计算。胜率以非重开的已知胜负为分母；重开保留在对局数与活跃日历中，不计入胜负、均分、KDA和连续胜负。</p>
        <p v-if="overview.current_streak?.kind && overview.current_streak.kind !== 'unknown'" class="streak">最近连续{{ overview.current_streak.kind === 'win' ? '胜利' : '失利' }} {{ val(overview.current_streak.count) }} 场</p>
        <div class="lol-chart-grid"><LolTrend :rows="analysis.trend" metric="winrate" label="胜率趋势" unit="%" /><LolTrend :rows="analysis.trend" metric="average_score" label="参考评分趋势" :min="3" :max="16" /></div>
        <section class="lol-panel"><div class="panel-heading"><h3>对局活跃日历</h3><span>{{ loadedFilter.days === 0 ? '最近 365 天' : `最近 ${loadedFilter.days} 天` }} · 北京时间</span></div><p class="method-note">颜色表示本地已归档对局数量；空格仅表示当日无归档记录。</p><div class="heatmap-scroll"><div class="heatmap"><div v-for="day in heatDays" :key="day.date" class="heat-cell" :style="day.games ? { background: 'var(--accent)', opacity: .25 + .75 * day.games / heatMaximum } : {}" :title="`${day.date}：${day.games} 场归档，${day.wins} 胜`" role="img" :aria-label="`${day.date}：${day.games} 场归档，${day.wins} 胜`" /></div></div><div class="heat-labels"><span>{{ heatDays[0]?.date }}</span><span>少 ▪ ▪ ▪ 多</span><span>{{ heatDays.at(-1)?.date }}</span></div></section>
        <section class="lol-panel"><div class="panel-heading"><h3>常用英雄</h3><span>当前筛选的个人样本</span></div><div v-if="analysis.champions?.length" class="lol-table-wrap"><table><thead><tr><th>英雄</th><th>场次</th><th>胜率</th><th>参考评分</th></tr></thead><tbody><tr v-for="champion in analysis.champions" :key="champion.champion_id"><td>{{ champion.name || `英雄 #${champion.champion_id}` }}</td><td>{{ val(champion.games) }}</td><td>{{ percent(champion.winrate) }}</td><td>{{ val(champion.average_score) }}</td></tr></tbody></table></div><p v-else class="method-note">当前筛选没有可统计的英雄。</p></section>
        <section v-if="analysis.highlights?.length" class="lol-panel"><div class="panel-heading"><h3>个人高光</h3><span>本地样本记录</span></div><div class="highlights"><div v-for="(item, index) in analysis.highlights.slice(0, 6)" :key="index"><strong>{{ item.label }} · {{ val(item.value) }}</strong><span>{{ item.champion_name || '未知英雄' }} · {{ fmt(item.start_at) }}</span></div></div></section>
      </template>
      <template v-else-if="section === 'history'">
        <p class="method-note">按时间从新到旧 · 时间均为北京时间 · 评分为 LOLhelper v3 参考评分</p>
        <p v-if="!matches.length" class="lol-empty">当前时间和模式下没有已归档对局，可调整筛选。</p>
        <article v-for="row in matches" :key="row.match_id" class="lol-match" :class="resultClass(row)">
          <div class="match-main"><div class="match-result">{{ result(row.win, row.remake) }}<small>{{ row.mode || queues.find(([id]) => id === String(row.queue_id))?.[1] || '未知模式' }}</small></div><div class="match-champion"><strong>{{ row.champion_name || `英雄 #${row.champion_id ?? '?'}` }}</strong><small>{{ fmt(row.start_at) }} · {{ row.duration_seconds == null ? '时长未知' : `${val(row.duration_seconds / 60)} 分钟` }}</small></div><div class="match-kda"><strong>{{ kda(row) }}</strong><small>K / D / A</small></div><div class="match-score"><strong>{{ val(row.score) }}</strong><small>参考评分</small></div><button type="button" :aria-expanded="expanded === row.match_id" @click="toggleDetail(row)">{{ expanded === row.match_id ? '收起详情' : '查看详情' }}</button></div>
          <div class="match-tags"><span>伤害 {{ val(row.damage) }}</span><span>参团 {{ percent(row.kp) }}</span><span>伤害占比 {{ percent(row.damage_share) }}</span><span v-for="augment in row.augments" :key="augment.id" class="augment">{{ augment.name || `强化 #${augment.id}` }}</span><span v-for="label in row.highlights" :key="label">{{ label }}</span></div>
          <section v-if="expanded === row.match_id" class="match-detail"><p v-if="detailLoading" role="status">对局详情加载中…</p><p v-else-if="detailError" class="lol-error" role="alert">{{ detailError }}</p><template v-else-if="detail"><div v-for="team in detail.teams || []" :key="team.team_id"><h4>{{ result(team.win, row.remake || detail.remake) }} · 队伍 {{ team.team_id }}<span v-if="team.participants?.some(p => p.is_own)"> · 我方</span></h4><div class="lol-table-wrap"><table><thead><tr><th>英雄</th><th>K / D / A</th><th>伤害</th><th>金币</th></tr></thead><tbody><tr v-for="(player, i) in team.participants || []" :key="i" :class="{ own: player.is_own }"><td>{{ player.champion_name || `英雄 #${player.champion_id ?? '?'}` }}<span v-if="player.is_own"> · 我</span></td><td>{{ kda(player) }}</td><td>{{ val(player.damage) }}</td><td>{{ val(player.gold) }}</td></tr></tbody></table></div></div></template><p v-else>本机未取得详情，可启动客户端后重新采集。</p></section>
        </article>
      </template>
      <template v-else-if="section === 'hex'">
        <section class="hex-intro lol-panel"><span class="eyebrow">HEXTECH ARAM · QUEUE 2400</span><h3>我的海克斯样本</h3><p>当前筛选内海克斯对局 {{ val(hex.games) }} 场 · 已记录强化 {{ val(hex.recorded_games) }} 场</p><p class="method-note">只统计海克斯大乱斗（2400）。个人样本胜率不代表外部强度，也不能说明强化导致胜负。重开与未知胜负不计入胜率分母。</p><p class="method-note">{{ hex.rating_note || '暂无同版本英雄与强化强度资料，因此不生成强化评级。' }}</p></section>
        <section class="lol-panel"><div class="panel-heading"><h3>强化选择记录</h3><span>单局同名强化去重</span></div><div v-if="hex.augments?.length" class="lol-table-wrap"><table><thead><tr><th>强化</th><th>场次</th><th>胜场</th><th>样本胜率</th></tr></thead><tbody><tr v-for="augment in hex.augments" :key="augment.id"><td>{{ augment.name || `强化 #${augment.id}` }}</td><td>{{ val(augment.games) }}</td><td>{{ val(augment.wins) }}</td><td>{{ percent(augment.winrate) }}</td></tr></tbody></table></div><p v-else class="method-note">暂无强化选择记录；未记录强化的对局不会虚构为零强度。</p></section>
        <section class="lol-panel"><div class="panel-heading"><h3>强化组合</h3><span>本地出现过的组合</span></div><div v-if="hex.combinations?.length" class="lol-table-wrap"><table><thead><tr><th>组合</th><th>场次</th><th>胜场</th><th>样本胜率</th></tr></thead><tbody><tr v-for="(combo, i) in hex.combinations" :key="i"><td>{{ combo.names?.join(' + ') || combo.ids?.join(' + ') || '未知组合' }}</td><td>{{ val(combo.games) }}</td><td>{{ val(combo.wins) }}</td><td>{{ percent(combo.winrate) }}</td></tr></tbody></table></div><p v-else class="method-note">暂无可统计的强化组合。</p></section>
      </template>
      <footer class="lol-footnote">{{ coverage.scope_note || '数据来自当前账号的本机 LCU 归档，仅包含已采集窗口，不代表完整历史。' }}<span v-if="coverage.first_at"> · 归档范围 {{ fmt(coverage.first_at) }} — {{ fmt(coverage.last_at) }}</span></footer>
    </template>
  </div>
</template>

<style scoped>
.lol-dashboard{min-width:0;--lol-gold:var(--accent,#c7a66b)}.lol-header{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:24px;border:1px solid var(--border);border-radius:14px;background:radial-gradient(ellipse at 100% 0,var(--accent-soft),transparent 65%),var(--card-bg)}.eyebrow{font-size:10px;letter-spacing:2px;color:var(--accent)}.lol-header h2{font-size:25px;letter-spacing:.5px;margin:9px 0}.lol-header p,.coverage-line,.method-note,.lol-footnote{font-size:12px;line-height:1.8;color:var(--text-muted)}.lol-header p{margin:0}.lol-dashboard button,.lol-dashboard select{font:inherit}.collect-button{flex-shrink:0;background:var(--accent-fill);color:var(--accent-ink);border:1px solid var(--accent-fill);padding:11px 17px;border-radius:8px;font-size:12px!important;font-weight:600;cursor:pointer}.lol-dashboard button:disabled{opacity:.55;cursor:wait}.lol-toolbar{display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:15px;margin:22px 0 12px}.detail-tabs{display:flex;flex-wrap:wrap;gap:5px}.detail-tabs button{border:0;border-bottom:2px solid transparent;padding:10px 14px;background:transparent;color:var(--text-muted);font-size:12px;cursor:pointer}.detail-tabs button[aria-pressed=true]{color:var(--accent);border-bottom-color:var(--accent)}.lol-filters{display:flex;flex-wrap:wrap;align-items:center;gap:10px}.lol-filters label{display:flex;align-items:center;gap:6px;color:var(--text-muted);font-size:11px}.lol-filters select{color:var(--text);background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:7px;max-width:160px}.reload-button,.lol-match button{background:var(--accent-soft);border:1px solid var(--border);color:var(--accent);border-radius:6px;padding:8px 10px;font-size:11px!important;cursor:pointer}.coverage-line{margin:0 0 16px;overflow-wrap:anywhere}.lol-notice,.lol-error{padding:11px 14px;border-radius:8px;font-size:12px;line-height:1.7;margin:12px 0}.lol-notice{color:var(--text-muted);background:var(--accent-soft)}.lol-error{color:var(--danger);background:var(--danger-bg);overflow-wrap:anywhere}.lol-empty{padding:42px 24px;border:1px dashed var(--border);border-radius:12px;margin:20px 0;text-align:center}.lol-empty h3{font-size:18px}.lol-empty p{max-width:590px;margin:12px auto;color:var(--text-muted);font-size:13px;line-height:1.9}.empty-symbol{font-size:34px;color:var(--accent)}.method-note{margin:12px 0}.streak{font-size:12px;color:var(--accent)}.lol-chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:20px 0}.lol-panel{border:1px solid var(--border);background:var(--card-bg);border-radius:12px;padding:20px;margin:16px 0;min-width:0}.panel-heading{display:flex;justify-content:space-between;align-items:baseline;gap:10px;flex-wrap:wrap}.panel-heading h3,.hex-intro h3{margin:0;font-size:15px}.panel-heading>span{font-size:11px;color:var(--text-muted)}.heatmap-scroll{overflow-x:auto;padding:8px 0}.heatmap{display:grid;grid-template-rows:repeat(7,11px);grid-auto-flow:column;grid-auto-columns:11px;gap:4px;width:max-content}.heat-cell{background:var(--border);border-radius:3px}.heat-labels{display:flex;justify-content:space-between;gap:8px;font-size:10px;color:var(--text-muted);margin-top:6px}.lol-table-wrap{overflow:auto;margin-top:12px}table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}th,td{text-align:left;border-bottom:1px solid var(--border);padding:12px 10px;white-space:nowrap}th{color:var(--text-muted);font-weight:400;font-size:11px}td:first-child{white-space:normal;min-width:90px}tbody tr:last-child td{border-bottom:0}.highlights{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(220px,100%),1fr));gap:12px;margin-top:15px}.highlights>div{border-left:2px solid var(--accent);padding:5px 12px}.highlights strong,.highlights span{display:block;font-size:12px}.highlights span{font-size:10px;color:var(--text-muted);margin-top:8px}.lol-match{border:1px solid var(--border);border-left:3px solid var(--text-muted);border-radius:10px;padding:16px 18px;margin:12px 0;background:var(--card-bg)}.lol-match.win{border-left-color:var(--success)}.lol-match.loss{border-left-color:var(--danger)}.match-main{display:grid;grid-template-columns:100px minmax(150px,1fr) minmax(95px,.6fr) 75px auto;gap:16px;align-items:center}.match-main strong{font-size:14px;font-weight:500}.match-main small{display:block;font-size:10px;color:var(--text-muted);margin-top:7px;line-height:1.6}.match-result{font-size:14px}.win .match-result{color:var(--success)}.loss .match-result{color:var(--danger)}.match-score strong{color:var(--accent);font-size:22px}.match-tags{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}.match-tags span{font-size:10px;color:var(--text-muted);background:var(--bg);padding:4px 7px;border-radius:4px}.match-tags .augment{color:var(--accent);background:var(--accent-soft)}.match-detail{border-top:1px solid var(--border);margin-top:16px;padding-top:8px;font-size:12px}.match-detail h4{font-size:12px;color:var(--text-muted);font-weight:400}.own{background:var(--accent-soft)}.hex-intro{background:linear-gradient(120deg,var(--accent-soft),var(--card-bg));padding:24px}.hex-intro h3{margin:14px 0}.hex-intro>p:not(.method-note){font-size:14px}.lol-footnote{border-top:1px solid var(--border);padding-top:16px;margin:22px 0 4px}.lol-dashboard :focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@media(max-width:900px){.match-main{grid-template-columns:85px 1fr 100px;gap:12px}.match-score{grid-column:1}.match-main>button{justify-self:end;grid-column:3}.lol-chart-grid{grid-template-columns:1fr}}
@media(max-width:540px){.lol-header{align-items:flex-start;flex-direction:column;padding:19px}.lol-header h2{font-size:22px}.collect-button{width:100%}.lol-toolbar{gap:10px}.detail-tabs button{padding:9px 10px}.lol-filters{width:100%;gap:8px}.lol-filters label{flex:1}.lol-filters select{min-width:0;width:100%;max-width:none}.reload-button{width:100%}.lol-panel{padding:15px}.lol-match{padding:14px 12px}.match-main{grid-template-columns:75px minmax(0,1fr);gap:12px}.match-kda{grid-column:2}.match-score{grid-row:2;grid-column:1}.match-main>button{grid-column:1/-1;justify-self:stretch}.match-main strong{font-size:12px}.match-score strong{font-size:20px}.heat-labels{font-size:9px}th,td{padding:10px 7px}.lol-empty{padding:30px 18px}}
</style>
