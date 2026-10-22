<script setup>
import MenuSelect from './components/MenuSelect.vue'
import { computed, nextTick, onMounted, onBeforeUnmount, provide, ref, watch } from 'vue'
import { createCloudDashboard } from './cloud-dashboard.js'
import { accountCapabilities, providerName, getPublicSnapshot } from './accounts-api.js'
import { endfieldRoleChoices, endfieldFallbackCandidates } from './endfield-accounts.js'
import { revokeSession, getMe } from './identity-api.js'
import { followSystem } from './theme.js'
import { lazyPage } from './lazy-page.js'
import { useFloatingNavigation } from './floating-navigation.js'
import { useElasticCards } from './elastic-cards.js'
import { collectionState } from './snapshot-state.js'
import { capabilityLabel, dataReadIssue } from './cloud-display.js'
import { displayBeijing } from './time.js'
import AppIcon from './components/AppIcon.vue'
import ThemeToggle from './components/ThemeToggle.vue'
import SystemUpdateControl from './components/SystemUpdateControl.vue'
import GameIcon from './components/GameIcon.vue'
import { gameStyle, gameVars, readRoute } from './dashboard.js'
import SiteLogin from './components/SiteLogin.vue'
import OverviewPage from './components/OverviewPage.vue'

// The overview needs none of these; each loads when its page is first opened. The game card also pulls in
// every game module and catalog.
const CloudGameCard = lazyPage(() => import('./components/CloudGameCard.vue'))
const AccountSettings = lazyPage(() => import('./components/AccountSettings.vue'))
const QqBindingPanel = lazyPage(() => import('./components/QqBindingPanel.vue'))
const LoginPanel = lazyPage(() => import('./components/LoginPanel.vue'))
const CalendarPage = lazyPage(() => import('./components/CalendarPage.vue'))
const CloudBilibiliSourcePanel = lazyPage(() => import('./components/CloudBilibiliSourcePanel.vue'))
const CloudGuideAdminPanel = lazyPage(() => import('./components/CloudGuideAdminPanel.vue'))
const CloudSklandConnect = lazyPage(() => import('./components/CloudSklandConnect.vue'))
const SearchDialog = lazyPage(() => import('./components/SearchDialog.vue'))
const dashboard = createCloudDashboard(), state = dashboard.state
const initialHash = globalThis.window?.location?.hash || ''
const initialRoute = /#\/sessions(?:$|\?)/.test(initialHash) ? {page:'sessions',game:''} : readRoute(initialHash)
const page = ref(initialRoute.page), logoutBusy = ref(false), overviewRefreshing = ref(false)
const calendarGame = ref(initialRoute.page === 'calendar' ? initialRoute.game || 'all' : 'all'), now = ref(Date.now())
const publicGame = ref('wuthering_waves'), publicSnapshots = ref({})
const calendarSnapshots = ref({}), calendarReadErrors = ref({}), calendarLoading = ref(false)
const publicGames = [{game_id:'wuthering_waves',display_name:'鸣潮',capabilities:['news','events']},{game_id:'nte',display_name:'异环',capabilities:['news','events']},{game_id:'endfield',display_name:'终末地',capabilities:['news','events']}]
const menuOpen = ref(false), sidebar = ref(null), menuToggle = ref(null), mainContent = ref(null)
const navigationMedia = globalThis.window?.matchMedia?.('(max-width: 960px)')
const mobileNavigation = ref(navigationMedia?.matches || false)
const workbench = ref(null), navigationSurface = ref(null)
const { closeMenu, onGripPointerdown, onGripKeydown, onTogglePointerdown, onToggleClick, onToggleKeydown, handleKey: handleNavigationKey } = useFloatingNavigation({ root: workbench, surface: navigationSurface, sidebar, menuToggle, menuOpen, mobileNavigation })
useElasticCards(mainContent, {
  selector: '.ov-hero, .ov-tasks, .ov-deadlines, .ov-gacha, .ov-news, .ov-game, .event-card, .card-head, .cap-card, .wuwa-panel, .calendar-board, .calendar-agenda, .calendar-detail, .calendar-stat, .calendar-split, .ef-card, .ef-count, .eg-card, .pool-card, .hl-card, .challenge-season, .challenge-monument, .ef-news-summary, .ef-attendance, .loadout-hero, .loadout-module, .ef-gacha-summary, .es-card, .bili-panel, .connection-note, .cloud-game-heading, .login-panel',
  resetOn: () => page.value,
})

const todayFormatter = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })
const today = computed(() => todayFormatter.format(now.value))
let routeGame = initialRoute.page === 'game' ? initialRoute.game : ''
const routeTab = ref(initialRoute.page === 'game' ? initialRoute.tab || '' : '')
// Jump-to search over pages, the games this account has, their tabs, events and roles.
const searchOpen = ref(false), jumps = ref(0)
const macKeys = /Mac|iPhone|iPad/.test(globalThis.navigator?.platform || '')
const searchPages = [
  { label: '今日总览', href: '#/', icon: 'grid', hint: '体力、每日进度和近期截止' },
  { label: '活动日历', href: '#/calendar', icon: 'calendar', hint: '所有游戏的活动时间线' },
  { label: '账号与授权', href: '#/accounts', icon: 'user', hint: '游戏授权、QQ 绑定和密码' },
  { label: '网站会话', href: '#/sessions', icon: 'shield', hint: '登录过本站的设备' },
]
function openSearch() { menuOpen.value = false; searchOpen.value = true }
function jumpTo(href) {
  searchOpen.value = false
  const hash = globalThis.window?.location?.hash || ''
  if (hash === href || (href === '#/' && !hash)) { jumps.value++; syncRoute() }
  else if (globalThis.window) window.location.hash = href
}
function writeRoute(destination, game='') {
  if (!globalThis.window) return
  const next = destination==='game' ? `/game/${encodeURIComponent(game)}` : destination==='calendar' ? `/calendar${game && game!=='all' ? '?game='+encodeURIComponent(game) : ''}` : destination==='overview' ? '/' : `/${destination}`
  if (window.location.hash !== '#'+next) window.location.hash = next
}
function setPage(destination) { routeGame=''; page.value=destination; writeRoute(destination); sidebarNavigate() }
function sidebarNavigate() { menuOpen.value=false; if(mobileNavigation.value)nextTick(()=>mainContent.value?.focus?.({preventScroll:true})) }
function mediaChanged(event) { mobileNavigation.value=event.matches; if(!event.matches)menuOpen.value=false }
function handleKey(event) {
  if((event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey && event.key?.toLowerCase() === 'k' && state.user) { event.preventDefault(); if(!searchOpen.value)openSearch(); return }
  handleNavigationKey(event)
}
function syncRoute() {
  const hash=globalThis.window?.location?.hash || '', route=/#\/sessions(?:$|\?)/.test(hash)?{page:'sessions',game:''}:readRoute(hash)
  page.value=route.page; routeGame=route.page==='game'?route.game:''; routeTab.value=route.page==='game'?route.tab || '':''
  if(route.page==='calendar') { calendarGame.value=route.game || 'all'; if(state.user)loadCalendar() }
  if(routeGame && state.user) { const account=state.accounts.find(a=>a.state!=='revoked' && gameFor(a)===routeGame); if(account && gameFor(state.selected)!==routeGame)dashboard.selectAccount(account); if(account){publicGame.value=routeGame;loadPublic(routeGame)} }
  menuOpen.value=false;globalThis.window?.scrollTo?.({top:0,behavior:'instant'});nextTick(()=>mainContent.value?.focus?.({preventScroll:true}))
}
const gameFor = account => ({kuro:'wuthering_waves',tajiduo:'nte',hypergryph:'endfield',skland:'endfield'})[account?.provider]
const ownerGames = computed(() => publicGames.filter(game => state.accounts.some(a => a.state !== 'revoked' && gameFor(a) === game.game_id)))
const defaultRole = account => account?.roles?.find(role => role.is_default)?.role_id || account?.roles?.[0]?.role_id || ''
const endfieldChoices = computed(() => endfieldRoleChoices(state.accounts))
const sameChoice = (choice, account, role) => choice.account.account_id === account?.account_id && choice.role === role || Object.values(choice.sources).some(source => source.account.account_id === account?.account_id && source.role === role)
const selectedChoice = computed(() => endfieldChoices.value.find(choice => sameChoice(choice, state.selected, state.role)))
// The Endfield authorization guide names the entries it could not choose between.
provide('endfieldCandidates', computed(() => Object.fromEntries(['hypergryph', 'skland'].map(provider => [provider, endfieldFallbackCandidates(endfieldChoices.value, selectedChoice.value, provider)]))))
const channelLabel = account => ({ official: '官服', bilibili: 'B 服' })[account?.channel] || '渠道未提供'
const choiceName = choice => {
  const role = choice.account.roles?.find(row => row.role_id === choice.role)
  return `${role?.display_name || '未命名角色'} · ${channelLabel(choice.account)}${role?.game_uid ? ` · ${role.game_uid}` : ''}`
}
const choiceSources = choice => choice.sources.hypergryph && choice.sources.skland ? '鹰角与森空岛' : choice.account.provider === 'skland' ? '森空岛档案' : '鹰角寻访'
function openChoice(key) { const choice = endfieldChoices.value.find(row => row.key === key); if (choice) openAccount(choice.account, choice.role) }
const navigationAccounts = computed(() => [
  ...state.accounts.filter(account => gameFor(account) !== 'endfield').map((account, index) => ({ key: account.account_id, account, role: defaultRole(account), name: providerName(account), note: `授权 ${index + 1}` })),
  ...endfieldChoices.value.map(choice => ({ ...choice, name: choice.account.roles?.find(role => role.role_id === choice.role)?.display_name || '未命名角色', channel: channelLabel(choice.account), detail: `终末地 · ${choiceName(choice)} · ${choiceSources(choice)}`, note: choiceSources(choice).replace('与', ' · ') })),
])
const overviewEntries = computed(() => Object.fromEntries(ownerGames.value.map(game => {
  if (game.game_id === 'endfield') {
    const choices = endfieldChoices.value.filter(choice => choice.account.state !== 'revoked')
    const choice = choices.find(row => row.account.is_default && row.role === defaultRole(row.account)) || choices.find(row => row.role === defaultRole(row.account)) || choices[0]
    return [game.game_id, choice || { account: state.accounts.find(row => row.state !== 'revoked' && gameFor(row) === game.game_id), role: '', sources: {} }]
  }
  const account = state.accounts.find(row => row.state !== 'revoked' && gameFor(row) === game.game_id)
  return [game.game_id, { account, role: defaultRole(account), sources: {} }]
})))
const overviewOwners = computed(() => Object.fromEntries(Object.entries(overviewEntries.value).map(([game, entry]) => [game, entry?.account])))
const overviewGames = computed(() => ownerGames.value.map(game => {
  const entry = overviewEntries.value[game.game_id], sources = entry?.sources || {}
  const capabilities = Object.keys(sources).length ? [...new Set(Object.values(sources).flatMap(source => accountCapabilities(source.account)))] : accountCapabilities(entry?.account)
  if (sources.skland) for (const cap of ['stamina', 'progress']) if (!capabilities.includes(cap)) capabilities.push(cap)
  return { ...game, capabilities, credentials_configured: true }
}))
const overviewSnapshots = computed(() => Object.fromEntries(overviewGames.value.map(game => {
  const entry = overviewEntries.value[game.game_id]
  const read = source => {
    const cached = source && state.overview[source.account.account_id]
    return cached && source && cached.role === source.role ? cached.snapshots || {} : {}
  }
  let snaps = read(entry)
  if (game.game_id === 'endfield' && entry) {
    const sources = entry.sources, passport = read(sources.hypergryph), profile = read(sources.skland).account
    snaps = { ...passport, passport_account: passport.account || null }
    if (profile) {
      snaps.skland_account = profile
      if (profile.payload?.base) snaps.account = { ...profile, payload: { schema_version: 1, nickname: profile.payload.base.name, level: profile.payload.base.level } }
      snaps.stamina = { ...profile, payload: profile.payload?.stamina ? { schema_version: 1, ...profile.payload.stamina } : null }
      snaps.progress = { ...profile, payload: Array.isArray(profile.payload?.progress) ? { schema_version: 1, items: profile.payload.progress } : null }
    }
  }
  return [game.game_id, { ...snaps, ...publicSnapshots.value[game.game_id], ...calendarSnapshots.value[game.game_id] }]
})))
const overviewAccounts = computed(() => Object.fromEntries(overviewGames.value.map(game => [game.game_id,{state:'connected'}])))
const overviewErrors = computed(() => Object.fromEntries(overviewGames.value.flatMap(game => {
  const snap=Object.entries(overviewSnapshots.value[game.game_id] || {}).filter(([cap])=>!['news','events','announcement'].includes(cap)).map(([,snap])=>snap).find(s=>s?.error || s?.poll_status?.error), error=snap?.error || snap?.poll_status?.error
  return error?[[game.game_id,error]]:[]
})))
const overviewPublicErrors = computed(()=>Object.fromEntries(overviewGames.value.map(game=>[game.game_id,['events','news'].map(cap=>dataReadIssue(cap,overviewSnapshots.value[game.game_id]?.[cap])).filter(Boolean)])))
const overviewCollection = computed(() => overviewGames.value.flatMap(game => Object.entries(overviewSnapshots.value[game.game_id] || {}).filter(([cap])=>!['news','events'].includes(cap)).map(([cap,snap])=>({game_id:game.game_id,capability:cap,state:collectionState(snap)==='failed'?'error':snap?.state === 'never' ? 'never' : snap?.state || 'never',last_success_at:snap?.fetched_at}))))
const selectedGame = computed(() => gameFor(state.selected) || (page.value === 'game' ? routeGame : ''))
// Search sees each game with the tabs its cloud page shows (GameCard adds news and events).
const searchGames = computed(() => overviewGames.value.map(game => ({ ...game, capabilities: [...game.capabilities, 'news', 'events'] })))
const refreshPending = computed(() => Object.values(state.refreshPending).some(Boolean))
const refreshMessages = computed(() => Object.entries(state.refreshing).filter(([, value]) => value))
const refreshLabel = key => { const [provider, cap] = key.split(':'); return cap ? `${provider === 'skland' ? '森空岛' : '鹰角'} · ${capabilityLabel(cap)}` : capabilityLabel(key) }
const dataKey = computed(() => `${state.user?.user_id}:${state.selected?.account_id}:${state.role}:${state.revision}`)
const publicReadVersions = new Map()
const publicReads = new Map()
let timer, stopTheme, publicGeneration = 0, calendarGeneration = 0
function clearPublicData() {
  publicGeneration++; calendarGeneration++; publicReadVersions.clear(); publicReads.clear()
  publicSnapshots.value = {}
  calendarSnapshots.value = {}; calendarReadErrors.value = {}; calendarLoading.value = false; calendarGame.value = 'all'
}
// A reload or a login on #/sessions leaves the page unchanged, so its watcher stays silent and the list is asked for here.
// When the route changes the page (a login after a logout), the watcher asks.
function enterRoute() { const shown = page.value; syncRoute(); if(page.value==='sessions' && shown==='sessions' && state.user)dashboard.loadSessions() }
async function authenticated() { await dashboard.initialize(); enterRoute() }
async function logout() { if (logoutBusy.value) return; logoutBusy.value = true; clearPublicData(); try { await dashboard.logout() } finally { logoutBusy.value = false; page.value = 'overview' } }
async function refresh() { await dashboard.refreshSelected() }
async function readSnapshots() { if (state.user && state.selected?.state !== 'revoked') await dashboard.loadSelectedSnapshots() }
async function revoke(id) { try { await revokeSession(id); await getMe(); await dashboard.loadSessions() } catch (error) { if (error.status !== 401 && error.name !== 'AbortError') state.error = error.message } }
function readPublicSnapshot(game, cap) {
  const key=JSON.stringify([publicGeneration,state.user?.user_id,game,cap])
  if(publicReads.has(key))return publicReads.get(key)
  const pending=performPublicRead(game,cap).finally(()=>{if(publicReads.get(key)===pending)publicReads.delete(key)})
  publicReads.set(key,pending);return pending
}
async function performPublicRead(game, cap) {
  const generation = publicGeneration, owner = state.user?.user_id, key = `${game}:${cap}`
  const version = (publicReadVersions.get(key) || 0) + 1
  publicReadVersions.set(key,version)
  const current = () => generation === publicGeneration && owner === state.user?.user_id && version === publicReadVersions.get(key)
  try {
    const snapshot = await getPublicSnapshot(game,cap)
    if (current()) {
      publicSnapshots.value = {...publicSnapshots.value,[game]:{...publicSnapshots.value[game],[cap]:snapshot}}
      if(cap === 'events' || cap === 'news') calendarSnapshots.value = {...calendarSnapshots.value,[game]:{...calendarSnapshots.value[game],[cap]:snapshot}}
      if(cap === 'events') delete calendarReadErrors.value[game]
    }
    return current() ? snapshot : null
  } catch(error) {
    if(!current()) return null
    if(current() && error.name !== 'AbortError') {
      const old=publicSnapshots.value[game]?.[cap]
      {
        const retained={...(old || {payload:null}),state:'error',error:error.message}
        publicSnapshots.value={...publicSnapshots.value,[game]:{...publicSnapshots.value[game],[cap]:retained}}
        if(cap==='events' || cap==='news') calendarSnapshots.value={...calendarSnapshots.value,[game]:{...calendarSnapshots.value[game],[cap]:retained}}
      }
    }
    throw error
  }
}
async function loadPublic(game = publicGame.value) {
  if (!state.user?.user_id) return
  // Each read preserves its own error; one failure must not end the other read.
  await Promise.allSettled([readPublicSnapshot(game,'news'), readPublicSnapshot(game,'events')])
}
function openCalendar(game = 'all') { calendarGame.value = game; page.value = 'calendar'; writeRoute('calendar',game); sidebarNavigate() }
function openAccount(account, role) { if (!account) return; const choice = gameFor(account) === 'endfield' && endfieldChoices.value.find(row => sameChoice(row, account, role || defaultRole(account))); if (choice) { account = choice.account; role = choice.role } dashboard.selectAccount(account, role); publicGame.value = gameFor(account) || 'wuthering_waves'; page.value = 'game'; routeGame=publicGame.value; writeRoute('game',routeGame); sidebarNavigate(); loadPublic(publicGame.value) }
function navigate(destination, game) { if (destination === 'calendar') openCalendar(game || 'all'); else if (destination === 'game') openAccount(overviewOwners.value[game]); else setPage(destination) }
async function readOverview() { await Promise.all([readSnapshots(), dashboard.loadOverview(), ...ownerGames.value.map(game=>loadPublic(game.game_id))]) }
async function refreshOverview() {
  if (overviewRefreshing.value) return
  overviewRefreshing.value = true
  try { await readOverview() } finally { overviewRefreshing.value = false }
}
async function loadCalendar() {
  if (!state.user || calendarLoading.value) return
  const version = ++calendarGeneration, owner = state.user.user_id
  const current = () => version === calendarGeneration && owner === state.user?.user_id
  calendarLoading.value = true
  try {
    await Promise.all(publicGames.map(async game => {
      const id = game.game_id
      // Events includes a cache-only artwork index; calendar navigation needs no article bodies.
      await Promise.allSettled([
        (async () => {
          try {
            const events = await readPublicSnapshot(id, 'events')
            if (events && current()) delete calendarReadErrors.value[id]
          } catch (error) {
            if (current() && error.name !== 'AbortError') calendarReadErrors.value[id] = error.message
          }
        })(),
      ])
    }))
  } finally { if (current()) calendarLoading.value = false }
}
watch(()=>state.accounts,()=>{if(routeGame && page.value==='game'){const account=state.accounts.find(a=>a.state!=='revoked' && gameFor(a)===routeGame);if(account && state.selected && gameFor(state.selected)!==routeGame)openAccount(account)}}, {flush:'post'})
watch(dataKey, () => { if(page.value === 'overview') readOverview(); else if(page.value === 'game') readSnapshots() })
watch(() => state.user?.user_id, clearPublicData, { flush: 'sync' })
watch(page, value => { if (value === 'sessions') dashboard.loadSessions(); if (value === 'calendar') loadCalendar(); if(value === 'overview') readOverview(); if(value === 'game') readSnapshots() })
let polling = false, lastPoll = Date.now()
const POLL_INTERVAL = 60000
async function poll() {
  // A background tab skips the minute check; it catches up when shown again.
  if (globalThis.document?.hidden) return
  // initialize invalidates the controller epoch. Let bounded refresh tracking
  // settle first; its snapshot GETs still enforce session ownership and 401.
  now.value = Date.now(); if (!state.user || refreshPending.value || polling) return
  polling = true; lastPoll = Date.now()
  try { await dashboard.initialize(); if(page.value === 'overview') await readOverview(); else if(page.value === 'game') await Promise.all([readSnapshots(),loadPublic(selectedGame.value)]); else if(page.value === 'calendar') await loadCalendar() }
  finally { polling = false }
}
const schedulePoll = () => { clearInterval(timer); timer = setInterval(poll, POLL_INTERVAL) }
// Shown again after a missed minute: check now and restart the minute from here.
function visibilityChanged() { if (!globalThis.document?.hidden && Date.now() - lastPoll > POLL_INTERVAL) { schedulePoll(); poll() } }
onMounted(() => { globalThis.window?.addEventListener('hashchange',syncRoute); globalThis.window?.addEventListener('keydown',handleKey); navigationMedia?.addEventListener('change',mediaChanged); globalThis.document?.addEventListener?.('visibilitychange',visibilityChanged); dashboard.initialize().then(enterRoute); stopTheme = followSystem(); schedulePoll() })
onBeforeUnmount(() => { globalThis.window?.removeEventListener('hashchange',syncRoute); globalThis.window?.removeEventListener('keydown',handleKey); navigationMedia?.removeEventListener('change',mediaChanged); globalThis.document?.removeEventListener?.('visibilitychange',visibilityChanged); clearInterval(timer); stopTheme?.(); dashboard.dispose(); clearPublicData() })
</script>
<template>
  <div ref="workbench" class="workbench cloud-app" :class="{'menu-open':menuOpen}">
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus?.()">跳到主要内容</a>
    <main v-if="!state.user" class="cloud-content"><p v-if="!state.ready || logoutBusy" role="status">{{ logoutBusy ? '退出中…' : '加载中…' }}</p><section v-else-if="state.logoutFailed" class="cap-card logout-retry"><p role="alert">退出登录未完成，请稍后重试。</p><button class="ui-button" @click="logout">退出登录</button></section><SiteLogin v-else @authenticated="authenticated" /><p v-if="state.error" role="alert">{{ state.error }}</p></main>
    <div v-else>
      <button class="sidebar-scrim" :aria-hidden="!menuOpen" :inert="!menuOpen" aria-label="关闭导航" tabindex="-1" @click="closeMenu"></button>
      <div ref="navigationSurface" class="floating-navigation" :role="mobileNavigation && menuOpen ? 'dialog' : undefined" :aria-modal="mobileNavigation && menuOpen ? true : undefined" :aria-label="mobileNavigation ? '游戏与菜单' : undefined">
      <button type="button" class="navigation-grip" :aria-label="mobileNavigation ? (menuOpen ? '收起导航' : '展开导航') : '移动菜单，使用方向键调整位置'" :aria-expanded="mobileNavigation ? menuOpen : undefined" aria-controls="workspace-sidebar" @pointerdown="onGripPointerdown" @keydown="onGripKeydown" @click="mobileNavigation && onToggleClick($event)"><span aria-hidden="true"></span></button>
      <aside id="workspace-sidebar" ref="sidebar" class="workspace-sidebar cloud-navigation" :style="gameVars(selectedGame)" :inert="mobileNavigation && !menuOpen">
        <a class="brand" href="#/" @click.prevent="setPage('overview')"><span class="brand-mark" aria-hidden="true"><i></i><i></i><i></i><i></i></span><span>游戏管家<small aria-hidden="true">game · manage</small></span></a>
        <button class="mobile-sidebar-close icon-button" aria-label="关闭导航" @click="closeMenu"><AppIcon name="close" /></button>
        <nav class="primary-nav" aria-label="云端导航"><button :aria-current="page === 'overview' ? 'page' : undefined" @click="setPage('overview')"><AppIcon name="grid" /><span>今日总览</span></button><button :aria-current="page === 'calendar' ? 'page' : undefined" @click="openCalendar()"><AppIcon name="calendar" /><span>活动日历</span></button><button :aria-current="page === 'accounts' ? 'page' : undefined" @click="setPage('accounts')"><AppIcon name="user" /><span>账号与授权</span></button><button :aria-current="page === 'sessions' ? 'page' : undefined" @click="setPage('sessions')"><AppIcon name="shield" /><span>网站会话</span></button></nav><div class="sidebar-label"><span>我的游戏</span></div><nav class="game-nav" aria-label="游戏导航"><button v-for="game in ownerGames" :key="game.game_id" :aria-current="page === 'game' && selectedGame === game.game_id ? 'page' : undefined" @click="openAccount(overviewOwners[game.game_id])"><GameIcon class="nav-game-mark" :game-id="game.game_id" :name="game.display_name" :style="{ '--mark-tone': gameStyle(game.game_id).tone }" /><span>{{ game.display_name }}</span></button></nav><nav class="cloud-grants" aria-label="本人游戏角色">
          <p v-if="navigationAccounts.length" class="role-list-label">角色档案</p>
          <button v-for="entry in navigationAccounts" :key="entry.key" type="button" class="role-entry" :aria-label="entry.detail || `${entry.name} · ${entry.note}`" :title="entry.detail || entry.name" :aria-pressed="entry.sources ? sameChoice(entry, state.selected, state.role) : entry.account.account_id === state.selected?.account_id" @click="openAccount(entry.account, entry.role)">
            <GameIcon class="role-entry-icon" :game-id="gameFor(entry.account)" aria-hidden="true" />
            <span class="role-entry-copy"><span class="role-entry-heading"><span class="role-entry-name">{{ entry.name }}</span><span v-if="entry.channel" class="role-entry-channel">{{ entry.channel }}</span></span><span class="role-entry-note">{{ entry.note }}</span></span>
            <AppIcon class="role-entry-check" name="check" :size="14" aria-hidden="true" />
          </button>
        </nav></aside>
      <nav class="mobile-tabbar" aria-label="常用页面">
        <button type="button" :class="{ active: page === 'overview' }" :aria-current="page === 'overview' ? 'page' : undefined" @click="setPage('overview')"><AppIcon name="grid" :size="19" /><span>总览</span></button>
        <button type="button" :class="{ active: page === 'calendar' }" :aria-current="page === 'calendar' ? 'page' : undefined" @click="openCalendar()"><AppIcon name="calendar" :size="19" /><span>日历</span></button>
        <button type="button" :class="{ active: page === 'accounts' }" :aria-current="page === 'accounts' ? 'page' : undefined" @click="setPage('accounts')"><AppIcon name="user" :size="19" /><span>账号</span></button>
        <button ref="menuToggle" class="nav-menu-toggle" type="button" :class="{ active: page === 'game' || page === 'sessions' }" :aria-expanded="menuOpen" aria-controls="workspace-sidebar" @pointerdown="onTogglePointerdown" @click="onToggleClick" @keydown="onToggleKeydown"><AppIcon name="chevron" :size="19" /><span>游戏与菜单</span></button>
      </nav>
    </div>
      <div class="workspace-body" :inert="mobileNavigation && menuOpen"><header class="workspace-topbar"><div class="topbar-left"><button class="search-trigger" type="button" aria-haspopup="dialog" :aria-keyshortcuts="macKeys ? 'Meta+K' : 'Control+K'" @click="openSearch"><AppIcon name="search" :size="16" /><span>搜索页面、游戏、活动和角色</span><kbd aria-hidden="true">{{ macKeys ? '⌘ K' : 'Ctrl K' }}</kbd></button></div><div class="topbar-right"><span class="topbar-date"><AppIcon name="calendar" :size="15" /><span>{{ today }}</span></span><ThemeToggle /><SystemUpdateControl :allowed="state.user.is_admin === true" /><button class="ui-button small-button" :disabled="logoutBusy" @click="logout">退出登录</button></div></header>
      <main id="main-content" ref="mainContent" tabindex="-1" class="workspace-main cloud-content"><p v-if="state.error" role="alert">{{ state.error }}</p>
        <template v-if="page === 'accounts'"><header class="page-heading"><div class="page-heading-copy"><h1>账号与授权</h1></div></header><CloudBilibiliSourcePanel v-if="state.user.is_admin" :key="state.user.user_id" /><CloudGuideAdminPanel v-if="state.user.is_admin" :key="state.user.user_id" /><QqBindingPanel :key="state.user.user_id" /><AccountSettings :key="state.user.user_id" :accounts="state.accounts" :is-admin="state.user.is_admin" @changed="dashboard.loadAccounts()" /><LoginPanel :key="state.user.user_id" @account-changed="dashboard.loadAccounts()" /><CloudSklandConnect :key="state.user.user_id" :accounts="state.accounts" :user-id="state.user.user_id" @changed="dashboard.loadAccounts()" /></template>
        <section v-else-if="page === 'calendar'" class="cloud-calendar"><div class="cloud-calendar-controls"><button class="ui-button" :disabled="calendarLoading" @click="loadCalendar">刷新活动</button></div><CalendarPage :key="state.user.user_id" :games="publicGames" :snapshots="calendarSnapshots" :initial-game-id="calendarGame" :read-errors="calendarReadErrors" :loading="calendarLoading" show-source-status /></section><section v-else-if="page === 'sessions'" class="cloud-sessions"><header class="page-heading"><div class="page-heading-copy"><h1>网站会话</h1></div><button class="ui-button" @click="dashboard.loadSessions()"><AppIcon name="refresh" :size="15" />刷新</button></header><div class="cap-card session-card"><p class="session-note">撤销后，该设备需要重新登录。</p><article v-for="(session, index) in state.sessions" :key="session.session_id"><AppIcon name="shield" :size="20" /><p>会话 {{ index + 1 }} · 创建 {{ displayBeijing(session.created_at) }} · 过期 {{ displayBeijing(session.expires_at) }}</p><button class="ui-button small-button" @click="revoke(session.session_id)">撤销此会话</button></article></div></section>
<template v-else><template v-if="page === 'overview'"><OverviewPage :games="overviewGames" :snapshots="overviewSnapshots" :accounts="overviewAccounts" :read-errors="overviewErrors" :public-errors="overviewPublicErrors" :collection="overviewCollection" :now="now" :loading="state.loading || state.overviewLoading" :refreshing="{ overview: overviewRefreshing }" :is-admin="state.user.is_admin === true" @navigate="navigate" @refresh="refreshOverview" /><details class="cloud-owner-note"><summary>数据来源</summary><p v-for="game in overviewGames" :key="game.game_id">{{ game.display_name }} · {{ game.game_id === 'endfield' && overviewEntries[game.game_id] ? choiceSources(overviewEntries[game.game_id]) : providerName(overviewOwners[game.game_id]) }} · {{ overviewOwners[game.game_id].roles?.find(r=>r.is_default)?.display_name || overviewOwners[game.game_id].roles?.[0]?.display_name || '未命名角色' }}{{ overviewOwners[game.game_id].roles?.some(r=>r.is_default) ? '（默认）' : '' }}</p></details><p v-if="!state.accounts.length">还没有游戏账号，请到「账号与授权」登录。</p></template><template v-else><header class="cloud-game-heading"><template v-if="selectedGame === 'endfield'"><p class="cloud-identity">终末地 · {{ selectedChoice ? choiceSources(selectedChoice) : '游戏档案' }}</p><label v-if="endfieldChoices.length">查看角色<MenuSelect class="cloud-identity-menu" label="查看角色" :model-value="selectedChoice?.key || ''" :options="endfieldChoices.map(choice => ({ value: choice.key, label: choiceName(choice) }))" @change="openChoice" /></label></template><template v-else><p class="cloud-identity">{{ state.selected ? providerName(state.selected) : '游戏档案' }}</p><label v-if="state.selected">查看授权<MenuSelect class="cloud-identity-menu" label="查看授权" :model-value="state.selected.account_id" :options="state.accounts.filter(a=>gameFor(a)===selectedGame).map((account,index) => ({value:account.account_id,label:`${providerName(account)} · 授权 ${index+1}`}))" @change="openAccount(state.accounts.find(a=>a.account_id === $event))" /></label><label v-if="state.selected">查看角色<MenuSelect class="cloud-identity-menu" label="查看角色" :model-value="state.role" :options="(state.selected.roles || []).map((role,index) => ({value:role.role_id,label:`${role.display_name || `角色 ${index + 1}`}${role.is_default ? '（默认）' : ''}`}))" @change="dashboard.selectAccount(state.selected, $event)" /></label></template></header><p v-if="!state.accounts.length">还没有游戏账号，请到「账号与授权」登录。</p><p v-if="state.accounts.length && !state.selected" role="status">当前角色的授权已失效，请重新选择角色或到「账号与授权」检查。</p><p v-if="state.selected?.state === 'revoked'">此项授权已撤销，请重新授权。</p><template v-else-if="state.selected && state.role"><p v-for="[cap, value] in refreshMessages" :key="cap" role="status">{{ refreshLabel(cap) }}：{{ value }}</p><CloudGameCard :key="`${dataKey}:${routeTab}:${jumps}`" :section="routeTab || 'overview'" :account="state.selected" :role="state.role" :user-id="state.user.user_id" :is-admin="state.user.is_admin" :refreshing="refreshPending" :snapshots="state.snapshots" :read-states="state.readStates" :sources="state.sources" :source-snapshots="state.sourceSnapshots" :public-snapshots="publicSnapshots[selectedGame] || {}" @calendar="openCalendar(selectedGame)" @refresh="refresh" /></template><p v-else-if="state.selected && !state.role">此授权暂无角色，请到「账号与授权」检查。</p></template></template>
      </main></div>

      <SearchDialog v-if="searchOpen" :pages="searchPages" :games="searchGames" :snapshots="overviewSnapshots" :now="now" @select="jumpTo" @close="searchOpen = false" />
    </div>
  </div>
</template>
<style scoped>
/* A logout that did not finish: one card with the retry, where the login form would be. */
.logout-retry{width:min(100%,420px);margin:8vh auto;display:grid;gap:14px;justify-items:start}
/* One column that may shrink below its content: a rail of fixed-width cards must scroll, not widen the page. */
.cloud-content{display:grid;grid-template-columns:minmax(0,1fr);align-content:start;gap:20px}.cloud-navigation{overflow:auto}.cloud-navigation nav{display:grid;gap:5px}
.cloud-navigation nav button{display:flex;align-items:center;gap:11px;min-height:46px;text-align:left;padding:0 14px;border:0;border-radius:13px;background:transparent;color:var(--text-muted);cursor:pointer;font-size:14px;line-height:1.2}
.cloud-navigation small{font-size:12px;color:var(--text-muted)}
.cloud-grants{margin-top:16px;padding-top:12px;border-top:1px solid var(--border)}
.role-list-label{padding:0 14px 4px;color:var(--text-muted);font-size:12px;line-height:18px;font-weight:500}
.cloud-navigation .role-entry{display:grid;grid-template-columns:28px minmax(0,1fr) 14px;gap:10px;min-height:64px;min-width:0;padding:10px 14px;border-radius:12px;color:var(--text-body);font-weight:400;transition:background var(--duration-quick) var(--ease-smooth-out)}
.role-entry-icon{width:28px;height:28px;border-radius:8px;box-shadow:inset 0 0 0 1px var(--card-border)}
.role-entry-copy{display:grid;gap:2px;min-width:0}
.role-entry-heading{display:flex;align-items:center;gap:6px;min-width:0}
.role-entry-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:14px;line-height:20px;font-weight:500}
.role-entry-channel{flex-shrink:0;padding:0 4px;border:1px solid var(--border);border-radius:5px;color:var(--text-muted);font-size:11px;line-height:16px;font-weight:400;white-space:nowrap}
.role-entry-note{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--text-muted);font-size:12px;line-height:18px;font-weight:400}
.role-entry-check{color:var(--accent);opacity:0;transition:opacity var(--duration-quick) var(--ease-smooth-out)}
.role-entry[aria-pressed="true"] .role-entry-check{opacity:1}
.cloud-navigation .role-entry:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
/* Selected page: the pale accent with accent text, as on the local sidebar. */
.cloud-navigation .primary-nav button[aria-current="page"],
.cloud-navigation .game-nav button[aria-current="page"] { background:var(--nav-active-bg); color:var(--accent); font-weight:600; }
/* The chosen authorization is a setting, not the current page: a neutral tile, so only one item reads as "here". */
.cloud-navigation .cloud-grants button[aria-pressed="true"] { background:var(--panel-bg); color:var(--text); }
/* A selected game takes its own tone and ink. */
.cloud-navigation .game-nav button[aria-current="page"] { background:var(--game-tone, var(--nav-active-bg)); color:var(--game-accent, var(--accent)); }
@media(hover:hover) and (pointer:fine) {
  .cloud-navigation nav button:not([aria-current]):not([aria-pressed="true"]):hover { background:var(--hover-bg); color:var(--text); }
}
.cloud-navigation nav button:active { transform:translateY(1px); }
.cloud-game-heading{display:flex;flex-wrap:wrap;gap:12px 16px;align-items:end;padding:16px 18px;border-radius:var(--radius-tile);background:var(--card-bg);border:1px solid var(--card-border);box-shadow:var(--card-shadow)}.cloud-identity{width:100%;color:var(--text-muted);font-size:12px}.cloud-game-heading label{display:grid;gap:7px;font-size:13px;font-weight:500}
.cloud-identity-menu{max-width:100%;min-width:0}.cloud-identity-menu :deep(.menu-select-trigger){min-width:0;min-height:40px;width:100%}
.cloud-calendar{min-width:0;display:grid;gap:18px}.cloud-calendar-controls{display:flex;justify-content:flex-end}p[role=alert]{color:var(--danger);overflow-wrap:anywhere}
@media(max-width:960px){.cloud-game-heading>label{width:100%}.cloud-game-heading .cloud-identity-menu{width:100%}.cloud-content .cap-card{min-width:0}.topbar-right{gap:8px}}
/* Sessions (mockup .session-card): one row per signed-in device, hairlines between. */
.cloud-sessions{min-width:0;display:grid;gap:20px}
.cloud-sessions > .page-heading{display:grid;grid-template-columns:minmax(0,1fr) auto;margin-bottom:0}
.session-note{color:var(--text-muted);font-size:13px}
.session-card > article{display:flex;flex-wrap:wrap;align-items:center;gap:10px 12px;padding:14px 0;border-top:1px solid var(--border)}
.session-card > .session-note + article{margin-top:14px}
.session-card > article > svg{color:var(--text-muted)}
.session-card > article > p{flex:1;min-width:0;font-size:13px;font-variant-numeric:tabular-nums}
.cloud-owner-note{padding:12px 16px;border-radius:var(--radius-well);background:var(--panel-bg);border:1px solid var(--border);color:var(--text-muted);font-size:13px}
.cloud-owner-note > summary{cursor:pointer;color:var(--text-body);font-weight:500}
</style>
