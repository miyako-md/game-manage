<script setup>
import { nteItemLabel } from '../nte-display.js'
import { computed, reactive, ref, watch } from 'vue'
import { nteGuidePoints, nteModuleTitles } from '../nte-modules.js'
import { areaViews, catalogRole, gachaView, gauge, GLYPHS, houseView, officialPullIcon, progressView, roleBreakdown, rosterOrder, vehicleView } from '../nte-charts.js'
import { displayBeijing, monthDay } from '../time.js'
import { safeUrl } from '../calendar.js'
import { nteRoleIcon } from '../nte-icons.js'
import { friendlyDataError } from '../cloud-display.js'
import { vPop, vReveal } from '../motion.js'
import AppIcon from './AppIcon.vue'
import BarChart from './BarChart.vue'
import DonutChart from './DonutChart.vue'
import HRail from './HRail.vue'
import NteDetailDialog from './NteDetailDialog.vue'
import NteIcon from './NteIcon.vue'
import RingGauge from './RingGauge.vue'
import ArtworkImage from './ArtworkImage.vue'
import GameIcon from './GameIcon.vue'
const props=defineProps({capability:{type:String,required:true},snap:{default:null},accountId:{type:String,default:''},artwork:{type:Array,default:()=>[]}})
const opened=ref(false),title=computed(()=>nteModuleTitles[props.capability]||props.capability)
const inline=computed(()=>['stamina','record'].includes(props.capability))
// Cloud reads put a failure on the snapshot itself; local snapshots carry it in poll_status.
const error=computed(()=>props.snap?.error||props.snap?.poll_status?.error)
const readAt=computed(()=>props.capability==='stamina' ? props.snap?.payload?.updated_at || props.snap?.fetched_at : props.snap?.fetched_at)
watch(()=>props.accountId,()=>{opened.value=false})
watch(()=>props.capability,()=>{opened.value=false})

// Every picture is optional: one that fails to load drops out and its tile shows the letter instead.
const failed=reactive(new Set())
const usable=url=>{const safe=safeUrl(url);return safe && !failed.has(safe) ? safe : ''}
const broken=url=>{const safe=safeUrl(url);if(safe)failed.add(safe)}

const payload=computed(()=>props.snap?.payload?.schema_version===1 ? props.snap.payload : null)
const p=computed(()=>payload.value || {})
const show=value=>value===null || value===undefined || value==='' || (typeof value==='number' && !Number.isFinite(value)) ? '未知' : value
const percent=g=>g.known ? `${Math.round(g.pct)}%` : '—'
// A ring only draws from counts it knows; RingGauge takes numbers, the source may send numeric text.
const ring=g=>({value:g.known ? Number(g.current) : null,max:g.known ? Number(g.total) : null})


const account=computed(()=>({
  name:show(p.value.nickname),
  stats:[{label:'等级',value:show(p.value.level)},{label:'世界等级',value:show(p.value.world_level)},{label:'大亨等级',value:show(p.value.tycoon_level)},{label:'活跃天数',value:show(p.value.active_days),unit:'天'}],
  rings:[['成就',p.value.achievement_count,p.value.achievement_total,'var(--game-vivid)'],['房产',p.value.house_count,p.value.house_total,'var(--game-vivid)'],['载具',p.value.vehicle_count,p.value.vehicle_total,'var(--game-vivid)']]
    .map(([label,current,total,color])=>({label,color,...gauge(current,total)})),
}))
const stamina=computed(()=>[['本性像素',p.value.current,p.value.maximum,'var(--game-vivid)'],['都市活力',p.value.city_current,p.value.city_maximum,'var(--game-vivid)'],['日常活跃',p.value.daily_activity,100,'var(--game-vivid)']]
  .map(([label,current,total,color])=>({label,color,...gauge(current,total)})))
const progress=computed(()=>progressView(p.value))
const MEDAL={gold:'var(--chart-4)',silver:'color-mix(in srgb,var(--text-faint) 62%,var(--card-bg))',bronze:'var(--chart-2)'}
const medalBar=computed(()=>{const tiers=progress.value.medals,sum=tiers.reduce((total,tier)=>total+(tier.value||0),0);return sum>0 ? tiers.filter(tier=>tier.value>0).map(tier=>({...tier,share:tier.value/sum*100})) : []})

const QUALITY={S:'var(--chart-1)',A:'var(--chart-2)',B:'var(--chart-3)',C:'var(--chart-4)'}
const qualityColor=value=>QUALITY[value] || 'var(--chart-5)'
const breakdown=computed(()=>roleBreakdown(p.value.entries))
const roster=computed(()=>rosterOrder(p.value.entries).map(role=>({role,src:usable(role.icon_url)})))
const qualitySegments=computed(()=>breakdown.value.quality.map(row=>({...row,color:qualityColor(row.label)})))
const elementBars=computed(()=>breakdown.value.element.map(row=>({label:row.label,value:row.value})))

const areas=computed(()=>areaViews(p.value.areas))

const owned=computed(()=>gauge(p.value.owned_count,p.value.total))
const entries=computed(()=>(Array.isArray(p.value.entries) ? p.value.entries : []).filter(entry=>entry && typeof entry==='object'))
const houses=computed(()=>props.capability==='realestate' ? entries.value.map(houseView) : [])
const vehicles=computed(()=>props.capability==='vehicles' ? entries.value.map(entry=>vehicleView(entry,p.value.show_id)) : [])
const OWNERSHIP={true:'已拥有',false:'未拥有',null:'状态未知'}
// Residents are listed by id; only ones the public catalog names get an avatar.
const residents=ids=>ids.map(catalogRole).filter(Boolean)
const teams=computed(()=>props.capability==='teams' ? entries.value.map((entry,index)=>{
  const images=(Array.isArray(entry.image_urls) ? entry.image_urls : []).map(safeUrl).filter(Boolean)
  return {key:entry.id ?? index,name:entry.name || '未命名配队',description:entry.description || '',icon:usable(entry.icon_url),images,cover:images.find(url=>!failed.has(url)) || ''}
}) : [])

const gacha=computed(()=>gachaView(p.value))
const TONE={short:'var(--chart-3)',medium:'var(--chart-4)',long:'var(--chart-8)',unknown:'var(--text-faint)'}
const luckSegments=computed(()=>[['short','欧 / 超欧'],['medium','普通 / 非'],['long','超非'],['unknown','未标注']].map(([tone,label])=>({label,value:gacha.value.tones[tone],color:TONE[tone]})).filter(row=>row.value>0))
const poolBars=computed(()=>gacha.value.pools.map(pool=>({label:pool.name,value:pool.draws})))
const pulls=computed(()=>gacha.value.recent.map(item=>({...item,
  src:(()=>{const url=safeUrl(officialPullIcon(item.entry.item_id));return url && !failed.has(url) ? url : ''})(),
  label:nteItemLabel(item.entry.item_id,item.entry.name),day:item.time==null ? '' : monthDay(item.time)})))
</script>
<template>
  <section v-reveal class="cap-card nte-module-card" :class="`module-${capability}`">
    <header class="mod-head"><h2>{{ title }}</h2><button v-if="!inline" type="button" class="ui-button soft small-button mod-open" @click="opened = true">查看{{ title }}<AppIcon name="arrow" :size="14" /></button></header>

    <div v-if="capability === 'record'" class="inline-content"><slot /></div>

    <div v-else-if="capability === 'guides'" class="guides-body">
      <ul class="guide-points">
        <li v-for="metric in nteGuidePoints" :key="metric.label"><span>{{ metric.label }}</span><strong>{{ metric.value }}</strong></li>
        <li class="guide-kinds"><span class="chip-list"><span v-for="kind in ['弧盘', '配队', '套装', '属性', '技能']" :key="kind" class="chip">{{ kind }}</span></span></li>
      </ul>
      <p>完整角色攻略目录已并入角色练度，可搜索并查看原图与摘要。</p>
    </div>

    <p v-else-if="!payload && snap?.reading" class="module-state" role="status">正在读取{{ title }}…</p>
    <p v-else-if="!payload && snap?.readError" class="module-state" role="status">{{ snap.readError }}</p>
    <p v-else-if="!payload" class="module-state">{{ snap?.payload && snap.payload.schema_version !== 1 ? '数据格式已更新，请刷新' : '暂无数据，请刷新后查看' }}</p>

    <div v-else-if="capability === 'account'" class="account-body">
      <div class="account-top">
        <ArtworkImage class="account-backdrop" :candidates="artwork" decorative />
        <div class="account-id"><GameIcon class="account-avatar" game-id="nte" name="异环" /><div class="account-name"><strong>{{ account.name }}</strong><span v-if="p.server_name" class="chip">{{ p.server_name }}</span></div></div>
        <dl class="account-stats"><div v-for="stat in account.stats" :key="stat.label"><dt>{{ stat.label }}</dt><dd>{{ stat.value }}<small v-if="stat.unit && stat.value !== '未知'">{{ stat.unit }}</small></dd></div></dl>
      </div>
      <ul class="own-rings">
        <li v-for="item in account.rings" :key="item.label" class="own-ring">
          <RingGauge v-bind="ring(item)" :label="item.label" :size="64" :stroke="7" :color="item.color"><b class="ring-pct">{{ percent(item) }}</b></RingGauge>
          <span class="own-copy"><span class="kicker">{{ item.label }}</span><strong class="mid">{{ show(item.current) }}<small>/ {{ show(item.total) }}</small></strong></span>
        </li>
        <li class="own-ring plain"><span class="own-copy"><span class="kicker">角色数</span><strong class="mid">{{ show(p.character_count) }}</strong></span></li>
      </ul>
    </div>

    <div v-else-if="capability === 'stamina'" class="stamina-body">
      <div v-for="row in stamina" :key="row.label" class="ring-tile">
        <span class="kicker">{{ row.label }}</span>
        <progress v-if="row.known" class="sr-only" :value="row.current" :max="row.total" :aria-label="row.label" />
        <span aria-hidden="true"><RingGauge v-bind="ring(row)" :label="row.label" :size="88" :stroke="9" :color="row.color"><b class="ring-pct">{{ percent(row) }}</b></RingGauge></span>
        <span v-pop class="ring-value">{{ show(row.current) }} <small>/ {{ show(row.total) }}</small></span>
      </div>
    </div>

    <div v-else-if="capability === 'progress'" class="progress-body">
      <div class="progress-hero">
        <progress v-if="progress.ring.known" class="sr-only" :value="progress.ring.current" :max="progress.ring.total" aria-label="成就总进度" />
        <span aria-hidden="true"><RingGauge v-bind="ring(progress.ring)" label="成就总进度" :size="108" :stroke="11" color="var(--game-vivid)"><b class="ring-pct large">{{ percent(progress.ring) }}</b></RingGauge></span>
        <div class="hero-copy">
          <span class="kicker">成就</span>
          <strong class="big">{{ show(p.completed) }}<small>/ {{ show(p.total) }}</small></strong>
          <div v-if="medalBar.length" class="stack-bar" aria-hidden="true"><i v-for="tier in medalBar" :key="tier.key" :style="{ '--series': MEDAL[tier.key], width: `${tier.share}%` }" /></div>
          <ul class="legend medals"><li v-for="tier in progress.medals" :key="tier.key" :style="{ '--series': MEDAL[tier.key] }">{{ tier.label }}奖章 <b>{{ show(tier.value) }}</b></li></ul>
        </div>
      </div>
      <ul v-if="progress.categories.length" class="bar-list categories">
        <li v-for="item in progress.categories" :key="item.key" class="bar-row" :title="item.name">
          <span class="k">{{ show(item.name) }}</span>
          <span class="meter" aria-hidden="true"><i :style="{ '--pct': `${item.pct ?? 0}%` }" /></span>
          <span class="v">{{ show(item.current) }} <small>/ {{ show(item.total) }}</small></span>
        </li>
      </ul>
    </div>

    <div v-else-if="capability === 'roles'" class="roles-body">
      <div class="roles-summary">
        <div class="sum-panel"><DonutChart :segments="qualitySegments" label="角色品质分布" unit=" 名" :size="104" :stroke="14"><b class="donut-total">{{ breakdown.total }}</b><small>角色</small></DonutChart></div>
        <div v-if="elementBars.length" class="sum-panel"><span class="kicker">各元素角色数</span><BarChart :items="elementBars" label="各元素角色数" unit=" 名" :height="64" /></div>
        <dl v-if="breakdown.averageLevel != null" class="sum-panel sum-levels"><div><dt>平均等级</dt><dd>{{ breakdown.averageLevel }}</dd></div><div><dt>最高等级</dt><dd>{{ breakdown.maxLevel }}</dd></div></dl>
      </div>
      <HRail label="角色列表" class="rail roles-rail">
        <figure v-for="({ role, src }, index) in roster" :key="role.id ?? index" class="role-tile">
          <img v-if="src" class="role-avatar" :src="src" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken(src)" />
          <NteIcon v-else :src="nteRoleIcon(role.id) || nteRoleIcon(role.name)" :name="role.name || '角色'" size="xl" />
          <figcaption><strong :title="role.name">{{ role.name || '未命名' }}</strong><span class="meta"><i v-if="role.quality" class="rank" :class="`rank-${role.quality}`">{{ role.quality }}</i><span v-if="role.level != null">Lv{{ role.level }}</span></span></figcaption>
        </figure>
      </HRail>
    </div>

    <div v-else-if="capability === 'exploration'" class="explore-body">
      <p v-if="!areas.length" class="module-state">暂无探索数据</p>
      <ul v-else class="area-grid">
        <li v-for="area in areas" :key="area.key" class="area-tile">
          <RingGauge v-bind="ring(area)" :label="area.name || '区域探索'" :size="68" :stroke="8" color="var(--game-vivid)"><b class="ring-pct">{{ percent(area) }}</b></RingGauge>
          <span class="own-copy"><strong class="area-name" :title="area.name">{{ show(area.name) }}</strong><span class="mid">{{ show(area.current) }}<small>/ {{ show(area.total) }}</small></span><em v-if="area.over" class="target-met">已达目标</em></span>
          <ul v-if="area.details.length" class="bar-list area-details">
            <li v-for="item in area.details" :key="item.key" class="bar-row" :title="item.name"><span class="k">{{ show(item.name) }}</span><span class="meter" aria-hidden="true"><i :style="{ '--pct': `${item.pct ?? 0}%` }" /></span><span class="v">{{ show(item.current) }}<small>/{{ show(item.total) }}</small></span></li>
          </ul>
        </li>
      </ul>
    </div>

    <div v-else-if="capability === 'realestate' || capability === 'vehicles'" class="assets-body">
      <div class="own-head">
        <RingGauge v-bind="ring(owned)" label="拥有" :size="64" :stroke="7" color="var(--game-vivid)"><b class="ring-pct">{{ percent(owned) }}</b></RingGauge>
        <span class="own-copy"><span class="kicker">拥有</span><strong class="big">{{ show(p.owned_count) }}<small>/ {{ show(p.total) }}</small></strong></span>
        <span v-if="capability === 'vehicles' && (p.show_name || p.show_id)" class="chip game">展示载具：{{ p.show_name || p.show_id }}</span>
      </div>
      <p v-if="!entries.length" class="module-state">{{ capability === 'vehicles' ? '暂无载具明细' : '暂无资产明细' }}</p>
      <HRail v-else :label="capability === 'vehicles' ? '载具列表' : '房产列表'" class="rail assets-rail">
        <article v-for="(house, index) in houses" :key="`h${index}`" class="asset-card" :class="{ off: house.owned !== true }">
          <div class="asset-cover"><img v-if="usable(house.image)" :src="usable(house.image)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken(house.image)" /><svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="GLYPHS.house" /></svg><span class="asset-badge">{{ OWNERSHIP[house.owned] }}</span></div>
          <strong class="asset-name" :title="house.name">{{ house.name || '未命名房产' }}</strong>
          <div class="asset-meta">
            <span v-if="residents(house.residents).length" class="stack"><NteIcon v-for="resident in residents(house.residents).slice(0, 3)" :key="resident.name" :src="resident.icon" :name="resident.name" size="small" /></span>
            <span v-else-if="house.residents.length" class="muted">入住 {{ house.residents.length }}</span>
            <span v-else class="muted">暂无入住</span>
            <span v-if="house.furnitureTotal" class="muted"><b>{{ house.furnitureOwned }}</b>/{{ house.furnitureTotal }} 件家具</span>
          </div>
        </article>
        <article v-for="(car, index) in vehicles" :key="`v${index}`" class="asset-card" :class="{ off: car.owned !== true, showcase: car.showcase }">
          <div class="asset-cover"><img v-if="usable(car.image)" :src="usable(car.image)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken(car.image)" /><svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="GLYPHS.car" /></svg><span class="asset-badge">{{ car.showcase ? '展示中' : OWNERSHIP[car.owned] }}</span></div>
          <strong class="asset-name" :title="car.name">{{ car.name || '未命名载具' }}</strong>
          <dl v-if="car.base.length" class="car-stats"><div v-for="stat in car.base.slice(0, 3)" :key="stat.name"><dt>{{ stat.name }}</dt><dd>{{ stat.value }}</dd></div></dl>
        </article>
      </HRail>
    </div>

    <div v-else-if="capability === 'teams'" class="teams-body">
      <p v-if="!teams.length" class="module-state">暂无官方配队推荐</p>
      <span v-else class="kicker">官方推荐 <b class="count">{{ teams.length }}</b></span>
      <HRail v-if="teams.length" label="官方配队推荐" class="rail teams-rail">
        <article v-for="team in teams" :key="team.key" class="team-card">
          <div class="team-pic">
            <img v-if="team.cover" :src="team.cover" :alt="`${team.name}配队图`" loading="lazy" referrerpolicy="no-referrer" @error="broken(team.cover)" />
            <span v-else class="team-fallback" aria-hidden="true">{{ String(team.name).slice(0, 1) }}</span>
            <span class="glass team-badge"><img v-if="team.icon" class="team-icon" :src="team.icon" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken(team.icon)" /><b>{{ team.name }}</b></span>
            <span v-if="team.images.length > 1" class="glass team-count">{{ team.images.length }} 张图</span>
          </div>
          <p v-if="team.description" class="team-desc">{{ team.description }}</p>
        </article>
      </HRail>
    </div>

    <div v-else-if="capability === 'gacha'" class="gacha-body">
      <div class="gacha-hero" :data-tone="gacha.titleTone">
        <span class="kicker">近期评价</span>
        <strong class="luck">{{ gacha.title || '暂无评价' }}</strong>
        <dl class="luck-nums"><div><dt>统计抽数</dt><dd>{{ show(gacha.totalDraws) }}</dd></div><div><dt>出 S 数</dt><dd>{{ show(gacha.totalS) }}</dd></div></dl>
      </div>
      <p v-if="!gacha.pools.length" class="module-state gacha-empty">暂无卡池统计</p>
      <template v-else>
        <div class="gacha-pools"><span class="kicker">各卡池统计抽数</span><BarChart :items="poolBars" label="各卡池统计抽数" unit=" 抽" :height="96" /></div>
        <div v-if="luckSegments.length" class="gacha-luck"><span class="kicker">出 S 评价分布</span><DonutChart :segments="luckSegments" label="出 S 评价分布" unit=" 次" :size="96" :stroke="14"><b class="donut-total">{{ gacha.pulls }}</b><small>次出 S</small></DonutChart></div>
        <ul v-if="gacha.pools.some(pool => pool.reach)" class="gacha-reach">
          <li v-for="pool in gacha.pools.filter(item => item.reach)" :key="pool.key" class="own-ring">
            <RingGauge v-bind="ring(pool.reach)" :label="`${pool.name}出 S 平均抽数`" :size="64" :stroke="7" color="var(--game-vivid)"><b class="ring-pct">{{ percent(pool.reach) }}</b></RingGauge>
            <span class="own-copy"><span class="kicker">{{ pool.name }}</span><strong class="mid">{{ pool.average }}<small>/ 保底 {{ pool.guarantee }} 抽</small></strong></span>
          </li>
        </ul>
        <div v-if="pulls.length" class="gacha-recent">
          <span class="kicker">最近出 S</span>
          <HRail label="最近出 S" class="rail pull-rail">
            <article v-for="(item, index) in pulls" :key="item.key" class="pull-card" :class="{ newest: index === 0 }" :data-tone="item.tone">
              <div class="pull-pic">
                <img v-if="item.src" :src="item.src" alt="" loading="lazy" referrerpolicy="no-referrer" @error="broken(item.src)" />
                <span v-else class="pull-letter" aria-hidden="true">{{ item.label.slice(0, 1) }}</span>
                <span v-if="item.rating" class="pull-rating">{{ item.rating }}</span>
              </div>
              <strong class="pull-name" :title="item.label">{{ item.label }}</strong>
              <span class="pull-meta"><template v-if="item.entry.pity != null"><b>{{ item.entry.pity }}</b> 抽 · </template>{{ item.pool }}</span>
              <time v-if="item.day" class="pull-day">{{ item.day }}</time>
            </article>
          </HRail>
        </div>
      </template>
    </div>

    <p v-if="capability === 'stamina'" class="module-state weekly"><AppIcon name="clock" :size="14" />周本剩余 · {{ snap?.payload?.schema_version === 1 ? snap.payload.weekly_remaining ?? '未提供' : '未提供' }}</p>
    <p v-if="error || snap?.state === 'auth_expired'" class="module-error" role="status">{{ friendlyDataError(error,snap?.state) }}</p>
    <footer><span v-if="snap?.stale" class="old">旧数据</span><span v-if="readAt">{{ displayBeijing(readAt) }}</span><span v-else-if="capability === 'guides' || capability === 'teams'">公开资料</span></footer>
    <NteDetailDialog v-if="!inline && opened" :title="title" @close="opened = false"><slot /></NteDetailDialog>
  </section>
</template>
<style scoped>
/* The card is the shared .cap-card (white, hairline). Cards in a row stretch to one
   height and keep their footer at the bottom. Colour comes only from the game's tone:
   a feature block is filled with it, its labels take the ink, and everything else is a
   soft tile with a hairline. */
.nte-module-card{display:flex;flex-direction:column;gap:16px;align-self:stretch;grid-column:1/-1}
/* Stamina and progress share a row; alone each takes the full width. */
.nte-module-card.module-stamina,.nte-module-card.module-progress{grid-column:auto}
.nte-module-card.module-stamina:not(:has(+ .module-progress)),.nte-module-card.module-progress:not(.module-stamina + .module-progress){grid-column:1/-1}
.module-record{flex-direction:row;flex-wrap:wrap;align-items:center;gap:12px 32px}
.module-record>.mod-head{min-width:96px}
.module-record>.inline-content{flex:1 1 360px;min-width:0}
.nte-module-card.module-record footer{margin:0 0 0 auto}
.mod-head{display:flex;align-items:center;gap:12px;min-height:34px}
.mod-head h2{font-size:16px;line-height:24px;font-weight:600;letter-spacing:-.02em;color:var(--text)}
.mod-open{margin-left:auto}
.inline-content :deep(.cap-card){margin:0;padding:0;border:0;border-radius:0;background:none;box-shadow:none}
.inline-content :deep(.cap-title),.inline-content :deep(.fetched-at){display:none}
.module-state{color:var(--text-muted);font-size:13px;line-height:1.7}
.module-state.weekly{display:inline-flex;align-items:center;gap:6px;align-self:flex-start;padding:2px 12px 2px 10px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-body);font-size:12px;font-weight:500;line-height:22px}
.module-error{color:var(--danger);font-size:13px;line-height:1.7}
.nte-module-card footer{display:flex;gap:10px;margin-top:auto;min-height:12px;color:var(--text-faint);font-size:12px}
.old{color:var(--stale-text)}
.kicker{color:var(--text-muted);font-size:12px;line-height:18px;font-weight:500}
.kicker .count{margin-left:2px;color:var(--text);font-size:13px;font-weight:600}
/* Big numerals carry a small unit at about half their size. */
.big,.mid{font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums;white-space:nowrap}
.big{font-size:32px;line-height:38px}
.mid{font-size:20px;line-height:26px;letter-spacing:-.03em}
.big small,.mid small,.ring-value small{margin-left:4px;color:var(--text-muted);font-size:13px;font-weight:400;letter-spacing:0}
.ring-pct{color:var(--text);font-size:14px;font-weight:600;letter-spacing:-.01em}
.ring-pct.large{font-size:20px;letter-spacing:-.02em}
.own-copy{display:grid;gap:1px;min-width:0}
.rail{--rail-gap:12px;--rail-pad:2px;--rail-pad-block:10px}
.teams-rail{--rail-gap:16px}

/* Account: the name and four numerals on the tone, then what is owned as rings. */
.account-body{display:grid;gap:12px}
.account-top{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px 32px;padding:18px 20px;border-radius:var(--radius-tile);background:var(--game-tone)}
.account-top{position:relative;isolation:isolate;overflow:hidden}
.account-backdrop{position:absolute;inset:0;width:100%;height:100%;z-index:-2;object-position:75% center}
.account-top:has(.account-backdrop)::after{content:'';position:absolute;inset:0;z-index:-1;background:linear-gradient(90deg,var(--game-tone),color-mix(in srgb,var(--game-tone) 94%,transparent) 48%,color-mix(in srgb,var(--game-tone) 64%,transparent))}
.account-id{display:flex;align-items:center;gap:16px;min-width:0}
.account-avatar{display:grid;place-items:center;flex-shrink:0;width:60px;height:60px;border-radius:20px;background:var(--card-bg);color:var(--game-accent);font-size:26px;font-weight:600}
.account-name{display:grid;justify-items:start;gap:6px;min-width:0}
.account-name strong{color:var(--text);font-size:24px;line-height:30px;font-weight:600;letter-spacing:-.03em;overflow-wrap:anywhere}
.account-name .chip{background:var(--card-bg);color:var(--game-accent)}
.account-stats{display:flex;flex-wrap:wrap;gap:12px 36px;margin:0}
.account-stats>div{display:grid;align-content:start;gap:2px}
.account-stats dt{color:var(--game-accent);font-size:12px;line-height:18px}
.account-stats dd{margin:0;color:var(--text);font-size:30px;line-height:36px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums;white-space:nowrap}
.account-stats dd small{margin-left:3px;color:var(--game-accent);font-size:14px;font-weight:400;line-height:1;letter-spacing:0}
.own-rings{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:0;padding:0;list-style:none}
.own-ring{display:flex;align-items:center;gap:14px;min-width:0;padding:14px 16px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.own-ring.plain{justify-content:flex-start;padding-left:20px}

/* Stamina: three rings, one per resource. */
.stamina-body{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;flex:1}
.ring-tile{position:relative;display:grid;justify-items:center;align-content:center;gap:10px;min-width:0;padding:16px 8px 14px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.ring-value{color:var(--text);font-size:19px;line-height:24px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums;white-space:nowrap}
.ring-value small{font-size:12px}

/* Achievements: the ring and its medals, then one thin bar per category. */
.progress-body{display:grid;gap:18px}
.progress-hero{position:relative;display:flex;align-items:center;gap:20px;min-width:0}
.hero-copy{display:grid;gap:6px;min-width:0;flex:1}
.hero-copy .stack-bar{height:8px;margin-top:2px}
.legend.medals{margin:2px 0 0}
.categories{--bar-label:26%;gap:4px;margin:0;padding:0}

/* Roles: counts and levels in a row of soft tiles, every role as a small portrait card below. */
.roles-body{display:grid;gap:16px;min-width:0}
.roles-summary{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,1.2fr) minmax(0,.7fr);gap:12px}
.sum-panel{display:grid;align-content:center;gap:6px;min-width:0;padding:16px 18px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.sum-levels{grid-auto-flow:column;grid-auto-columns:1fr;align-content:center;gap:12px;margin:0}
.sum-levels dt{color:var(--text-muted);font-size:12px;line-height:18px}
.sum-levels dd{margin:0;font-size:32px;line-height:38px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.donut-total{font-size:24px;line-height:26px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.donut-total + small{color:var(--text-muted);font-size:12px}
/* The portrait sits on the tone, bottom right, the way the role cards do; the name and a muted line follow. */
.role-tile{display:grid;align-content:start;gap:8px;width:100px;margin:0;text-align:left}
.role-avatar{display:block;width:100px;height:100px;border-radius:14px;background:var(--game-tone);object-fit:contain;object-position:right bottom}
.role-tile .nte-icon[data-size]{--size:100px;border-radius:14px}
.role-tile figcaption{display:grid;justify-items:start;gap:3px;max-width:100%;padding:0 2px}
.role-tile strong{max-width:100%;overflow:hidden;color:var(--text);font-size:13px;line-height:18px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.meta{display:inline-flex;align-items:center;gap:6px;color:var(--text-muted);font-size:12px;font-variant-numeric:tabular-nums}
.rank{padding:0 6px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-body);font-size:12px;font-style:normal;font-weight:600;line-height:18px}
.rank-S{background:var(--game-tone);color:var(--game-accent)}

/* Exploration: one tile per area, its detail lines as thin bars. */
.area-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:12px;margin:0;padding:0;list-style:none}
.area-tile{display:grid;grid-template-columns:auto minmax(0,1fr);align-items:center;gap:8px 14px;align-content:start;min-width:0;padding:16px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.area-name{overflow:hidden;color:var(--text);font-size:14px;line-height:20px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.target-met{justify-self:start;margin-top:2px;padding:0 8px;border-radius:var(--radius-chip);background:var(--success-bg);color:var(--success);font-size:12px;font-style:normal;font-weight:500;line-height:18px}
.area-details{--bar-label:34%;grid-column:1/-1;gap:0;margin-top:6px;padding-top:8px;border-top:1px solid var(--border)}
.area-details .bar-row{min-height:24px;font-size:12px}
.area-details .v small{margin-left:1px}

/* Houses and vehicles: a tone cover per card in a rail; one not owned steps back to a soft tile. */
.assets-body{display:grid;gap:16px;min-width:0}
.own-head{display:flex;align-items:center;gap:16px;flex-wrap:wrap}
.asset-card{display:grid;align-content:start;gap:8px;width:172px}
.asset-cover{position:relative;display:grid;place-items:center;height:100px;overflow:hidden;border-radius:var(--radius-tile);background:var(--game-tone);color:var(--game-accent)}
.asset-cover>img{width:100%;height:100%;object-fit:contain}
.asset-cover svg{width:48px;height:48px}
.asset-card.off .asset-cover{background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2);color:var(--text-faint)}
.asset-card.showcase .asset-cover{box-shadow:inset 0 0 0 2px var(--game-vivid)}
.asset-badge{position:absolute;left:8px;top:8px;padding:1px 8px;border-radius:var(--radius-chip);background:var(--card-bg);color:var(--game-accent);font-size:12px;font-weight:500;line-height:20px}
.asset-card.off .asset-badge{color:var(--text-muted)}
.asset-card.showcase .asset-badge{background:var(--accent-fill);color:var(--accent-ink)}
.asset-name{overflow:hidden;color:var(--text);font-size:14px;line-height:20px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.asset-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;min-height:28px;font-size:12px}
.asset-meta .muted{color:var(--text-muted)}
.asset-meta b{color:var(--text);font-weight:600}
.stack{display:inline-flex}
.stack>*{box-shadow:0 0 0 2px var(--card-bg)}
.stack>*+*{margin-left:-8px}
.car-stats{display:grid;gap:2px;margin:0;font-size:12px}
.car-stats>div{display:flex;justify-content:space-between;gap:8px}
.car-stats dt{color:var(--text-muted)}
.car-stats dd{margin:0;color:var(--text);font-weight:500;font-variant-numeric:tabular-nums;white-space:nowrap}

/* Official teams: the picture leads, with frosted badges over it. */
.team-card{display:grid;align-content:start;gap:12px;width:clamp(260px,calc((100% - 32px) / 3),420px)}
.team-pic{position:relative;aspect-ratio:16/9;overflow:hidden;border-radius:var(--radius-tile);background:var(--game-tone)}
.team-pic>img{display:block;width:100%;height:100%;object-fit:cover}
.team-fallback{display:grid;place-items:center;height:100%;color:var(--game-accent);font-size:48px;font-weight:600}
.team-badge{position:absolute;left:10px;bottom:10px;display:inline-flex;align-items:center;gap:8px;max-width:calc(100% - 20px);padding:4px 14px 4px 4px;border-radius:var(--radius-chip);color:var(--text);font-size:13px;line-height:22px}
.team-badge:not(:has(img)){padding-left:14px}
.team-badge b{overflow:hidden;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.team-icon{width:26px;height:26px;border-radius:30%;object-fit:cover}
.team-count{position:absolute;right:10px;top:10px;padding:1px 10px;border-radius:var(--radius-chip);color:var(--text);font-size:12px;font-weight:500;line-height:20px}
.team-desc{display:-webkit-box;overflow:hidden;color:var(--text-body);font-size:13px;line-height:1.65;-webkit-line-clamp:2;-webkit-box-orient:vertical}

/* Gacha: the rating on the tone, then pools as bars, the luck split, and the newest S pulls. */
.gacha-body{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:16px}
.gacha-body>*{min-width:0}
.gacha-hero{grid-column:span 4;display:grid;align-content:space-between;gap:10px;padding:18px 20px;border-radius:var(--radius-tile);background:var(--game-tone)}
.gacha-hero .kicker,.luck-nums dt{color:var(--game-accent)}
.luck{color:var(--text);font-size:30px;line-height:36px;font-weight:600;letter-spacing:-.03em;overflow-wrap:anywhere}
.luck-nums{display:flex;gap:28px;margin:0}
.luck-nums dt{font-size:12px;line-height:18px}
.luck-nums dd{margin:0;color:var(--text);font-size:24px;line-height:30px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.gacha-pools{grid-column:span 5;display:grid;align-content:start;gap:2px;padding:16px 18px 12px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.gacha-luck{grid-column:span 3;display:grid;align-content:start;gap:10px;padding:16px 18px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.gacha-empty{grid-column:span 8;align-self:center}
.gacha-reach{grid-column:1/-1;display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,240px),1fr));gap:12px;margin:0;padding:0;list-style:none}
.gacha-reach .mid small{font-size:12px}
.gacha-recent{grid-column:1/-1;display:grid;gap:4px}
.pull-card{position:relative;display:grid;align-content:start;gap:4px;width:136px;padding:8px 8px 12px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.pull-pic{position:relative;display:grid;place-items:center;aspect-ratio:3/4;overflow:hidden;border-radius:calc(var(--radius-tile) - 6px);background:var(--game-tone)}
.pull-pic>img{width:100%;height:100%;object-fit:cover;object-position:top}
.pull-letter{color:var(--game-accent);font-size:40px;font-weight:600}
.pull-rating{position:absolute;left:6px;top:6px;padding:0 8px;border-radius:var(--radius-chip);background:var(--card-bg);color:var(--text);font-size:12px;font-weight:500;line-height:20px}
.pull-name{overflow:hidden;margin-top:4px;color:var(--text);font-size:13px;line-height:18px;font-weight:600;text-overflow:ellipsis;white-space:nowrap}
.pull-meta{overflow:hidden;color:var(--text-muted);font-size:12px;line-height:18px;text-overflow:ellipsis;white-space:nowrap}
.pull-meta b{color:var(--text);font-weight:600}
.pull-day{color:var(--text-faint);font-size:12px;line-height:16px;font-variant-numeric:tabular-nums}
/* Only the newest pull is filled with the tone. */
.pull-card.newest{background:var(--game-tone);box-shadow:none}
.pull-card.newest :is(.pull-meta,.pull-day){color:var(--game-accent)}
.pull-card.newest .pull-pic{background:var(--card-bg)}

/* Guides: what a guide holds, and the roles that have a summary. */
.guides-body{display:grid;grid-template-columns:minmax(220px,300px) minmax(0,1fr);gap:20px;align-items:center}
.guide-points{display:grid;gap:10px;margin:0;padding:0;list-style:none}
.guide-points li{display:grid;gap:2px;padding:14px 16px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.guide-points span{color:var(--text-muted);font-size:12px;line-height:18px}
.guide-points strong{font-size:18px;line-height:26px;font-weight:600;letter-spacing:-.02em}
.guide-kinds{padding-block:12px !important}

@media(max-width:1240px){.gacha-hero{grid-column:span 5}.gacha-pools{grid-column:span 7}.gacha-luck{grid-column:1/-1}}
@media(max-width:1000px){.roles-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.sum-levels{grid-column:1/-1}.own-rings{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:860px){
  .guides-body{grid-template-columns:minmax(0,1fr)}
  .gacha-hero,.gacha-pools,.gacha-luck,.gacha-empty{grid-column:1/-1}
}
@media(max-width:650px){
  .roles-summary{grid-template-columns:minmax(0,1fr)}
  .account-body .own-ring{flex-direction:column;align-items:flex-start;gap:10px;padding:14px}
  .nte-module-card{padding:18px;gap:14px}
  .account-top{padding:16px}
  .account-avatar{width:52px;height:52px;border-radius:17px;font-size:24px}
  .account-name strong{font-size:22px;line-height:28px}
  .account-stats{gap:10px 24px}
  .account-stats dd{font-size:26px;line-height:32px}
  .progress-hero{gap:14px}
  .big{font-size:28px;line-height:34px}
}
@media(max-width:420px){
  .stamina-body{gap:8px}
  .ring-tile{padding:14px 4px 12px}
}
</style>
