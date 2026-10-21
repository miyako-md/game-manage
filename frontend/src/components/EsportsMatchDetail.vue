<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { esportsTime, esportsGroupLabel, esportsImage, esportsMonogram, esportsOutcome, ESPORTS_STATUS, officialEsportsUrl } from '../esports.js'
const props = defineProps({ payload: Object, match: Object, restored: Boolean })
const emit = defineEmits(['back', 'select-team'])
const detail = ref(null)
const tournament = computed(() => props.payload.tournaments?.find(t => t.id === props.match?.tournament_id))
const score = computed(() => ['completed', 'live'].includes(props.match?.status) && props.match.score_a != null && props.match.score_b != null)
const team = side => props.payload.teams?.find(t => t.id === props.match?.['team_' + side + '_id'])
const image = side => esportsImage(team(side)?.logo_url)
const mark = side => esportsMonogram(team(side)?.short_name || props.match?.['team_' + side + '_name'])
// One pip per game a side needs to win the series (2 of a best of 3), filled for each game won.
const pips = side => {
  const need = props.match?.best_of ? Math.ceil(props.match.best_of / 2) : 0, won = props.match?.['score_' + side]
  return score.value && need ? Array.from({ length: need }, (_, i) => i < won) : []
}
watch(() => props.match?.id, async (id, prev) => { if (!id || (prev === undefined && props.restored)) return; await nextTick(); detail.value?.scrollIntoView?.({ block: 'start' }); detail.value?.focus?.({ preventScroll: true }) }, { immediate: true })
</script>
<template>
  <article class="es-detail" ref="detail" tabindex="-1" :id="'es-' + (match?.id || 'missing')">
    <button class="es-back ui-button small-button" @click="emit('back')">← 返回</button>
    <template v-if="match">
      <div class="es-detail-heading"><div><span class="es-eyebrow">比赛摘要</span><h3>{{ tournament?.name || '赛事资料暂缺' }}</h3><p class="es-note">{{ esportsTime(match.start_at) }} · 北京时间 · {{ match.stage || '阶段待公布' }}<span v-if="match.round_name"> · {{ match.round_name }}</span> · {{ match.best_of ? 'BO' + match.best_of : '赛制待公布' }}</p></div><span class="es-badge" :class="`is-${match.status}`">{{ ESPORTS_STATUS[match.status] || ESPORTS_STATUS.unknown }}</span></div>
      <div class="es-detail-versus">
        <button id="es-detail-team-a" class="es-side" :class="{ 'es-winner': esportsOutcome(match, 'a') === '胜' }" :disabled="!match.team_a_id" @click="emit('select-team', match.team_a_id, 'es-detail-team-a')"><span class="es-logo xl" :data-letter="mark('a')"><img v-if="image('a')" :src="image('a')" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"></span>{{ match.team_a_name || '待定' }}<small>{{ esportsOutcome(match, 'a') }}</small><span v-if="pips('a').length" class="es-pips" aria-hidden="true"><i v-for="(won, index) in pips('a')" :key="index" :class="{ won }"></i></span></button>
        <div class="es-detail-score"><strong>{{ score ? match.score_a + ' : ' + match.score_b : '比分待定' }}</strong><p class="es-note">{{ match.status === 'completed' && !esportsOutcome(match, 'a') ? '胜者未确认' : match.status === 'live' ? '进行中，请以实时直播为准' : '系列赛比分' }}</p></div>
        <button id="es-detail-team-b" class="es-side" :class="{ 'es-winner': esportsOutcome(match, 'b') === '胜' }" :disabled="!match.team_b_id" @click="emit('select-team', match.team_b_id, 'es-detail-team-b')"><span class="es-logo xl" :data-letter="mark('b')"><img v-if="image('b')" :src="image('b')" alt="" referrerpolicy="no-referrer" @error="$event.target.hidden = true"></span>{{ match.team_b_name || '待定' }}<small>{{ esportsOutcome(match, 'b') }}</small><span v-if="pips('b').length" class="es-pips" aria-hidden="true"><i v-for="(won, index) in pips('b')" :key="index" :class="{ won }"></i></span></button>
      </div>
      <div class="es-links"><a v-if="officialEsportsUrl(match.source_url)" class="ui-button small-button" :href="officialEsportsUrl(match.source_url)" target="_blank" rel="noopener noreferrer">官方赛事 ↗</a><a v-if="officialEsportsUrl(match.live_url)" class="ui-button small-button" :href="officialEsportsUrl(match.live_url)" target="_blank" rel="noopener noreferrer">直播入口 ↗</a><a v-if="officialEsportsUrl(match.vod_url)" class="ui-button small-button" :href="officialEsportsUrl(match.vod_url)" target="_blank" rel="noopener noreferrer">官方回放 ↗</a></div>
      <p class="es-note es-freshness">{{ esportsGroupLabel(payload.coverage?.['matches:' + match.tournament_id]) }}</p>
    </template><p v-else class="es-empty">本场比赛资料暂缺，可返回已收录列表。</p>
  </article>
</template>
