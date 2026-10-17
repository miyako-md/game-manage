<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import * as api from './api.js'
import { getAuthStatus } from './auth-api.js'
import { createDashboard, readRoute, gameStyle, gameVars } from './dashboard.js'
import { GAME_SECTIONS } from './search-index.js'
import { vGlide } from './motion.js'
import { followSystem, setTheme, theme } from './theme.js'
import { lazyPage } from './lazy-page.js'
import { useFloatingNavigation } from './floating-navigation.js'
import { useElasticCards } from './elastic-cards.js'
import AppIcon from './components/AppIcon.vue'
import SystemUpdateControl from './components/SystemUpdateControl.vue'
import GameIcon from './components/GameIcon.vue'
import OverviewPage from './components/OverviewPage.vue'
import CalendarPage from './components/CalendarPage.vue'
import LoginPanel from './components/LoginPanel.vue'
import BilibiliSourcePanel from './components/BilibiliSourcePanel.vue'

// Game pages carry every game module plus the icon and guide catalogs; the
// overview, calendar and accounts need none of it.
const GameCard = lazyPage(() => import('./components/GameCard.vue'))
const SearchDialog = lazyPage(() => import('./components/SearchDialog.vue'))

const dashboard = createDashboard({ ...api, getAuthStatus })
const state = dashboard.state
const route = ref(readRoute(window.location.hash))
const menuOpen = ref(false)
const navigationMedia = window.matchMedia('(max-width: 960px)')
const mobileNavigation = ref(navigationMedia.matches)
const sidebar = ref(null)
const menuToggle = ref(null)
const mainContent = ref(null)
const workbench = ref(null), navigationSurface = ref(null)
const { closeMenu, onGripPointerdown, onGripKeydown, onTogglePointerdown, onToggleClick, onToggleKeydown, handleKey: handleNavigationKey } = useFloatingNavigation({ root: workbench, surface: navigationSurface, sidebar, menuToggle, menuOpen, mobileNavigation })
useElasticCards(mainContent, {
  selector: '.ov-hero, .ov-tasks, .ov-deadlines, .ov-gacha, .ov-news, .ov-game, .event-card, .card-head, .cap-card, .wuwa-panel, .calendar-board, .calendar-agenda, .calendar-detail, .calendar-stat, .calendar-split, .ef-card, .ef-count, .eg-card, .pool-card, .hl-card, .challenge-season, .challenge-monument, .ef-news-summary, .ef-attendance, .loadout-hero, .loadout-module, .ef-gacha-summary, .es-card, .bili-panel, .connection-note, .cloud-game-heading, .login-panel',
  resetOn: () => route.value,
})

const now = ref(Date.now())
const clock = ref('')
function tickClock() { clock.value = new Intl.DateTimeFormat('zh-CN', { timeZone:'Asia/Shanghai', hourCycle:'h23', hour:'2-digit',minute:'2-digit' }).format(Date.now()) }
const accountRevisions = ref({})
const selectedGame = computed(() => state.games.find(game => game.game_id === route.value.game))
const today = computed(() => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' }).format(now.value))
const refreshing = computed(() => Object.values(state.refreshing).some(Boolean))
const calendarErrors = computed(() => Object.fromEntries(state.games.map(g => {
  const source = state.collection.find(row => row.game_id === g.game_id && row.capability === 'events' && ['error', 'auth_expired'].includes(row.state))
  return [g.game_id, [state.readErrors[g.game_id], state.refreshErrors[g.game_id], source?.error].filter(Boolean).join('；')]
})))
// Jump-to search: pages, games and their tabs, events and roles already on this machine.
const searchOpen = ref(false)
const macKeys = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform || '')
const searchPages = [
  { label: '今日总览', href: '#/', icon: 'grid', hint: '体力、每日进度和近期截止' },
  { label: '活动日历', href: '#/calendar', icon: 'calendar', hint: '所有游戏的活动时间线' },
  { label: '社区账号', href: '#/accounts', icon: 'user', hint: '登录游戏社区账号' },
]
// Choosing the page already shown still reopens it at the chosen tab.
const jumps = ref(0)
let timer, clockTimer, stopFollowingSystem
// The LoL page keeps its tab in the shared browse state rather than a prop.
function followTab({ game, tab }) { if (game === 'league_of_legends' && GAME_SECTIONS.league_of_legends.some(([id]) => id === tab)) state.esportsBrowse.league_of_legends.section = tab }
followTab(route.value)
function syncRoute() {
  route.value = readRoute(window.location.hash)
  followTab(route.value)
  menuOpen.value = false; window.scrollTo({ top: 0, behavior: 'instant' }); nextTick(() => mainContent.value?.focus({ preventScroll: true }))
}
function openSearch() { menuOpen.value = false; searchOpen.value = true }
function jumpTo(href) {
  searchOpen.value = false
  if (window.location.hash === href || (href === '#/' && !window.location.hash)) { jumps.value++; syncRoute() }
  else window.location.hash = href
}
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
let themeWipe = 0
function toggleTheme(event) {
  const next = theme.value === 'light' ? 'dark' : 'light'
  const root = document.documentElement
  if (!document.startViewTransition || matchMedia('(prefers-reduced-motion: reduce)').matches) { setTheme(next); return }
  // beUI theme toggle: the new theme opens as a circle from the button.
  const box = event.currentTarget.getBoundingClientRect()
  const x = box.left + box.width / 2, y = box.top + box.height / 2
  root.style.setProperty('--theme-x', `${x}px`)
  root.style.setProperty('--theme-y', `${y}px`)
  root.style.setProperty('--theme-r', `${Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))}px`)
  // Colour transitions pause until the wipe ends, so the revealed theme is already settled.
  // A second click mid-wipe skips this wipe and settles it early, so only the
  // latest wipe may resume them.
  const wipe = ++themeWipe
  root.dataset.themeSwitching = ''
  const settle = () => { if (wipe === themeWipe) delete root.dataset.themeSwitching }
  try {
    const transition = document.startViewTransition(async () => { setTheme(next); await nextTick() })
    transition.finished.then(settle, settle)
    // The skipped wipe rejects its ready promise.
    transition.ready.catch(() => {})
  } catch {
    setTheme(next)
    settle()
  }
}
async function refreshAll() { if (!refreshing.value) await Promise.all(state.games.map(game => dashboard.refresh(game.game_id))) }
async function onAccountChanged({ game }) {
  dashboard.invalidateGame(game)
  accountRevisions.value = { ...accountRevisions.value, [game]: (accountRevisions.value[game] || 0) + 1 }
  await dashboard.load()
}
function handleKey(event) {
  if ((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key.toLowerCase() === 'k') { event.preventDefault(); if (!searchOpen.value) openSearch(); return }
  handleNavigationKey(event)
}
onMounted(() => {
  dashboard.load()
  stopFollowingSystem = followSystem()
  window.addEventListener('hashchange', syncRoute)
  window.addEventListener('keydown', handleKey)
  navigationMedia.addEventListener('change', mediaChanged)
  timer = setInterval(() => { now.value = Date.now(); dashboard.loadSnapshots(); dashboard.loadStatus() }, 60000)
  tickClock(); clockTimer = setInterval(tickClock,1000)
})
onBeforeUnmount(() => { clearInterval(timer); clearInterval(clockTimer); stopFollowingSystem?.(); dashboard.dispose(); window.removeEventListener('hashchange', syncRoute); window.removeEventListener('keydown', handleKey); navigationMedia.removeEventListener('change', mediaChanged) })
</script>
<template>
  <div ref="workbench" class="workbench" :class="{ 'menu-open': menuOpen }">
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus?.()">跳到主要内容</a>
    <button class="sidebar-scrim" :aria-hidden="!menuOpen" :inert="!menuOpen" aria-label="关闭导航" tabindex="-1" @click="closeMenu"></button>
    <div ref="navigationSurface" class="floating-navigation" :role="mobileNavigation && menuOpen ? 'dialog' : undefined" :aria-modal="mobileNavigation && menuOpen ? true : undefined" :aria-label="mobileNavigation ? '游戏与菜单' : undefined">
      <button type="button" class="navigation-grip" :aria-label="mobileNavigation ? (menuOpen ? '收起导航' : '展开导航') : '移动菜单，使用方向键调整位置'" :aria-expanded="mobileNavigation ? menuOpen : undefined" aria-controls="workspace-sidebar" @pointerdown="onGripPointerdown" @keydown="onGripKeydown" @click="mobileNavigation && onToggleClick($event)"><span aria-hidden="true"></span></button>
      <aside id="workspace-sidebar" ref="sidebar" class="workspace-sidebar" :inert="mobileNavigation && !menuOpen">
      <a class="brand" href="#/" @click="sidebarNavigate"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span>游戏管家<small aria-hidden="true">game · manage</small></span></a>
      <button class="mobile-sidebar-close icon-button" aria-label="关闭导航" @click="closeMenu"><AppIcon name="close" /></button>
      <nav v-glide.hover class="primary-nav" aria-label="主导航" @click="sidebarNavigate">
        <a href="#/" :class="{ active: route.page === 'overview' }" :aria-current="route.page === 'overview' ? 'page' : undefined"><AppIcon name="grid" /><span>今日总览</span></a>
        <a href="#/calendar" :class="{ active: route.page === 'calendar' }" :aria-current="route.page === 'calendar' ? 'page' : undefined"><AppIcon name="calendar" /><span>活动日历</span></a>
        <a href="#/accounts" :class="{ active: route.page === 'accounts' }" :aria-current="route.page === 'accounts' ? 'page' : undefined"><AppIcon name="user" /><span>社区账号</span></a>
      </nav>
      <div class="sidebar-label"><span>我的游戏</span></div>
      <nav v-glide.hover class="game-nav" :class="{ 'game-theme': route.page === 'game' }" :style="gameVars(route.game)" aria-label="游戏档案" @click="sidebarNavigate"><a v-for="game in state.games" :key="game.game_id" :href="`#/game/${encodeURIComponent(game.game_id)}`" :class="{ active: route.page === 'game' && route.game === game.game_id }" :aria-current="route.page === 'game' && route.game === game.game_id ? 'page' : undefined"><GameIcon class="nav-game-mark" :game-id="game.game_id" :name="game.display_name" :style="{ '--mark-tone': gameStyle(game.game_id).tone }" /><span>{{ game.display_name }}</span><AppIcon class="nav-arrow" name="arrow" :size="14" /></a></nav>
      <div v-if="state.loadError || state.serviceError || state.notify?.enabled" class="sidebar-bottom"><p v-if="state.loadError || state.serviceError" class="local-status"><i class="offline"></i>本地服务连接异常</p><p v-if="state.notify?.enabled">微信提醒已开启</p></div>
    </aside>
    <nav class="mobile-tabbar" aria-label="常用页面">
      <a href="#/" :class="{ active: route.page === 'overview' }" :aria-current="route.page === 'overview' ? 'page' : undefined"><AppIcon name="grid" :size="19" /><span>总览</span></a>
      <a href="#/calendar" :class="{ active: route.page === 'calendar' }" :aria-current="route.page === 'calendar' ? 'page' : undefined"><AppIcon name="calendar" :size="19" /><span>日历</span></a>
      <a href="#/accounts" :class="{ active: route.page === 'accounts' }" :aria-current="route.page === 'accounts' ? 'page' : undefined"><AppIcon name="user" :size="19" /><span>账号</span></a>
      <button ref="menuToggle" class="nav-menu-toggle" type="button" :class="{ active: route.page === 'game' }" :aria-expanded="menuOpen" aria-controls="workspace-sidebar" @pointerdown="onTogglePointerdown" @click="onToggleClick" @keydown="onToggleKeydown"><AppIcon name="chevron" :size="19" /><span>游戏与菜单</span></button>
    </nav>
    </div>
    <div class="workspace-body" :inert="mobileNavigation && menuOpen">
      <header class="workspace-topbar">
        <div class="topbar-left">
          <button class="search-trigger" type="button" aria-haspopup="dialog" :aria-keyshortcuts="macKeys ? 'Meta+K' : 'Control+K'" @click="openSearch"><AppIcon name="search" :size="16" /><span>搜索页面、游戏、活动和角色</span><kbd aria-hidden="true">{{ macKeys ? '⌘ K' : 'Ctrl K' }}</kbd></button>
        </div>
        <div class="topbar-right">
          <span class="topbar-date"><AppIcon name="calendar" :size="15" /><span>{{ today }}</span><span class="topbar-clock" aria-hidden="true">{{ clock }}</span></span>
          <button class="icon-button theme-toggle" :aria-label="theme === 'light' ? '切换到夜间模式' : '切换到白天模式'" :title="theme === 'light' ? '夜间模式' : '白天模式'" @click="toggleTheme">
            <span class="icon-swap"><AppIcon name="sun" :size="16" :data-active="theme !== 'light'" /><AppIcon name="moon" :size="16" :data-active="theme === 'light'" /></span>
          </button>
          <SystemUpdateControl :allowed="true" />
        </div>
      </header>
      <main id="main-content" ref="mainContent" tabindex="-1" class="workspace-main">
        <div v-if="state.loadError" class="service-error" role="alert"><div><strong>暂时无法读取游戏数据</strong></div><button class="ui-button" :disabled="state.loading" @click="dashboard.load">重试连接</button></div>
        <OverviewPage v-if="route.page === 'overview'" class="t-page" :games="state.games" :snapshots="state.snapshots" :accounts="state.accounts" :collection="state.collection" :read-errors="state.readErrors" :refresh-errors="state.refreshErrors" :refreshing="state.refreshing" :now="now" :loading="state.loading" @navigate="navigate" @refresh="refreshAll" />
        <CalendarPage v-else-if="route.page === 'calendar'" class="t-page" :games="state.games" :snapshots="state.snapshots" :loading="state.loading" :initial-game-id="route.game" :read-errors="calendarErrors" />
        <template v-else-if="route.page === 'game'"><GameCard v-if="selectedGame" class="t-page" :key="`${selectedGame.game_id}:${accountRevisions[selectedGame.game_id] || 0}:${route.tab || ''}:${jumps}`" :game="selectedGame" :auth-account="state.accounts[selectedGame.game_id]" :esports-browse="state.esportsBrowse[selectedGame.game_id]" @esports-browse="Object.assign(state.esportsBrowse.league_of_legends, $event)" @esports-snapshot="state.snapshots.league_of_legends = { ...state.snapshots.league_of_legends, esports: $event }" :initial-section="route.tab || 'overview'" :collection-status="state.collection" :external-snapshots="state.snapshots[selectedGame.game_id] || {}" :external-refreshing="!!state.refreshing[selectedGame.game_id]" :external-error="state.refreshErrors[selectedGame.game_id] || state.readErrors[selectedGame.game_id] || ''" @refresh="dashboard.refresh(selectedGame.game_id)" @calendar="navigate('calendar', selectedGame.game_id)" /><div v-else class="empty-page"><p>{{ state.loading ? '加载中…' : '这个游戏尚未启用。' }}</p><button class="ui-button" @click="navigate('overview')">返回总览</button></div></template>
        <div v-show="route.page === 'accounts'" class="accounts-page"><header class="page-heading"><div class="page-heading-copy"><h1>社区账号</h1></div></header><LoginPanel @account-changed="onAccountChanged" /><section class="connection-note"><AppIcon name="shield" :size="16" /><p>凭据在本机加密保存。英雄联盟读取本机客户端，无需登录。</p></section></div>
        <BilibiliSourcePanel v-if="route.page === 'overview' || route.page === 'game'" :game-id="route.page === 'game' ? route.game : ''" @collected="dashboard.loadSnapshots()" />
      </main>
    </div>

    <SearchDialog v-if="searchOpen" :pages="searchPages" :games="state.games" :snapshots="state.snapshots" :now="now" @select="jumpTo" @close="searchOpen = false" />
  </div>
</template>
