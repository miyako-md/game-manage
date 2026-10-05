<script setup>
import { computed, nextTick, ref } from 'vue'
import { esportsSections } from '../esports.js'
import EsportsMatchRow from './EsportsMatchRow.vue'
import EsportsMatchDetail from './EsportsMatchDetail.vue'
const props = defineProps({ payload: Object, filters: Object })
const emit = defineEmits(['select-team', 'select-match', 'page-change', 'back'])
const sections = computed(() => esportsSections(props.payload, props.filters))
const selected = computed(() => props.payload.matches?.find(m => m.id === props.filters.matchId))
const resultsHeading = ref(null)
const noFuture = computed(() => !sections.value.some(s => ['live', 'scheduled'].includes(s.key) && s.total))
async function page(value) { emit('page-change', value); await nextTick(); resultsHeading.value?.scrollIntoView?.({ block: 'start' }); resultsHeading.value?.focus?.({ preventScroll: true }) }
</script>
<template>
  <section :aria-label="filters.view === 'results' ? '职业赛事赛果' : '职业赛事赛程'">
    <EsportsMatchDetail v-if="filters.matchId" :payload="payload" :match="selected" @back="emit('back')" @select-team="(id, focus) => emit('select-team', id, focus)" />
    <template v-else>
      <p class="es-list-caption">北京时间 · {{ filters.view === 'results' ? '最新赛果在前' : '来源状态分区 · 近期赛果倒序' }} · 点击比分查看详情</p>
      <p v-if="filters.view !== 'results' && noFuture" class="es-inline-notice">当前缓存未收录进行中或未来比赛；筛选或来源覆盖可能不完整，不能据此判断没有比赛。</p>
      <template v-for="section in sections" :key="section.key">
        <section v-if="section.total || filters.view === 'results'" class="es-match-section" :aria-label="section.label">
          <h3 :ref="el => { if (section.key === 'completed') resultsHeading = el }" tabindex="-1">{{ section.label }}<span>{{ section.total }} 场已收录</span></h3>
          <p v-if="section.key === 'live' && section.total" class="es-inline-notice">来源标记进行中，缓存可能滞后；以官方直播为准。</p>
          <p v-if="!section.total" class="es-empty">当前筛选下没有已收录赛果。资料可能尚未发布或来源未覆盖，不代表没有比赛。</p>
          <div v-for="group in section.groups" :key="group.date" class="es-date-group"><h4>{{ group.date }}</h4><EsportsMatchRow v-for="match in group.matches" :key="match.id" :match="match" :payload="payload" @select-team="(id, focus) => emit('select-team', id, focus)" @select-match="(id, focus) => emit('select-match', id, focus)" /></div>
          <nav v-if="section.key === 'completed' && section.pages > 1" class="es-pagination" aria-label="赛果分页"><button :disabled="section.page <= 1" @click="page(section.page - 1)">上一页</button><span aria-live="polite">{{ section.page }} / {{ section.pages }} 页</span><button :disabled="section.page >= section.pages" @click="page(section.page + 1)">下一页</button></nav>
        </section>
      </template>
      <p v-if="!sections.some(s => s.total) && filters.view !== 'results'" class="es-empty">当前筛选下没有已收录赛程。资料可能尚未发布或来源未覆盖，不代表没有比赛。</p>
    </template>
  </section>
</template>
