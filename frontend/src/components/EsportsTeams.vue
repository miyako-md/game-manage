<script setup>
import { computed } from 'vue'
import { esportsGroupLabel, esportsImage, officialEsportsUrl, esportsSections } from '../esports.js'
import EsportsMatchRow from './EsportsMatchRow.vue'
const props = defineProps({ payload: Object, filters: Object })
const emit = defineEmits(['select-team', 'select-player', 'select-match', 'back'])
const selected = computed(() => props.payload.teams?.find(t => t.id === props.filters.teamId))
const teams = computed(() => (props.payload.teams || []).filter(t => !props.filters.family || t.tournament_ids?.some(id => props.payload.tournaments?.find(e => e.id === id)?.family === props.filters.family)))
const roster = computed(() => (props.payload.roster_memberships || []).filter(r => r.team_id === selected.value?.id))
const player = id => props.payload.players?.find(p => p.id === id)
const related = computed(() => esportsSections(props.payload, { family: props.filters.family, teamId: selected.value?.id }, 12).flatMap(s => s.groups).slice(0, 12))
</script>
<template>
  <section aria-label="职业战队">
    <template v-if="filters.teamId"><button class="es-back" @click="emit('back')">← 返回</button>
      <template v-if="selected"><div class="es-profile"><img v-if="esportsImage(selected.logo_url)" :src="esportsImage(selected.logo_url)" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><span v-else class="es-monogram">{{ selected.short_name?.slice(0, 3) || '队' }}</span><div><h3 tabindex="-1">{{ selected.name }}</h3><p>{{ selected.kind === 'national' ? '国家／地区代表队' : selected.kind === 'club' ? '职业俱乐部' : '队伍类型未提供' }}</p></div></div>
        <p v-if="selected.description" class="es-note">{{ selected.description }}</p>
        <a v-if="officialEsportsUrl(selected.source_url)" :href="officialEsportsUrl(selected.source_url)" target="_blank" rel="noopener noreferrer">官方战队资料 ↗</a>
        <h4>来源所列当前阵容</h4><p class="es-note">以下为来源当前名单，不代表历史首发或某场比赛实际登场阵容。</p><p class="es-note">{{ esportsGroupLabel(payload.coverage?.[`roster:${selected.id}`]) }}</p>
        <div v-if="roster.length" class="es-grid"><button v-for="r in roster" :id="'es-roster-' + r.player_id + '-' + r.scope" :key="`${r.player_id}:${r.scope}`" class="es-tile" @click="emit('select-player', r.player_id, 'es-roster-' + r.player_id + '-' + r.scope)"><img v-if="esportsImage(player(r.player_id)?.image_url)" :src="esportsImage(player(r.player_id)?.image_url)" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><strong>{{ player(r.player_id)?.nickname || '选手资料暂缺' }}</strong><span>{{ r.position || '位置未提供' }} · {{ r.scope === 'source_current' ? '来源当前阵容' : r.scope === 'season_registered' ? '赛季报名阵容' : '单场登场阵容' }}</span></button></div><p v-else class="es-empty">阵容资料暂缺。</p>
        <h4>已收录相关赛程与近期赛果</h4><div v-for="(group, index) in related" :key="index" class="es-date-group"><h4>{{ group.date }}</h4><EsportsMatchRow v-for="m in group.matches" :key="m.id" :match="m" :payload="payload" @select-match="(id, focus) => emit('select-match', id, focus)" @select-team="(id, focus) => emit('select-team', id, focus)" /></div><p v-if="!related.length" class="es-empty">暂未收录该队相关赛程。</p>
      </template><p v-else class="es-empty">该战队资料暂缺，可返回赛程。</p>
    </template>
    <template v-else><h3 tabindex="-1">已收录战队</h3><p class="es-note">仅展示已收录目标赛事的参赛队，可能包含国际队伍。</p><div class="es-grid"><button v-for="team in teams" :id="'es-team-card-' + team.id" :key="team.id" class="es-tile" @click="emit('select-team', team.id, 'es-team-card-' + team.id)"><img v-if="esportsImage(team.logo_url)" :src="esportsImage(team.logo_url)" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><strong>{{ team.name }}</strong><span>{{ team.short_name || '简称未提供' }}</span></button></div><p v-if="!teams.length" class="es-empty">当前赛事战队资料暂缺。</p></template>
  </section>
</template>
