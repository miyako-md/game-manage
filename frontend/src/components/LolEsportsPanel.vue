<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { getLolEsports, refreshLolEsports } from '../lol-esports-api.js'
import { createEsportsBrowseState, ESPORTS_FAMILIES, esportsDensity, esportsGroupLabel, esportsTime, selectEsportsMatches } from '../esports.js'
import { vGlide } from '../motion.js'
import AppIcon from './AppIcon.vue'
import BarChart from './BarChart.vue'
import EsportsSchedule from './EsportsSchedule.vue'
import EsportsTeams from './EsportsTeams.vue'
import EsportsPlayers from './EsportsPlayers.vue'
const props = defineProps({ snap: Object, browseState: { type: Object, default: createEsportsBrowseState } })
const emit = defineEmits(['snapshot', 'browse-change'])
const filtersOpen = ref(false)
const local = ref(props.snap), browse = ref({ ...createEsportsBrowseState(), ...props.browseState }), restored = ref(Boolean(props.browseState?.matchId)), loading = ref(false), error = ref(''), note = ref('')
let controller, generation = 0, disposed = false, navigation = 0
watch(() => props.snap, value => { local.value = value })
watch(() => props.browseState, value => { browse.value = { ...createEsportsBrowseState(), ...value } }, { deep: true })
const valid = computed(() => local.value?.payload?.schema_version === 1)
const payload = computed(() => valid.value ? local.value.payload : {})
const missing = computed(() => payload.value.missing_families || Object.keys(ESPORTS_FAMILIES).filter(f => !(payload.value.tournaments || []).some(t => t.family === f)))
const matchView = computed(() => ['schedule', 'results'].includes(browse.value.view))
const tournaments = computed(() => (payload.value.tournaments || []).filter(t => !browse.value.family || t.family === browse.value.family))
const filteredTeams = computed(() => (payload.value.teams || []).filter(t => !browse.value.family || t.tournament_ids?.some(id => tournaments.value.some(e => e.id === id))))
const familyMatches = computed(() => selectEsportsMatches(payload.value, { family: browse.value.family }))
const coverage = computed(() => tournaments.value.map(t => ({ ...t, meta: payload.value.coverage?.['matches:' + t.id] })))
// Matches per day for the week either side of today; the chart only appears where it has something to show.
const density = computed(() => matchView.value ? esportsDensity(familyMatches.value) : [])
const hasDensity = computed(() => density.value.some(day => day.value))
function change(patch) { navigation++; restored.value = false; browse.value = { ...browse.value, ...patch }; emit('browse-change', patch) }
function filter(patch) { change({ ...patch, page: 1, matchId: '', teamId: '', playerId: '', returnTo: [] }) }
async function go(patch, focusId) {
  const { returnTo, ...previous } = browse.value
  previous.returnFocus = focusId || globalThis.document?.activeElement?.id || ''
  previous.returnScroll = globalThis.window?.scrollY || 0
  change({ ...patch, returnTo: [...(returnTo || []), previous].slice(-12) })
  const current = navigation
  await nextTick()
  if (current !== navigation || disposed) return
  const heading = globalThis.document?.querySelector('.es-main h3')
  heading?.focus?.({ preventScroll: true })
  if (!patch.matchId) heading?.scrollIntoView?.({ block: 'start' })
}
async function back() {
  const stack = [...(browse.value.returnTo || [])], previous = stack.pop()
  change({ ...(previous || { view: 'schedule', teamId: '', playerId: '', matchId: '' }), returnTo: stack })
  const current = navigation
  await nextTick(); await nextTick()
  if (current !== navigation || disposed) return
  globalThis.document?.getElementById(previous?.returnFocus)?.focus?.({ preventScroll: true })
  if (previous) globalThis.window?.scrollTo?.({ top: previous.returnScroll || 0, behavior: 'instant' })
}
function showTeam(id, focus) { go({ view: 'teams', teamId: id, playerId: '' }, focus) }
function showPlayer(id, focus) { go({ view: 'players', playerId: id, teamId: '' }, focus) }
function showMatch(id, focus) {
  const match = payload.value.matches?.find(m => m.id === id)
  go({ view: matchView.value ? browse.value.view : match?.status === 'completed' ? 'results' : 'schedule', teamId: '', playerId: '', matchId: id }, focus)
}
async function load(refresh) {
  if (loading.value) return
  loading.value = true; error.value = ''; note.value = ''; const current = ++generation
  controller = new AbortController()
  try {
    const value = await (refresh ? refreshLolEsports : getLolEsports)({ signal: controller.signal })
    if (disposed || current !== generation) return
    local.value = refresh ? value.snapshot : value; emit('snapshot', local.value)
    if (refresh) {
      if (!value.ok) error.value = '更新未成功，保留已有赛事缓存，请稍后重试。'
      else note.value = '赛事已更新。'
    }
  } catch (err) { if (!disposed && current === generation && err.name !== 'AbortError') error.value = err.message }
  finally { if (!disposed && current === generation) loading.value = false }
}
if (!props.snap) load(false)
onBeforeUnmount(() => { disposed = true; generation++; controller?.abort() })
</script>
<template>
  <div class="esports-panel">
    <header class="es-header"><div class="es-heading"><h2>{{ payload.season_year || '' }} 职业赛事</h2><span v-if="local?.fetched_at" class="es-fresh">更新于 {{ esportsTime(local.fetched_at).slice(5) }}</span></div><button class="es-update ui-button primary" :disabled="loading" @click="load(true)"><AppIcon name="refresh" :size="15" :class="{ spinning: loading }" />{{ loading ? '正在读取…' : '更新赛事' }}</button></header>
    <p v-if="loading" role="status" class="es-note">正在更新赛事…</p><p v-if="error" role="alert" class="es-warning">{{ error }}</p><p v-if="note" role="status" class="es-note">{{ note }}</p>
    <p v-if="local?.payload && !valid" role="alert" class="es-warning">赛事数据版本不兼容，请更新服务。</p>
    <template v-else>
      <section v-if="!local?.fetched_at && !payload.tournaments?.length" class="es-onboard cap-card"><p class="es-empty">暂无当年赛事记录，点击右上角「更新赛事」获取。</p><div class="es-ghost" aria-hidden="true"><span v-for="n in 3" :key="n"><i></i><b></b><i></i></span></div></section>
      <div v-if="local?.stale || missing.length" class="es-notices"><p v-if="local?.stale">赛事资料待更新，当前显示上次同步结果。</p><p v-if="missing.length">{{ missing.map(f => ESPORTS_FAMILIES[f]).join('、') }} · 当年资料暂缺。</p></div>
      <nav v-glide class="es-tabs segmented" aria-label="职业赛事视图"><button v-for="[key, label] in [['schedule','赛程'],['results','赛果'],['teams','战队'],['players','选手']]" :key="key" :aria-pressed="browse.view === key" @click="change({ view: key, page: 1, teamId: '', playerId: '', matchId: '', returnTo: [] })">{{ label }}</button></nav>
      <div class="es-layout">
        <aside class="es-sidebar"><div class="es-filter-disclosure" :class="{ 'is-expanded': filtersOpen }"><button class="es-filter-toggle" aria-controls="es-filter-fields" :aria-expanded="filtersOpen" @click="filtersOpen = !filtersOpen">筛选赛事 <span>{{ ESPORTS_FAMILIES[browse.family] || '全部赛事' }}{{ browse.date ? ' · ' + browse.date : '' }}{{ browse.filterTeamId ? ' · 已选战队' : '' }}</span></button><div id="es-filter-fields" class="es-filters">
          <label>赛事<MenuSelect class="es-filter-menu" label="筛选赛事" :model-value="browse.family" :options="[{value:'',label:'全部赛事'},...Object.entries(ESPORTS_FAMILIES).map(([value,name]) => ({value,label:name + (missing.includes(value) ? ' · 暂缺' : '')}))]" @change="filter({ family: $event, filterTeamId: '' })" /></label>
          <template v-if="matchView"><label>比赛日期（北京时间）<input aria-label="比赛日期" type="date" :value="browse.date" @change="filter({ date: $event.target.value })"></label><label>战队<MenuSelect class="es-filter-menu" label="筛选战队" :model-value="browse.filterTeamId" :options="[{value:'',label:'全部战队'},...filteredTeams.map(team => ({value:team.id,label:team.short_name || team.name}))]" @change="filter({ filterTeamId: $event })" /></label></template>
          <button class="es-reset ui-button small-button" @click="filter({ family: '', date: '', filterTeamId: '' })">清除筛选</button>
          <div class="es-directory"><span class="es-eyebrow">赛事目录</span><button v-for="(name, key) in ESPORTS_FAMILIES" :key="key" class="ui-button small-button" :aria-pressed="browse.family === key" @click="filter({ family: key, filterTeamId: '' })"><strong>{{ name }}</strong><small v-if="missing.includes(key)">资料暂缺</small></button></div>
        </div></div></aside>
        <main class="es-main">
          <div class="es-context cap-card" :class="{ 'has-density': hasDensity }"><div class="es-context-head"><strong>{{ ESPORTS_FAMILIES[browse.family] || '全部赛事' }}</strong><span>{{ payload.season_year || '' }} · {{ familyMatches.length }} 场 / {{ filteredTeams.length }} 队已收录</span></div><div v-if="hasDensity" class="es-density"><span class="es-eyebrow">前后一周每天的比赛场数 · {{ density[0].label }} 至 {{ density.at(-1).label }}</span><BarChart :items="density.map(day => ({ label: String(day.day), value: day.value }))" label="前后一周每天的比赛场数" unit=" 场" :highlight="7" :height="64" /></div><details><summary>来源与覆盖</summary><p class="es-note">腾讯官方公开资料 · 当前已收录范围</p><p v-for="item in coverage" :key="item.id" class="es-note"><strong>{{ item.name }}</strong><br>{{ esportsGroupLabel(item.meta) }}</p><p v-if="!coverage.length" class="es-note">暂无赛事覆盖资料。</p></details></div>
          <EsportsSchedule v-if="matchView" :payload="payload" :filters="browse" :restored="restored" @select-team="showTeam" @select-match="showMatch" @page-change="page => change({ page })" @back="back" />
          <EsportsTeams v-else-if="browse.view === 'teams'" :payload="payload" :filters="browse" @select-team="showTeam" @select-player="showPlayer" @select-match="showMatch" @back="back" />
          <EsportsPlayers v-else :payload="payload" :filters="browse" @select-team="showTeam" @select-player="showPlayer" @back="back" />
        </main>
      </div>
      <footer class="es-note es-footer">赛事目录：{{ esportsGroupLabel(payload.catalog) }}</footer>
    </template>
  </div>
</template>
<style src="../esports.css"></style>

<style scoped>
.es-filter-menu { width:100%; min-width:0; }
.es-filter-menu :deep(.menu-select-trigger) { width:100%; min-width:0; min-height:38px; font-size:13px; font-weight:500; }
@media(max-width:760px) { .es-filter-menu :deep(.menu-select-trigger) { min-height:44px; } }
</style>
