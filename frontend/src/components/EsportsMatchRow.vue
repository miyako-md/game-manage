<script setup>
import { computed } from 'vue'
import { esportsTime, esportsImage, esportsOutcome, ESPORTS_STATUS } from '../esports.js'
const props = defineProps({ match: Object, payload: Object })
const emit = defineEmits(['select-match', 'select-team'])
const tournament = computed(() => props.payload.tournaments?.find(t => t.id === props.match.tournament_id))
const image = side => esportsImage(props.payload.teams?.find(t => t.id === props.match['team_' + side + '_id'])?.logo_url)
const score = computed(() => ['completed', 'live'].includes(props.match.status) && props.match.score_a != null && props.match.score_b != null)
const label = computed(() => (props.match.team_a_name || '待定') + ' 对 ' + (props.match.team_b_name || '待定') + '，' + (score.value ? props.match.score_a + ' : ' + props.match.score_b : '比分待定') + '，查看比赛摘要')
</script>
<template>
  <article class="es-row" :id="'es-row-' + match.id">
    <div class="es-row-time"><time>{{ match.start_at ? esportsTime(match.start_at).slice(11, 16) : '待公布' }}</time><span :class="{ 'es-live': match.status === 'live' }">{{ ESPORTS_STATUS[match.status] || ESPORTS_STATUS.unknown }}</span></div>
    <div class="es-row-versus">
      <button :id="'es-team-' + match.id + '-a'" class="es-row-team es-team-a" :class="{ 'es-winner': esportsOutcome(match, 'a') === '胜' }" :disabled="!match.team_a_id" @click="emit('select-team', match.team_a_id, 'es-team-' + match.id + '-a')"><span>{{ match.team_a_name || '待定' }}</span><img v-if="image('a')" :src="image('a')" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"></button>
      <button :id="'es-open-' + match.id" class="es-row-score" :data-open-match="match.id" :aria-label="label" @click="emit('select-match', match.id, 'es-open-' + match.id)">
        <strong v-if="score"><span :class="{ 'es-score-win': esportsOutcome(match, 'a') === '胜', 'es-score-loss': esportsOutcome(match, 'a') === '负' }">{{ match.score_a }}</span> : <span :class="{ 'es-score-win': esportsOutcome(match, 'b') === '胜', 'es-score-loss': esportsOutcome(match, 'b') === '负' }">{{ match.score_b }}</span></strong><strong v-else>VS</strong>
        <small v-if="match.status === 'completed'">{{ esportsOutcome(match, 'a') ? esportsOutcome(match, 'a') + ' / ' + esportsOutcome(match, 'b') : '胜者未确认' }}</small><small v-else>{{ score ? '来源比分' : '比分待定' }}</small>
      </button>
      <button :id="'es-team-' + match.id + '-b'" class="es-row-team es-team-b" :class="{ 'es-winner': esportsOutcome(match, 'b') === '胜' }" :disabled="!match.team_b_id" @click="emit('select-team', match.team_b_id, 'es-team-' + match.id + '-b')"><img v-if="image('b')" :src="image('b')" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"><span>{{ match.team_b_name || '待定' }}</span></button>
    </div>
    <button class="es-row-context" :aria-label="label" @click="emit('select-match', match.id, 'es-open-' + match.id)"><span>{{ tournament?.name || '赛事资料暂缺' }}</span><small>{{ match.stage || '阶段待公布' }}</small></button>
    <span class="es-row-bo">{{ match.best_of ? 'BO' + match.best_of : '赛制待定' }}</span>
  </article>
</template>
