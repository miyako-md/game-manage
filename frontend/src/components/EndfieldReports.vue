<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, nextTick, ref, watch } from 'vue'
import { profileReport, rows, displayValue as display, sourceName as named, selectOperators, selectMedals, rarityParts, phaseParts, medalCategoryParts, recentMedals, platedSummary } from '../endfield-reports.js'
import { displayBeijing } from '../time.js'
import { SHIP_CONVERSION_MODEL } from '../endfield-ship.js'
import { vReveal } from '../motion.js'
import DonutChart from './DonutChart.vue'
import HRail from './HRail.vue'
import RingGauge from './RingGauge.vue'
import SummaryMetrics from './SummaryMetrics.vue'
import EndfieldArtwork from './EndfieldArtwork.vue'
import EndfieldShipResident from './EndfieldShipResident.vue'
import EndfieldLoadout from './EndfieldLoadout.vue'
const props = defineProps({ payload: Object, imageMode:Boolean, view: { type: String, default: 'overview' }, fetchedAt: String, stale: Boolean,
  operatorDetail: Object, operatorDetailId: String, operatorBusy: Boolean, operatorError: String, operatorStale: Boolean, operatorFetchedAt: String })
const emit = defineEmits(['inspect', 'navigate', 'close-detail'])
const report = computed(() => profileReport(props.payload))
const overview = computed(() => report.value.overview || {})
const training = computed(() => report.value.training || {})
const regions = computed(() => rows(report.value.regions?.items))
const rooms = computed(() => rows(report.value.ship?.rooms))
const honor = computed(() => report.value.honor || { summary: { declared_count: props.payload?.achievements?.count }, items: [] })
const medalSearch=ref(''), medalCategory=ref(''), medalSort=ref('recent')
const medals=computed(()=>rows(honor.value.items))
const categories=computed(()=>[...new Set(medals.value.map(item=>item.category ?? null))].sort((a,b)=>a==null?1:b==null?-1:a.localeCompare(b,'zh-CN')))
const filteredMedals=computed(()=>selectMedals(medals.value,{search:medalSearch.value,category:medalCategory.value===''?undefined:JSON.parse(medalCategory.value),sort:medalSort.value}))
function clearMedalFilters(){medalSearch.value='';medalCategory.value=''}
const mainMission=computed(()=>typeof overview.value.base?.main_mission === 'string' ? overview.value.base.main_mission.trim() : '')
const search = ref(''), rarity = ref(''), profession = ref(''), sort = ref('level')
const operators = computed(() => rows(training.value.items))
const selected = computed(() => selectOperators(operators.value, { search: search.value, rarity: rarity.value, profession: profession.value, sort: sort.value }))
const rarities = computed(() => [...new Set(operators.value.map(item => item.rarity).filter(value => value != null))].sort((a,b) => b-a))
const professions = computed(() => [...new Set(operators.value.map(item => named(item.profession)).filter(value => value !== '未知'))])
const detailPanel = ref(null)
let detailOpener = null
function inspect(id, event) { detailOpener = event?.currentTarget || null; emit('inspect', id) }
watch(() => props.operatorDetailId, async id => {
  await nextTick()
  if (id) { detailPanel.value?.scrollIntoView?.({ block: 'start' }); detailPanel.value?.focus?.({ preventScroll: true }) }
  else detailOpener?.focus?.()
})
const time = value => value == null || value === '' ? '未知' : displayBeijing(value)
const pair = value => `${display(value?.current ?? value?.count)} / ${display(value?.total ?? value?.maximum)}`

// ── Overview ──
const stamina = computed(() => overview.value.stamina || {})
const staminaFull = computed(() => Number.isFinite(stamina.value.current) && Number.isFinite(stamina.value.maximum) && stamina.value.maximum > 0 && stamina.value.current >= stamina.value.maximum)
const staminaNote = computed(() => staminaFull.value ? '该次观测理智已满' : `预计回满 ${time(stamina.value.expected_full_at)}`)
const percentOf = (current, total) => Number.isFinite(current) && Number.isFinite(total) && total > 0 ? Math.round(Math.min(1, current / total) * 100) : null
const progressItems = computed(() => rows(overview.value.progress).map((item, index) => ({ key: item.id || index, label: item.name || item.title || '进度', current: item.cur, total: item.total,
  note: item.remaining == null ? '' : item.remaining === 0 ? '已完成' : `还需 ${item.remaining}`, percent: percentOf(item.cur, item.total) })))
const emptyTodoStatus = computed(() => {
  const known = new Set(rows(overview.value.progress).filter(item => ['daily', 'weekly'].includes(item.id) && item.remaining != null).map(item => item.id))
  if (overview.value.todos == null || !known.size) return '任务进度未知。'
  return known.has('daily') && known.has('weekly') ? '已同步的每日与每周任务已完成。' : '已同步任务暂无待办，部分进度未知。'
})

// ── Operators ──
const trainingMetrics = computed(() => [
  { label: '已记录干员', value: training.value.summary?.listed_count },
  { label: '来源干员数', value: training.value.summary?.declared_count },
  { label: '已知等级均值', value: training.value.summary?.average_level == null ? null : Number(training.value.summary.average_level.toFixed(1)), note: `${display(training.value.summary?.known_levels)} 名有等级记录` },
  { label: '最高已知等级', value: training.value.summary?.max_level },
])
// Rarity takes the chart order (the game colour first); higher tiers read first.
const RARITY_COLORS = ['var(--ef-vivid)', 'var(--chart-2)', 'var(--ef-grey)', 'var(--ef-grey-2)']
const rarityChart = computed(() => rarityParts(training.value.summary?.rarity_counts).map((part, index) => ({ ...part, color: RARITY_COLORS[Math.min(index, RARITY_COLORS.length - 1)] })))
// Elite phases are ordinal, so one hue steps from the track colour up to the full game colour.
const phaseChart = computed(() => {
  const parts = phaseParts(training.value.summary?.phase_counts)
  return parts.map((part, index) => ({ ...part, color: `color-mix(in srgb, var(--ef-vivid) ${parts.length > 1 ? Math.round(22 + 78 * index / (parts.length - 1)) : 100}%, var(--track))` }))
})
const phaseColor = value => phaseChart.value.find(part => part.key === String(value))?.color || 'var(--track)'
const counts = computed(() => [
  { key: 'operators', label: '已记录干员', value: training.value.summary?.listed_count, action: '查看全员练度', parts: rarityChart.value },
  { key: 'regions', label: '建设地区', value: report.value.regions?.summary?.region_count, action: '查看地区建设' },
  { key: 'ship', label: '帝江号房间', value: report.value.ship?.summary?.room_count, action: '查看帝江号' },
])
const featured = computed(() => selected.value.filter(item => Number(item.rarity) >= 6))
const rarityBadge = value => Number(value) >= 6 ? 'top' : Number(value) === 5 ? 'high' : ''

// ── Regions ──
function collections(area) {
  if (Array.isArray(area.collections)) return area.collections
  return [['puzzles','醚质'],['chests','宝箱'],['equipment_chests','装备制造模板'],['pieces','维修灵感点'],['blackboxes','协议采录桩']]
    .map(([key,label]) => ({ key, label, current: area[key]?.count, total: area[key]?.total }))
}
const settlementCount = region => region.settlements_available === false ? null : region.settlements_available === true || rows(region.settlements).length ? rows(region.settlements).length : null
const couponPercent = settlement => { const coupon = settlement.coupon || { current: settlement.money, total: settlement.money_max }; return Number.isFinite(coupon.percent) ? coupon.percent : percentOf(coupon.current ?? coupon.count, coupon.total ?? coupon.maximum) }

// ── Honor ──
const categoryChart = computed(() => medalCategoryParts(medals.value).map((part, index) => ({ ...part, color: `var(--chart-${Math.min(index + 1, 8)})` })))
const plating = computed(() => platedSummary(medals.value))
const honorMetrics = computed(() => [
  { label: '来源成就总数', value: honor.value.summary?.declared_count },
  { label: '已记录奖章', value: honor.value.summary?.listed_count },
  // Plating is only counted when it was reported for every listed medal; a partial count would read as the total.
  ...(plating.value.listed && plating.value.known === plating.value.listed ? [{ label: '已镀层', value: plating.value.plated }] : []),
])
const recent = computed(() => recentMedals(filteredMedals.value, 8))
const dayOf = value => { const text = time(value); return /^\d{4}-\d{2}-\d{2}/.test(text) ? text.slice(0, 10) : text }

const detail = computed(() => props.operatorDetail)
const detailName = computed(() => detail.value?.name || operators.value.find(item => String(item.id) === props.operatorDetailId)?.name || '干员配装')
</script>

<template>
  <div class="endfield-reports" :class="{ 'is-image': imageMode }">
    <!-- 概览 -->
    <template v-if="view === 'overview'">
      <section v-reveal class="ef-card ef-hero"><header><div><h2>今日档案</h2></div><span v-if="stale && !imageMode" class="badge badge-stale">待更新</span><span v-else class="chip">森空岛档案</span></header>
        <div class="ef-hero-body">
          <div class="ef-hero-main">
            <div class="ef-identity"><EndfieldArtwork :src="overview.base?.avatar_url" :name="overview.base?.name || '管理员'" /><div><h3>{{ overview.base?.name || '未知昵称' }}</h3><p v-if="!imageMode">UID {{ display(overview.base?.role_id) }}</p></div></div>
            <dl class="ef-levels"><div><dt>账号等级</dt><dd>{{ display(overview.base?.level) }}</dd></div><div><dt>探索等级</dt><dd>{{ display(overview.base?.world_level) }}</dd></div></dl>
            <p v-if="mainMission" class="ef-main-mission"><span>主线进度</span><strong>{{ mainMission }}</strong></p>
          </div>
          <div class="ef-stamina">
            <RingGauge :value="stamina.current" :max="stamina.maximum" label="理智" :size="136" :stroke="13" color="var(--ef-vivid)"><span v-if="imageMode" class="ef-pct">{{ Number.isFinite(stamina.current) && stamina.maximum > 0 ? Math.round(stamina.current / stamina.maximum * 100) + '%' : '—' }}</span><span v-else class="ef-ring-center"><span class="k">理智</span><strong>{{ display(stamina.current) }} <small>/ {{ display(stamina.maximum) }}</small></strong></span></RingGauge>
            <p v-if="imageMode" class="ef-stamina-values">理智 {{ display(stamina.current) }} / {{ display(stamina.maximum) }}</p>
            <p class="ef-note">{{ staminaNote }}</p>
          </div>
        </div>
      </section>
      <section v-reveal class="ef-card ef-progress"><header><div><h2>每日与通行证进度</h2></div></header>
        <ul v-if="progressItems.length" class="ef-prog-list"><li v-for="item in progressItems" :key="item.key" class="ef-prog">
          <RingGauge :value="item.current" :max="item.total" :label="item.label" :size="88" :stroke="10" color="var(--ef-vivid)"><span class="ef-pct">{{ item.percent == null ? '—' : `${item.percent}%` }}</span></RingGauge>
          <div class="ef-prog-copy"><span class="k">{{ item.label }}</span><strong>{{ display(item.current) }} <small>/ {{ display(item.total) }}</small></strong><p v-if="item.note">{{ item.note }}</p></div>
        </li></ul>
        <p v-else class="ef-empty">暂无进度记录。</p>
      </section>
      <component :is="imageMode ? 'div' : 'button'" v-for="item in counts" :key="item.key" v-reveal class="ef-count" :type="imageMode ? undefined : 'button'" @click="imageMode ? undefined : emit('navigate', item.key)">
        <span class="k">{{ item.label }}</span><strong>{{ display(item.value) }}</strong>
        <span v-if="item.parts?.length > 1" class="ef-split stack-bar" aria-hidden="true"><i v-for="part in item.parts" :key="part.key" :style="{ '--series': part.color, flex: part.value }"></i></span>
        <span v-if="item.parts?.length" class="ef-split-legend">{{ item.parts.map(part => `${part.label} ${part.value}`).join(' · ') }}</span>
        <span v-if="!imageMode" class="go">{{ item.action }} →</span>
      </component>
      <section v-reveal class="ef-card ef-todo"><header><div><h2>已知待办</h2></div></header>
        <ul v-if="rows(overview.todos).length" class="ef-todos"><li v-for="(item,index) in overview.todos" :key="item.id || index"><span>{{ item.name }}</span><strong>还需 {{ display(item.remaining) }}</strong></li></ul>
        <p v-else class="ef-empty">{{ emptyTodoStatus }}</p>
      </section>
    </template>

    <!-- 全员练度 与 干员配装 -->
    <template v-else-if="view === 'operators' || view === 'detail'">
      <div v-if="view === 'operators'" v-show="!operatorDetailId" class="ef-contents">
        <section v-reveal class="ef-card ef-stats"><header><div><h2>全员练度</h2></div><span class="ef-note">显示 {{ selected.length }} / {{ operators.length }} 名</span></header>
          <SummaryMetrics compact :metrics="trainingMetrics" />
        </section>
        <section v-if="rarityChart.length" v-reveal class="ef-card ef-rarity"><h2 class="ef-title">稀有度分布</h2>
          <DonutChart v-if="rarityChart.length > 1" :segments="rarityChart" label="干员稀有度分布" unit=" 名" :size="124" :stroke="15"><span class="ef-donut-center"><strong>{{ display(training.summary?.listed_count) }}</strong><small>名</small></span></DonutChart>
          <ul v-else class="ef-single"><li v-for="part in rarityChart" :key="part.key">{{ part.label }} <b>{{ part.value }}</b></li></ul>
        </section>
        <section v-if="phaseChart.length" v-reveal class="ef-card ef-phases"><h2 class="ef-title">精英阶段</h2>
          <div class="stack-bar" role="img" :aria-label="phaseChart.map(part => `${part.label} ${part.value}`).join('，')"><i v-for="part in phaseChart.filter(part => part.value)" :key="part.key" :style="{ '--series': part.color, flex: part.value }" /></div>
          <ul class="legend"><li v-for="part in phaseChart" :key="part.key" :style="{ '--series': part.color }">{{ part.label }} <b>{{ part.value }}</b></li></ul>
        </section>
        <section v-if="featured.length && !imageMode" v-reveal class="ef-card ef-featured"><h2 class="ef-title">6★ 干员</h2>
          <HRail label="6★ 干员"><button v-for="(operator,index) in featured" :key="operator.id || index" type="button" class="ef-feature" :aria-label="`查看${operator.name || '干员'}配装`" :aria-expanded="operatorDetailId === String(operator.id)" :disabled="operatorBusy && operatorDetailId === String(operator.id) || !operator.id" @click="inspect(operator.id,$event)">
            <span class="ef-feature-art"><EndfieldArtwork role portrait :operator-id="operator.char_id || operator.id" :src="operator.avatar_url" :name="operator.name || '干员'" /></span>
            <span class="ef-feature-copy"><strong>{{ display(operator.name) }}</strong><span>Lv. {{ display(operator.level) }}<small>潜能 {{ display(operator.potential) }}</small></span></span>
          </button></HRail>
        </section>
        <section v-reveal class="ef-card ef-roster-card">
          <p v-if="imageMode" class="ef-note">武器、装备、技能与战术道具详情：发送「终末地 角色 干员名」，按精确名称查看单干员配装。</p>
          <div v-if="!imageMode" class="ef-filters"><label>查找干员<input :value="search" @input="search = $event.target.value" type="search" placeholder="姓名或编号" /></label><label>稀有度<MenuSelect v-model="rarity" label="稀有度" :options="[{value:'',label:'全部稀有度'},...rarities.map(value=>({value:String(value),label:value+'★'}))]" /></label><label>职业<MenuSelect v-model="profession" label="职业" :options="[{value:'',label:'全部职业'},...professions.map(value=>({value,label:value}))]" /></label><label>排序<MenuSelect v-model="sort" label="排序" :options="[{value:'level',label:'等级从高到低'},{value:'rarity',label:'稀有度从高到低'},{value:'potential',label:'潜能从高到低'},{value:'name',label:'姓名'}]" /></label></div>
          <p v-if="!selected.length" class="ef-empty">{{ operators.length ? '没有匹配的干员，可调整筛选。' : '尚无干员资料。' }}</p>
          <div v-else class="ef-roster"><article v-for="(operator,index) in selected" :key="operator.id || index" class="ef-operator" :class="rarityBadge(operator.rarity)">
            <div class="ef-operator-top">
              <div class="ef-avatar"><EndfieldArtwork role :operator-id="operator.char_id || operator.id" :src="operator.avatar_url" :name="operator.name || '干员'" /><small class="ef-tier">{{ display(operator.rarity) }}★</small></div>
              <div class="ef-operator-copy"><h3>{{ display(operator.name) }}</h3><p class="ef-operator-level">Lv. {{ display(operator.level) }} <span>潜能 {{ display(operator.potential) }}</span></p></div>
            </div>
            <p class="ef-phase"><i class="ef-phase-dot" :style="{ '--tone': phaseColor(operator.evolve_phase ?? operator.phase) }" aria-hidden="true"></i>精英阶段 {{ display(operator.evolve_phase ?? operator.phase) }}</p>
            <p class="ef-note ef-profession">{{ named(operator.profession) }} · {{ named(operator.property) }}</p>
            <button v-if="!imageMode" type="button" class="ui-button small-button" :disabled="operatorBusy && operatorDetailId === String(operator.id) || !operator.id" :aria-expanded="operatorDetailId === String(operator.id)" @click="inspect(operator.id,$event)">查看配装</button>
          </article></div>
        </section>
      </div>
      <section v-if="operatorDetailId" ref="detailPanel" class="ef-detail" tabindex="-1" aria-label="干员配装详情"><div v-if="!imageMode" class="ef-detail-toolbar"><button type="button" class="text-link" @click="emit('close-detail')">← 返回全员练度</button><span v-if="operatorStale" class="badge badge-stale">配装待更新</span></div><header><div><h2>干员配装<span v-if="!detail"> · {{ detailName }}</span></h2></div><button v-if="!imageMode" type="button" class="ui-button" :disabled="operatorBusy" @click="emit('inspect',operatorDetailId)">重新读取配装</button></header>
        <p v-if="operatorBusy" class="ef-empty" role="status">正在读取干员配装…</p><p v-if="operatorError" class="ef-error" role="alert">{{ operatorError }}</p>
        <p v-if="!imageMode" class="ef-detail-time">配装同步于 {{ time(operatorFetchedAt) }}<span v-if="operatorStale"> · 正在显示上次成功读取的配装</span><span v-else-if="!operatorFetchedAt"> · 来源未提供独立更新时间</span></p>
        <EndfieldLoadout v-if="detail" :operator="detail" />
      </section>
    </template>

    <!-- 地区建设 -->
    <template v-else-if="view === 'regions'">
      <section v-reveal class="ef-card ef-section-intro"><header><div><h2>地区建设</h2></div><span class="ef-note">地区数 {{ display(report.regions?.summary?.region_count) }}</span></header><p v-if="!regions.length" class="ef-empty">尚无地区建设资料。</p></section>
      <section v-for="(region,index) in regions" :key="region.id || index" v-reveal class="ef-card ef-region"><header><div><h2>{{ named(region) }}</h2></div><span class="ef-level">等级 {{ display(region.level) }}</span></header>
        <div class="ef-region-top">
          <div class="ef-money"><span class="k">地区调度券</span>
            <RingGauge :value="region.money?.current ?? region.money?.count" :max="region.money?.total" label="地区调度券" :size="108" :stroke="11" color="var(--ef-vivid)"><span v-if="imageMode" class="ef-pct">{{ typeof region.money?.percent === 'number' ? Math.round(region.money.percent) + '%' : '—' }}</span><span v-else class="ef-ring-center"><strong>{{ display(region.money?.current ?? region.money?.count) }} <small>/ {{ display(region.money?.total) }}</small></strong></span></RingGauge>
            <p v-if="imageMode" class="ef-money-values">{{ display(region.money?.current ?? region.money?.count) }} / {{ display(region.money?.total) }}</p>
          </div>
          <div class="ef-bases"><div class="ef-bases-head"><span class="k">据点</span><strong>{{ display(settlementCount(region)) }}</strong></div>
            <HRail v-if="rows(region.settlements).length" label="据点"><article v-for="(settlement,number) in rows(region.settlements)" :key="settlement.id || number" class="ef-settlement"><h3>{{ settlement.name || '据点' }} <small>等级 {{ display(settlement.level) }}</small></h3><p>基地调度券 <strong>{{ pair(settlement.coupon || {current:settlement.money,total:settlement.money_max}) }}</strong></p><span v-if="couponPercent(settlement) != null" class="ef-bar meter" aria-hidden="true"><i :style="{ width: `${couponPercent(settlement)}%` }"></i></span><p class="ef-note">派驻干员：{{ rows(settlement.officers).map(item => item.name || item.id || '未知').join('、') || (settlement.officers_available === true ? '无派驻' : '未提供') }}</p><div v-if="rows(settlement.officers).length" class="ef-assigned"><EndfieldArtwork v-for="(officer,officerIndex) in rows(settlement.officers)" :key="officer.id || officerIndex" role :operator-id="officer.id" :src="officer.avatar_url" :name="officer.name || officer.id || '干员'" /></div></article></HRail>
          </div>
        </div>
        <div class="ef-areas"><article v-for="(area,number) in rows(region.areas || region.levels)" :key="area.id || number" class="ef-subsection"><h3>{{ area.name || '区域' }}</h3><ul class="ef-facts"><li v-for="item in collections(area)" :key="item.key"><span>{{ item.label }}</span><strong>{{ pair(item) }}<small v-if="item.remaining != null"> · 剩余 {{ item.remaining }}</small></strong><progress v-if="Number.isFinite(item.percent)" :value="item.percent" max="100" :aria-label="`${area.name || '区域'}${item.label}`" /></li></ul></article></div>
      </section>
    </template>

    <!-- 帝江号 -->
    <template v-else-if="view === 'ship'">
      <section v-reveal class="ef-card ef-ship-intro"><header><div><h2>帝江号</h2></div><span class="chip">快照换算</span></header><dl class="ef-ship-counts"><div><dt>房间数</dt><dd>{{ display(report.ship?.summary?.room_count) }}</dd></div><div><dt>有驻守记录的房间</dt><dd>{{ display(report.ship?.summary?.staffed_rooms) }}</dd></div><div><dt>驻守席位记录</dt><dd>{{ display(report.ship?.summary?.operator_slots) }}</dd></div></dl><p v-if="!imageMode" class="ef-note ef-ship-time">游戏观测于 {{ time(report.observed_at) }} · 抓取于 {{ time(fetchedAt || report.fetched_at) }}（北京时间）</p><details v-if="!imageMode" class="ef-model-note"><summary>查看换算依据</summary><p>心情与信赖采用原站 API v3.5.0 参考模型换算该次快照，不外推当前状态。心情以 100% 为上限，信赖最高 200%。</p><p>心情原始值范围 0–10000，超出范围保留原值；信赖按阈值分为友好、亲近、信任。</p><a :href="SHIP_CONVERSION_MODEL.source_url" target="_blank" rel="noopener noreferrer">公开模型说明 ↗</a></details></section>
      <p v-if="!rooms.length" class="ef-empty ef-card">尚无帝江号资料。</p>
      <div class="ef-ship-rooms"><section v-for="(room,index) in rooms" :key="room.id || index" v-reveal class="ef-card ef-ship-room"><header><div><h2>{{ room.name || '舱室' }}</h2></div><span class="ef-room-level"><span>等级</span> LV. {{ display(room.level) }}</span></header><p v-if="!rows(room.operators).length" class="ef-empty">{{ room.operators_available === true ? '当前没有驻守干员记录。' : '尚未采集驻守干员资料。' }}</p><EndfieldShipResident v-for="(operator,number) in rows(room.operators)" :key="operator.id || operator.charId || number" :operator="operator" :image-mode="imageMode" /></section></div>
    </template>

    <!-- 光荣之路 -->
    <template v-else-if="view === 'honor'">
      <section v-reveal class="ef-card ef-honor-head" :class="{ 'is-wide': categoryChart.length < 2 }"><header><div><h2>光荣之路</h2></div><span v-if="medals.length" class="ef-note" role="status">显示 {{ filteredMedals.length }} / {{ medals.length }} 条已记录奖章</span></header><SummaryMetrics compact :metrics="honorMetrics" /><div v-if="medals.length && !imageMode" class="ef-filters ef-medal-filters"><label>查找奖章<input :value="medalSearch" @input="medalSearch=$event.target.value" type="search" placeholder="输入奖章名称" /></label><label>奖章分类<MenuSelect v-model="medalCategory" label="奖章分类" :options="[{value:'',label:'全部分类'},...categories.map(category=>({value:JSON.stringify(category),label:category||'未提供分类'}))]" /></label><label>获得时间排序<MenuSelect v-model="medalSort" label="获得时间排序" :options="[{value:'recent',label:'最近获得优先'},{value:'oldest',label:'最早获得优先'},{value:'source',label:'来源顺序'}]" /></label></div></section>
      <section v-if="categoryChart.length > 1" v-reveal class="ef-card ef-categories"><h2 class="ef-title">奖章分类</h2>
        <DonutChart :segments="categoryChart" label="已记录奖章的分类占比" unit=" 枚" :size="116" :stroke="14"><span class="ef-donut-center"><strong>{{ medals.length }}</strong><small>枚</small></span></DonutChart>
      </section>
      <section v-if="recent.length >= 3 && !imageMode" v-reveal class="ef-card ef-recent"><h2 class="ef-title">最近获得</h2>
        <HRail label="最近获得的奖章"><div v-for="(medal,index) in recent" :key="medal.id ?? index" class="ef-recent-medal" :class="{ plated: medal.is_plated === true }"><EndfieldArtwork :src="medal.icon_url" :name="medal.name || '奖章'" /><strong>{{ medal.name || '未命名奖章' }}</strong><span>{{ dayOf(medal.obtained_at) }}</span></div></HRail>
      </section>
      <p v-if="!medals.length" class="ef-card ef-empty">{{ honor.available === true ? '当前档案没有奖章记录。' : '尚未采集奖章详情，请刷新档案。' }}</p>
      <section v-else-if="!filteredMedals.length" class="ef-card ef-empty"><p>没有匹配的奖章；可调整名称或分类筛选。</p><button type="button" class="ui-button" @click="clearMedalFilters">清除奖章筛选</button></section>
      <div v-else class="ef-medals"><article v-for="(medal,index) in filteredMedals" :key="medal.id ?? index" v-reveal class="ef-medal" :class="{ plated: medal.is_plated === true }"><EndfieldArtwork :src="medal.icon_url" :name="medal.name || '奖章'" /><div><h3>{{ medal.name || '未命名奖章' }}</h3><span class="ef-medal-category">{{ medal.category || '未提供分类' }}</span><p>等级 {{ display(medal.level) }} <span class="ef-medal-plated">{{ medal.is_plated === true ? '已镀层' : medal.is_plated === false ? '未镀层' : '镀层未知' }}</span></p><p class="ef-note">获得于 {{ time(medal.obtained_at) }}</p></div></article></div>
    </template>
    <footer v-if="!imageMode" class="ef-source"><details><summary>{{ stale ? '档案来源 · 待更新' : '档案来源' }}</summary><p>森空岛档案 · {{ stale ? '正在显示已有资料，等待更新' : '已采集资料' }} · 观测于 {{ time(report.observed_at) }} · 同步于 {{ time(fetchedAt || report.fetched_at) }}（北京时间）</p></details></footer>
  </div>
</template>

<style scoped>
/* Flat white cards on a hairline; the game's pale tone is the one colour fill (--ef-tone, ink --ef-ink).
   Bot images set only --game-accent, so every game colour here has a static fallback. */
.endfield-reports { --ef-vivid:var(--game-vivid,var(--game-endfield-vivid)); --ef-tone:var(--game-tone,var(--game-endfield-tone)); --ef-ink:var(--game-accent,var(--game-endfield)); --ef-grey:color-mix(in srgb,var(--text-faint) 34%,var(--card-bg)); --ef-grey-2:var(--border-strong); --accent:var(--ef-ink); --accent-soft:var(--ef-tone);
  display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:16px; min-width:0; }
.endfield-reports > * { grid-column:1 / -1; min-width:0; }
.ef-contents { grid-column:1 / -1; display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:16px; min-width:0; }
.ef-contents > * { grid-column:1 / -1; min-width:0; }
.ef-card { position:relative; min-width:0; padding:20px; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); box-shadow:var(--card-shadow); }
.ef-card > header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
.ef-card h2 { font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.02em; }
.ef-card .ef-title { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 10px; margin:0 0 10px; font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.02em; }
.ef-sub { color:var(--text-faint); font-size:12px; font-weight:400; letter-spacing:0; }
.k { display:block; color:var(--text-muted); font-size:12px; line-height:18px; font-weight:500; }
.ef-note { font-size:13px; color:var(--text-muted); line-height:1.7; }
.ef-empty { color:var(--text-muted); font-size:13px; padding:14px 0; line-height:1.7; }
.ef-empty.ef-card { padding:24px; }
.ef-section-intro { padding:14px 20px; }
.ef-section-intro > header { margin-bottom:0; }
.ef-section-intro .ef-empty { padding:10px 0 0; }
.ef-source { font-size:12px; color:var(--text-muted); line-height:1.7; padding:0 4px; }
.ef-source details { min-width:0; width:100%; }
.ef-source summary { cursor:pointer; padding:6px 0; }
.ef-source details p { padding:6px 0; overflow-wrap:anywhere; }
.ef-error { color:var(--danger); font-size:13px; padding:12px; border-radius:var(--radius-control); background:var(--danger-bg); margin-bottom:16px; }

/* ── 概览 ── */
.ef-hero { grid-column:span 7; overflow:hidden; }
.ef-progress { grid-column:span 5; }
.ef-hero-body { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:18px 28px; }
.ef-hero-main { display:grid; gap:16px; min-width:0; }
.ef-identity { display:flex; gap:16px; align-items:center; min-width:0; }
.ef-identity > .endfield-artwork { width:72px; height:72px; border-radius:var(--radius-tile); }
.ef-identity h3 { font-size:20px; line-height:28px; font-weight:600; letter-spacing:-.02em; overflow-wrap:anywhere; }
.ef-identity p { display:inline-block; margin-top:4px; padding:0 10px; border-radius:var(--radius-chip); background:var(--control-track); font-family:var(--font-mono); font-size:12px; line-height:22px; color:var(--text-muted); }
.ef-levels { display:flex; gap:10px; flex-wrap:wrap; }
.ef-levels > div { min-width:104px; padding:10px 16px; border-radius:var(--radius-well); background:var(--surface-soft); }
.ef-levels dt { font-size:12px; color:var(--text-muted); line-height:18px; }
.ef-levels dd { margin:2px 0 0; font-size:30px; line-height:34px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
.ef-main-mission { display:flex; gap:12px; align-items:baseline; font-size:13px; line-height:1.7; }
.ef-main-mission > span { color:var(--text-muted); white-space:nowrap; }
.ef-main-mission > strong { font-weight:500; overflow-wrap:anywhere; }
.ef-stamina { display:grid; justify-items:center; gap:10px; text-align:center; }
.ef-ring-center { display:grid; justify-items:center; gap:1px; line-height:1.1; }
.ef-ring-center strong { font-size:24px; line-height:28px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
.ef-ring-center small, .ef-prog-copy small { font-size:13px; font-weight:500; letter-spacing:0; color:var(--text-muted); }
.ef-prog-list { display:grid; grid-template-columns:repeat(auto-fit,minmax(112px,1fr)); gap:12px; }
.ef-prog { display:grid; justify-items:center; align-content:start; gap:10px; padding:16px 10px 14px; border-radius:var(--radius-tile); background:var(--surface-soft); min-width:0; text-align:center; }
.ef-pct { font-size:15px; font-weight:550; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
.ef-prog-copy { min-width:0; display:grid; justify-items:center; }
.ef-prog-copy strong { display:block; font-size:20px; line-height:26px; font-weight:550; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.ef-prog-copy p { font-size:12px; color:var(--text-muted); line-height:1.6; }
.ef-count { grid-column:span 3; position:relative; display:grid; align-content:space-between; gap:6px; min-height:128px; padding:18px 20px; text-align:left; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); box-shadow:var(--card-shadow); color:var(--text); font:inherit; }
.ef-count strong { font-size:44px; line-height:48px; font-weight:550; letter-spacing:-.05em; font-variant-numeric:tabular-nums; }
.ef-split { height:8px; gap:3px; }
.ef-split-legend { color:var(--text-muted); font-size:12px; line-height:18px; font-variant-numeric:tabular-nums; }
.ef-count .go { color:var(--ef-ink); font-size:12px; font-weight:500; }
button.ef-count { cursor:pointer; }
@media (hover:hover) and (pointer:fine) { button.ef-count:hover { background:var(--panel-bg); border-color:var(--border-strong); } }
button.ef-count:active { transform:translateY(1px); }
.ef-todo { grid-column:span 3; }
.ef-todo > header { margin-bottom:6px; }
.ef-todo h2 { font-size:16px; }
.ef-todos li { display:flex; justify-content:space-between; flex-wrap:wrap; gap:4px 10px; padding:10px 0; border-bottom:1px solid var(--border); font-size:13px; }
.ef-todos li:last-child { border-bottom:0; }
.ef-todos strong { color:var(--ef-ink); font-weight:500; }

/* ── 全员练度 ── */
.ef-stats { grid-column:span 5; }
.ef-stats :deep(.summary-metrics) { grid-template-columns:repeat(2,minmax(0,1fr)); margin:0; }
.ef-rarity { grid-column:span 4; }
.ef-phases { grid-column:span 3; }
.ef-rarity :deep(.donut-chart) { gap:10px 18px; }
.ef-donut-center { display:grid; justify-items:center; line-height:1; }
.ef-donut-center strong { font-size:26px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; }
.ef-donut-center small { margin-top:3px; font-size:12px; color:var(--text-muted); }
.ef-single { display:flex; flex-wrap:wrap; gap:6px; }
.ef-single li { padding:2px 12px; border-radius:var(--radius-chip); background:var(--control-track); font-size:13px; }
.ef-phases .stack-bar { height:14px; gap:3px; margin:6px 0 10px; }
.ef-phases .legend { display:grid; gap:6px; margin:0; font-size:13px; }
.ef-phases .legend > li { justify-content:space-between; }
.ef-phases .legend > li::before { order:-1; }
.ef-phases .legend b { margin-left:auto; }
.ef-featured { overflow:hidden; }
.ef-featured :deep(.h-rail) { --rail-gap:12px; --rail-pad-block:10px; --rail-pad:2px; }
/* The 6★ rail (web only) is the mockup role card: a white frame, the art on the game tone with the level as a white tag, then the name. */
.ef-feature { display:grid; grid-template-columns:minmax(0,1fr); gap:0; width:172px; padding:6px; text-align:left; border:1px solid var(--card-border); border-radius:22px; background:var(--card-bg); box-shadow:var(--card-shadow); color:var(--text); font:inherit; }
.ef-feature-art { grid-area:1 / 1; position:relative; display:block; height:164px; border-radius:16px; overflow:hidden; background:var(--ef-tone); }
.ef-feature-art .endfield-artwork { position:absolute; right:0; bottom:-10px; width:150px; height:190px; border-radius:0; background:transparent; }
.ef-feature-copy { display:contents; }
.ef-feature-copy strong { grid-area:2 / 1; min-width:0; overflow:hidden; padding:12px 8px 8px; font-size:14px; line-height:20px; font-weight:600; text-overflow:ellipsis; white-space:nowrap; }
.ef-feature-copy > span { grid-area:1 / 1; z-index:1; align-self:end; justify-self:start; margin:0 0 11px 11px; padding:3px 8px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--ef-ink); font-size:12px; line-height:16px; font-weight:500; font-variant-numeric:tabular-nums; white-space:nowrap; }
.ef-feature-copy small { margin-left:6px; font-size:12px; font-weight:400; color:var(--text-muted); }
@media (hover:hover) and (pointer:fine) { .ef-feature:hover:not(:disabled) { background:var(--panel-bg); border-color:var(--border-strong); } }
.ef-feature:active:not(:disabled) { transform:translateY(1px); }
.ef-filters { display:grid; grid-template-columns:minmax(150px,2fr) repeat(3,minmax(100px,1fr)); gap:12px; margin:0 0 16px; }
.ef-filters label { display:grid; gap:6px; font-size:12px; color:var(--text-muted); }
.ef-filters input { min-width:0; width:100%; min-height:38px; padding:7px 14px; background:var(--card-bg); color:var(--text); border:1px solid var(--border); border-radius:var(--radius-control); font-size:13px; }
.ef-filters :deep(.menu-select) { min-width:0; width:100%; }
.ef-filters :deep(.menu-select-trigger) { min-height:38px; }
.ef-filters input:focus-visible { border-color:var(--ef-ink); outline:0; box-shadow:var(--ring); }
.ef-roster { display:grid; grid-template-columns:repeat(auto-fill,minmax(208px,1fr)); gap:12px; }
/* Compact tile: bot images show the whole roster, so it stays short there. */
.ef-operator { position:relative; display:grid; gap:10px; align-content:start; min-width:0; padding:14px; border-radius:var(--radius-tile); background:var(--surface-soft); overflow:hidden; }
.ef-operator.top { background:var(--ef-tone); }
.ef-operator-top { display:grid; grid-template-columns:auto minmax(0,1fr); align-items:start; gap:12px; }
.ef-avatar { position:relative; justify-self:start; padding-bottom:9px; }
.ef-operator-top .endfield-artwork { width:60px; height:60px; border-radius:var(--radius-control); }
.ef-operator-copy { min-width:0; }
.ef-operator h3 { font-size:15px; line-height:22px; font-weight:600; letter-spacing:-.01em; overflow-wrap:anywhere; }
.ef-operator .ef-operator-level { margin-top:2px; font-size:14px; font-weight:600; font-variant-numeric:tabular-nums; }
.ef-operator-level span { margin-left:4px; color:var(--text-muted); font-size:12px; font-weight:400; }
.ef-tier { position:absolute; left:50%; bottom:0; transform:translateX(-50%); padding:0 9px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--text-body); font-size:12px; font-weight:500; line-height:20px; white-space:nowrap; box-shadow:inset 0 0 0 1px var(--border-strong),0 0 0 2px var(--surface-soft); }
.ef-operator.high .ef-tier { background:var(--ef-tone); color:var(--ef-ink); box-shadow:0 0 0 2px var(--surface-soft); }
.ef-operator.top .ef-tier { background:var(--ef-ink); color:var(--accent-ink); box-shadow:0 0 0 2px var(--ef-tone); }
.ef-phase { display:flex; align-items:center; gap:8px; font-size:13px; font-weight:500; }
.ef-phase-dot { flex:0 0 auto; width:10px; height:10px; border-radius:3px; background:var(--tone,var(--track)); }
.ef-profession { margin-top:-4px; }
.ef-operator .ui-button { justify-self:stretch; margin-top:2px; }
/* On the website each operator is the mockup role card: a white frame, the art on the game tone with the level as a white tag, then the text. */
.endfield-reports:not(.is-image) .ef-roster { grid-template-columns:repeat(auto-fill,minmax(196px,1fr)); gap:16px; }
.endfield-reports:not(.is-image) .ef-operator { grid-template-columns:minmax(0,1fr); gap:0; padding:6px; border:1px solid var(--card-border); border-radius:22px; background:var(--card-bg); box-shadow:var(--card-shadow); }
.endfield-reports:not(.is-image) .ef-operator-top, .endfield-reports:not(.is-image) .ef-operator-copy { display:contents; }
.endfield-reports:not(.is-image) .ef-avatar { grid-area:1 / 1; justify-self:stretch; height:136px; padding:0; border-radius:16px; background:var(--ef-tone); overflow:hidden; }
.endfield-reports:not(.is-image) .ef-operator-top .endfield-artwork { position:absolute; right:0; bottom:0; width:128px; height:128px; border-radius:0; background:transparent; }
.endfield-reports:not(.is-image) .ef-tier { left:11px; top:11px; bottom:auto; transform:none; padding:3px 7px; line-height:16px; background:var(--card-bg); color:var(--ef-ink); box-shadow:none; }
.endfield-reports:not(.is-image) .ef-operator.top .ef-tier { background:var(--ef-ink); color:var(--accent-ink); }
.endfield-reports:not(.is-image) .ef-operator .ef-operator-level { grid-area:1 / 1; z-index:1; align-self:end; justify-self:start; margin:0 0 11px 11px; padding:3px 8px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--ef-ink); font-size:12px; line-height:16px; font-weight:500; white-space:nowrap; }
.endfield-reports:not(.is-image) .ef-operator-level span { margin-left:6px; color:var(--text-muted); }
.endfield-reports:not(.is-image) .ef-operator h3 { grid-area:2 / 1; padding:12px 10px 0; font-size:14px; line-height:20px; }
.endfield-reports:not(.is-image) .ef-profession { grid-area:3 / 1; margin-top:0; padding:2px 10px 0; font-size:12px; line-height:18px; }
.endfield-reports:not(.is-image) .ef-phase { grid-area:4 / 1; padding:4px 10px 0; font-size:12px; line-height:18px; }
.endfield-reports:not(.is-image) .ef-operator .ui-button { grid-area:5 / 1; margin:12px 4px 4px; }
.ef-detail { scroll-margin-top:80px; }
.ef-detail:focus { outline:none; }
.ef-detail > header { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:14px; flex-wrap:wrap; }
.ef-detail h2 { font-size:20px; line-height:28px; font-weight:600; letter-spacing:-.02em; }
.ef-detail-toolbar { display:flex; justify-content:space-between; gap:10px; margin-bottom:8px; }
.ef-detail-time { font-size:12px; line-height:1.8; color:var(--text-muted); margin:-6px 0 18px; }

/* ── 地区建设 ── */
.ef-region { display:grid; gap:16px; }
.ef-region > header { margin-bottom:0; }
.ef-level { padding:0 12px; border-radius:var(--radius-chip); background:var(--ef-tone); color:var(--ef-ink); font-size:13px; font-weight:500; line-height:26px; font-variant-numeric:tabular-nums; }
.ef-region-top { display:grid; grid-template-columns:auto minmax(0,1fr); gap:12px; align-items:stretch; }
.ef-money { display:grid; justify-items:center; align-content:center; gap:10px; padding:16px 22px; border-radius:var(--radius-tile); background:var(--surface-soft); }
.ef-money .ef-ring-center strong { display:grid; justify-items:center; font-size:21px; line-height:24px; }
.ef-money .ef-ring-center small { font-size:12px; line-height:16px; }
.ef-bases { display:grid; gap:10px; align-content:start; min-width:0; padding:16px; border-radius:var(--radius-tile); background:var(--surface-soft); }
.ef-bases-head { display:flex; align-items:baseline; gap:10px; }
.ef-bases-head strong { font-size:26px; line-height:30px; font-weight:550; letter-spacing:-.03em; font-variant-numeric:tabular-nums; }
.ef-bases :deep(.h-rail) { --rail-gap:10px; --rail-pad-block:4px; --rail-pad:0px; }
.ef-settlement { display:grid; gap:6px; align-content:start; width:232px; padding:14px; border-radius:var(--radius-well); background:var(--card-bg); }
.ef-settlement h3 { font-size:14px; line-height:20px; font-weight:600; }
.ef-settlement h3 small { margin-left:6px; font-size:12px; font-weight:400; color:var(--text-muted); }
.ef-settlement p { font-size:13px; line-height:1.6; overflow-wrap:anywhere; }
.ef-settlement p strong { font-weight:500; font-variant-numeric:tabular-nums; }
.ef-bar { --series:var(--ef-vivid); }
.ef-assigned { display:flex; gap:6px; flex-wrap:wrap; }
.ef-assigned > .endfield-artwork { width:36px; height:36px; border-radius:var(--radius-control); }
.ef-areas { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(250px,100%),1fr)); gap:12px; }
.ef-subsection { padding:16px; border-radius:var(--radius-tile); background:var(--surface-soft); min-width:0; }
.ef-subsection h3 { font-size:14px; line-height:20px; font-weight:600; margin-bottom:8px; }
.ef-facts { font-size:13px; }
.ef-facts li { display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:2px 8px; padding:7px 0 9px; }
.ef-facts li > span { color:var(--text-muted); }
.ef-facts strong { font-weight:500; font-variant-numeric:tabular-nums; }
.ef-facts small { font-size:12px; color:var(--text-muted); }
.ef-facts progress { flex-basis:100%; width:100%; height:8px; appearance:none; border:0; border-radius:6px; overflow:hidden; background:var(--track); }
.ef-facts progress::-webkit-progress-bar { background:var(--track); border-radius:6px; }
.ef-facts progress::-webkit-progress-value { background:var(--ef-vivid); border-radius:6px; }
.ef-facts progress::-moz-progress-bar { background:var(--ef-vivid); border-radius:6px; }

/* ── 帝江号 ── */
.ef-ship-counts { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; margin:0 0 12px; }
.ef-ship-counts > div { padding:12px 16px; border-radius:var(--radius-well); background:var(--surface-soft); }
.ef-ship-counts dt { font-size:12px; color:var(--text-muted); line-height:1.7; }
.ef-ship-counts dd { font-size:30px; line-height:34px; font-weight:550; letter-spacing:-.04em; font-variant-numeric:tabular-nums; margin:2px 0 0; }
.ef-ship-time { font-size:12px; }
.ef-model-note { margin-top:8px; font-size:12px; line-height:1.8; color:var(--text-muted); }
.ef-model-note summary { cursor:pointer; padding:6px 0; }
.ef-model-note p { margin:7px 0; }
.ef-ship-rooms { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:16px; align-items:start; }
.ef-ship-room { display:grid; gap:10px; }
.ef-ship-room > header { margin-bottom:0; }
.ef-room-level { padding:0 12px; border-radius:var(--radius-chip); background:var(--ef-tone); color:var(--ef-ink); font-size:13px; font-weight:500; line-height:26px; font-variant-numeric:tabular-nums; }
.ef-room-level > span { position:absolute; width:1px; height:1px; overflow:hidden; clip-path:inset(50%); }

/* ── 光荣之路 ── */
.ef-honor-head { grid-column:span 8; }
.ef-honor-head.is-wide { grid-column:1 / -1; }
.ef-honor-head :deep(.summary-metrics) { margin:0 0 14px; }
.ef-categories { grid-column:span 4; }
.ef-categories :deep(.donut-chart) { gap:10px 18px; }
.ef-medal-filters { grid-template-columns:2fr 1fr 1fr; margin:0; }
.ef-recent { overflow:hidden; }
.ef-recent :deep(.h-rail) { --rail-gap:12px; --rail-pad-block:10px; --rail-pad:2px; }
.ef-recent-medal { display:grid; justify-items:start; gap:4px; width:132px; padding:12px; border-radius:var(--radius-tile); background:var(--surface-soft); }
.ef-recent-medal .endfield-artwork { width:64px; height:72px; margin-bottom:4px; background:transparent; }
.ef-recent-medal strong { max-width:100%; overflow:hidden; font-size:13px; line-height:20px; font-weight:600; text-overflow:ellipsis; white-space:nowrap; }
.ef-recent-medal span { font-size:12px; color:var(--text-muted); font-variant-numeric:tabular-nums; }
.ef-recent-medal.plated { background:var(--ef-tone); }
.ef-medals { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(300px,100%),1fr)); gap:16px; }
.ef-medal { display:flex; gap:16px; align-items:center; min-width:0; padding:16px 18px; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); box-shadow:var(--card-shadow); }
.ef-medal.plated { background:var(--ef-tone); border-color:transparent; }
.ef-medal > .endfield-artwork { width:78px; height:88px; border-radius:var(--radius-well); }
.ef-medal.plated > .endfield-artwork { background:var(--card-bg); }
.ef-medal > div { min-width:0; }
.ef-medal h3 { font-size:14px; line-height:1.6; font-weight:600; overflow-wrap:anywhere; }
.ef-medal p { margin-top:6px; font-size:13px; }
.ef-medal-category { display:inline-block; padding:0 8px; border-radius:var(--radius-chip); background:var(--control-track); color:var(--text-body); font-size:12px; margin-top:6px; line-height:20px; overflow-wrap:anywhere; }
.ef-medal.plated .ef-medal-category { background:var(--card-bg); }
.ef-medal-plated { margin-left:8px; font-weight:500; color:var(--text); }
.ef-medal.plated .ef-medal-plated { padding:0 8px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--ef-ink); }
.ef-empty .ui-button { margin-top:14px; }

/* A bot image is one still frame: flat fills, no shadows (they inflate the PNG). */
.is-image .ef-card, .is-image .ef-count, .is-image .ef-medal { box-shadow:none; border-color:var(--border); }
.is-image .ef-count { min-height:0; gap:14px; }
.is-image .ef-medal.plated { border-color:transparent; }

@media (max-width:900px) {
  .ef-hero, .ef-progress, .ef-stats, .ef-rarity, .ef-phases, .ef-honor-head, .ef-categories { grid-column:1 / -1; }
  .ef-count { grid-column:span 6; }
  .ef-todo { grid-column:1 / -1; }
  .ef-ship-rooms { grid-template-columns:1fr; }
  .ef-region-top { grid-template-columns:1fr; }
  .ef-money { grid-template-columns:auto 1fr; justify-items:start; gap:18px; }
}
@media (max-width:600px) {
  .ef-card { padding:16px; border-radius:22px; }
  .ef-hero-body { grid-template-columns:1fr; justify-items:stretch; }
  .ef-stamina { justify-items:start; grid-template-columns:auto 1fr; align-items:center; text-align:left; gap:16px; }
  .ef-count { grid-column:1 / -1; min-height:104px; border-radius:22px; }
  .ef-filters, .ef-medal-filters { grid-template-columns:1fr 1fr; }
  .ef-roster { grid-template-columns:repeat(auto-fill,minmax(160px,1fr)); }
  .ef-operator { padding:12px; }
  .ef-operator-top { grid-template-columns:1fr; gap:8px; }
  .endfield-reports:not(.is-image) .ef-roster { grid-template-columns:repeat(auto-fill,minmax(148px,1fr)); gap:12px; }
  .endfield-reports:not(.is-image) .ef-operator { padding:6px; }
  .endfield-reports:not(.is-image) .ef-avatar { height:124px; }
  .endfield-reports:not(.is-image) .ef-operator-top .endfield-artwork { width:118px; height:118px; }
  .ef-medal { gap:12px; padding:14px; border-radius:22px; }
  .ef-medal > .endfield-artwork { width:60px; height:70px; }
}
@media (max-width:420px) {
  .ef-filters, .ef-medal-filters { grid-template-columns:1fr; }
}
</style>
