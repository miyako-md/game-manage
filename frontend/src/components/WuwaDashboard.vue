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
import { vGlide } from '../motion.js'
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
  ['news', '公告'],
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
      <nav v-glide class="wuwa-tabs" aria-label="鸣潮数据分区">
        <button
          v-for="[key, name] in tabs"
          :key="key"
          :aria-pressed="section === key"
          @click="section = key"
        >
          {{ name }}
        </button>
      </nav>
      <button class="wuwa-calendar" @click="$emit('calendar')">
        活动日历 ↗
      </button>
    </div>
    <div :key="`${accountKey}:${section}`" class="wuwa-stack t-panel">
      <template v-if="section === 'news'"
        ><AnnouncementList
          :snap="snaps.news?.payload ? snaps.news : snaps.announcement"
      /></template>
      <p v-else-if="!configured" class="wuwa-panel">
        请先登录鸣潮账号以查看私人档案。
      </p>
      <template v-else-if="section === 'profile'"
        ><WuwaProfile :snap="current.account" />
        <div class="wuwa-grid">
          <StaminaCard :snap="current.stamina" /><ProgressCard
            :snap="current.progress"
          /><ExplorationCard :snap="current.exploration" /><CalabashCard
            :snap="current.calabash"
          /></div></template
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
      /><WuwaResources
        v-else-if="section === 'resources'"
        :snap="current.resources"
        :account-key="accountKey"
      /><template v-else-if="accountKey"
        ><WuwaGacha
          v-if="section === 'gacha'"
          :account-key="accountKey" /><WuwaHistory
          v-if="section === 'history'"
          :account-key="accountKey"
          :role-names="roleNames"
      /></template>
      <p v-else class="wuwa-panel">
        尚未读取到当前账号标识，请刷新数据后重试。
      </p>
    </div>
  </div>
</template>
<style src="../wuwa.css"></style>
