<script setup>
import { computed, ref } from 'vue'
import { list, value, stamp } from '../wuwa-display.js'
import { bestRank, deepZone as deepOf, endLabel, otherZoneStars, towerFloors, towerTeam, towerTotals } from '../wuwa-charts.js'
import { percentOf } from '../dashboard.js'
import { share } from '../chart-math.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaRoleDialog from './WuwaRoleDialog.vue'
import WuwaCombatRecord from './WuwaCombatRecord.vue'
import WuwaChallengeGuides from './WuwaChallengeGuides.vue'
import WuwaCombatRole from './WuwaCombatRole.vue'
import RingGauge from './RingGauge.vue'
import { vGlide, vReveal } from '../motion.js'
const props = defineProps({ roleNames: { type: Object, default: () => ({}) }, snap: { default: null }, imageMode:Boolean })
const payload = computed(() => props.snap?.payload || {})
const selected = ref(''), view = ref('records')
const titles = { tower:'逆境深塔', hologram:'战术全息', slash:'冥歌海墟' }
// A card per mode: the tower leads, the slash takes a full row.
const spans = { tower: 'span-7', hologram: 'span-5', slash: 'span-12' }
// One row per boss: the record cleared on the highest difficulty.
const bossRows = computed(() => {
  const groups = new Map()
  for (const record of Object.values(payload.value.hologram?.data?.challenge_info || {}).flatMap(list)) {
    if (!record.boss_name) continue
    groups.set(record.boss_name, [...(groups.get(record.boss_name) || []), record])
  }
  return [...groups].map(([name, records]) => ({ name, best: records.reduce((a, b) => (Number(b.difficulty) > Number(a.difficulty) ? b : a)) }))
})
const bosses = computed(() => bossRows.value.map(boss => boss.name))
const deepZone = computed(() => deepOf(payload.value.tower?.data?.difficulty_list))
const areas = computed(() => list(deepZone.value?.tower_area_list))
const stars = computed(() => towerTotals(areas.value))
const seasonEnd = computed(() => endLabel(payload.value.tower?.data?.season_end_at))
// The card's own summary of the records: full floors, the deepest team, the other zones.
// The bot image embeds the whole record below the card, so these stay off it.
const floors = computed(() => towerFloors(deepZone.value))
const team = computed(() => towerTeam(deepZone.value))
const otherZones = computed(() => otherZoneStars(payload.value.tower?.data?.difficulty_list))
const hasTeams = challenge => list(challenge.half_list).some(half => list(half.role_list).length)
const zones = computed(() => list(payload.value.slash?.data?.difficulty_list))
const percent = (done, cap) => { const r = share(done, cap); return r == null ? '—' : `${Math.round(r * 100)}%` }
const amount = v => (typeof v === 'number' ? v.toLocaleString('zh-CN') : value(v))
function open(mode) { selected.value=mode; view.value='records' }
</script>
<template>
  <div class="wuwa-board wuwa-combat">
    <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    <div class="wuwa-bento">
      <section v-for="(title, mode) in titles" :key="mode" v-reveal class="wuwa-panel wuwa-module-card" :class="[`combat-${mode}`, spans[mode], { 'is-openable': !imageMode, 'is-hero': mode === 'tower' }]">
        <header class="cap-title wuwa-module-heading"><h2>{{ title }}</h2><button v-if="!imageMode" type="button" class="ui-button small-button wuwa-open" @click="open(mode)">查看{{ title }}</button></header>
        <template v-if="mode === 'tower'">
          <p class="wuwa-meta">深境区 · 周期结束 {{ stamp(payload.tower?.data?.season_end_at) }}（北京时间）<span v-if="seasonEnd && (imageMode || !areas.length)" class="chip">{{ seasonEnd }}</span></p>
          <div v-if="areas.length" class="tower-summary">
            <RingGauge :value="stars.got" :max="stars.cap" label="深境区总星数" :size="132" :stroke="12" color="var(--wuwa-vivid)">
              <b class="ring-value">{{ value(stars.got) }}</b><small class="ring-cap">/ {{ value(stars.cap) }} 星</small>
            </RingGauge>
            <dl v-if="!imageMode && (floors || seasonEnd)" class="wuwa-stats tower-metrics">
              <div v-if="floors" class="wuwa-stat"><dt>满星层数</dt><dd>{{ value(floors.full) }}<small> / {{ floors.total }} 层</small></dd></div>
              <div v-if="seasonEnd" class="wuwa-stat"><dt>本期剩余</dt><dd class="is-label">{{ seasonEnd }}</dd></div>
            </dl>
            <ul class="bar-list tower-areas">
              <li v-for="(area, i) in areas" :key="i" class="bar-row">
                <span class="k">{{ area.area_name || `区域 ${i + 1}` }}</span>
                <span class="meter"><i :style="{ '--pct': `${percentOf(area.star, area.max_star) ?? 0}%` }"></i></span>
                <span class="v">{{ value(area.star) }}<small> / {{ value(area.max_star) }}</small></span>
              </li>
            </ul>
          </div>
          <div v-if="team && !imageMode" class="tower-team">
            <span class="k">本期队伍</span><span class="wuwa-meta">{{ team.area }}<template v-if="team.floor != null"> · 第 {{ team.floor }} 层</template></span>
            <ul class="chip-list"><li v-for="(role, k) in team.roles" :key="k" class="chip"><WuwaCombatRole :role="role" :role-names="roleNames" /></li></ul>
          </div>
          <p v-if="!deepZone" class="wuwa-muted">深境区记录暂不可用，仍可查看社区攻略。</p>
          <ul v-if="otherZones.length && !imageMode" class="chip-list tower-zones" aria-label="其他分区星数">
            <li v-for="zone in otherZones" :key="zone.name" class="chip">{{ zone.name }} <b>{{ zone.got }}</b><template v-if="zone.cap != null"> / {{ zone.cap }}</template> 星</li>
          </ul>
        </template>
        <template v-else-if="mode === 'hologram'">
          <p class="combat-count"><small>{{ bosses.length ? '已记录' : '尚无首领记录' }}</small><template v-if="bosses.length"><b>{{ bosses.length }}</b><small>位首领</small></template></p>
          <ul v-if="bossRows.length" class="boss-list">
            <li v-for="boss in bossRows" :key="boss.name">
              <span class="boss-mark" aria-hidden="true">{{ boss.name.slice(0, 1) }}</span>
              <strong>{{ boss.name }}</strong>
              <span class="wuwa-meta">难度 {{ value(boss.best.difficulty) }} · 通关时间 {{ value(boss.best.pass_time) }}</span>
            </li>
          </ul>
        </template>
        <template v-else>
          <div v-for="(zone, i) in zones" :key="i" class="slash-zone">
            <RingGauge :value="zone.all_score" :max="zone.max_score" :label="zone.difficulty_name || `难度 ${value(zone.difficulty)}`" :size="112" :stroke="11" color="var(--wuwa-vivid)">
              <span class="ring-pct">{{ percent(zone.all_score, zone.max_score) }}</span>
            </RingGauge>
            <div class="slash-copy">
              <span class="slash-zone-title"><span class="k">{{ zone.difficulty_name || `难度 ${value(zone.difficulty)}` }}</span><span v-if="!imageMode && bestRank(zone.challenge_list)" class="badge wuwa-rank">最高评级 {{ bestRank(zone.challenge_list) }}</span></span>
              <strong class="slash-score">{{ amount(zone.all_score) }}<small> / {{ amount(zone.max_score) }}</small></strong>
            </div>
            <ul v-if="list(zone.challenge_list).length" class="slash-challenges">
              <li v-for="(challenge, j) in list(zone.challenge_list)" :key="j">
                <span class="k">{{ challenge.challenge_name }}</span>
                <b>{{ amount(challenge.score) }}</b>
                <span class="badge wuwa-rank">评级 {{ value(challenge.rank) }}</span>
                <div v-if="!imageMode && hasTeams(challenge)" class="slash-teams">
                  <template v-for="(half, k) in list(challenge.half_list)" :key="k"><ul v-if="list(half.role_list).length" class="slash-team" :aria-label="half.half_name || `第 ${k + 1} 半场`">
                    <li v-for="(role, m) in list(half.role_list).slice(0, 3)" :key="m"><WuwaCombatRole :role="role" :role-names="roleNames" compact /></li>
                  </ul></template>
                </div>
              </li>
            </ul>
          </div>
        </template>
        <p v-if="payload[mode]?.data?.is_unlock === false" class="wuwa-muted">尚未解锁</p>
        <WuwaStatus :snap="payload[mode] || snap" />
        <WuwaCombatRecord v-if="imageMode" :mode="mode" :snap="snap" :role-names="roleNames" />
      </section>
    </div>
    <WuwaRoleDialog v-if="selected" :title="`${titles[selected]} · 详情`" :width="760" @close="selected = ''">
      <div v-glide class="segmented wuwa-dialog-tabs" role="group" aria-label="挑战详情视图">
        <button :aria-pressed="view === 'records'" @click="view = 'records'">战绩详情</button>
        <button :aria-pressed="view === 'guides'" @click="view = 'guides'">社区攻略</button>
      </div>
      <WuwaCombatRecord v-if="view === 'records'" :mode="selected" :snap="snap" :role-names="roleNames" />
      <WuwaChallengeGuides v-else :key="selected" :mode="selected" :bosses="bosses" />
    </WuwaRoleDialog>
  </div>
</template>
