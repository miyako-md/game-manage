<script setup>
import { computed, ref } from 'vue'
import WuwaProfile from './WuwaProfile.vue'
import WuwaRoles from './WuwaRoles.vue'
import WuwaCombat from './WuwaCombat.vue'
import WuwaActivities from './WuwaActivities.vue'
import WuwaResources from './WuwaResources.vue'
import WuwaGacha from './WuwaGacha.vue'
import WuwaHistory from './WuwaHistory.vue'
import WuwaHistorySummary from './WuwaHistorySummary.vue'
import StaminaCard from './StaminaCard.vue'
import ExplorationCard from './ExplorationCard.vue'
import CalabashCard from './CalabashCard.vue'
import ProgressCard from './ProgressCard.vue'
import AnnouncementList from './AnnouncementList.vue'
import AppIcon from './AppIcon.vue'
import RingGauge from './RingGauge.vue'
import { vGlide, vParallax, vReveal } from '../motion.js'
import { characterIcon } from '../wuwa-icons.js'
import { gameBanner, roleArtwork } from '../game-visuals.js'
import ArtworkImage from './ArtworkImage.vue'
import WuwaModuleCard from './WuwaModuleCard.vue'
import { count, fieldLabels, value } from '../wuwa-display.js'
import { expProgress } from '../wuwa-charts.js'
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
// The account card: level on an experience ring, then the headline counts.
const account = computed(() => current.value.account?.payload ?? null)
const profile = computed(() => account.value?.extra?.profile || {})
const exp = computed(() => expProgress(profile.value))
const levelName = computed(() => profile.value.level_name || '联觉等级')
const accountStats = ['world_level', 'active_days', 'achievement_count', 'achievement_star']
// The current lead role lends its portrait to the card; it drifts a little as the page scrolls.
const portrait = computed(() => {
  const roles = Array.isArray(current.value.roles?.payload) ? current.value.roles.payload : []
  const main = roles.find((role) => role?.extra?.is_main_role === true)
  return main ? [...roleArtwork(main), characterIcon(main.role_id)] : []
})
const banner = computed(() => gameBanner('wuthering_waves', props.snaps))
const activeRead = computed(() => current.value[({gacha:'account',history:'account'})[section.value] || section.value])
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
      <p v-else-if="!configured" class="wuwa-panel wuwa-empty">
        请先登录鸣潮账号。
      </p>
      <p v-else-if="section !== 'profile' && activeRead?.reading && !activeRead?.payload" class="wuwa-panel" role="status">正在读取数据…</p>
      <p v-else-if="section !== 'profile' && activeRead?.readError && !activeRead?.payload" class="wuwa-panel" role="status">{{ activeRead.readError }}</p>
      <div v-else-if="section === 'profile'" class="wuwa-bento">
        <WuwaModuleCard v-reveal v-parallax class="span-7 profile-account is-hero" title="账号档案" :snap="current.account" :sheet-width="640">
          <template #preview>
            <ArtworkImage class="profile-backdrop" :candidates="banner" decorative />
            <div class="account-hero">
              <RingGauge :value="exp?.cur" :max="exp?.max" :label="`${levelName}经验`" :size="116" :stroke="10" color="var(--game-vivid, var(--accent))">
                <small class="ring-cap">{{ levelName }}</small>
                <b class="ring-value">{{ value(account?.level) }}</b>
              </RingGauge>
              <div class="account-copy">
                <p class="account-name">{{ account?.nickname || '漂泊者档案' }}</p>
                <p v-if="exp" class="account-exp">经验 {{ count(exp.cur) }} / {{ count(exp.max) }}</p>
              </div>
              <ArtworkImage class="account-portrait plx-layer" :style="{ '--plx-range': '-18px' }" :candidates="portrait" decorative />
            </div>
            <dl class="wuwa-stats">
              <div v-for="key in accountStats" :key="key" class="wuwa-stat">
                <dt>{{ fieldLabels[key] }}</dt>
                <dd>{{ count(profile[key]) }}</dd>
              </div>
            </dl>
          </template>
          <WuwaProfile :snap="current.account" />
        </WuwaModuleCard>
        <WuwaModuleCard v-reveal class="span-5 profile-stamina" title="体力" inline :snap="current.stamina">
          <StaminaCard label="结晶波片" :snap="current.stamina" />
        </WuwaModuleCard>
        <WuwaModuleCard v-reveal class="span-8" title="周期进度" inline :snap="current.progress">
          <ProgressCard :snap="current.progress" />
        </WuwaModuleCard>
        <WuwaModuleCard v-reveal class="span-4" title="数据坞" inline :snap="current.calabash">
          <CalabashCard :snap="current.calabash" />
        </WuwaModuleCard>
        <WuwaModuleCard v-reveal class="span-12" title="探索收集" :snap="current.exploration" :sheet-width="640">
          <template #preview><ExplorationCard compact :snap="current.exploration" /></template>
          <ExplorationCard :snap="current.exploration" />
        </WuwaModuleCard>
      </div>
      <WuwaRoles
        v-else-if="section === 'roles'"
        :snap="current.roles"
        :account-key="accountKey"
      />
      <WuwaCombat
        v-else-if="section === 'combat'"
        :snap="current.combat"
        :role-names="roleNames"
      />
      <WuwaActivities
        v-else-if="section === 'activities'"
        :snap="current.activities"
      />
      <WuwaResources v-else-if="section === 'resources'" :snap="current.resources" :account-key="accountKey" />
      <template v-else-if="accountKey">
        <WuwaModuleCard v-if="section === 'gacha'" v-reveal class="wuwa-launcher is-hero" title="抽卡历史" primary :sheet-width="960">
          <template #preview><p class="wuwa-launcher-copy">导入官方记录后，按卡池查看抽数分布、五星记录和当前垫抽。</p></template>
          <WuwaGacha :account-key="accountKey" />
        </WuwaModuleCard>
        <WuwaModuleCard v-if="section === 'history'" v-reveal class="wuwa-launcher is-hero" title="成长记录" primary :sheet-width="820">
          <template #preview><WuwaHistorySummary :account-key="accountKey" :combat="current.combat" /></template>
          <WuwaHistory :account-key="accountKey" :role-names="roleNames" />
        </WuwaModuleCard>
      </template>
      <p v-else class="wuwa-panel wuwa-empty">
        尚未读取到账号信息，请刷新数据。
      </p>
    </div>
  </div>
</template>
<style scoped>
.profile-account { position:relative; isolation:isolate; overflow:hidden; }
.profile-backdrop { position:absolute; inset:0; width:100%; height:100%; z-index:-2; object-position:70% center; }
.profile-account:has(.profile-backdrop)::after { content:''; position:absolute; inset:0; z-index:-1; pointer-events:none; background:linear-gradient(90deg,var(--game-tone) 10%,color-mix(in srgb,var(--game-tone) 92%,transparent) 46%,color-mix(in srgb,var(--game-tone) 40%,transparent)),linear-gradient(0deg,var(--game-tone),transparent 70%); }
</style>
<style src="../wuwa.css"></style>
