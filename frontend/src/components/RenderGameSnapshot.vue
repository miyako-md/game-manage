<script setup>
import { computed, provide } from 'vue'
import { gameVars } from '../dashboard.js'
import { collectCalendarEvents } from '../calendar.js'
import { friendlyDataError } from '../cloud-display.js'
import AccountCard from './AccountCard.vue'
import StaminaCard from './StaminaCard.vue'
import ExplorationCard from './ExplorationCard.vue'
import ProgressCard from './ProgressCard.vue'
import CalabashCard from './CalabashCard.vue'
import NteDataCard from './NteDataCard.vue'
import NteAssetsPanel from './NteAssetsPanel.vue'
import NteRolesPanel from './NteRolesPanel.vue'
import NteCommunityGacha from './NteCommunityGacha.vue'
import WuwaProfile from './WuwaProfile.vue'
import WuwaRoles from './WuwaRoles.vue'
import WuwaCombat from './WuwaCombat.vue'
import WuwaActivities from './WuwaActivities.vue'
import WuwaResources from './WuwaResources.vue'
import WuwaGacha from './WuwaGacha.vue'
import EndfieldGachaPanel from './EndfieldGachaPanel.vue'
import EndfieldReports from './EndfieldReports.vue'
import EndfieldChallenges from './EndfieldChallenges.vue'
import AnnouncementList from './AnnouncementList.vue'
import RenderCalendar from './RenderCalendar.vue'
const props=defineProps({panel:{type:Object,required:true},asOf:{type:Number,required:true}})
provide('wuwaImageMode',true)
const names={nte:'异环',wuthering_waves:'鸣潮',endfield:'终末地'}
const snap=computed(()=>props.panel.snapshot)
const cap=computed(()=>props.panel.capability)
const nativeSnapshot=computed(()=>props.panel.game==='endfield' && cap.value==='stamina' && !snap.value?.payload?.stamina && !snap.value?.payload?.report && !snap.value?.payload?.base
 ? {...snap.value,payload:{stamina:snap.value?.payload}} : snap.value)
const endfieldView=computed(()=>({account:'overview',stamina:'overview',progress:'overview',roles:'operators',training:'operators',exploration:'regions',regions:'regions',ship:'ship',record:'honor',honor:'honor',operator_detail:'detail'})[cap.value] || 'overview')
const challengeReports=computed(()=>Array.isArray(snap.value?.payload?.reports)?snap.value.payload.reports:[])
const gameTitle=computed(()=>names[props.panel.game]+(props.panel.game==='endfield' ? props.panel.provider==='skland'?' · 森空岛档案':' · 鹰角寻访' : ''))
const component=computed(()=>{
 if(['news','announcement'].includes(cap.value))return AnnouncementList
 if(props.panel.game==='nte'){
  if(['account','stamina','progress','exploration','record'].includes(cap.value))return NteDataCard
  if(['realestate','vehicles','teams'].includes(cap.value))return NteAssetsPanel
  return {roles:NteRolesPanel,gacha:NteCommunityGacha}[cap.value]
 }
 if(props.panel.game==='wuthering_waves')return {account:WuwaProfile,roles:WuwaRoles,stamina:StaminaCard,exploration:ExplorationCard,progress:ProgressCard,calabash:CalabashCard,combat:WuwaCombat,activities:WuwaActivities,resources:WuwaResources,gacha:WuwaGacha}[cap.value]
 if(props.panel.game==='endfield')return cap.value==='gacha'?EndfieldGachaPanel:props.panel.provider==='skland'?EndfieldReports:AccountCard
 return null
})
const componentProps=computed(()=>({snap:nativeSnapshot.value,capability:cap.value,gameId:props.panel.game,imageMode:true,
 label:props.panel.game==='wuthering_waves'?'结晶波片':'体力',snapshot:cap.value==='gacha'&&props.panel.game==='wuthering_waves'?snap.value?.payload:undefined,
 payload:nativeSnapshot.value?.payload,view:endfieldView.value,fetchedAt:snap.value?.fetched_at,stale:snap.value?.stale,
 operatorDetail:snap.value?.payload?.operator_detail,operatorDetailId:snap.value?.payload?.operator_detail_id,
 operatorFetchedAt:snap.value?.payload?.operator_fetched_at,operatorStale:snap.value?.payload?.operator_stale}))
const declaredProps=computed(()=>Object.fromEntries(Object.entries(componentProps.value).filter(([key])=>key in (component.value?.props || {}))))
const events=computed(()=>collectCalendarEvents([{game_id:props.panel.game,display_name:names[props.panel.game]}],{[props.panel.game]:{events:snap.value}}))
const error=computed(()=>snap.value?.state==='auth_expired'?friendlyDataError('',snap.value.state):'')
</script>
<template>
 <section class="render-snapshot-panel game-theme" :class="`cap-${cap}`" :data-capability="cap" :data-game="panel.game" :style="gameVars(panel.game)">
  <h2 class="snapshot-game-name">{{ gameTitle || '游戏数据' }}</h2>
  <p v-if="error" class="error-bar" role="status">{{ error }}</p>
  <RenderCalendar v-if="['events','recent_events'].includes(cap)" :events="events" :as-of="asOf" />
  <template v-else-if="panel.game==='endfield' && panel.provider==='skland' && cap==='combat'">
   <EndfieldChallenges v-for="report in challengeReports" :key="report.kind" :kind="report.kind" :value="{report}" image-mode />
   <p v-if="!challengeReports.length" class="cap-card empty">尚无挑战记录，请在看板读取后查看。</p>
  </template>
  <component v-else-if="component" :is="component" v-bind="declaredProps" />
  <p v-else class="cap-card empty">当前数据暂不可用，请到看板查看。</p>
 </section>
</template>
<style scoped>
.render-snapshot-panel{display:grid;gap:10px;min-width:0}.snapshot-game-name{font-size:15px;font-weight:500;color:var(--accent);margin:0}
</style>
