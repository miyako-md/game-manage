<script setup>
import { computed, ref } from 'vue'
import { gameStyle } from '../dashboard.js'
import { vGlide } from '../motion.js'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import SourceStatusPanel from './SourceStatusPanel.vue'
import AccountCard from './AccountCard.vue'
import AnnouncementList from './AnnouncementList.vue'
import CalabashCard from './CalabashCard.vue'
import ExplorationCard from './ExplorationCard.vue'
import MatchList from './MatchList.vue'
import NteDataCard from './NteDataCard.vue'
import NteAssetsPanel from './NteAssetsPanel.vue'
import NteRolesPanel from './NteRolesPanel.vue'
import NteGachaPanel from './NteGachaPanel.vue'
import ProgressCard from './ProgressCard.vue'
import StaminaCard from './StaminaCard.vue'
import StatsCard from './StatsCard.vue'
import WuwaDashboard from './WuwaDashboard.vue'

const props = defineProps({
  game: { type: Object, required: true },
  externalSnapshots: { type: Object, required: true },
  externalRefreshing: { type: Boolean, default: false },
  externalError: { type: String, default: '' },
  initialSection: { type: String, default: 'all' },
  collectionStatus: { type: Array, default: () => [] },
})
const emit = defineEmits(['refresh', 'calendar'])
const activeSection = ref(props.initialSection)
const style = computed(() => gameStyle(props.game.game_id))
const groups = computed(() => [
  { id: 'all', label: '全部', caps: props.game.capabilities },
  { id: 'overview', label: '概览', caps: ['account', 'stamina', 'progress', 'stats', 'record'] },
  { id: 'characters', label: '角色与探索', caps: ['roles', 'exploration', 'calabash'] },
  { id: 'assets', label: '房产与载具', caps: ['realestate', 'vehicles'] },
  { id: 'teams', label: '官方配队', caps: ['teams'] },
  { id: 'matches', label: '近期对局', caps: ['match'] },
  { id: 'gacha', label: '抽卡统计', caps: ['gacha'] },
  { id: 'news', label: '公告与资讯', caps: ['announcement', 'news'] },
].filter(group => group.caps.some(cap => cap !== 'events' && props.game.capabilities.includes(cap))))
// 「全部」按页签顺序排（概览类在前、对局和公告在后），不按后端能力列表的顺序。
const TAB_ORDER = groups => groups.filter(group => group.id !== 'all').flatMap(group => group.caps)
const visibleCaps = computed(() => {
  const current = groups.value.find(group => group.id === activeSection.value) || groups.value[0]
  const caps = props.game.capabilities.filter(cap => cap !== 'events' && current?.caps.includes(cap))
  if (current?.id !== 'all') return caps
  const order = TAB_ORDER(groups.value)
  const rank = cap => (order.includes(cap) ? order.indexOf(cap) : order.length)
  return caps.map((cap, index) => ({ cap, index })).sort((a, b) => rank(a.cap) - rank(b.cap) || a.index - b.index).map(item => item.cap)
})

const CAP_COMPONENTS = {
  stamina: StaminaCard,
  account: AccountCard,
  progress: ProgressCard,
  announcement: AnnouncementList,
  news: AnnouncementList,
  match: MatchList,
  stats: StatsCard,
  exploration: ExplorationCard,
  calabash: CalabashCard,
}

function capComponent(cap) {
  if (props.game.game_id === 'nte' && ['realestate', 'vehicles', 'teams'].includes(cap)) return NteAssetsPanel
  if (props.game.game_id === 'nte' && cap === 'roles') return NteRolesPanel
  if (props.game.game_id === 'nte' && cap === 'gacha') return NteGachaPanel
  if (props.game.game_id === 'nte' && ['account', 'stamina', 'progress', 'exploration', 'record'].includes(cap)) return NteDataCard
  return CAP_COMPONENTS[cap] || null
}

// Each panel gets only the props it declares; anything else would land on its
// root element as an attribute (roles="[object Object],…").
function capProps(cap) {
  const snaps = props.externalSnapshots
  const offered = {
    snap: snaps[cap],
    gameId: props.game.game_id,
    capability: cap,
    accountId: props.game.game_id === 'nte' ? snaps.account?.payload?.role_id || '' : '',
    roles: snaps.roles?.payload?.entries || [],
    stats: snaps.stats?.payload ?? null,
  }
  const declared = capComponent(cap)?.props ?? {}
  return Object.fromEntries(Object.entries(offered).filter(([key]) => key in declared))
}
</script>

<template>
  <section class="game-card" :class="`game-${game.game_id}`">
    <div v-if="externalError" class="error-bar" role="alert">
      {{ externalError }}
    </div>

    <header class="card-head">
      <div class="game-heading"><GameIcon class="detail-monogram" :game-id="game.game_id" :name="game.display_name" /><div><p class="eyebrow">{{ style.english }}</p><h1 class="game-name">{{ game.display_name }}</h1></div></div>
      <span
        v-if="!game.credentials_configured"
        class="badge badge-danger"
      >
        未配置凭据
      </span>
      <SourceStatusPanel :game="game" :collection="collectionStatus" />
      <button
        type="button"
        class="ui-button refresh-btn"
        :disabled="externalRefreshing"
        @click="emit('refresh')"
      >
        <AppIcon name="refresh" :size="15" :class="{ spinning: externalRefreshing }" /><span :class="{ 't-shimmer': externalRefreshing }">{{ externalRefreshing ? '刷新中…' : '刷新数据' }}</span>
      </button>
    </header>
    <div v-if="game.game_id !== 'wuthering_waves'" class="detail-navigation"><nav v-glide class="detail-tabs segmented" aria-label="游戏数据分区"><button v-for="group in groups" :key="group.id" type="button" :aria-pressed="activeSection === group.id" :class="{ active: activeSection === group.id }" @click="activeSection = group.id">{{ group.label }}</button></nav><button v-if="game.capabilities.includes('events')" class="text-link" @click="emit('calendar')"><AppIcon name="calendar" :size="15" />活动日历 <AppIcon name="arrow" :size="15" /></button></div>
    <WuwaDashboard v-if="game.game_id === 'wuthering_waves'" :snaps="externalSnapshots" :configured="game.credentials_configured" :initial-section="initialSection" @calendar="emit('calendar')" />
    <div v-else class="cap-list">
      <template v-for="(cap, index) in visibleCaps" :key="cap">
        <component
          :is="capComponent(cap)"
          v-if="capComponent(cap)"
          v-bind="capProps(cap)"
          :class="['detail-cap', 't-item', `detail-cap-${cap}`]"
          :style="{ '--i': index }"
        />
        <div v-else class="cap-card cap-coming">敬请期待</div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.detail-cap-realestate, .detail-cap-vehicles, .detail-cap-teams, .detail-cap-roles, .detail-cap-gacha, .detail-cap-match, .detail-cap-exploration { grid-column: 1 / -1; }
.game-card {
  min-width: 0;
}

.error-bar {
  background: var(--danger-bg);
  border: 1px solid var(--danger-border);
  color: var(--danger);
  padding: 12px 16px;
  font-size: 12px;
  border-radius: 10px;
  margin-bottom: 20px;
  overflow-wrap: anywhere;
}

.card-head { display:flex; align-items:center; gap:8px 10px; padding:0 0 14px; margin-bottom:16px; border-bottom:1px solid var(--border); flex-wrap:wrap; }
.game-heading { display:flex; align-items:center; gap:12px; margin-right:auto; min-width:0; }
.detail-monogram { display:grid; place-items:center; font-size:22px; width:40px; height:40px; border-radius:10px; box-shadow:0 1px 2px rgba(16, 24, 40, .06); }
.game-name { margin-top:2px; font-size:24px; line-height:30px; font-weight:700; letter-spacing:-.02em; }

.cap-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: start;
}
.detail-navigation { display:flex; justify-content:space-between; gap:10px 16px; align-items:center; margin:0 0 16px; flex-wrap:wrap; }
/* 英雄联盟 has one short identity card and one wide stats card: stack them full width. */
.game-league_of_legends .detail-cap-account,.game-league_of_legends .detail-cap-stats { grid-column:1/-1; }
@media(max-width:950px) { .cap-list { grid-template-columns:1fr; } }
@media(max-width:600px) { .card-head { padding-bottom:12px; margin-bottom:14px; }.game-heading { gap:10px; flex-basis:100%; }.game-name { font-size:22px; line-height:28px; }.detail-monogram { width:36px; height:36px; font-size:20px; }.detail-tabs button { padding:4px 9px; } }

.cap-coming {
  color: var(--text-muted);
  text-align: center;
}
</style>
