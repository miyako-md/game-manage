<script setup>
import { computed, ref } from 'vue'
import { list, value, stamp } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaRoleDialog from './WuwaRoleDialog.vue'
import WuwaCombatRecord from './WuwaCombatRecord.vue'
import WuwaChallengeGuides from './WuwaChallengeGuides.vue'
import SummaryMetrics from './SummaryMetrics.vue'
import { vGlide } from '../motion.js'
const props = defineProps({ roleNames: { type: Object, default: () => ({}) }, snap: { default: null } })
const payload = computed(() => props.snap?.payload || {})
const selected = ref(''), view = ref('records')
const titles = { tower:'逆境深塔', hologram:'战术全息', slash:'冥歌海墟' }
const bosses = computed(() => [...new Set(Object.values(payload.value.hologram?.data?.challenge_info || {}).flatMap(list).map(x=>x.boss_name).filter(Boolean))])
const deepZone = computed(() => list(payload.value.tower?.data?.difficulty_list).find(z=>String(z.difficulty)==='3'))
function open(mode) { selected.value=mode; view.value='records' }
</script>
<template>
  <div class="wuwa-stack">
    <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    <section v-for="(title, mode) in titles" :key="mode" class="wuwa-panel">
      <header class="cap-title wuwa-module-heading"><h2>{{ title }}</h2><button type="button" class="ui-button small-button" @click="open(mode)">查看{{ title }}</button></header>
      <template v-if="mode === 'tower'">
        <p class="wuwa-meta">深境区 · 周期结束 {{ stamp(payload.tower?.data?.season_end_at) }}（北京时间）</p>
        <SummaryMetrics :metrics="list(deepZone?.tower_area_list).map((area,i)=>({label:area.area_name || `区域 ${i+1}`,current:area.star,total:area.max_star,icon:'spark',note:'深境区星数'}))" />
        <p v-if="!deepZone" class="wuwa-muted">深境区记录暂不可用，仍可查看社区攻略。</p>
      </template>
      <template v-else-if="mode === 'hologram'">
        <p class="wuwa-meta">{{ bosses.length ? `已记录 ${bosses.length} 位首领` : '尚无首领记录' }} · 详情中查看难度、队伍与首领攻略</p>
      </template>
      <template v-else>
        <SummaryMetrics :metrics="list(payload.slash?.data?.difficulty_list).map(zone=>({label:zone.difficulty_name || `难度 ${value(zone.difficulty)}`,current:zone.all_score,total:zone.max_score,icon:'shield'}))" />
        <p class="wuwa-meta">分半场成绩、队伍与社区打法见详情</p>
      </template>
      <p v-if="payload[mode]?.data?.is_unlock === false" class="wuwa-muted">尚未解锁</p>
      <WuwaStatus :snap="payload[mode] || snap" />
    </section>
    <WuwaRoleDialog v-if="selected" :title="`${titles[selected]} · 详情`" @close="selected = ''">
      <div v-glide class="segmented wuwa-dialog-tabs" role="group" aria-label="挑战详情视图">
        <button :aria-pressed="view === 'records'" @click="view = 'records'">战绩详情</button>
        <button :aria-pressed="view === 'guides'" @click="view = 'guides'">社区攻略</button>
      </div>
      <WuwaCombatRecord v-if="view === 'records'" :mode="selected" :snap="snap" :role-names="roleNames" />
      <WuwaChallengeGuides v-else :key="selected" :mode="selected" :bosses="bosses" />
    </WuwaRoleDialog>
  </div>
</template>
