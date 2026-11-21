<script setup>
import {computed,provide} from 'vue'
import {gameVars} from '../dashboard.js'
import {sheetSkin} from './sheet-skin.js'
import {viewModel} from './models.js'
import {imageWidth} from './designs.js'
import {shellMeta} from './shell-meta.js'
import {displayBeijing} from '../time.js'
import ReuseBody from './ReuseBody.vue'
import AccountOverviewSheet from './AccountOverviewSheet.vue'
import HelpSheet from './HelpSheet.vue'
import OverviewShell from './OverviewShell.vue'
import RoleRosterSheet from './RoleRosterSheet.vue'
import EndfieldOperatorSheet from './EndfieldOperatorSheet.vue'
import WuwaRoleDetailSheet from './WuwaRoleDetailSheet.vue'
import NteRoleDetailSheet from './NteRoleDetailSheet.vue'
import WuwaDataSheet from './WuwaDataSheet.vue'
import NteDataSheet from './NteDataSheet.vue'
import EndfieldDataSheet from './EndfieldDataSheet.vue'
import WuwaGachaSheet from './WuwaGachaSheet.vue'
import NteGachaSheet from './NteGachaSheet.vue'
import EndfieldGachaSheet from './EndfieldGachaSheet.vue'
import EventCalendarSheet from './EventCalendarSheet.vue'
import GuideSheet from './GuideSheet.vue'
import NoticeSheet from './NoticeSheet.vue'

const props=defineProps({input:Object})
provide('wuwaImageMode',true)

const WUWA_DATA_CAPS=new Set(['exploration','progress','resources','combat'])
const NTE_DATA_CAPS=new Set(['exploration','progress','realestate','vehicles','teams'])
const EF_DATA_CAPS=new Set(['exploration','ship','honor','combat'])

const snap=computed(()=>props.input?.snapshot||{})
const model=computed(()=>viewModel(props.input))
const isExample=computed(()=>/合成|反馈示例|未绑定|未收录|无登录/.test(model.value.origin))
const panels=computed(()=>snap.value.display_data?.panels||[])
const singleCap=computed(()=>snap.value.kind==='game_snapshot'&&panels.value.length===1?panels.value[0].capability:null)
const singleGame=computed(()=>snap.value.kind==='game_snapshot'&&panels.value.length===1?panels.value[0].game:null)
const isAccountOverview=computed(()=>snap.value.kind==='game_snapshot'&&panels.value.some(p=>p.capability==='account'))
const isRoleRoster=computed(()=>
 (snap.value.kind==='nte_role'&&snap.value.display_data?.snapshot?.display_mode!=='detail')
 ||(snap.value.kind==='game_snapshot'&&singleCap.value==='roles'&&['wuthering_waves','nte','endfield'].includes(panels.value[0].game))
)
const isWuwaRoleDetail=computed(()=>snap.value.kind==='wuwa_role')
const isNteRoleDetail=computed(()=>snap.value.kind==='nte_role'&&snap.value.display_data?.snapshot?.display_mode==='detail')
const isEndfieldOperatorDetail=computed(()=>snap.value.kind==='game_snapshot'&&singleCap.value==='operator_detail'&&panels.value[0].game==='endfield')
const isWuwaData=computed(()=>singleGame.value==='wuthering_waves'&&WUWA_DATA_CAPS.has(singleCap.value))
const isNteData=computed(()=>singleGame.value==='nte'&&NTE_DATA_CAPS.has(singleCap.value))
const isEndfieldData=computed(()=>singleGame.value==='endfield'&&EF_DATA_CAPS.has(singleCap.value))
const isWuwaGacha=computed(()=>snap.value.kind==='wuwa_gacha'||(singleGame.value==='wuthering_waves'&&singleCap.value==='gacha'))
const isNteGacha=computed(()=>snap.value.kind==='nte_gacha'||(singleGame.value==='nte'&&singleCap.value==='gacha'))
const isEndfieldGacha=computed(()=>singleGame.value==='endfield'&&singleCap.value==='gacha')
const isEventCalendar=computed(()=>snap.value.kind==='calendar'||panels.value.some(p=>p.capability==='events'||p.capability==='recent_events'))
const isGuide=computed(()=>snap.value.kind==='guide')
const nteDetailRole=computed(()=>snap.value.display_data?.snapshot?.payload?.entries?.[0]||null)

// Cross-game pages keep the obsidian (Wuwa) shell; their game blocks carry their own skin.
const skin=computed(()=>sheetSkin(props.input?.snapshot?.game))
// 帮助 and 我的账号 are registry/status notices with their own command-card layout.
const helpVariant=computed(()=>{const s=props.input?.snapshot;return s?.kind!=='notice'?null:/帮助/.test(s.display_data?.title)?'help':/我的账号/.test(s.display_data?.title)?'account':null})
const isNotice=computed(()=>snap.value.kind==='notice'&&!helpVariant.value)

const meta=computed(()=>shellMeta(props.input,model.value))

const shellNotices=computed(()=>{
 const out=[]
 if(isRoleRoster.value){
  if(snap.value.game==='wuthering_waves')out.push('完整角色列表。查看装备、属性与声骸评分：发送「鸣潮 角色 精确名称」。')
  else if(snap.value.game==='nte')out.push('完整角色概览。查看装备、属性与技能详情：发送「异环 角色 精确名称」。')
  else if(snap.value.game==='endfield')out.push('武器、装备、技能与战术道具详情：发送「终末地 角色 干员名」，按精确名称查看单干员配装。')
 }
 if(isEndfieldOperatorDetail.value){
  const p=panels.value[0]?.snapshot?.payload||{}
  if(p.operator_fetched_at){
   out.push(`配装同步于 ${displayBeijing(p.operator_fetched_at)}${p.operator_stale?' · 当前显示上次成功读取的配装':''}`)
  }
 }
 const liftsNotices=isRoleRoster.value||isEndfieldOperatorDetail.value||isWuwaData.value||isNteData.value||isEndfieldData.value||isWuwaGacha.value||isNteGacha.value||isEndfieldGacha.value||isEventCalendar.value
 if(liftsNotices&&Array.isArray(snap.value.display_data?.notices)){
  for(const n of snap.value.display_data.notices)if(n)out.push(n)
 }
 return [...new Set(out)]
})
</script>
<template>
 <article class="lab-sheet dossier reuse" :class="['page-'+input.snapshot.kind,{'is-account-overview':isAccountOverview,'is-overview-styled':!isAccountOverview,['page-'+helpVariant]:helpVariant}]" :data-game="input.snapshot.game||'all'" :data-skin="skin" :style="{width:imageWidth(input)+'px',...gameVars(input.snapshot.game)}">
  <AccountOverviewSheet v-if="isAccountOverview" :input="input" />
  <OverviewShell
   v-else
   :title="meta.title"
   :game-tag="meta.gameTag"
   :sub-tag="meta.subTag"
   :extra-tag="meta.extraTag"
   :avatar-url="meta.avatarUrl"
   :hero-stats="meta.heroStats"
   :notices="shellNotices"
   :as-of="model.asOf"
   :command="model.command"
   :example-label="isExample?model.origin:''"
  >
   <RoleRosterSheet v-if="isRoleRoster" :input="input" />
   <EndfieldOperatorSheet v-else-if="isEndfieldOperatorDetail" :input="input" />
   <WuwaRoleDetailSheet v-else-if="isWuwaRoleDetail" :data="input.snapshot.display_data.detail" />
   <NteRoleDetailSheet v-else-if="isNteRoleDetail && nteDetailRole" :role="nteDetailRole" />
   <WuwaDataSheet v-else-if="isWuwaData" :input="input" />
   <NteDataSheet v-else-if="isNteData" :input="input" />
   <EndfieldDataSheet v-else-if="isEndfieldData" :input="input" />
   <WuwaGachaSheet v-else-if="isWuwaGacha" :input="input" />
   <NteGachaSheet v-else-if="isNteGacha" :input="input" />
   <EndfieldGachaSheet v-else-if="isEndfieldGacha" :input="input" />
   <EventCalendarSheet v-else-if="isEventCalendar" :input="input" :model="model" />
   <GuideSheet v-else-if="isGuide" :input="input" :model="model" />
   <HelpSheet v-else-if="helpVariant" :data="input.snapshot.display_data" :variant="helpVariant" />
   <NoticeSheet v-else-if="isNotice" :input="input" :model="model" />
   <ReuseBody v-else :input="input" />
  </OverviewShell>
 </article>
</template>
