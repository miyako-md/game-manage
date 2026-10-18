<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import AnnouncementList from './AnnouncementList.vue'
import AccountCard from './AccountCard.vue'
import AppIcon from './AppIcon.vue'
import BarChart from './BarChart.vue'
import HRail from './HRail.vue'
import MatchList from './MatchList.vue'
import LolTrend from './LolTrend.vue'
import LolEsportsPanel from './LolEsportsPanel.vue'
import RingGauge from './RingGauge.vue'
import { createEsportsBrowseState } from '../esports.js'
import { getLolAnalysis, collectLol, getLolMatch } from '../lol-api.js'
import { prepareArticles } from '../articles.js'
import { formatBeijingDateTime } from '../calendar.js'
import { formRecord, formStrip, heatmapDays, heatmapLayout, hourCounts, kdaBar, kdaRatio, kdaSplit, letterOf, meanOf, rankedSolo, resultParts, weeklyCounts } from '../lol-charts.js'
import { vGlide, vReveal } from '../motion.js'

const props = defineProps({ snaps: { type: Object, default: () => ({}) }, esportsBrowse: { type: Object, default: createEsportsBrowseState } })
const emit = defineEmits(['refresh', 'esports-snapshot', 'esports-browse'])
const days = ref(90), queue = ref(''), section = ref(props.esportsBrowse.section || 'overview')
watch(section, value => emit('esports-browse', { section: value }))
const periods = [[7, '近 7 天'], [30, '近 30 天'], [90, '近 90 天'], [365, '近 365 天'], [0, '全部归档']]
const queues = [['', '全部模式'], ['2400', '海克斯大乱斗'], ['450', '极地大乱斗'], ['420', '单双排位'], ['440', '灵活排位']]
const tabs = [['overview', '个人总览'], ['history', '对局记录'], ['hex', '海克斯'], ['news', '公告与资讯'], ['esports', '职业赛事']]
const analysis = ref(null), loadedFilter = ref({ days: 90, queue: '' }), loading = ref(false), error = ref('')
const collecting = ref(false), collectError = ref(''), collectNote = ref('')
const expanded = ref(null), detail = ref(null), detailLoading = ref(false), detailError = ref('')
let generation = 0, analysisController, detailGeneration = 0, detailController, collectGeneration = 0, collectController, disposed = false
// The normalized summoner snapshot carries the stable LCU owner in extra.puuid.
const accountKey = computed(() => props.snaps.account?.payload?.extra?.puuid || '')
const val = value => Number.isFinite(value) ? Number(value.toFixed(1)) : '未知'
const percent = value => Number.isFinite(value) ? `${val(value)}%` : '未知'
// Averages and scores keep one decimal so a column of them lines up (7.0, not 7).
const dec1 = value => Number.isFinite(value) ? value.toFixed(1) : '未知'
const result = (win, remake = false) => remake ? '重开' : win === true ? '胜利' : win === false ? '失败' : '胜负未知'
const resultClass = row => row.remake ? 'remake' : row.win === true ? 'win' : row.win === false ? 'loss' : 'unknown'
const kda = row => `${val(row.kills)} / ${val(row.deaths)} / ${val(row.assists)}`
const fmt = formatBeijingDateTime
const overview = computed(() => analysis.value?.overview || {})
const coverage = computed(() => analysis.value?.coverage || {})
const hex = computed(() => analysis.value?.hextech || {})
const matches = computed(() => analysis.value?.matches || [])
const hasArchive = computed(() => (coverage.value.archived_games ?? overview.value.games ?? 0) > 0)
const filterLabel = computed(() => `${periods.find(([key]) => key === loadedFilter.value.days)?.[1]} · ${queues.find(([key]) => key === loadedFilter.value.queue)?.[1]}`)
const filterable = computed(() => !['esports', 'news'].includes(section.value))

// Header: who this is, from the archive when it has been read and the account snapshot otherwise.
const rank = computed(() => rankedSolo(props.snaps.account?.payload))
const initial = computed(() => letterOf(analysis.value?.account?.nickname || props.snaps.account?.payload?.nickname, 'L'))
const level = computed(() => analysis.value?.account ? analysis.value.account.level : props.snaps.account?.payload?.level)

// Overview.
const winrate = computed(() => Number.isFinite(overview.value.winrate) ? overview.value.winrate : null)
const parts = computed(() => resultParts(overview.value))
const resultNote = computed(() => `${val(overview.value.wins)} 胜 · ${val(overview.value.losses)} 负 · ${val(overview.value.unknown_results)} 未知 · ${val(overview.value.remakes)} 重开`)
const streak = computed(() => overview.value.current_streak?.kind && overview.value.current_streak.kind !== 'unknown' ? overview.value.current_streak : null)
const heat = computed(() => heatmapLayout(heatmapDays(analysis.value?.heatmap, loadedFilter.value.days || 365)))
// Short windows read better as one bar per day; longer ones as a calendar.
const dailyBars = computed(() => loadedFilter.value.days > 0 && loadedFilter.value.days <= 31
  ? heat.value.cells.map(cell => ({ label: heat.value.cells.length <= 10 ? cell.date.slice(5).replace('-', '/') : String(Number(cell.date.slice(8))), value: cell.games }))
  : null)
const hours = computed(() => {
  const counts = hourCounts(matches.value), top = Math.max(0, ...counts)
  return { counts: counts.map(count => ({ count, height: count ? Math.max(12, count / top * 100) : 0 })), top, peak: top ? counts.indexOf(top) : -1 }
})
const heatRecent = computed(() => {
  const cells = heat.value.cells.slice(-14), top = Math.max(1, ...cells.map(cell => cell.games))
  return cells.map(cell => ({ ...cell, height: cell.games ? Math.max(14, cell.games / top * 100) : 0 }))
})
const kdaAverage = computed(() => kdaRatio(overview.value.avg_kills, overview.value.avg_deaths, overview.value.avg_assists))
const kdaShare = computed(() => kdaSplit(overview.value.avg_kills, overview.value.avg_deaths, overview.value.avg_assists))
const participation = computed(() => ({ kp: meanOf(matches.value, 'kp'), share: meanOf(matches.value, 'damage_share') }))
const scorePosition = computed(() => Number.isFinite(overview.value.average_score) ? Math.max(0, Math.min(100, (overview.value.average_score - 3) / 13 * 100)) : null)
const playHours = computed(() => Number.isFinite(overview.value.play_minutes) ? Number((overview.value.play_minutes / 60).toFixed(1)) : null)
const champions = computed(() => analysis.value?.champions || [])
const highlightValue = item => item.label === '最高伤害' && Number.isFinite(item.value) ? `${Number((item.value / 10000).toFixed(1))} 万` : val(item.value)

// History: the newest twenty games as a strip, and the cards' own bars.
const recent = computed(() => formStrip(matches.value, resultClass, 20))
const recentRecord = computed(() => formRecord(recent.value))
const recentBars = computed(() => recent.value.map(({ row, kind, label }) => ({
  row, kind, label,
  bar: kind === 'remake' ? null : kdaBar(kdaRatio(row.kills, row.deaths, row.assists)),
  tip: [fmt(row.start_at).slice(5, 10), row.champion_name, result(row.win, row.remake), kind === 'remake' ? null : kda(row)].filter(Boolean).join(' · '),
})))
const ratioOf = row => kdaRatio(row.kills, row.deaths, row.assists)
const splitOf = row => row.remake ? null : kdaSplit(row.kills, row.deaths, row.assists)
const detailTop = computed(() => Math.max(1, ...(detail.value?.teams || []).flatMap(team => (team.participants || []).map(player => Number.isFinite(player.damage) ? player.damage : 0))))
const damageShare = player => Number.isFinite(player.damage) ? `${Math.round(player.damage / detailTop.value * 100)}%` : '0%'

// Hex.
const topAugments = computed(() => (hex.value.augments || []).slice(0, 10).map(augment => ({ label: augment.name || `强化 #${augment.id}`, value: Number.isFinite(augment.games) ? augment.games : null })))
const hexCoverage = computed(() => Number.isFinite(hex.value.games) && hex.value.games > 0 && Number.isFinite(hex.value.recorded_games) ? hex.value.recorded_games : null)

// Announcements and news: how often something is published, from the same rows the list shows.
const articles = computed(() => prepareArticles([props.snaps.news, props.snaps.announcement ? { ...props.snaps.announcement, capability: 'announcement' } : null]))
const weekly = computed(() => weeklyCounts(articles.value.map(row => row.published_at), 8))
const newest = computed(() => articles.value.find(row => row.published_at))

function closeDetail() {
  detailGeneration++; detailController?.abort(); expanded.value = null; detail.value = null; detailLoading.value = false; detailError.value = ''
}
async function load(resetDetail = true) {
  const current = ++generation, filters = { days: days.value, queue: queue.value }
  analysisController?.abort(); analysisController = new AbortController()
  if (resetDetail) closeDetail()
  loading.value = true; error.value = ''
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
    collectNote.value = `已同步 ${val(data.games)} 场对局，取得 ${val(data.details)} 场详情${data.failed_details === 0 ? '。' : `；${val(data.failed_details)} 场详情未取得。`}`
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
// Snapshot refreshes (hourly while the client is online) keep an open match;
// new filters or another account start from a closed list.
watch([
  days, queue, accountKey,
  () => props.snaps.account?.fetched_at,
  () => props.snaps.match?.fetched_at,
  () => props.snaps.stats?.fetched_at,
], (next, previous) => load(!previous || next.slice(0, 3).some((value, index) => value !== previous[index])), { immediate: true })
onBeforeUnmount(() => { disposed = true; generation++; analysisController?.abort(); collectController?.abort(); closeDetail() })
</script>

<template>
  <div class="lol-dashboard">
    <header v-if="section !== 'esports'" class="lol-header">
      <div class="lol-id">
        <span class="lol-avatar" aria-hidden="true">{{ initial }}</span>
        <div class="lol-id-copy">
          <h2>{{ analysis?.account?.nickname || snaps.account?.payload?.nickname || '我的英雄联盟' }}</h2>
          <ul v-if="analysis?.account || rank || level != null" class="chip-list lol-chips">
            <li v-if="level != null" class="chip">等级 {{ val(level) }}</li>
            <li v-if="rank" class="chip game rank-chip"><b>{{ rank.tier }}</b>{{ rank.division ? ` ${rank.division}` : '' }} · {{ val(rank.points) }} LP</li>
            <li v-if="rank && rank.wins != null && rank.losses != null" class="chip">单双排 {{ rank.wins }} 胜 {{ rank.losses }} 负</li>
          </ul>
        </div>
      </div>
      <button type="button" class="collect-button ui-button primary" :disabled="collecting" @click="collect"><AppIcon name="refresh" :size="15" :class="{ spinning: collecting }" />{{ collecting ? '正在同步…' : '同步战绩' }}</button>
    </header>
    <p v-if="collecting && section !== 'esports'" class="lol-notice" role="status">正在同步近期战绩与详情…</p>
    <p v-if="collectError && section !== 'esports'" class="lol-error" role="alert">{{ collectError }}<span v-if="analysis && section !== 'esports'">；已有分析数据仍保留。</span></p>
    <p v-if="collectNote && section !== 'esports'" class="lol-notice" role="status">{{ collectNote }}</p>
    <div class="lol-toolbar">
      <nav v-glide class="lol-tabs segmented" aria-label="英雄联盟数据分区"><button v-for="[key, label] in tabs" :key="key" type="button" :aria-pressed="section === key" @click="section = key">{{ label }}</button></nav>
      <div v-if="filterable" class="lol-filters"><label>时间<MenuSelect class="lol-filter-menu" label="时间" v-model="days" :options="periods.map(([value,label]) => ({value,label}))" /></label><label>模式<MenuSelect class="lol-filter-menu" label="模式" v-model="queue" :options="queues.map(([value,label]) => ({value,label}))" /></label><button class="reload-button ui-button small-button" type="button" :disabled="loading" @click="load()">重新读取</button></div>
    </div>
    <p v-if="loading && filterable" class="lol-notice" role="status">正在读取本地分析…</p>
    <p v-if="error && filterable" class="lol-error" role="alert">{{ error }}<span v-if="analysis && filterable">；保留上次成功读取的数据。</span></p>
    <ul v-if="analysis && filterable" class="coverage-line chip-list"><li class="chip">当前展示：{{ filterLabel }}</li><li class="chip">归档 {{ val(coverage.archived_games) }} 场</li><li class="chip">当前筛选 {{ val(overview.games) }} 场</li><li class="chip">有详情 {{ val(coverage.detail_games) }} 场</li><li v-if="analysis.collected_at" class="chip">同步于 {{ fmt(analysis.collected_at) }}（北京时间）</li></ul>

    <div :key="section" class="lol-view t-panel">
      <LolEsportsPanel v-if="section === 'esports'" :snap="snaps.esports" :browse-state="esportsBrowse" @snapshot="emit('esports-snapshot', $event)" @browse-change="emit('esports-browse', $event)" />
      <template v-else-if="section === 'news'">
        <div class="bento">
          <section v-reveal class="cap-card b-card tone news-count"><div class="b-head"><h3>发布概况</h3></div><p class="big">{{ articles.length }}<small>条</small></p><p class="b-note">{{ newest ? `最近一条发布于 ${fmt(newest.published_at).slice(0, 10)}` : '暂无发布时间' }}</p></section>
          <section v-reveal class="cap-card b-card news-rhythm"><div class="b-head"><h3>近 8 周发布数量</h3><span class="b-meta">按周一起算 · 北京时间</span></div><BarChart :items="weekly" label="近 8 周每周发布的公告与资讯数量" unit=" 条" :height="76" /></section>
        </div>
        <AnnouncementList game-id="league_of_legends" :snap="snaps.news" :extra-snaps="[{ ...snaps.announcement, capability: 'announcement' }]" />
      </template>
      <template v-else-if="!loading && !hasArchive">
        <section class="cap-card lol-empty">
          <div class="lol-empty-copy">
            <h3>{{ analysis ? '本机尚无归档' : '本地档案暂不可用' }}</h3>
            <p>请启动并登录英雄联盟客户端，再点击上方「同步战绩」。</p>
            <p>同步需保持客户端在线，已归档的对局可离线查看。</p>
          </div>
          <div class="lol-ghost" aria-hidden="true">
            <span class="ghost-ring"></span>
            <span class="ghost-bars"><i style="height:38%"></i><i style="height:64%"></i><i style="height:48%"></i><i style="height:82%"></i><i style="height:56%"></i><i style="height:92%"></i><i style="height:70%"></i></span>
            <span class="ghost-cells"><i v-for="n in 21" :key="n" :style="{ opacity: [0.35, 0.7, 0.2, 1, 0.5, 0.25, 0.85][n % 7] }"></i></span>
          </div>
        </section>
        <template v-if="section === 'history' && snaps.match?.payload?.length">
          <p class="legacy-note">以下为升级前保留的近期对局快照，不计入新归档统计；实时详情需要客户端在线。</p>
          <MatchList :snap="snaps.match" :stats="snaps.stats?.payload ?? null" game-id="league_of_legends" />
        </template>
      </template>
      <template v-else-if="analysis && hasArchive">
        <template v-if="section === 'overview'">
          <div class="bento">
            <section v-reveal class="cap-card b-card tone ov-win">
              <div class="b-head"><h3>个人胜率</h3><span class="b-meta">{{ filterLabel }}</span></div>
              <div class="win-body">
                <RingGauge :value="winrate" :max="100" label="个人胜率" :size="172" :stroke="15" color="var(--game-vivid)">
                  <span class="ring-big" aria-hidden="true"><template v-if="winrate != null"><b>{{ val(winrate) }}</b><small>%</small></template><b v-else>未知</b></span>
                  <span class="sr-only">{{ percent(overview.winrate) }}</span>
                </RingGauge>
                <p class="b-note">{{ resultNote }}</p>
                <p v-if="streak" class="streak" :class="streak.kind">最近连续{{ streak.kind === 'win' ? '胜利' : '失利' }} {{ val(streak.count) }} 场</p>
              </div>
              <div class="split">
                <div class="stack-bar" role="img" :aria-label="`胜负分布：${resultNote}`"><i v-for="part in parts.filter(item => item.value)" :key="part.key" :class="part.key" :style="{ flex: part.value }"></i></div>
                <ul class="legend"><li v-for="part in parts" :key="part.key" :class="part.key">{{ part.label }} <b>{{ part.value }}</b></li></ul>
              </div>
            </section>
            <section v-reveal class="cap-card b-card t-games">
              <div class="b-head"><h3>对局场次</h3></div>
              <p class="big">{{ val(overview.games) }}<small>场</small></p>
              <div class="mini-bars" role="img" aria-label="近 14 天每天的对局数"><i v-for="cell in heatRecent" :key="cell.date" :style="{ height: `${cell.height}%` }" :class="{ idle: !cell.games }" :title="`${cell.date}：${cell.games} 场`"></i></div>
              <p class="b-note">活跃 {{ heat.activeDays }} 天<template v-if="playHours != null"> · 已记录 {{ playHours }} 小时</template></p>
            </section>
            <section v-reveal class="cap-card b-card t-kda">
              <div class="b-head"><h3>场均 K / D / A</h3><span v-if="kdaAverage != null" class="chip game">KDA {{ dec1(kdaAverage) }}</span></div>
              <div class="kda-trio"><div><b>{{ dec1(overview.avg_kills) }}</b><span>击杀</span></div><div><b>{{ dec1(overview.avg_deaths) }}</b><span>死亡</span></div><div><b>{{ dec1(overview.avg_assists) }}</b><span>助攻</span></div></div>
              <div v-if="kdaShare" class="kda-bar" role="img" aria-label="击杀、死亡、助攻的占比"><i class="k" :style="{ flex: kdaShare.k }"></i><i class="d" :style="{ flex: kdaShare.d }"></i><i class="a" :style="{ flex: kdaShare.a }"></i></div>
              <p class="b-note">已记录时长 {{ val(overview.play_minutes) }} 分钟</p>
            </section>
            <section v-reveal class="cap-card b-card t-part">
              <div class="b-head"><h3>团战参与</h3></div>
              <div class="meter-row"><span>参团率</span><b>{{ percent(participation.kp) }}</b><span class="meter"><i :style="{ '--pct': `${participation.kp ?? 0}%` }"></i></span></div>
              <div class="meter-row"><span>伤害占比</span><b>{{ percent(participation.share) }}</b><span class="meter"><i :style="{ '--pct': `${participation.share ?? 0}%` }"></i></span></div>
              <p class="b-note">均值取自有完整队伍数据的对局</p>
            </section>
            <section v-reveal class="cap-card b-card t-score">
              <div class="b-head"><h3>平均参考评分</h3></div>
              <p class="big">{{ dec1(overview.average_score) }}<small>分</small></p>
              <div class="scale" role="img" :aria-label="`参考评分 3 至 16，平均 ${val(overview.average_score)}`"><span class="meter"><i :style="{ '--pct': `${scorePosition ?? 0}%` }"></i></span><em>3</em><em>16</em></div>
              <p class="b-note">基于 {{ val(coverage.score_games) }} 场对局</p>
            </section>
          </div>
          <div class="bento trend-row">
            <LolTrend v-reveal class="span-6" :rows="analysis.trend" metric="winrate" label="胜率趋势" unit="%" />
            <LolTrend v-reveal class="span-6" :rows="analysis.trend" metric="average_score" label="参考评分趋势" :min="3" :max="16" />
          </div>
          <div class="bento">
            <section v-reveal class="cap-card b-card span-7 heat-card">
              <div class="b-head"><h3>对局活跃日历</h3><span class="b-meta">{{ loadedFilter.days === 0 ? '最近 365 天' : `最近 ${loadedFilter.days} 天` }} · 北京时间</span></div>
              <div class="heat-body">
                <BarChart v-if="dailyBars" class="heat-bars" :items="dailyBars" label="每天的对局数" unit=" 场" :height="112" />
                <div v-else class="heat-scroll">
                  <div class="heat" :style="{ '--weeks': heat.weeks }">
                    <div class="heat-months" aria-hidden="true"><span v-for="month in heat.months" :key="month.col" :style="{ gridColumn: month.col + 1 }">{{ month.label }}</span></div>
                    <div class="heat-weekdays" aria-hidden="true"><span style="grid-row:1">一</span><span style="grid-row:3">三</span><span style="grid-row:5">五</span><span style="grid-row:7">日</span></div>
                    <div class="heat-grid"><div v-for="(day, index) in heat.cells" :key="day.date" class="heat-cell" :data-level="day.level" :style="index === 0 ? { gridRowStart: heat.first + 1 } : undefined" :title="`${day.date}：${day.games} 场归档，${day.wins} 胜`" role="img" :aria-label="`${day.date}：${day.games} 场归档，${day.wins} 胜`" /></div>
                  </div>
                </div>
                <dl class="heat-stats">
                  <div><dt>活跃天数</dt><dd>{{ heat.activeDays }}<small>/ {{ heat.cells.length }} 天</small></dd></div>
                  <div><dt>最忙一天</dt><dd>{{ heat.busiest ? heat.busiest.games : 0 }}<small>场<template v-if="heat.busiest"> · {{ heat.busiest.date.slice(5) }}</template></small></dd></div>
                  <div><dt>最长连续活跃</dt><dd>{{ heat.longest }}<small>天</small></dd></div>
                </dl>
              </div>
              <div class="heat-labels"><span>{{ heat.cells[0]?.date }}</span><span v-if="!dailyBars" class="heat-legend" aria-hidden="true">少 <i data-level="0"></i><i data-level="1"></i><i data-level="2"></i><i data-level="3"></i><i data-level="4"></i> 多</span><span>{{ heat.cells.at(-1)?.date }}</span></div>
              <div v-if="hours.top" class="hours">
                <p class="hours-title">开局时段<small>北京时间<template v-if="hours.peak >= 0"> · 最常在 {{ hours.peak }} 点前后开局</template></small></p>
                <div class="hour-bars" role="img" :aria-label="`24 小时内各时段开局数，最多的是 ${hours.peak} 点`"><i v-for="(hour, index) in hours.counts" :key="index" :class="{ peak: index === hours.peak, idle: !hour.count }" :style="{ height: `${hour.height}%` }" :title="`${index} 点：${hour.count} 场`"></i></div>
                <div class="hour-axis" aria-hidden="true"><span>0</span><span>6</span><span>12</span><span>18</span><span>24</span></div>
              </div>
            </section>
            <section v-reveal class="cap-card b-card span-5">
              <div class="b-head"><h3>常用英雄</h3><span v-if="champions.length" class="b-meta">{{ champions.length }} 个英雄</span></div>
              <ol v-if="champions.length" class="champ-list">
                <li v-for="champion in champions.slice(0, 7)" :key="champion.champion_id">
                  <span class="champ-tile" aria-hidden="true">{{ letterOf(champion.name) }}</span>
                  <span class="champ-copy"><strong>{{ champion.name || `英雄 #${champion.champion_id}` }}</strong><small>{{ val(champion.games) }} 场 · 评分 {{ dec1(champion.average_score) }}</small></span>
                  <span class="champ-rate"><span class="meter"><i :style="{ '--pct': `${champion.winrate ?? 0}%` }"></i></span><b>{{ percent(champion.winrate) }}</b></span>
                </li>
              </ol>
              <p v-else class="method-note">当前筛选没有可统计的英雄。</p>
              <details v-if="champions.length > 7" class="more"><summary>查看全部 {{ champions.length }} 个英雄</summary><div class="lol-table-wrap"><table class="data-table"><thead><tr><th>英雄</th><th>场次</th><th>胜率</th><th>参考评分</th></tr></thead><tbody><tr v-for="champion in champions" :key="champion.champion_id"><td>{{ champion.name || `英雄 #${champion.champion_id}` }}</td><td>{{ val(champion.games) }}</td><td>{{ percent(champion.winrate) }}</td><td>{{ dec1(champion.average_score) }}</td></tr></tbody></table></div></details>
            </section>
          </div>
          <section v-if="analysis.highlights?.length" v-reveal class="highlights">
            <HRail label="个人高光">
              <template #head><h3>个人高光</h3><span class="count-badge">{{ analysis.highlights.length }} 项</span></template>
              <article v-for="(item, index) in analysis.highlights" :key="index" class="hl-card" :class="{ rare: item.label === '五杀' || item.label === '四杀' }">
                <span class="hl-label">{{ item.label }}</span>
                <strong class="hl-value">{{ highlightValue(item) }}</strong>
                <span class="hl-who">{{ item.champion_name || '未知英雄' }}</span>
                <small>{{ fmt(item.start_at) }}</small>
              </article>
            </HRail>
          </section>
          <details class="cap-card quiet"><summary>统计说明</summary><p>参考评分采用 LOLhelper v3，范围为 3–16 分，需完整队伍指标。胜率只统计已知胜负；重开与未知胜负不计入。重开计入对局场次与活跃日历，不计入平均评分、击杀／死亡／助攻与连续胜负。</p></details>
        </template>
        <template v-else-if="section === 'history'">
          <div v-if="matches.length" class="bento">
            <section v-reveal class="cap-card b-card form-card">
              <div class="b-head"><h3>近期状态</h3><span class="b-meta">近 {{ recent.length }} 场 · 柱高为 KDA，封顶 10</span></div>
              <ol class="form-bars" :aria-label="`近 ${recent.length} 场结果，较早的在左`">
                <li v-for="item in recentBars" :key="item.row.match_id" class="form-col" :class="item.kind" :title="item.tip" :aria-label="item.tip">
                  <span class="form-slot"><span v-if="item.bar" class="form-bar" :class="{ clipped: item.bar.clipped }" :style="{ height: `${item.bar.pct}%` }"></span><span v-else class="form-bar stub"></span></span>
                  <b class="form-pill">{{ item.label }}</b>
                </li>
              </ol>
              <ul class="legend"><li class="win">胜利</li><li class="loss">失败</li><li class="unknown">重开 / 胜负未知</li></ul>
            </section>
            <section v-reveal class="cap-card b-card tone form-side">
              <div class="b-head"><h3>近 {{ recent.length }} 场</h3></div>
              <div class="form-ring">
                <RingGauge :value="recentRecord.rate" :max="100" label="近期胜率" :size="124" :stroke="12" color="var(--game-vivid)"><span class="ring-big small" aria-hidden="true"><template v-if="recentRecord.rate != null"><b>{{ recentRecord.rate }}</b><small>%</small></template><b v-else>—</b></span></RingGauge>
                <p class="b-note">{{ recentRecord.wins }} 胜 {{ recentRecord.losses }} 负</p>
                <p v-if="streak" class="streak" :class="streak.kind">最近连续{{ streak.kind === 'win' ? '胜利' : '失利' }} {{ val(streak.count) }} 场</p>
              </div>
            </section>
          </div>
          <p v-if="!matches.length" class="lol-empty-line">当前时间和模式下没有已归档对局，可调整筛选。</p>
          <div v-if="matches.length" class="cap-card match-list">
          <div class="b-head"><h3>对局记录</h3><span class="b-meta">{{ matches.length }} 场</span></div>
          <article v-for="row in matches" :key="row.match_id" class="lol-match" :class="resultClass(row)">
            <div class="match-main">
              <div class="match-result"><b>{{ result(row.win, row.remake) }}</b><small>{{ row.mode || queues.find(([id]) => id === String(row.queue_id))?.[1] || '未知模式' }}</small></div>
              <div class="match-champion"><span class="champ-tile" aria-hidden="true">{{ letterOf(row.champion_name) }}</span><span class="champ-copy"><strong>{{ row.champion_name || `英雄 #${row.champion_id ?? '?'}` }}</strong><small>{{ fmt(row.start_at) }} · {{ row.duration_seconds == null ? '时长未知' : `${val(row.duration_seconds / 60)} 分钟` }}</small></span></div>
              <div class="match-kda"><strong>{{ kda(row) }}</strong><small>K / D / A<template v-if="ratioOf(row) != null && !row.remake"> · KDA {{ dec1(ratioOf(row)) }}</template></small><span v-if="splitOf(row)" class="kda-bar thin" aria-hidden="true"><i class="k" :style="{ flex: splitOf(row).k }"></i><i class="d" :style="{ flex: splitOf(row).d }"></i><i class="a" :style="{ flex: splitOf(row).a }"></i></span></div>
              <div class="match-score"><strong :class="{ unknown: !Number.isFinite(row.score) }">{{ dec1(row.score) }}</strong><small>参考评分</small></div>
              <button type="button" class="ui-button small-button" :aria-expanded="expanded === row.match_id" @click="toggleDetail(row)">{{ expanded === row.match_id ? '收起详情' : '查看详情' }}</button>
            </div>
            <div class="match-tags"><span>伤害 {{ val(row.damage) }}</span><span>参团 {{ percent(row.kp) }}</span><span>伤害占比 {{ percent(row.damage_share) }}</span><span v-for="augment in row.augments" :key="augment.id" class="augment">{{ augment.name || `强化 #${augment.id}` }}</span><span v-for="label in row.highlights" :key="label" class="rare-tag">{{ label }}</span></div>
            <section v-if="expanded === row.match_id" class="match-detail"><p v-if="detailLoading" role="status">对局详情加载中…</p><p v-else-if="detailError" class="lol-error" role="alert">{{ detailError }}</p><template v-else-if="detail"><div v-for="team in detail.teams || []" :key="team.team_id" class="team-block"><h4 :class="resultClass({ win: team.win, remake: row.remake || detail.remake })">{{ result(team.win, row.remake || detail.remake) }} · 队伍 {{ team.team_id }}<span v-if="team.participants?.some(p => p.is_own)"> · 我方</span></h4><div class="lol-table-wrap"><table class="data-table"><thead><tr><th>英雄</th><th>K / D / A</th><th>伤害</th><th>金币</th></tr></thead><tbody><tr v-for="(player, i) in team.participants || []" :key="i" :class="{ own: player.is_own }"><td>{{ player.champion_name || `英雄 #${player.champion_id ?? '?'}` }}<span v-if="player.is_own"> · 我</span></td><td>{{ kda(player) }}</td><td><span class="cell-meter"><span class="meter" aria-hidden="true"><i :style="{ '--pct': damageShare(player) }"></i></span>{{ val(player.damage) }}</span></td><td>{{ val(player.gold) }}</td></tr></tbody></table></div></div></template><p v-else>本机暂无详情，可启动客户端后重新同步。</p></section>
          </article>
          </div>
        </template>
        <template v-else-if="section === 'hex'">
          <div class="bento">
            <section v-reveal class="cap-card b-card tone hex-intro">
              <div class="b-head"><h3>我的海克斯样本</h3></div>
              <div class="hex-cover">
                <RingGauge v-if="hexCoverage != null" :value="hexCoverage" :max="hex.games" label="已记录强化的海克斯对局占比" :size="112" :stroke="11" color="var(--game-vivid)"><span class="ring-big small" aria-hidden="true">{{ Math.round(hexCoverage / hex.games * 100) }}<small>%</small></span></RingGauge>
                <p class="hex-count">当前筛选内海克斯对局 {{ val(hex.games) }} 场 · 已记录强化 {{ val(hex.recorded_games) }} 场</p>
              </div>
              <p class="method-note">重开与胜负未知不计入胜率。</p>
              <p v-if="hex.rating_note" class="method-note">{{ hex.rating_note }}</p>
            </section>
            <section v-reveal class="cap-card b-card hex-chart">
              <div class="b-head"><h3>选择次数最多的强化</h3><span v-if="topAugments.length" class="b-meta">前 {{ topAugments.length }} 项 · 单位：场</span></div>
              <BarChart v-if="topAugments.length" :items="topAugments" label="选择次数最多的强化" unit=" 场" :highlight="0" :height="190" />
              <p v-else class="method-note">暂无强化选择记录。</p>
            </section>
          </div>
          <section v-reveal class="cap-card b-card"><div class="b-head"><h3>强化选择记录</h3><span v-if="hex.augments?.length" class="b-meta">{{ hex.augments.length }} 项</span></div><div v-if="hex.augments?.length" class="lol-table-wrap tall"><table class="data-table"><thead><tr><th>强化</th><th>场次</th><th>胜场</th><th>样本胜率</th></tr></thead><tbody><tr v-for="augment in hex.augments" :key="augment.id"><td>{{ augment.name || `强化 #${augment.id}` }}</td><td>{{ val(augment.games) }}</td><td>{{ val(augment.wins) }}</td><td><span class="cell-meter"><span class="meter" aria-hidden="true"><i :style="{ '--pct': `${augment.winrate ?? 0}%` }"></i></span>{{ percent(augment.winrate) }}</span></td></tr></tbody></table></div><p v-else class="method-note">暂无强化选择记录。</p></section>
          <section v-reveal class="cap-card b-card"><div class="b-head"><h3>强化组合</h3><span v-if="hex.combinations?.length" class="b-meta">{{ hex.combinations.length }} 项</span></div><div v-if="hex.combinations?.length" class="lol-table-wrap tall"><table class="data-table"><thead><tr><th>组合</th><th>场次</th><th>胜场</th><th>样本胜率</th></tr></thead><tbody><tr v-for="(combo, i) in hex.combinations" :key="i"><td>{{ combo.names?.join(' + ') || combo.ids?.join(' + ') || '未知组合' }}</td><td>{{ val(combo.games) }}</td><td>{{ val(combo.wins) }}</td><td><span class="cell-meter"><span class="meter" aria-hidden="true"><i :style="{ '--pct': `${combo.winrate ?? 0}%` }"></i></span>{{ percent(combo.winrate) }}</span></td></tr></tbody></table></div><p v-else class="method-note">暂无可统计的强化组合。</p></section>
        </template>
      </template>
      <details v-if="section === 'overview' && snaps.account?.payload" class="cap-card quiet"><summary>账号与排位{{ snaps.account.stale ? ' · 待更新' : '' }}</summary><AccountCard :snap="snaps.account" /></details>
      <footer v-if="analysis && hasArchive && filterable && (coverage.scope_note || coverage.first_at)" class="lol-footnote">{{ coverage.scope_note }}<span v-if="coverage.first_at"> · 归档范围 {{ fmt(coverage.first_at) }} — {{ fmt(coverage.last_at) }}</span></footer>
    </div>
  </div>
</template>

<style scoped>
.lol-dashboard{min-width:0}
.lol-dashboard button{font:inherit}
.lol-dashboard :focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.lol-dashboard button:disabled{opacity:.55;cursor:wait}

/* Identity: a tone tile with the first letter, the name and a few tags; the sync button is the page's one filled action. */
.lol-header{display:flex;justify-content:space-between;align-items:center;gap:16px 20px;flex-wrap:wrap;margin-bottom:18px}
.lol-id{display:flex;align-items:center;gap:14px;min-width:0}
.lol-avatar{display:grid;place-items:center;flex-shrink:0;width:52px;height:52px;border-radius:16px;background:var(--game-tone);box-shadow:inset 0 0 0 1px var(--card-border);color:var(--game-accent);font-size:22px;font-weight:600}
.lol-id-copy{min-width:0}
.lol-id-copy h2{font-size:22px;line-height:28px;font-weight:600;letter-spacing:-.02em;margin:0 0 4px;overflow-wrap:anywhere}
.lol-chips .chip{background:var(--card-bg);box-shadow:inset 0 0 0 1px var(--border)}
.lol-chips .rank-chip{background:var(--game-tone);box-shadow:none;color:var(--game-accent)}
.collect-button{flex-shrink:0}
.lol-notice,.lol-error{padding:10px 16px;border-radius:var(--radius-well);font-size:13px;line-height:1.7;margin:0 0 12px}
.lol-notice{color:var(--game-accent);background:var(--game-tone)}
.lol-error{color:var(--danger);background:var(--danger-bg);border:1px solid var(--danger-border);overflow-wrap:anywhere}

/* Tabs use the shared segmented control; web menus filter the archive. */
.lol-toolbar{display:flex;justify-content:space-between;flex-wrap:wrap;align-items:center;gap:12px 16px;margin:0 0 16px}
.lol-tabs{max-width:100%}
.lol-filters{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.lol-filters label{position:relative;display:flex;align-items:center;gap:8px;color:var(--text-muted);font-size:12px;white-space:nowrap}
.lol-filter-menu{min-width:0;max-width:170px}.lol-filter-menu :deep(.menu-select-trigger){min-height:34px;width:100%;min-width:0;font-size:13px;font-weight:500}
@media(pointer:coarse){.lol-filter-menu :deep(.menu-select-trigger){min-height:44px}}
.coverage-line{gap:2px 20px;margin:0 0 16px}
.coverage-line .chip{padding:0;border-radius:0;background:transparent;color:var(--text-muted)}

/* The view is the size container the bento folds against, so the page's own sidebar does not matter. */
.lol-view{min-width:0;container:lol-view/inline-size}

/* Bento: twelve columns, white cards of different widths; narrow containers fold them. The one tone card per
   tab holds the number the tab is about, with its labels in the game's ink. */
.bento{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:20px;margin-bottom:20px}
.bento>*{min-width:0}
.span-5{grid-column:span 5}.span-6{grid-column:span 6}.span-7{grid-column:span 7}
.b-card{display:flex;flex-direction:column;gap:12px;position:relative}
.b-card.tone{background:var(--game-tone);border-color:transparent}
.b-head{display:flex;align-items:baseline;justify-content:space-between;gap:4px 12px;flex-wrap:wrap}
.b-head h3{font-size:16px;line-height:24px;font-weight:600;letter-spacing:-.02em;margin:0;color:var(--text)}
.b-meta{color:var(--text-faint);font-size:12px}
.b-note{color:var(--text-muted);font-size:12px;line-height:1.7;margin:0}
.tone .b-meta,.tone .b-note,.tone .method-note,.tone .legend{color:var(--game-accent)}
.tone :deep(.ring-track){stroke:color-mix(in srgb,var(--card-bg) 72%,transparent)}
.big{font-size:36px;line-height:42px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums;margin:0}
.big small{margin-left:5px;font-size:15px;font-weight:500;letter-spacing:0;color:var(--text-muted)}
.tone .big small{color:var(--game-accent)}

/* Win rate: a ring with the split of results under it. Win and loss use the status tokens and always carry a word. */
.ov-win{grid-column:1/span 4;grid-row:1/span 2;gap:16px}
.win-body{display:grid;justify-items:center;gap:14px;margin:6px 0 4px;text-align:center}
.ring-big b{display:inline;font-size:42px;line-height:1;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.ring-big small{margin-left:2px;font-size:18px;font-weight:500;color:var(--text-muted)}
.tone .ring-big small{color:var(--game-accent)}
.ring-big.small b,.ring-big.small{font-size:30px}.ring-big.small{font-weight:550;letter-spacing:-.04em}.ring-big.small small{font-size:14px}
.streak{display:inline-flex;align-items:center;gap:6px;margin:0;padding:1px 8px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-body);font-size:12px;font-weight:500;line-height:20px}
.streak.win{background:var(--success-bg);color:var(--success)}.streak.loss{background:var(--danger-bg);color:var(--danger)}
.split{margin-top:auto}
.stack-bar>i{--series:var(--text-faint)}.stack-bar>i.win{--series:var(--success)}.stack-bar>i.loss{--series:var(--danger)}.stack-bar>i.remake{--series:var(--border-strong)}
.tone .stack-bar{background:color-mix(in srgb,var(--card-bg) 70%,transparent)}
.legend{margin-top:10px}.legend>li{--series:var(--text-faint)}.legend>li.win{--series:var(--success)}.legend>li.loss{--series:var(--danger)}.legend>li.remake{--series:var(--border-strong)}
.t-games{grid-column:5/span 4}.t-kda{grid-column:9/span 4}.t-part{grid-column:5/span 4}.t-score{grid-column:9/span 4}
.mini-bars{display:flex;align-items:flex-end;gap:3px;height:34px}
.mini-bars i{flex:1;min-width:0;border-radius:4px 4px 0 0;background:var(--game-vivid)}.mini-bars i.idle{height:3px;border-radius:0;background:var(--track)}
.kda-trio{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.kda-trio div{display:grid;gap:2px}.kda-trio b{font-size:30px;line-height:34px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}.kda-trio span{color:var(--text-muted);font-size:12px}
.kda-trio span::before{content:'';display:inline-block;width:8px;height:8px;margin-right:5px;border-radius:3px;background:var(--series)}
.kda-trio div:nth-child(1){--series:var(--game-vivid)}.kda-trio div:nth-child(2){--series:color-mix(in srgb,var(--text-faint) 55%,var(--track))}.kda-trio div:nth-child(3){--series:color-mix(in srgb,var(--game-vivid) 55%,var(--card-bg))}
.kda-bar{display:flex;gap:2px;height:8px;border-radius:4px;overflow:hidden;background:var(--track)}
.kda-bar i{display:block;min-width:2px}.kda-bar .k{background:var(--game-vivid)}.kda-bar .d{background:color-mix(in srgb,var(--text-faint) 55%,var(--track))}.kda-bar .a{background:color-mix(in srgb,var(--game-vivid) 55%,var(--card-bg))}
.kda-bar.thin{height:5px;margin-top:6px}
.meter-row{display:grid;grid-template-columns:1fr auto;align-items:baseline;gap:6px 10px;font-size:13px;color:var(--text-muted)}
.meter-row b{color:var(--text);font-size:22px;line-height:26px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.meter-row .meter{grid-column:1/-1}
.scale{position:relative;display:grid;grid-template-columns:1fr auto;gap:4px 8px}.scale .meter{grid-column:1/-1}.scale em{font-style:normal;color:var(--text-faint);font-size:11px;line-height:14px}.scale em:last-child{justify-self:end;grid-column:2;grid-row:2}.scale em:first-of-type{grid-column:1;grid-row:2}

.trend-row .lol-trend{height:100%}

/* Activity: bars per day for a short window, a Monday-first calendar for a long one, then the hours of the day. */
.heat-card{gap:14px}
.heat-body{display:flex;gap:28px;align-items:flex-start;min-width:0}
.heat-bars{flex:1 1 auto;min-width:0}
.heat-scroll{min-width:0;flex:0 1 auto;overflow-x:auto;padding:2px 2px 6px}
.heat{--cell:clamp(13px,calc(380px / var(--weeks) - 5px),24px);--gap:5px;display:grid;grid-template-columns:auto auto;grid-template-rows:auto auto;gap:6px 8px;width:max-content}
.heat-months{grid-column:2;display:grid;grid-auto-columns:var(--cell);column-gap:var(--gap);height:14px;color:var(--text-faint);font-size:11px;line-height:14px}
.heat-months span{white-space:nowrap}
.heat-weekdays{display:grid;grid-template-rows:repeat(7,var(--cell));row-gap:var(--gap);color:var(--text-faint);font-size:11px;line-height:var(--cell)}
.heat-grid{display:grid;grid-template-rows:repeat(7,var(--cell));grid-auto-flow:column;grid-auto-columns:var(--cell);gap:var(--gap)}
.heat-cell{border-radius:4px;background:var(--track)}
.heat-cell[data-level="1"],.heat-legend i[data-level="1"]{background:color-mix(in srgb,var(--game-vivid) 28%,var(--track))}
.heat-cell[data-level="2"],.heat-legend i[data-level="2"]{background:color-mix(in srgb,var(--game-vivid) 52%,var(--track))}
.heat-cell[data-level="3"],.heat-legend i[data-level="3"]{background:color-mix(in srgb,var(--game-vivid) 76%,var(--track))}
.heat-cell[data-level="4"],.heat-legend i[data-level="4"]{background:var(--game-vivid)}
.heat-stats{display:grid;gap:14px;flex:0 0 auto;min-width:130px;margin:0 0 0 auto}
.heat-stats div{display:grid;gap:2px}.heat-stats dt{color:var(--text-muted);font-size:12px}.heat-stats dd{margin:0;font-size:22px;line-height:28px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.heat-stats small{margin-left:4px;font-size:12px;font-weight:400;letter-spacing:0;color:var(--text-muted)}
.heat-labels{display:flex;justify-content:space-between;align-items:center;gap:8px;font-size:12px;color:var(--text-faint)}
.heat-legend{display:inline-flex;align-items:center;gap:4px}.heat-legend i{display:block;width:12px;height:12px;border-radius:4px;background:var(--track)}
.hours{margin-top:auto;padding-top:14px;border-top:1px solid var(--border)}
.hours-title{margin:0 0 8px;font-size:13px;font-weight:500;color:var(--text)}.hours-title small{margin-left:8px;color:var(--text-faint);font-size:12px;font-weight:400}
.hour-bars{display:flex;align-items:flex-end;gap:3px;height:44px}
.hour-bars i{flex:1;min-width:0;border-radius:4px 4px 0 0;background:color-mix(in srgb,var(--game-vivid) 45%,var(--track))}.hour-bars i.peak{background:var(--game-vivid)}.hour-bars i.idle{height:3px;border-radius:0;background:var(--track)}
.hour-axis{display:flex;justify-content:space-between;margin-top:4px;color:var(--text-faint);font-size:11px}

/* Champion pool: ranked rows, a tone tile with the first letter each, win rate as a meter. */
.champ-list{display:grid;gap:4px;margin:0;padding:0;list-style:none}
.champ-list li{display:grid;grid-template-columns:auto minmax(0,1fr) minmax(96px,38%);align-items:center;gap:12px;padding:6px 0}
.champ-tile{display:grid;place-items:center;flex-shrink:0;width:36px;height:36px;border-radius:30%;background:var(--game-tone);color:var(--game-accent);font-size:15px;font-weight:600}
.champ-copy{display:grid;min-width:0}.champ-copy strong{font-size:14px;line-height:20px;font-weight:500;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.champ-copy small{color:var(--text-muted);font-size:12px;line-height:18px;white-space:nowrap}
.champ-rate{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px}.champ-rate b{min-width:44px;text-align:right;font-size:13px;font-weight:500;font-variant-numeric:tabular-nums}
.more{margin-top:4px}.more summary,.quiet summary{cursor:pointer;color:var(--text-muted);font-size:13px;font-weight:500}
@media(hover:hover) and (pointer:fine){.more summary:hover,.quiet summary:hover{color:var(--text)}}
.quiet{padding:16px 20px;margin:0 0 16px;border-radius:var(--radius-tile)}.quiet p{margin:10px 0 0;font-size:12px;line-height:1.8;color:var(--text-muted)}
.quiet>:deep(.cap-card){margin-top:12px;padding:0;border:0;border-radius:0;background:transparent;box-shadow:none}

/* Highlights: a rail of small white tiles; four and five kills take the tone. */
.highlights{margin:0 0 20px}
.highlights .h-rail{--rail-pad:2px;--rail-pad-block:4px;--rail-gap:14px}
.highlights h3{margin:0;font-size:18px;line-height:26px;font-weight:600;letter-spacing:-.02em}
.hl-card{display:grid;align-content:start;gap:4px;width:204px;min-height:132px;padding:16px 18px;border:1px solid var(--card-border);border-radius:var(--radius-tile);background:var(--card-bg);box-shadow:var(--card-shadow)}
.hl-label{justify-self:start;padding:1px 8px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-body);font-size:12px;font-weight:500;line-height:20px}
.hl-value{margin-top:6px;font-size:30px;line-height:34px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.hl-who{font-size:13px;font-weight:500}.hl-card small{color:var(--text-muted);font-size:12px}
.hl-card.rare{border-color:transparent;background:var(--game-tone)}
.hl-card.rare .hl-label{background:var(--card-bg);color:var(--game-accent)}.hl-card.rare small{color:var(--game-accent)}

/* Empty state: copy on the left, a faded sketch of what the archive will fill in on the right. */
.lol-empty{display:flex;align-items:center;justify-content:space-between;gap:28px 40px;flex-wrap:wrap;padding:32px 36px;overflow:hidden;margin-bottom:20px}
.lol-empty-copy{flex:1 1 320px;max-width:560px}
.lol-empty h3{font-size:20px;line-height:28px;font-weight:600;letter-spacing:-.02em;margin:0}
.lol-empty p{margin:12px 0 0;color:var(--text-muted);font-size:13px;line-height:1.9}
.lol-ghost{position:relative;display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;gap:14px 20px;align-items:center;flex:0 1 330px;min-width:240px}
.ghost-ring{width:84px;height:84px;border-radius:50%;border:12px solid var(--track);border-top-color:var(--game-vivid);transform:rotate(-30deg)}
.ghost-bars{display:flex;align-items:flex-end;gap:6px;height:84px}.ghost-bars i{flex:1;border-radius:4px 4px 0 0;background:color-mix(in srgb,var(--game-vivid) 35%,var(--track))}
.ghost-cells{grid-column:1/-1;display:grid;grid-template-columns:repeat(21,1fr);gap:5px}.ghost-cells i{aspect-ratio:1;border-radius:4px;background:var(--game-vivid)}
.legacy-note{margin:4px 4px 14px;color:var(--text-muted);font-size:13px;line-height:1.8}
.lol-empty-line{padding:28px 0;text-align:center;color:var(--text-muted);font-size:13px}
.method-note{font-size:12px;line-height:1.8;color:var(--text-muted)}
p.method-note{margin:0 4px 12px}.b-card .method-note{margin:0}.lol-footnote{margin:20px 4px 4px;font-size:12px;line-height:1.8;color:var(--text-muted)}

/* History: a form chart (bar height is KDA, the tag underneath says the result), then one card of rows. */
.form-card{grid-column:span 8}.form-side{grid-column:span 4}
.form-bars{display:flex;align-items:flex-end;gap:5px;margin:6px 0 0;padding:0;list-style:none}
.form-col{display:grid;gap:6px;flex:1 1 0;min-width:0;justify-items:center}
.form-slot{display:flex;align-items:flex-end;justify-content:center;width:100%;height:118px;border-bottom:1px solid var(--border)}
.form-bar{position:relative;width:min(22px,76%);border-radius:4px 4px 0 0;background:var(--text-faint)}
.form-col.win .form-bar{background:color-mix(in srgb,var(--success) 78%,var(--card-bg))}.form-col.loss .form-bar{background:color-mix(in srgb,var(--danger) 72%,var(--card-bg))}
.form-col.remake .form-bar,.form-col.unknown .form-bar{background:color-mix(in srgb,var(--text-faint) 50%,var(--track))}
.form-bar.stub{height:14px;border:1.5px dashed var(--text-faint);background:transparent!important}
.form-bar.clipped::before{content:'';position:absolute;left:50%;top:-5px;width:6px;height:6px;border-radius:1px;background:inherit;transform:translateX(-50%) rotate(45deg)}
.form-pill{display:grid;place-items:center;width:100%;max-width:26px;height:22px;border-radius:var(--radius-chip);font-size:12px;font-weight:600;line-height:1;background:var(--control-track);color:var(--text-muted)}
.form-col.win .form-pill{background:var(--success-bg);color:var(--success)}.form-col.loss .form-pill{background:var(--danger-bg);color:var(--danger)}
.form-card .legend{margin-top:2px}
.form-ring{display:grid;justify-items:center;gap:10px;margin:4px 0;text-align:center}
.match-list{padding:22px 22px 6px}
.lol-match{padding:16px 0;border-top:1px solid var(--border)}
.match-list .b-head{margin-bottom:12px}
.match-list .b-head+.lol-match{border-top:0;padding-top:4px}
.match-main{display:grid;grid-template-columns:104px minmax(210px,1.5fr) minmax(170px,1.2fr) 76px auto;gap:12px 20px;align-items:center}
.match-main strong{font-size:14px;font-weight:500}
.match-main small{display:block;font-size:12px;color:var(--text-muted);margin-top:2px;line-height:1.6}
.match-result{display:grid;justify-items:start}
.match-result b{display:inline-block;padding:1px 8px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-muted);font-size:12px;line-height:20px;font-weight:500}
.win .match-result b{background:var(--success-bg);color:var(--success)}.loss .match-result b{background:var(--danger-bg);color:var(--danger)}
.match-champion{display:flex;align-items:center;gap:12px;min-width:0}
.match-champion .champ-tile{width:44px;height:44px;font-size:18px}
.match-kda strong{font-size:20px;line-height:26px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.match-score strong{font-size:22px;line-height:28px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}.match-score strong.unknown{color:var(--text-faint)}
.match-main>button{justify-self:end}
.match-main>button[aria-expanded="true"]{background:var(--accent-soft);border-color:transparent;color:var(--accent)}
.match-tags{display:flex;gap:6px;flex-wrap:wrap;margin-top:12px}
.match-tags span{font-size:12px;line-height:20px;color:var(--text-muted);background:var(--control-track);padding:1px 8px;border-radius:var(--radius-chip)}
.match-tags .augment{color:var(--text-body)}
.match-tags .rare-tag{color:var(--game-accent);background:var(--game-tone);font-weight:500}
.match-detail{margin-top:14px;padding:4px 16px 8px;border:1px solid var(--border);border-radius:var(--radius-well);background:var(--card-bg);font-size:13px}
.match-detail>p{margin:10px 0}
.team-block+.team-block{margin-top:6px}
.match-detail h4{font-size:13px;font-weight:600;color:var(--text-muted);margin:12px 0 2px}
.match-detail h4.win{color:var(--success)}.match-detail h4.loss{color:var(--danger)}
.own td{background:color-mix(in srgb,var(--game-tone) 70%,transparent)}

/* Hex. */
.hex-intro{grid-column:span 5}.hex-chart{grid-column:span 7}
.hex-cover{display:flex;align-items:center;gap:18px;margin:4px 0 2px}
.hex-count{margin:0;font-size:14px;line-height:1.7;font-weight:500;color:var(--text)}

/* Tables are the shared .data-table; the first column names the row and the rest are numbers. */
.lol-table-wrap{overflow:auto;margin-top:8px}
.lol-table-wrap.tall{max-height:520px}
.lol-table-wrap.tall th{position:sticky;top:0;z-index:1}
.lol-table-wrap :is(th,td):not(:first-child){text-align:right}
.lol-table-wrap td{white-space:nowrap;font-variant-numeric:tabular-nums}
.lol-table-wrap td:first-child{white-space:normal;min-width:90px}
.match-detail table{table-layout:fixed;min-width:560px}.match-detail th:nth-child(1){width:30%}.match-detail th:nth-child(2){width:22%}.match-detail th:nth-child(3){width:32%}
.cell-meter{display:inline-flex;align-items:center;gap:12px}.cell-meter .meter{flex:0 0 72px;height:6px}

/* News: one tone card for the count, one for the weekly rhythm, then the shared list. */
.news-count{grid-column:span 4;align-content:start}
.news-rhythm{grid-column:span 8}

@container lol-view (max-width:980px){
  .ov-win{grid-column:1/-1;grid-row:auto}
  .t-games,.t-part{grid-column:1/span 6}.t-kda,.t-score{grid-column:7/span 6}
  .span-7,.span-5{grid-column:1/-1}
  .form-card,.form-side,.hex-intro,.hex-chart{grid-column:1/-1}
  .match-main{grid-template-columns:104px minmax(190px,1.4fr) minmax(150px,1fr) auto}
  .match-score{display:none}
}
@container lol-view (min-width:560px) and (max-width:980px){
  .ov-win{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:8px 36px}
  .ov-win .b-head{grid-column:1/-1}
  .ov-win .split{margin-top:0}
  .form-side .form-ring{grid-template-columns:auto 1fr;grid-template-rows:1fr auto auto 1fr;justify-items:start;column-gap:28px;row-gap:8px;text-align:left}
  .form-side .form-ring>:first-child{grid-row:1/span 4}
  .form-side .form-ring>.b-note{grid-column:2;grid-row:2}
  .form-side .form-ring>.streak{grid-column:2;grid-row:3}
}
@container lol-view (max-width:700px){
  .t-games,.t-part,.t-kda,.t-score,.span-6,.news-count,.news-rhythm{grid-column:1/-1}
  .heat-body{flex-direction:column;align-items:stretch;gap:16px}.heat-stats{grid-template-columns:repeat(3,minmax(0,1fr));width:100%;margin:0}
  .heat{--cell:clamp(11px,calc((100cqw - 72px - (var(--weeks) - 1) * 5px) / var(--weeks)),22px)}
  .match-main{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px 14px}
  .match-champion{grid-column:1/-1}
  .match-main>button{grid-column:1/-1;justify-self:stretch}
  .match-score{display:block}
}
@media(max-width:600px){
  .lol-header{align-items:flex-start;flex-direction:column}.collect-button{width:100%}
  .lol-id-copy h2{font-size:20px}
  .lol-toolbar{gap:10px}.lol-filters{width:100%}.lol-filters label{flex:1}.lol-filter-menu{min-width:0;width:100%;max-width:none}.reload-button{width:100%}
  .bento{gap:14px;margin-bottom:14px}
  .lol-empty{padding:24px 20px}
  .form-bars{gap:2px}.form-pill{max-width:none}
  .match-list{padding:18px 16px 2px}.lol-match{padding:14px 0}
  .kda-trio b{font-size:26px}
  .data-table th,.data-table td{padding:10px 7px}
  /* The opened match has four columns; on a phone they all fit once the damage bar sits under its number. */
  .match-detail{padding:2px 12px 6px}
  .match-detail table{table-layout:auto;min-width:0}
  .match-detail th:nth-child(-n+3){width:auto}
  .match-detail .cell-meter{flex-direction:column-reverse;align-items:flex-end;gap:4px}
  .match-detail .cell-meter .meter{flex:none;width:44px}
}
</style>
