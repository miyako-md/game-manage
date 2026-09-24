<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as api from './api.js'
import { getAuthStatus } from './auth-api.js'
import { createDashboard, readRoute } from './dashboard.js'
import { vGlide } from './motion.js'
import AppIcon from './components/AppIcon.vue'
import GameIcon from './components/GameIcon.vue'
import OverviewPage from './components/OverviewPage.vue'
import CalendarPage from './components/CalendarPage.vue'
import GameCard from './components/GameCard.vue'
import LoginPanel from './components/LoginPanel.vue'
import BilibiliSourcePanel from './components/BilibiliSourcePanel.vue'

const dashboard = createDashboard({ ...api, getAuthStatus })
const state = dashboard.state
const route = ref(readRoute(window.location.hash))
const menuOpen = ref(false)
const navigationMedia = window.matchMedia('(max-width: 720px)')
const mobileNavigation = ref(navigationMedia.matches)
const sidebar = ref(null)
const menuToggle = ref(null)
const mainContent = ref(null)
const now = ref(Date.now())
const accountRevisions = ref({})
const selectedGame = computed(() => state.games.find(game => game.game_id === route.value.game))
const pageTitle = computed(() => ({ overview: '今日总览', calendar: '活动日历', accounts: '社区账号', game: selectedGame.value?.display_name || '游戏档案' })[route.value.page])
const today = computed(() => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' }).format(now.value))
const refreshing = computed(() => Object.values(state.refreshing).some(Boolean))
const calendarErrors = computed(() => Object.fromEntries(state.games.map(g => {
  const source = state.collection.find(row => row.game_id === g.game_id && row.capability === 'events' && ['error', 'auth_expired'].includes(row.state))
  return [g.game_id, [state.readErrors[g.game_id], state.refreshErrors[g.game_id], source?.error].filter(Boolean).join('；')]
})))
let timer
function syncRoute() { route.value = readRoute(window.location.hash); menuOpen.value = false; window.scrollTo({ top: 0, behavior: 'instant' }); nextTick(() => mainContent.value?.focus({ preventScroll: true })) }
async function openMenu() { menuOpen.value = true; await nextTick(); sidebar.value?.querySelector('.primary-nav a')?.focus() }
async function closeMenu() { menuOpen.value = false; await nextTick(); menuToggle.value?.focus() }
function sidebarNavigate(event) {
  if (!event.target.closest?.('a[href]')) return
  menuOpen.value = false
  if (mobileNavigation.value) nextTick(() => mainContent.value?.focus({ preventScroll: true }))
}
function mediaChanged(event) { mobileNavigation.value = event.matches; if (!event.matches) menuOpen.value = false }
function navigate(page, game = '') {
  window.location.hash = page === 'game' ? `/game/${encodeURIComponent(game)}` : page === 'calendar' ? `/calendar${game ? '?game=' + encodeURIComponent(game) : ''}` : page === 'accounts' ? '/accounts' : '/'
  menuOpen.value = false
}
async function refreshAll() { if (!refreshing.value) await Promise.all(state.games.map(game => dashboard.refresh(game.game_id))) }
async function onAccountChanged({ game }) {
  dashboard.invalidateGame(game)
  accountRevisions.value = { ...accountRevisions.value, [game]: (accountRevisions.value[game] || 0) + 1 }
  await dashboard.load()
}
function handleKey(event) {
  if (event.key === 'Escape' && menuOpen.value) closeMenu()
  if (event.key === 'Tab' && menuOpen.value && mobileNavigation.value) {
    const controls = [...sidebar.value.querySelectorAll('a[href],button:not([disabled])')]
    const first = controls[0], last = controls[controls.length - 1]
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
  }
}
onMounted(() => {
  dashboard.load()
  window.addEventListener('hashchange', syncRoute)
  window.addEventListener('keydown', handleKey)
  navigationMedia.addEventListener('change', mediaChanged)
  timer = setInterval(() => { now.value = Date.now(); dashboard.loadSnapshots(); dashboard.loadStatus() }, 60000)
})
onBeforeUnmount(() => { clearInterval(timer); dashboard.dispose(); window.removeEventListener('hashchange', syncRoute); window.removeEventListener('keydown', handleKey); navigationMedia.removeEventListener('change', mediaChanged) })
</script>
<template>
  <div class="workbench" :class="{ 'menu-open': menuOpen }">
    <a class="skip-link" href="#main-content" @click.prevent="$refs.mainContent?.focus()">跳到主要内容</a>
    <button v-if="menuOpen" class="sidebar-scrim" aria-label="关闭导航" tabindex="-1" @click="closeMenu"></button>
    <aside id="workspace-sidebar" ref="sidebar" class="workspace-sidebar" :inert="mobileNavigation && !menuOpen">
      <a class="brand" href="#/" @click="sidebarNavigate"><span class="brand-symbol"><AppIcon name="spark" :size="20" /></span><span>游戏管家<small>PERSONAL GAME SPACE</small></span></a>
      <button class="mobile-sidebar-close icon-button" aria-label="关闭导航" @click="closeMenu"><AppIcon name="close" /></button>
      <nav v-glide class="primary-nav" aria-label="主导航" @click="sidebarNavigate">
        <a href="#/" :class="{ active: route.page === 'overview' }" :aria-current="route.page === 'overview' ? 'page' : undefined"><AppIcon name="grid" /><span>今日总览</span></a>
        <a href="#/calendar" :class="{ active: route.page === 'calendar' }" :aria-current="route.page === 'calendar' ? 'page' : undefined"><AppIcon name="calendar" /><span>活动日历</span></a>
        <a href="#/accounts" :class="{ active: route.page === 'accounts' }" :aria-current="route.page === 'accounts' ? 'page' : undefined"><AppIcon name="user" /><span>社区账号</span></a>
      </nav>
      <div class="sidebar-label"><span>我的游戏</span><span>{{ String(state.games.length).padStart(2, '0') }}</span></div>
      <nav v-glide class="game-nav" aria-label="游戏档案" @click="sidebarNavigate"><a v-for="game in state.games" :key="game.game_id" :href="`#/game/${encodeURIComponent(game.game_id)}`" :class="{ active: route.page === 'game' && route.game === game.game_id }" :aria-current="route.page === 'game' && route.game === game.game_id ? 'page' : undefined"><GameIcon class="nav-game-mark" :game-id="game.game_id" :name="game.display_name" /><span>{{ game.display_name }}</span><AppIcon class="nav-arrow" name="arrow" :size="14" /></a></nav>
      <div class="sidebar-bottom"><p class="local-status"><i :class="{ offline: state.loadError || state.serviceError }"></i>{{ state.loadError || state.serviceError ? '本地服务连接异常' : state.loadedAt ? '本地工作台已连接' : '正在连接本地服务' }}</p><p>{{ state.notify ? state.notify.enabled ? '微信推送已启用' : '微信推送未启用' : '提醒状态读取中' }}</p><div><AppIcon name="shield" :size="13" />个人使用 · 数据保存在本机</div></div>
    </aside>
    <div class="workspace-body" :inert="mobileNavigation && menuOpen">
      <header class="workspace-topbar"><div class="topbar-left"><button ref="menuToggle" class="menu-toggle icon-button" :aria-expanded="menuOpen" aria-controls="workspace-sidebar" aria-label="打开导航" @click="openMenu"><AppIcon name="menu" /></button><span class="breadcrumb">个人空间 <span>/</span> <b>{{ pageTitle }}</b></span></div><div class="topbar-right"><span class="topbar-date">{{ today }}</span><button class="ui-button small-button" @click="navigate('accounts')"><AppIcon name="user" :size="15" />社区账号</button></div></header>
      <main id="main-content" ref="mainContent" tabindex="-1" class="workspace-main">
        <div v-if="state.loadError" class="service-error" role="alert"><div><strong>暂时无法读取游戏数据</strong><p>{{ state.loadError }}</p></div><button class="ui-button" :disabled="state.loading" @click="dashboard.load">重试连接</button></div>
        <OverviewPage v-if="route.page === 'overview'" class="t-page" :games="state.games" :snapshots="state.snapshots" :accounts="state.accounts" :collection="state.collection" :read-errors="state.readErrors" :refresh-errors="state.refreshErrors" :refreshing="state.refreshing" :now="now" :loading="state.loading" @navigate="navigate" @refresh="refreshAll" />
        <CalendarPage v-else-if="route.page === 'calendar'" class="t-page" :games="state.games" :snapshots="state.snapshots" :loading="state.loading" :initial-game-id="route.game" :read-errors="calendarErrors" />
        <template v-else-if="route.page === 'game'"><GameCard v-if="selectedGame" class="t-page" :key="`${selectedGame.game_id}:${accountRevisions[selectedGame.game_id] || 0}`" :game="selectedGame" initial-section="overview" :collection-status="state.collection" :external-snapshots="state.snapshots[selectedGame.game_id] || {}" :external-refreshing="!!state.refreshing[selectedGame.game_id]" :external-error="state.refreshErrors[selectedGame.game_id] || state.readErrors[selectedGame.game_id] || ''" @refresh="dashboard.refresh(selectedGame.game_id)" @calendar="navigate('calendar', selectedGame.game_id)" /><div v-else class="empty-page"><p>{{ state.loading ? '正在读取游戏列表…' : '这个游戏尚未启用或已从配置中移除。' }}</p><button class="ui-button" @click="navigate('overview')">返回总览</button></div></template>
        <div v-if="route.page === 'accounts'" class="accounts-page t-page"><header class="page-heading"><p class="eyebrow">CONNECTED WORLDS</p><h1>社区账号</h1><p class="page-description">连接你的游戏世界，让账号与进度自动汇聚。</p></header><LoginPanel @account-changed="onAccountChanged" /><section class="connection-note"><AppIcon name="shield" :size="24" /><div><h2>授权只保存在本机</h2><p>鸣潮与异环使用社区手机号登录；短期凭据自动续期。英雄联盟通过本机客户端读取数据，无需在这里登录。</p><p>登录成功后，进入对应游戏点击「刷新数据」即可加载账号快照。</p></div></section></div>
        <BilibiliSourcePanel v-if="route.page === 'overview' || route.page === 'game'" :game-id="route.page === 'game' ? route.game : ''" @collected="dashboard.loadSnapshots()" />
      </main>
    </div>
  </div>
</template>
