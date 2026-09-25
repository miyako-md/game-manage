<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getSnapshot, refreshGame } from '../api.js'
import { gameStyle } from '../dashboard.js'
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
import EndfieldGachaPanel from './EndfieldGachaPanel.vue'
import ProgressCard from './ProgressCard.vue'
import RoleWallCard from './RoleWallCard.vue'
import StaminaCard from './StaminaCard.vue'
import StatsCard from './StatsCard.vue'
import WuwaDashboard from './WuwaDashboard.vue'

const props = defineProps({
  game: { type: Object, required: true },
  externalSnapshots: { type: Object, default: null },
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
const visibleCaps = computed(() => {
  const current = groups.value.find(group => group.id === activeSection.value) || groups.value[0]
  return props.game.capabilities.filter(cap => cap !== 'events' && current?.caps.includes(cap))
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
  roles: RoleWallCard,
}

const localSnaps = ref({})
const snaps = computed(() => props.externalSnapshots ?? localSnaps.value)
const refreshing = ref(false)
const refreshError = ref('')
const isRefreshing = computed(() => props.externalSnapshots !== null ? props.externalRefreshing : refreshing.value)
const displayedError = computed(() => props.externalError || refreshError.value)
let generation = 0
let disposed = false
let errorTimer = null

function capComponent(cap) {
  if (props.game.game_id === 'nte' && ['realestate', 'vehicles', 'teams'].includes(cap)) return NteAssetsPanel
  if (props.game.game_id === 'nte' && cap === 'roles') return NteRolesPanel
  if (props.game.game_id === 'nte' && cap === 'gacha') return NteGachaPanel
  if (props.game.game_id === 'endfield' && cap === 'gacha') return EndfieldGachaPanel
  if (props.game.game_id === 'nte' && ['account', 'stamina', 'progress', 'exploration', 'record'].includes(cap)) return NteDataCard
  return CAP_COMPONENTS[cap] || null
}

async function loadSnapshots() {
  if (props.externalSnapshots !== null) return
  const request = ++generation
  const caps = props.game.capabilities || []
  const results = await Promise.allSettled(
    caps.map((cap) => getSnapshot(props.game.game_id, cap)),
  )
  if (disposed || request !== generation) return
  const next = { ...localSnaps.value }
  caps.forEach((cap, i) => {
    if (results[i].status === 'fulfilled') next[cap] = results[i].value
  })
  localSnaps.value = next
}

function showError(message) {
  refreshError.value = message
  if (errorTimer) clearTimeout(errorTimer)
  errorTimer = setTimeout(() => {
    refreshError.value = ''
  }, 10000)
}

async function onRefresh() {
  if (props.externalSnapshots !== null) { emit('refresh'); return }
  if (refreshing.value) return
  refreshing.value = true
  try {
    const data = await refreshGame(props.game.game_id)
    const failed = Object.entries(data?.results || {}).filter(
      ([, r]) => !r || r.ok !== true,
    )
    if (failed.length > 0) {
      showError(
        '刷新失败：' +
          failed.map(([, r]) => r?.error || '未知错误').join('；'),
      )
    }
  } catch (e) {
    showError('刷新失败：' + (e?.message || '请求异常'))
  } finally {
    refreshing.value = false
    await loadSnapshots()
  }
}

onMounted(loadSnapshots)

onBeforeUnmount(() => {
  disposed = true
  generation += 1
  if (errorTimer) clearTimeout(errorTimer)
})
</script>

<template>
  <section class="game-card">
    <div v-if="displayedError" class="error-bar" role="alert">
      {{ displayedError }}
    </div>

    <header class="card-head">
      <div class="game-heading"><GameIcon class="detail-monogram" :game-id="game.game_id" :name="game.display_name" /><div><p class="eyebrow">{{ style.english }}</p><h1 class="game-name">{{ game.display_name }}</h1></div></div>
      <span
        v-if="!game.credentials_configured"
        class="badge badge-danger"
      >
        未配置凭据
      </span>
      <button
        type="button"
        class="refresh-btn"
        :disabled="isRefreshing"
        @click="onRefresh"
      >
        <AppIcon name="refresh" :size="15" :class="{ spinning: isRefreshing }" />{{ isRefreshing ? '刷新中…' : '刷新数据' }}
      </button>
    </header>

    <SourceStatusPanel v-if="externalSnapshots !== null" :game="game" :collection="collectionStatus" />
    <div v-if="game.game_id !== 'wuthering_waves'" class="detail-navigation"><nav class="detail-tabs" aria-label="游戏数据分区"><button v-for="group in groups" :key="group.id" type="button" :aria-pressed="activeSection === group.id" :class="{ active: activeSection === group.id }" @click="activeSection = group.id">{{ group.label }}</button></nav><button v-if="game.capabilities.includes('events')" class="text-link" @click="emit('calendar')"><AppIcon name="calendar" :size="15" />活动日历 <AppIcon name="arrow" :size="15" /></button></div>
    <WuwaDashboard v-if="game.game_id === 'wuthering_waves'" :snaps="snaps" :configured="game.credentials_configured" :initial-section="initialSection" @calendar="emit('calendar')" />
    <div v-else class="cap-list">
      <template v-for="cap in visibleCaps" :key="cap">
        <component
          :is="capComponent(cap)"
          v-if="capComponent(cap)"
          :snap="snaps[cap]"
          :game-id="game.game_id"
          :capability="cap"
          :account-id="['nte', 'endfield'].includes(game.game_id) ? snaps.account?.payload?.role_id || '' : ''"
          :roles="snaps.roles?.payload?.entries || []"
          :class="['detail-cap', `detail-cap-${cap}`]"
        />
        <div v-else class="cap-card cap-coming">敬请期待</div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.detail-cap-realestate, .detail-cap-vehicles, .detail-cap-teams, .detail-cap-roles, .detail-cap-gacha { grid-column: 1 / -1; }
.game-card {
  min-width: 0;
}

.error-bar {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 13px 16px;
  font-size: 12px;
  border-radius: 7px;
  margin-bottom: 20px;
  overflow-wrap: anywhere;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 0 28px;
  flex-wrap: wrap;
}
.game-heading { display:flex; align-items:center; gap:17px; margin-right:auto; }
.detail-monogram { display:grid; place-items:center; font-size:32px; width:58px; height:58px; border:1px solid var(--border); border-radius:10px; background:var(--card-bg); }
.game-heading .eyebrow { font-size:9px; }

.game-name {
  font-size: 30px;
  font-weight: 550;
  margin-top: 5px;
}

.refresh-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  padding: 9px 13px;
  border-radius: 6px;
  cursor: pointer;
  display: inline-flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.cap-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
}
.detail-navigation { display:flex; justify-content:space-between; gap:15px; align-items:center; border-bottom:1px solid var(--border); margin-bottom:25px; flex-wrap:wrap; }
.detail-tabs { display:flex; gap:5px; flex-wrap:wrap; }.detail-tabs button { color:var(--text-muted); background:none; border:0; padding:11px 13px; font-size:12px; border-bottom:2px solid transparent; }.detail-tabs button.active { color:var(--accent); border-bottom-color:var(--accent); }
.detail-cap-roles,.detail-cap-match,.detail-cap-gacha,.detail-cap-exploration { grid-column:1/-1; }
.detail-cap-match :deep(.item-main),.detail-cap-match :deep(.item-sub) { font-size:13px; }
.detail-cap-roles :deep(.role-grid) { grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); }
.detail-cap-roles:not(.nte-card):not(.nte-roles-panel) :deep(.role-grid) { grid-template-columns:repeat(auto-fill,minmax(92px,1fr)); }
@media(max-width:950px) { .cap-list { grid-template-columns:1fr; gap:16px; } }
@media(max-width:600px) { .card-head { gap:12px; }.game-heading { gap:11px; }.game-name { font-size:25px; }.detail-monogram { width:43px; height:43px; font-size:25px; }.detail-tabs button { padding:10px 8px; font-size:11px; }.detail-navigation>.text-link { margin-bottom:12px; }.game-heading .eyebrow { font-size:8px; letter-spacing:.7px; } }

.cap-coming {
  color: var(--text-muted);
  text-align: center;
}
</style>
