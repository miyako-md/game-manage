<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { esportsTime, esportsGroupLabel, esportsOutcome, ESPORTS_STATUS, officialEsportsUrl } from '../esports.js'
const props = defineProps({ payload: Object, match: Object })
const emit = defineEmits(['back', 'select-team'])
const detail = ref(null)
const tournament = computed(() => props.payload.tournaments?.find(t => t.id === props.match?.tournament_id))
const score = computed(() => ['completed', 'live'].includes(props.match?.status) && props.match.score_a != null && props.match.score_b != null)
watch(() => props.match?.id, async () => { await nextTick(); detail.value?.scrollIntoView?.({ block: 'start' }); detail.value?.focus?.({ preventScroll: true }) }, { immediate: true })
</script>
<template>
  <article class="es-detail" ref="detail" tabindex="-1" :id="'es-' + (match?.id || 'missing')">
    <button class="es-back" @click="emit('back')">← 返回</button>
    <template v-if="match">
      <div class="es-detail-heading"><div><span class="es-eyebrow">比赛摘要</span><h3>{{ tournament?.name || '赛事资料暂缺' }}</h3><p class="es-note">{{ esportsTime(match.start_at) }} · 北京时间 · {{ match.stage || '阶段待公布' }}<span v-if="match.round_name"> · {{ match.round_name }}</span> · {{ match.best_of ? 'BO' + match.best_of : '赛制待公布' }}</p></div><span class="es-badge">{{ ESPORTS_STATUS[match.status] || ESPORTS_STATUS.unknown }}</span></div>
      <div class="es-detail-versus"><button id="es-detail-team-a" :disabled="!match.team_a_id" @click="emit('select-team', match.team_a_id, 'es-detail-team-a')">{{ match.team_a_name || '待定' }}<small>{{ esportsOutcome(match, 'a') }}</small></button><div><strong>{{ score ? match.score_a + ' : ' + match.score_b : '比分待定' }}</strong><p class="es-note">{{ match.status === 'completed' && !esportsOutcome(match, 'a') ? '胜者未确认' : match.status === 'live' ? '来源标记进行中，缓存可能滞后' : '系列赛比分' }}</p></div><button id="es-detail-team-b" :disabled="!match.team_b_id" @click="emit('select-team', match.team_b_id, 'es-detail-team-b')">{{ match.team_b_name || '待定' }}<small>{{ esportsOutcome(match, 'b') }}</small></button></div>
      <div class="es-links"><a v-if="officialEsportsUrl(match.source_url)" :href="officialEsportsUrl(match.source_url)" target="_blank" rel="noopener noreferrer">官方赛事 ↗</a><a v-if="officialEsportsUrl(match.live_url)" :href="officialEsportsUrl(match.live_url)" target="_blank" rel="noopener noreferrer">直播入口 ↗</a><a v-if="officialEsportsUrl(match.vod_url)" :href="officialEsportsUrl(match.vod_url)" target="_blank" rel="noopener noreferrer">官方回放 ↗</a><span v-else class="es-note">回放链接暂缺</span></div>
      <p class="es-note es-freshness">{{ esportsGroupLabel(payload.coverage?.['matches:' + match.tournament_id]) }}</p>
      <p class="es-note">当前资料未提供逐局统计、BP 或本场实际登场阵容。</p>
    </template><p v-else class="es-empty">本场比赛资料暂缺，可返回已收录列表。</p>
  </article>
</template>
