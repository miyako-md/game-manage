<script setup>
import { computed, ref } from 'vue'
import WuwaProfile from './WuwaProfile.vue'
import WuwaRoles from './WuwaRoles.vue'
import WuwaCombat from './WuwaCombat.vue'
import WuwaActivities from './WuwaActivities.vue'
import WuwaResources from './WuwaResources.vue'
import WuwaGacha from './WuwaGacha.vue'
import WuwaHistory from './WuwaHistory.vue'
import StaminaCard from './StaminaCard.vue'
import ExplorationCard from './ExplorationCard.vue'
import CalabashCard from './CalabashCard.vue'
import ProgressCard from './ProgressCard.vue'
import AnnouncementList from './AnnouncementList.vue'
import AppIcon from './AppIcon.vue'
import { vGlide } from '../motion.js'
import WuwaModuleCard from './WuwaModuleCard.vue'
import { list, value } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import SummaryMetrics from './SummaryMetrics.vue'
const props = defineProps({
  snaps: { type: Object, default: () => ({}) },
  initialSection: { type: String, default: 'overview' },
  configured: { type: Boolean, default: false },
})
defineEmits(['calendar'])
const tabs = [
  ['profile', '档案'],
  ['roles', '角色'],
  ['combat', '挑战'],
  ['activities', '玩法'],
  ['resources', '资源简报'],
  ['gacha', '抽卡历史'],
  ['history', '成长记录'],
  ['news', '公告与资讯'],
]
const section = ref(
  { characters: 'roles', overview: 'profile', all: 'profile' }[
    props.initialSection
  ] ||
    (tabs.some((t) => t[0] === props.initialSection)
      ? props.initialSection
      : 'profile'),
)
const accountKey = computed(() => {
  if (!props.configured) return ''
  const extra = props.snaps.account?.payload?.extra
  return extra?.role_id != null && extra?.server_id != null
    ? `${extra.role_id}:${extra.server_id}`
    : ''
})
// Snapshot capabilities refresh independently; drop any identified older owner.
const current = computed(() =>
  Object.fromEntries(
    Object.entries(props.snaps).map(([cap, snap]) => {
      const p = snap?.payload
      const owner =
        cap === 'account'
          ? p?.extra
          : Array.isArray(p)
            ? p.find((r) => r?.extra?.account_role_id)?.extra
            : p
      const id = owner?.account_role_id ?? owner?.role_id
      return [
        cap,
        id != null &&
        owner?.server_id != null &&
        `${id}:${owner.server_id}` !== accountKey.value
          ? null
          : snap,
      ]
    }),
  ),
)
const roleNames = computed(() =>
  Object.fromEntries(
    (Array.isArray(current.value.roles?.payload)
      ? current.value.roles.payload
      : []
    )
      .filter(Boolean)
      .map((r) => [r.role_id, r.name]),
  ),
)
</script>
<template>
  <div class="wuwa-dashboard">
    <div class="wuwa-nav">
      <nav v-glide class="segmented" aria-label="鸣潮数据分区">
        <button
          v-for="[key, name] in tabs"
          :key="key"
          type="button"
          :aria-pressed="section === key"
          @click="section = key"
        >
          {{ name }}
        </button>
      </nav>
      <button
        type="button"
        class="text-link wuwa-calendar"
        @click="$emit('calendar')"
      >
        <AppIcon name="calendar" :size="15" />活动日历<AppIcon
          name="arrow"
          :size="15"
        />
      </button>
    </div>
    <div :key="`${accountKey}:${section}`" class="wuwa-stack t-panel">
      <template v-if="section === 'news'">
        <AnnouncementList game-id="wuthering_waves" :snap="snaps.news?.payload ? snaps.news : snaps.announcement" />
      </template>
      <p v-else-if="!configured" class="wuwa-panel">
        请先登录鸣潮账号以查看私人档案。
      </p>
      <template v-else-if="section === 'profile'">
        <WuwaModuleCard title="账号档案" :description="current.account?.payload?.nickname || '漂泊者档案'" :snap="current.account" :metrics="[
          { label: '联觉等级', value: current.account?.payload?.level },
          { label: '世界等级', value: current.account?.payload?.extra?.profile?.world_level },
          { label: '成就数', value: current.account?.payload?.extra?.profile?.achievement_count },
        ]"><WuwaProfile :snap="current.account" /></WuwaModuleCard>
        <div class="wuwa-grid profile-grid">
          <WuwaModuleCard class="profile-stamina" title="体力" inline :snap="current.stamina">
            <StaminaCard label="结晶波片" :snap="current.stamina" />
          </WuwaModuleCard>
          <WuwaModuleCard class="profile-progress" title="周期进度" inline :snap="current.progress">
            <ProgressCard :snap="current.progress" />
          </WuwaModuleCard>
          <WuwaModuleCard class="profile-exploration" title="探索收集" description="地区探索度、残象与分类收集统计" :snap="current.exploration" :metrics="[{label:'已收录残象',value:current.exploration?.payload?.detections?.total}]">
            <template #preview><SummaryMetrics compact :metrics="(current.exploration?.payload?.country_groups || []).map(g=>({label:g.name,current:g.progress,total:100,icon:'grid'}))" /></template>
            <ExplorationCard :snap="current.exploration" />
          </WuwaModuleCard>
          <WuwaModuleCard class="profile-calabash" title="数据坞" inline :snap="current.calabash">
            <CalabashCard :snap="current.calabash" />
          </WuwaModuleCard>
        </div></template
      ><WuwaRoles
        v-else-if="section === 'roles'"
        :snap="current.roles"
        :account-key="accountKey"
      /><WuwaCombat
        v-else-if="section === 'combat'"
        :snap="current.combat"
        :role-names="roleNames"
      /><WuwaActivities
        v-else-if="section === 'activities'"
        :snap="current.activities"
      /><WuwaModuleCard v-else-if="section === 'resources'" title="资源简报" description="期间获取量，非当前钱包余额；在详情中切换周、月或版本报告。" :snap="current.resources" :metrics="[
        {label:'当前报告贝币',value:current.resources?.payload?.current?.data?.total_coin},
        {label:'当前报告星声',value:current.resources?.payload?.current?.data?.total_star},
      ]">
        <template #preview>
          <p v-if="current.resources?.payload?.current" class="wuwa-meta">报告周期：{{ { week:'周',month:'月',version:'版本' }[current.resources.payload.current.kind] || '未知' }} {{ value(current.resources.payload.current.period) }}</p>
          <WuwaStatus v-if="current.resources?.payload?.current" :snap="current.resources.payload.current" />
        </template>
        <WuwaResources :snap="current.resources" :account-key="accountKey" />
      </WuwaModuleCard>
      <template v-else-if="accountKey">
        <WuwaModuleCard v-if="section === 'gacha'" title="抽卡历史" description="本地抽卡档案、出金统计与手动导入。只有点击导入才会使用授权链接。"><WuwaGacha :account-key="accountKey" /></WuwaModuleCard>
        <WuwaModuleCard v-if="section === 'history'" title="成长记录" description="跨期深塔成绩、角色练度和完整面板的历史观测。"><WuwaHistory :account-key="accountKey" :role-names="roleNames" /></WuwaModuleCard>
      </template>
      <p v-else class="wuwa-panel">
        尚未读取到当前账号标识，请刷新数据后重试。
      </p>
    </div>
  </div>
</template>
<style src="../wuwa.css"></style>
<style scoped>
.profile-grid{grid-template-areas:'stamina calabash' 'progress progress' 'exploration exploration';align-items:start}
.profile-stamina{grid-area:stamina}.profile-progress{grid-area:progress}.profile-exploration{grid-area:exploration}.profile-calabash{grid-area:calabash}
@media(max-width:760px){.profile-grid{grid-template-columns:1fr;grid-template-areas:'stamina' 'progress' 'calabash' 'exploration'}}
</style>
