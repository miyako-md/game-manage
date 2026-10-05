<script setup>
import { computed } from 'vue'
import { esportsGroupLabel, esportsImage, officialEsportsUrl } from '../esports.js'
const props = defineProps({ payload: Object, filters: Object })
const emit = defineEmits(['select-player', 'select-team', 'back'])
const selected = computed(() => props.payload.players?.find(p => p.id === props.filters.playerId))
const team = id => props.payload.teams?.find(t => t.id === id)
const memberships = id => (props.payload.roster_memberships || []).filter(r => r.player_id === id)
const players = computed(() => (props.payload.players || []).filter(p => !props.filters.family || memberships(p.id).some(r => team(r.team_id)?.tournament_ids?.some(id => props.payload.tournaments?.find(t => t.id === id)?.family === props.filters.family))))
</script>
<template>
  <section aria-label="职业选手">
    <template v-if="filters.playerId"><button class="es-back" @click="emit('back')">← 返回</button><template v-if="selected"><div class="es-profile"><img v-if="esportsImage(selected.image_url)" :src="esportsImage(selected.image_url)" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><span v-else class="es-monogram">选</span><h3 tabindex="-1">{{ selected.nickname }}</h3></div><a v-if="officialEsportsUrl(selected.source_url)" :href="officialEsportsUrl(selected.source_url)" target="_blank" rel="noopener noreferrer">官方选手资料 ↗</a><h4>队伍与位置</h4><p class="es-note">来源当前阵容不代表历史首发；未提供转会日期或单场登场证据时不作推断。</p><article v-for="r in memberships(selected.id)" :key="`${r.team_id}:${r.scope}`" class="es-match"><button :id="'es-membership-' + r.team_id + '-' + r.scope" @click="emit('select-team', r.team_id, 'es-membership-' + r.team_id + '-' + r.scope)">{{ team(r.team_id)?.name || '队伍资料暂缺' }}</button> · {{ r.position || '位置未提供' }}<p class="es-note">{{ r.scope === 'source_current' ? '来源当前阵容' : r.scope === 'season_registered' ? '赛季报名阵容' : '单场登场阵容' }} · {{ esportsGroupLabel(payload.coverage?.[`roster:${r.team_id}`]) }}</p></article><p v-if="!memberships(selected.id).length" class="es-empty">队伍与位置资料暂缺。</p></template><p v-else class="es-empty">该选手资料暂缺。</p></template>
    <template v-else><h3 tabindex="-1">已收录选手</h3><p class="es-note">选手来自已收录队伍的来源阵容。</p><div class="es-grid"><button v-for="player in players" :id="'es-player-card-' + player.id" :key="player.id" class="es-tile" @click="emit('select-player', player.id, 'es-player-card-' + player.id)"><img v-if="esportsImage(player.image_url)" :src="esportsImage(player.image_url)" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><strong>{{ player.nickname }}</strong><span>{{ memberships(player.id).map(r => team(r.team_id)?.name || '队伍未知').join(' / ') || '队伍暂缺' }}</span><span>{{ memberships(player.id).map(r => r.position || '位置未提供').join(' / ') || '位置未提供' }}</span></button></div><p v-if="!players.length" class="es-empty">选手资料暂缺。</p></template>
  </section>
</template>
