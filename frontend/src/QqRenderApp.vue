<script setup>
import { computed } from 'vue'
import OverviewPage from './components/OverviewPage.vue'
import CalendarPage from './components/CalendarPage.vue'
import GameCard from './components/GameCard.vue'
import AnnouncementList from './components/AnnouncementList.vue'
import { captureSection, selectOverviewAccount } from './qq-render-context.js'
import { selectQqEvents } from './qq-event-selection.js'

const props = defineProps({ input: { type:Object, required:true } })
const names = { wuthering_waves:'鸣潮', nte:'异环', endfield:'终末地' }
const entries = computed(() => props.input.entries.filter(entry => entry.account?.state !== 'revoked'))
const entry = computed(() => entries.value.find(row => row.account.game === props.input.game) || entries.value[0])
const games = computed(() => Object.keys(names).filter(id => props.input.game ? id === props.input.game : entries.value.some(row=>row.account.game===id) || props.input.publicSnapshots?.[id]).map(id => {
  const candidates = entries.value.filter(row=>row.account.game===id)
  const selected = selectOverviewAccount(candidates.map(row=>row.account))
  return { game_id:id, display_name:names[id], capabilities:selected?.provider === 'skland' ? ['account','stamina','news','events'] : [...new Set([...(selected?.capabilities || []),'news','events'])], credentials_configured:!!selected,
    platform:selected?.provider==='skland' ? '终末地 / 森空岛档案' : undefined }
}))
const snapshots = computed(() => Object.fromEntries(games.value.map(game => {
  const candidates = entries.value.filter(row=>row.account.game===game.game_id)
  const owner = selectOverviewAccount(candidates.map(row=>row.account))
  const row = candidates.find(candidate=>candidate.account===owner)
  const raw = row?.snapshots || {}
  const privateSnaps = props.input.command === 'overview' && owner?.provider === 'skland' && raw.account?.payload
    ? {...raw,account:{...raw.account,payload:{schema_version:1,nickname:raw.account.payload.base?.name,level:raw.account.payload.base?.level}},stamina:{...raw.account,payload:raw.account.payload.stamina ? {schema_version:1,...raw.account.payload.stamina} : null}}
    : raw
  const combined = {...privateSnaps,...props.input.publicSnapshots?.[game.game_id]}
  if (['calendar','events','recent_events'].includes(props.input.command) && combined.events?.payload != null) {
    combined.events = {...combined.events,payload:selectQqEvents(combined.events.payload,props.input.command,props.input.now)}
  }
  return [game.game_id,combined]
})))
const game = computed(()=>games.value.find(game=>game.game_id===props.input.game) || games.value[0])
const accounts = computed(()=>Object.fromEntries(games.value.map(game=>[game.game_id,{state:'connected'}])))
const collection = computed(()=>games.value.flatMap(game=>Object.entries(snapshots.value[game.game_id] || {}).filter(([cap])=>!['news','events'].includes(cap)).map(([cap,snap])=>({game_id:game.game_id,capability:cap,state:snap.state || 'never',last_success_at:snap.fetched_at}))))
</script>
<template>
  <main id="qq-capture" class="qq-capture">
    <OverviewPage v-if="input.command === 'overview'" :games="games" :snapshots="snapshots" :accounts="accounts" :collection="collection" :now="input.now" storage-label="云端本人空间 · 按授权与默认角色显示" refresh-label="读取总览快照" />
    <CalendarPage v-else-if="['calendar','events','recent_events'].includes(input.command)" :games="games" :snapshots="snapshots" :initial-game-id="input.game || ''" />
    <AnnouncementList v-else-if="input.command === 'news' && game" :game-id="game.game_id" :snap="snapshots[game.game_id]?.news" />
    <GameCard v-else-if="game && entry" :game="game" :external-snapshots="snapshots[game.game_id]" :collection-status="collection" :cloud-account="entry.account" :cloud-role="entry.role" :cloud-scope="{user_id:'qq-render',account_id:entry.account.account_id,role_id:entry.role,provider:entry.account.provider}" :initial-section="captureSection(game.game_id,input.command)" />
    <p v-else class="empty-page">尚无可用的本人游戏快照，请在网站检查授权。</p>
  </main>
</template>
