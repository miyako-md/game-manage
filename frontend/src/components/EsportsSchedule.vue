<script setup>
import { computed, nextTick, ref } from 'vue'
import { esportsDayLabel, esportsSections } from '../esports.js'
import { vReveal } from '../motion.js'
import EsportsMatchRow from './EsportsMatchRow.vue'
import EsportsMatchDetail from './EsportsMatchDetail.vue'
import HRail from './HRail.vue'
const props = defineProps({ payload: Object, filters: Object, restored: Boolean })
const emit = defineEmits(['select-team', 'select-match', 'page-change', 'back'])
const sections = computed(() => esportsSections(props.payload, props.filters))
const selected = computed(() => props.payload.matches?.find(m => m.id === props.filters.matchId))
const resultsHeading = ref(null)
const noFuture = computed(() => !sections.value.some(s => ['live', 'scheduled'].includes(s.key) && s.total))
// Matches still to come sit in a rail of cards for each day; finished ones stay a compact list.
const railed = key => key !== 'completed'
async function page(value) { emit('page-change', value); await nextTick(); resultsHeading.value?.scrollIntoView?.({ block: 'start' }); resultsHeading.value?.focus?.({ preventScroll: true }) }
</script>
<template>
  <section :aria-label="filters.view === 'results' ? '职业赛事赛果' : '职业赛事赛程'">
    <EsportsMatchDetail v-if="filters.matchId" :payload="payload" :match="selected" :restored="restored" @back="emit('back')" @select-team="(id, focus) => emit('select-team', id, focus)" />
    <template v-else>
      <p class="es-list-caption">北京时间 · {{ filters.view === 'results' ? '最新赛果在前' : '按比赛状态分组 · 近期赛果在前' }}</p>
      <p v-if="filters.view !== 'results' && noFuture" class="es-inline-notice">当前筛选暂无进行中或待赛记录。</p>
      <template v-for="section in sections" :key="section.key">
        <section v-if="section.total || filters.view === 'results'" class="es-match-section" :class="`is-${section.key}`" :aria-label="section.label">
          <h3 :ref="el => { if (section.key === 'completed') resultsHeading = el }" tabindex="-1">{{ section.label }}<span>{{ section.total }} 场已收录</span></h3>
          <p v-if="!section.total" class="es-empty">当前筛选暂无赛果。</p>
          <div v-for="group in section.groups" :key="group.date" v-reveal class="es-date-group" :class="railed(section.key) ? 'is-rail' : 'is-list'">
            <h4>{{ esportsDayLabel(group.date) }}</h4>
            <HRail v-if="railed(section.key)" :label="`${esportsDayLabel(group.date)}的比赛`">
              <EsportsMatchRow v-for="match in group.matches" :key="match.id" variant="card" :match="match" :payload="payload" @select-team="(id, focus) => emit('select-team', id, focus)" @select-match="(id, focus) => emit('select-match', id, focus)" />
            </HRail>
            <template v-else><EsportsMatchRow v-for="match in group.matches" :key="match.id" :match="match" :payload="payload" @select-team="(id, focus) => emit('select-team', id, focus)" @select-match="(id, focus) => emit('select-match', id, focus)" /></template>
          </div>
          <nav v-if="section.key === 'completed' && section.pages > 1" class="es-pagination" aria-label="赛果分页"><button class="ui-button small-button" :disabled="section.page <= 1" @click="page(section.page - 1)">上一页</button><span aria-live="polite">{{ section.page }} / {{ section.pages }} 页</span><button class="ui-button small-button" :disabled="section.page >= section.pages" @click="page(section.page + 1)">下一页</button></nav>
        </section>
      </template>
      <p v-if="!sections.some(s => s.total) && filters.view !== 'results'" class="es-empty">当前筛选暂无赛程。</p>
    </template>
  </section>
</template>
