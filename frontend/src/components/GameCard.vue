<script setup>
import { computed, ref } from 'vue'
import { gameStyle, gameVars } from '../dashboard.js'
import { vGlide, vParallax } from '../motion.js'
import { lazyPage } from '../lazy-page.js'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import ArtworkImage from './ArtworkImage.vue'
import { gameBanner } from '../game-visuals.js'
import AnnouncementList from './AnnouncementList.vue'
const NteDataCard = lazyPage(() => import('./NteDataCard.vue'))
const NteAssetsPanel = lazyPage(() => import('./NteAssetsPanel.vue'))
const NteRolesPanel = lazyPage(() => import('./NteRolesPanel.vue'))
const NteGachaPanel = lazyPage(() => import('./NteGachaPanel.vue'))
const EndfieldDashboard = lazyPage(() => import('./EndfieldDashboard.vue'))
const WuwaDashboard = lazyPage(() => import('./WuwaDashboard.vue'))
const NteModuleCard = lazyPage(() => import('./NteModuleCard.vue'))

// Only the local workbench shows League of Legends; the cloud never loads this dashboard or its esports tables.
const LolDashboard = lazyPage(() => import('./LolDashboard.vue'))

const props = defineProps({
  cloudAccount: Object,
  authAccount: Object,
  cloudRole: String,
  cloudScope: Object,
  cloudSources: Object,
  sourceSnapshots: Object,
  isAdmin: Boolean,
  esportsBrowse: Object,
  game: { type: Object, required: true },
  externalSnapshots: { type: Object, required: true },
  externalRefreshing: { type: Boolean, default: false },
  externalError: { type: String, default: '' },
  initialSection: { type: String, default: 'all' },
  collectionStatus: { type: Array, default: () => [] },
})
const emit = defineEmits(['refresh', 'calendar', 'esports-snapshot', 'esports-browse'])
const reauthorizationRequired = computed(() => props.cloudAccount?.state === 'expired' || props.collectionStatus.some(row => row.game_id === props.game.game_id && row.state === 'auth_expired'))
const errorNotice = computed(() => reauthorizationRequired.value ? '社区授权已失效，请到社区账号重新登录。' : props.externalError ? '暂时无法更新数据，请稍后重试。' : '')
const activeSection = ref(props.game.game_id==='nte' && props.initialSection==='guides'?'characters':props.initialSection)
const style = computed(() => gameStyle(props.game.game_id))
const banner = computed(() => gameBanner(props.game.game_id, props.externalSnapshots))
// The hero names whose data this is: the game role's nickname and level. Endfield's account
// snapshot is the Hypergryph passport, which stays apart from the Skland role, so it is not shown.
const identity = computed(() => {
  if (!['wuthering_waves', 'nte'].includes(props.game.game_id)) return ''
  const account = props.externalSnapshots.account?.payload
  if (!account || typeof account !== 'object') return ''
  return [account.nickname, Number.isFinite(account.level) ? `Lv.${account.level}` : ''].filter(Boolean).join(' · ')
})
const groups = computed(() => [
  { id: 'all', label: '全部', caps: props.game.capabilities },
  { id: 'overview', label: '概览', caps: ['account', 'stamina', 'progress', 'record'] },
  { id: 'characters', label: '角色', caps: ['roles', 'calabash'] },
  { id: 'assets', label: '房产、载具与探索', caps: ['realestate', 'vehicles', 'exploration'] },
  { id: 'teams', label: '官方配队', caps: ['teams'] },
  { id: 'gacha', label: '抽卡统计', caps: ['gacha'] },
  { id: 'news', label: '公告与资讯', caps: ['announcement', 'news'] },
].filter(group => group.caps.some(cap => cap !== 'events' && props.game.capabilities.includes(cap))))
// 「全部」按页签顺序排（概览类在前、对局和公告在后），不按后端能力列表的顺序。
const TAB_ORDER = groups => groups.filter(group => group.id !== 'all').flatMap(group => group.caps)
const visibleCaps = computed(() => {
  const current = groups.value.find(group => group.id === activeSection.value) || groups.value[0]
  const caps = props.game.capabilities.filter(cap => !['events', 'announcement', 'news'].includes(cap) && current?.caps.includes(cap))
  if (current?.id !== 'all') return caps
  const order = TAB_ORDER(groups.value)
  const rank = cap => (order.includes(cap) ? order.indexOf(cap) : order.length)
  return caps.map((cap, index) => ({ cap, index })).sort((a, b) => rank(a.cap) - rank(b.cap) || a.index - b.index).map(item => item.cap)
})

// Wuwa, LoL and Endfield have their own dashboards; this grid only serves NTE.
function capComponent(cap) {
  if (props.game.game_id !== 'nte') return null
  if (['realestate', 'vehicles', 'teams'].includes(cap)) return NteAssetsPanel
  if (cap === 'gacha') return NteGachaPanel
  if (['account', 'stamina', 'progress', 'exploration', 'record'].includes(cap)) return NteDataCard
  return null
}

// Each panel gets only the props it declares; anything else would land on its
// root element as an attribute (roles="[object Object],…").
function capProps(cap) {
  const snaps = props.externalSnapshots
  const offered = {
    snap: snaps[cap],
    capability: cap,
    accountId: props.cloudScope ? `${props.cloudScope.account_id}:${props.cloudScope.role_id}` : ['nte', 'endfield'].includes(props.game.game_id) ? snaps.account?.payload?.role_id || '' : '',
    roles: snaps.roles?.payload?.entries || [],
  }
  // Async wrappers do not expose the loaded component's prop declarations.
  const declared = cap === 'gacha' ? ['snap','accountId','roles']
      : ['realestate','vehicles','teams'].includes(cap) ? ['snap','capability','roles']
        : ['snap','capability']
  return Object.fromEntries(Object.entries(offered).filter(([key]) => declared.includes(key)))
}
</script>

<template>
  <section class="game-card game-theme" :class="`game-${game.game_id}`" :style="gameVars(game.game_id)">
    <div v-if="errorNotice" class="error-bar" role="alert">
      {{ errorNotice }}
    </div>

    <header v-parallax class="card-head game-hero">
      <ArtworkImage class="game-backdrop" :candidates="banner" decorative loading="eager" />
      <span class="hero-mark-art plx-layer" aria-hidden="true"><GameIcon class="hero-big-mark" :game-id="game.game_id" /></span>
      <div class="game-heading"><GameIcon class="detail-monogram" :game-id="game.game_id" :name="game.display_name" /><div><p class="game-en" aria-hidden="true">{{ style.english }}</p><h1 class="game-name">{{ game.display_name }}</h1><p v-if="identity" class="game-identity-line">{{ identity }}</p></div></div>
      <span
        v-if="!game.credentials_configured && game.game_id !== 'endfield'"
        class="badge badge-danger"
      >
        未登录
      </span>
      <button
        type="button"
        class="ui-button refresh-btn"
        :disabled="externalRefreshing"
        @click="emit('refresh')"
      >
        <AppIcon name="refresh" :size="15" :class="{ spinning: externalRefreshing }" /><span :class="{ 't-shimmer': externalRefreshing }">{{ externalRefreshing ? '刷新中…' : '刷新数据' }}</span>
      </button>
    </header>
    <div v-if="!['wuthering_waves','league_of_legends','endfield'].includes(game.game_id)" class="detail-navigation"><nav v-glide class="detail-tabs segmented" aria-label="游戏数据分区"><button v-for="group in groups" :key="group.id" type="button" :aria-pressed="activeSection === group.id" :class="{ active: activeSection === group.id }" @click="activeSection = group.id">{{ group.label }}</button></nav><button v-if="game.capabilities.includes('events')" class="text-link" @click="emit('calendar')"><AppIcon name="calendar" :size="15" />活动日历 <AppIcon name="arrow" :size="15" /></button></div>
    <WuwaDashboard v-if="game.game_id === 'wuthering_waves'" :snaps="externalSnapshots" :configured="game.credentials_configured" :initial-section="initialSection" @calendar="emit('calendar')" />
    <LolDashboard v-else-if="game.game_id === 'league_of_legends'" :snaps="externalSnapshots" :esports-browse="esportsBrowse" @esports-snapshot="emit('esports-snapshot', $event)" @esports-browse="emit('esports-browse', $event)" @refresh="emit('refresh')" />
    <EndfieldDashboard v-else-if="game.game_id === 'endfield'" :snaps="externalSnapshots" :configured="game.credentials_configured" :auth-account="authAccount" :refreshing="externalRefreshing" :initial-section="initialSection" :cloud-account="cloudAccount" :cloud-role="cloudRole" :cloud-sources="cloudSources" :source-snapshots="sourceSnapshots" :is-admin="isAdmin" @calendar="emit('calendar')" @refresh="emit('refresh')" />

    <div v-else class="cap-list">
      <template v-for="cap in visibleCaps" :key="cap">
        <NteRolesPanel v-if="cap==='roles'" :snap="externalSnapshots.roles" :account-id="cloudScope || externalSnapshots.account?.payload?.role_id || ''" :initial-guide-browser="initialSection==='guides'" :can-maintain="!cloudAccount || isAdmin" />
        <NteModuleCard v-else-if="capComponent(cap)" :capability="cap" :snap="externalSnapshots[cap]" :artwork="cap === 'account' ? banner : []" :account-id="externalSnapshots.account?.payload?.role_id || ''" :class="['detail-cap', `detail-cap-${cap}`]">
          <component :is="capComponent(cap)" v-bind="capProps(cap)" />
        </NteModuleCard>
      </template>
      <AnnouncementList v-if="['all', 'news'].includes(activeSection) && game.capabilities.some(cap => ['announcement', 'news'].includes(cap))" class="detail-articles" :game-id="game.game_id" :snap="externalSnapshots.news?.payload ? externalSnapshots.news : externalSnapshots.announcement" />
    </div>
  </section>
</template>

<style scoped>
.detail-articles{grid-column:1/-1}
.game-card {
  min-width: 0;
}

.error-bar {
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger);
  padding: 12px 16px;
  font-size: 13px;
  border-radius: var(--radius-well);
  margin-bottom: 20px;
  overflow-wrap: anywhere;
}

/* Hero: the game's pale tone inside a white frame (game-manage-ui-v1), its mark tile
   bleeding off the bottom edge and drifting a little against the scroll. */
.card-head { position:relative; display:flex; align-items:center; gap:10px 12px; min-height:160px; margin-bottom:22px; padding:24px 26px; flex-wrap:wrap; overflow:hidden; isolation:isolate; border:6px solid var(--card-bg); border-radius:26px; color:var(--text); background:var(--game-tone); box-shadow:0 0 0 1px var(--card-border), var(--card-shadow); }
.hero-mark-art { --plx-range:-10px; position:absolute; right:clamp(150px, 24%, 300px); bottom:-36px; z-index:-1; pointer-events:none; }
.hero-big-mark { width:132px; height:132px; border-radius:34px; background:var(--card-bg); box-shadow:0 18px 40px -22px rgba(38, 40, 46, .4); transform:rotate(-9deg); color:var(--game-accent); font-size:56px; font-weight:600; }
.game-en { color:var(--game-accent); font-size:11px; font-weight:600; letter-spacing:1.5px; line-height:16px; }
.card-head > :not(.hero-mark-art):not(.game-backdrop) { position:relative; }
.game-backdrop { position:absolute; inset:0 0 0 auto; width:78%; height:100%; object-position:center 38%; z-index:-2; }
.card-head:has(.game-backdrop)::after { content:''; position:absolute; inset:0; z-index:-1; pointer-events:none; background:linear-gradient(90deg,var(--game-tone) 12%,color-mix(in srgb,var(--game-tone) 94%,transparent) 34%,color-mix(in srgb,var(--game-tone) 22%,transparent) 78%); }
.card-head:has(.game-backdrop) .hero-mark-art { display:none; }
.game-heading { display:flex; align-items:center; gap:16px; margin-right:auto; min-width:0; }
.detail-monogram { display:grid; place-items:center; width:56px; height:56px; border:3px solid var(--card-bg); border-radius:16px; background:var(--card-bg); box-shadow:0 0 0 1px var(--card-border); font-size:24px; font-weight:600; }
.game-name { font-size:30px; line-height:38px; font-weight:600; letter-spacing:-.03em; }
.game-identity-line { margin-top:2px; color:var(--game-accent); font-size:13px; }

.cap-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}
.detail-navigation { display:flex; justify-content:space-between; gap:10px 16px; align-items:center; margin:0 0 16px; flex-wrap:wrap; }
@media(max-width:960px) { .cap-list { grid-template-columns:1fr; } }
@media(max-width:600px) {
  .card-head { min-height:150px; margin-bottom:16px; padding:20px 18px; gap:12px; border-radius:24px; }
  .hero-mark-art { right:-14px; bottom:-40px; scale:.7; transform-origin:100% 100%; }
  .game-heading { gap:12px; flex-basis:100%; }
  .game-name { font-size:26px; line-height:32px; }
  .detail-monogram { width:44px; height:44px; font-size:20px; border-radius:13px; }
  .detail-tabs button { padding:4px 10px; }
  .game-backdrop { width:100%; object-position:65% center; }
  .card-head:has(.game-backdrop)::after { background:linear-gradient(90deg,var(--game-tone),color-mix(in srgb,var(--game-tone) 86%,transparent) 46%,color-mix(in srgb,var(--game-tone) 35%,transparent)); }
}
</style>
