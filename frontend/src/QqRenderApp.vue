<script setup>
import { computed } from 'vue'
import OverviewPage from './components/OverviewPage.vue'
import CalendarPage from './components/CalendarPage.vue'
import CloudGameCard from './components/CloudGameCard.vue'
import AnnouncementList from './components/AnnouncementList.vue'
import { captureSection } from './qq-render-context.js'
import { CLOUD_GAMES, cloudOverviewView, gameForAccount } from './cloud-view-model.js'
import { selectQqEvents } from './qq-event-selection.js'

const props = defineProps({ input: { type:Object, required:true } })
const entries = computed(()=>props.input.entries.filter(entry=>entry.account?.state!=='revoked'))
const entry = computed(()=>entries.value.find(row=>gameForAccount(row.account)===props.input.game) || entries.value[0])
const overview = computed(()=>cloudOverviewView({accounts:entries.value.map(row=>row.account),snapshotsByAccount:Object.fromEntries(entries.value.map(row=>[row.account.account_id,row.snapshots])),publicSnapshots:props.input.publicSnapshots}))
const publicGames = computed(()=>CLOUD_GAMES.filter(game=>props.input.game ? game.game_id===props.input.game : entries.value.some(row=>gameForAccount(row.account)===game.game_id) || props.input.publicSnapshots?.[game.game_id]))
const publicSnapshots = computed(()=>Object.fromEntries(publicGames.value.map(game=>{
  const combined={...props.input.publicSnapshots?.[game.game_id]}
  if (['calendar','events','recent_events'].includes(props.input.command) && combined.events?.payload!=null) combined.events={...combined.events,payload:selectQqEvents(combined.events.payload,props.input.command,props.input.now)}
  return [game.game_id,combined]
})))
</script>
<template>
  <main id="qq-capture" class="workspace-main qq-capture">
    <OverviewPage v-if="input.command === 'overview'" :games="overview.games" :snapshots="overview.snapshots" :accounts="overview.accounts" :collection="overview.collection" :read-errors="overview.readErrors" :now="input.now" storage-label="云端本人空间 · 按授权与默认角色显示" refresh-label="读取总览快照" />
    <CalendarPage v-else-if="['calendar','events','recent_events'].includes(input.command)" :games="publicGames" :snapshots="publicSnapshots" :initial-game-id="input.game || ''" />
    <CloudGameCard v-else-if="entry" :account="entry.account" :role="entry.role" user-id="qq-render" :snapshots="entry.snapshots" :public-snapshots="input.publicSnapshots?.[gameForAccount(entry.account)] || {}" :initial-section="captureSection(gameForAccount(entry.account),input.command)" :show-snapshot-status="false" />
    <AnnouncementList v-else-if="input.command === 'news' && input.game" :game-id="input.game" :snap="input.publicSnapshots?.[input.game]?.news" />
    <p v-else class="empty-page">尚无可用的本人游戏快照，请在网站检查授权。</p>
  </main>
</template>
