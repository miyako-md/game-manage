<script setup>
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { createCloudDashboard } from './cloud-dashboard.js'
import { accountCapabilities, providerName, connectCloudSkland, getPublicSnapshot } from './accounts-api.js'
import { revokeSession, getMe } from './identity-api.js'
import { followSystem, theme, setTheme } from './theme.js'
import { CLOUD_GAMES, cloudOverviewView, gameForAccount } from './cloud-view-model.js'
import { capabilityLabel } from './cloud-display.js'
import AppIcon from './components/AppIcon.vue'
import GameIcon from './components/GameIcon.vue'
import { gameStyle, readRoute } from './dashboard.js'
import SiteLogin from './components/SiteLogin.vue'
import AccountSettings from './components/AccountSettings.vue'
import QqBindingPanel from './components/QqBindingPanel.vue'
import LoginPanel from './components/LoginPanel.vue'
import CloudGameCard from './components/CloudGameCard.vue'
import CalendarPage from './components/CalendarPage.vue'
import OverviewPage from './components/OverviewPage.vue'
import CloudBilibiliSourcePanel from './components/CloudBilibiliSourcePanel.vue'
const dashboard = createCloudDashboard(), state = dashboard.state
const initialHash = globalThis.window?.location?.hash || ''
const initialRoute = /#\/sessions(?:$|\?)/.test(initialHash) ? {page:'sessions',game:''} : readRoute(initialHash)
const page = ref(initialRoute.page), cred = ref(''), deviceId = ref(''), connectBusy = ref(false), logoutBusy = ref(false)
const calendarGame = ref(initialRoute.page === 'calendar' ? initialRoute.game || 'all' : 'all'), now = ref(Date.now())
const publicGame = ref('wuthering_waves'), publicSnapshots = ref({}), publicError = ref('')
const calendarSnapshots = ref({}), calendarReadErrors = ref({}), calendarLoading = ref(false)
const publicGames = CLOUD_GAMES
const menuOpen = ref(false), sidebar = ref(null), menuToggle = ref(null), mainContent = ref(null)
const navigationMedia = globalThis.window?.matchMedia?.('(max-width: 720px)')
const mobileNavigation = ref(navigationMedia?.matches || false)
const pageTitle = computed(()=>({overview:'今日总览',calendar:'活动日历',accounts:'社区账号',sessions:'网站会话',game:publicGames.find(g=>g.game_id===selectedGame.value)?.display_name || '游戏档案'})[page.value])
const today = computed(()=>new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'long',day:'numeric',weekday:'long'}).format(now.value))
let routeGame = initialRoute.page === 'game' ? initialRoute.game : ''
function writeRoute(destination, game='') {
  if (!globalThis.window) return
  const next = destination==='game' ? `/game/${encodeURIComponent(game)}` : destination==='calendar' ? `/calendar${game && game!=='all' ? '?game='+encodeURIComponent(game) : ''}` : destination==='overview' ? '/' : `/${destination}`
  if (window.location.hash !== '#'+next) window.location.hash = next
}
function setPage(destination) { routeGame=''; page.value=destination; writeRoute(destination); sidebarNavigate() }
async function openMenu() { menuOpen.value=true; await nextTick(); sidebar.value?.querySelector?.('.primary-nav button')?.focus?.() }
async function closeMenu() { menuOpen.value=false; await nextTick(); menuToggle.value?.focus?.() }
function sidebarNavigate() { menuOpen.value=false; if(mobileNavigation.value)nextTick(()=>mainContent.value?.focus?.({preventScroll:true})) }
function mediaChanged(event) { mobileNavigation.value=event.matches; if(!event.matches)menuOpen.value=false }
function handleKey(event) {
  if(event.key==='Escape' && menuOpen.value)closeMenu()
  if(event.key==='Tab' && menuOpen.value && mobileNavigation.value) {
    const controls=[...(sidebar.value?.querySelectorAll?.('a[href],button:not([disabled])') || [])], first=controls[0],last=controls.at(-1)
    if(event.shiftKey && globalThis.document?.activeElement===first){event.preventDefault();last?.focus()}
    else if(!event.shiftKey && globalThis.document?.activeElement===last){event.preventDefault();first?.focus()}
  }
}
function syncRoute() {
  const hash=globalThis.window?.location?.hash || '', route=/#\/sessions(?:$|\?)/.test(hash)?{page:'sessions',game:''}:readRoute(hash)
  page.value=route.page; routeGame=route.page==='game'?route.game:''
  if(route.page==='calendar')calendarGame.value=route.game || 'all'
  if(routeGame && state.user) { const account=state.accounts.find(a=>a.state!=='revoked' && gameFor(a)===routeGame); if(account && gameFor(state.selected)!==routeGame)dashboard.selectAccount(account); if(account){publicGame.value=routeGame;loadPublic(routeGame)} }
  menuOpen.value=false;globalThis.window?.scrollTo?.({top:0,behavior:'instant'});nextTick(()=>mainContent.value?.focus?.({preventScroll:true}))
}
const gameFor = gameForAccount
const overviewView = computed(()=>cloudOverviewView({accounts:state.accounts,snapshotsByAccount:Object.fromEntries(Object.entries(state.overview).map(([id,entry])=>[id,entry.snapshots || {}])),publicSnapshots:publicSnapshots.value,calendarSnapshots:calendarSnapshots.value}))
const ownerGames = computed(()=>overviewView.value.ownerGames)
const overviewOwners = computed(()=>overviewView.value.owners)
const overviewGames = computed(()=>overviewView.value.games)
const overviewSnapshots = computed(()=>overviewView.value.snapshots)
const overviewAccounts = computed(()=>overviewView.value.accounts)
const overviewErrors = computed(()=>overviewView.value.readErrors)
const overviewCollection = computed(()=>overviewView.value.collection)
const selectedGame = computed(() => gameFor(state.selected))
const refreshPending = computed(() => Object.values(state.refreshPending).some(Boolean))
const refreshMessages = computed(() => Object.entries(state.refreshing).filter(([, value]) => value))
const caps = computed(() => accountCapabilities(state.selected)), dataKey = computed(() => `${state.user?.user_id}:${state.selected?.account_id}:${state.role}:${state.revision}`)
const publicReadVersions = new Map(), publicLoadVersions = new Map()
let timer, stopTheme, publicGeneration = 0, calendarGeneration = 0
function clearPublicData() {
  publicGeneration++; calendarGeneration++; publicReadVersions.clear(); publicLoadVersions.clear()
  publicSnapshots.value = {}; publicError.value = ''
  calendarSnapshots.value = {}; calendarReadErrors.value = {}; calendarLoading.value = false; calendarGame.value = 'all'
}
async function authenticated() { await dashboard.initialize(); syncRoute() }
async function logout() { if (logoutBusy.value) return; logoutBusy.value = true; cred.value = ''; deviceId.value = ''; clearPublicData(); try { await dashboard.logout() } finally { logoutBusy.value = false; page.value = 'overview' } }
async function connect() { if (connectBusy.value || !cred.value.trim()) return; connectBusy.value = true; const bodyCred = cred.value.trim(), bodyDevice = deviceId.value.trim(); cred.value = ''; deviceId.value = ''; try { await connectCloudSkland(bodyCred, bodyDevice); await dashboard.loadAccounts() } catch (error) { if (error.name !== 'AbortError') state.error = error.message } finally { connectBusy.value = false } }
async function refresh() { await Promise.all(caps.value.map(cap => dashboard.refresh(cap))) }
async function readSnapshots() { if (state.user && state.selected?.state !== 'revoked') await Promise.all(caps.value.map(cap => dashboard.loadSnapshot(cap))) }
async function revoke(id) { try { await revokeSession(id); await getMe(); await dashboard.loadSessions() } catch (error) { if (error.status !== 401 && error.name !== 'AbortError') state.error = error.message } }
async function readPublicSnapshot(game, cap) {
  const generation = publicGeneration, owner = state.user?.user_id, key = `${game}:${cap}`
  const version = (publicReadVersions.get(key) || 0) + 1
  publicReadVersions.set(key,version)
  const current = () => generation === publicGeneration && owner === state.user?.user_id && version === publicReadVersions.get(key)
  try {
    const snapshot = await getPublicSnapshot(game,cap)
    if (current()) {
      publicSnapshots.value = {...publicSnapshots.value,[game]:{...publicSnapshots.value[game],[cap]:snapshot}}
      if(cap === 'events') { calendarSnapshots.value = {...calendarSnapshots.value,[game]:{events:snapshot}}; delete calendarReadErrors.value[game] }
    }
    return current() ? snapshot : null
  } catch(error) {
    if(!current()) return null
    if(current() && error.name !== 'AbortError') {
      const old=publicSnapshots.value[game]?.[cap]
      {
        const retained={...(old || {payload:null}),state:'error',error:error.message}
        publicSnapshots.value={...publicSnapshots.value,[game]:{...publicSnapshots.value[game],[cap]:retained}}
        if(cap==='events') calendarSnapshots.value={...calendarSnapshots.value,[game]:{events:retained}}
      }
    }
    throw error
  }
}
async function loadPublic(game = publicGame.value) {
  const version = publicGeneration, owner = state.user?.user_id, request = (publicLoadVersions.get(game) || 0)+1
  if (!owner) return
  publicLoadVersions.set(game,request); publicError.value = ''
  try { await Promise.all([readPublicSnapshot(game,'news'), readPublicSnapshot(game,'events')]) }
  catch (error) { if (version === publicGeneration && owner === state.user?.user_id && request === publicLoadVersions.get(game) && game === publicGame.value && error.name !== 'AbortError') publicError.value = error.message }
}
function openCalendar(game = 'all') { calendarGame.value = game; page.value = 'calendar'; writeRoute('calendar',game); sidebarNavigate() }
function openAccount(account) { if (!account) return; dashboard.selectAccount(account); publicGame.value = gameFor(account) || 'wuthering_waves'; page.value = 'game'; routeGame=publicGame.value; writeRoute('game',routeGame); sidebarNavigate(); loadPublic(publicGame.value) }
function navigate(destination, game) { if (destination === 'calendar') openCalendar(game || 'all'); else if (destination === 'game') openAccount(overviewOwners.value[game]); else setPage(destination) }
async function readOverview() { await readSnapshots(); await dashboard.loadOverview(); await Promise.all(ownerGames.value.map(game=>loadPublic(game.game_id))) }
async function loadCalendar() {
  if (!state.user || calendarLoading.value) return
  const version = ++calendarGeneration, owner = state.user.user_id
  const current = () => version === calendarGeneration && owner === state.user?.user_id
  calendarLoading.value = true
  try {
    await Promise.all(publicGames.map(async game => {
      const id = game.game_id
      try {
        const events = await readPublicSnapshot(id, 'events')
        if (events && current()) delete calendarReadErrors.value[id]
      } catch (error) {
        if (current() && error.name !== 'AbortError') calendarReadErrors.value[id] = error.message
      }
    }))
  } finally { if (current()) calendarLoading.value = false }
}
watch(()=>state.accounts,()=>{if(routeGame && page.value==='game'){const account=state.accounts.find(a=>a.state!=='revoked' && gameFor(a)===routeGame);if(account && gameFor(state.selected)!==routeGame)openAccount(account)}}, {flush:'post'})
watch(publicGame,()=>{publicError.value=''})
watch(dataKey, async () => { const key=dataKey.value; await readSnapshots(); if(key === dataKey.value && page.value === 'overview') { await dashboard.loadOverview(); await Promise.all(ownerGames.value.map(game=>loadPublic(game.game_id))) } })
watch(() => state.user?.user_id, () => { cred.value = ''; deviceId.value = ''; clearPublicData() }, { flush: 'sync' })
watch(page, value => { cred.value = ''; deviceId.value = ''; if (value === 'sessions') dashboard.loadSessions(); if (value === 'calendar') loadCalendar(); if(value === 'overview') readOverview() })
onMounted(() => { globalThis.window?.addEventListener('hashchange',syncRoute); globalThis.window?.addEventListener('keydown',handleKey); navigationMedia?.addEventListener('change',mediaChanged); dashboard.initialize().then(syncRoute); stopTheme = followSystem(); timer = setInterval(async () => {
  // initialize invalidates the controller epoch. Let bounded refresh tracking
  // settle first; its snapshot GETs still enforce session ownership and 401.
  now.value = Date.now(); if (state.user && !refreshPending.value) { await dashboard.initialize(); await readSnapshots(); if(page.value === 'overview') await dashboard.loadOverview() }
}, 60000) })
onBeforeUnmount(() => { globalThis.window?.removeEventListener('hashchange',syncRoute); globalThis.window?.removeEventListener('keydown',handleKey); navigationMedia?.removeEventListener('change',mediaChanged); clearInterval(timer); stopTheme?.(); dashboard.dispose(); clearPublicData(); cred.value = ''; deviceId.value = '' })
</script>
<template>
  <div class="workbench cloud-app" :class="{'menu-open':menuOpen}">
    <a class="skip-link" href="#main-content" @click.prevent="mainContent?.focus?.()">跳到主要内容</a>
    <main v-if="!state.user" class="cloud-content"><p v-if="!state.ready || logoutBusy" role="status">{{ logoutBusy ? '正在退出网站…' : '正在检查网站会话…' }}</p><SiteLogin v-else @authenticated="authenticated" /><p v-if="state.error" role="alert">{{ state.error }}</p></main>
    <div v-else>
      <button v-if="menuOpen" class="sidebar-scrim" aria-label="关闭导航" tabindex="-1" @click="closeMenu"></button>
      <aside id="workspace-sidebar" ref="sidebar" class="workspace-sidebar cloud-navigation" :inert="mobileNavigation && !menuOpen">
        <a class="brand" href="#/" @click.prevent="setPage('overview')"><span class="brand-symbol"><AppIcon name="spark" :size="20" /></span><span>游戏管家<small>PERSONAL GAME SPACE</small></span></a>
        <button class="mobile-sidebar-close icon-button" aria-label="关闭导航" @click="closeMenu"><AppIcon name="close" /></button>
        <nav class="primary-nav" aria-label="云端导航"><button :aria-current="page === 'overview' ? 'page' : undefined" @click="setPage('overview')">本人游戏看板</button><button :aria-current="page === 'calendar' ? 'page' : undefined" @click="openCalendar()">活动日历</button><button :aria-current="page === 'accounts' ? 'page' : undefined" @click="setPage('accounts')">账号与授权</button><button :aria-current="page === 'sessions' ? 'page' : undefined" @click="setPage('sessions')">网站会话</button></nav><p>云端模式 · 仅显示本人数据</p><div class="sidebar-label"><span>我的游戏</span><span>{{ String(ownerGames.length).padStart(2,'0') }}</span></div><nav class="game-nav" aria-label="游戏导航"><button v-for="game in ownerGames" :key="game.game_id" :aria-current="page === 'game' && selectedGame === game.game_id ? 'page' : undefined" @click="openAccount(overviewOwners[game.game_id])"><GameIcon class="nav-game-mark" :game-id="game.game_id" :name="game.display_name" /><span>{{ game.display_name }}</span></button></nav><nav class="cloud-grants" aria-label="本人授权"><button v-for="(account, index) in state.accounts" :key="account.account_id" :aria-pressed="account.account_id === state.selected?.account_id" @click="openAccount(account)">{{ providerName(account) }}<small>授权 {{ index + 1 }}</small></button></nav><div class="sidebar-bottom"><p class="local-status"><i></i>网站会话已连接</p><div><AppIcon name="shield" :size="13" />本人空间 · 按授权与角色隔离</div></div></aside>
      <div class="workspace-body" :inert="mobileNavigation && menuOpen"><header class="workspace-topbar"><div class="topbar-left"><button ref="menuToggle" class="menu-toggle icon-button" :aria-expanded="menuOpen" aria-controls="workspace-sidebar" aria-label="打开导航" @click="openMenu"><AppIcon name="menu" /></button><span class="breadcrumb"><span class="breadcrumb-root">个人空间</span><span class="breadcrumb-separator">/</span><b>{{ pageTitle }}</b></span></div><div class="topbar-right"><span class="topbar-date">{{ today }}</span><button class="icon-button theme-toggle" :aria-label="theme === 'light' ? '切换到夜间模式' : '切换到白天模式'" @click="setTheme(theme === 'light' ? 'dark' : 'light')"><AppIcon :name="theme === 'light' ? 'moon' : 'sun'" :size="16" /></button><button class="ui-button small-button" @click="setPage('accounts')">社区账号</button><button class="ui-button small-button" :disabled="logoutBusy" @click="logout">退出网站</button></div></header>
      <main id="main-content" ref="mainContent" tabindex="-1" class="workspace-main cloud-content"><p v-if="state.error" role="alert">{{ state.error }}</p>
        <template v-if="page === 'accounts'"><CloudBilibiliSourcePanel v-if="state.user.is_admin" :key="state.user.user_id" /><QqBindingPanel :key="state.user.user_id" /><AccountSettings :accounts="state.accounts" @changed="dashboard.loadAccounts()" /><LoginPanel @account-changed="dashboard.loadAccounts()" /><section class="cap-card cloud-skland"><h2>终末地 · 森空岛档案授权</h2><p>与鹰角寻访独立。凭据仅提交到云端授权中心，用后清空。</p><form @submit.prevent="connect"><label>森空岛 cred<input v-model="cred" type="password" autocomplete="off" required maxlength="4096" /></label><label>设备标识（如需要）<input v-model="deviceId" autocomplete="off" maxlength="512" /></label><button class="ui-button" :disabled="connectBusy">{{ connectBusy ? '连接中…' : '连接森空岛档案' }}</button></form></section></template>
        <section v-else-if="page === 'calendar'" class="cloud-calendar"><div class="cloud-calendar-controls"><p>默认汇总全部游戏活动，可在日历中筛选游戏。</p><button class="ui-button" :disabled="calendarLoading" @click="loadCalendar">读取公共活动</button></div><CalendarPage :key="state.user.user_id" :games="publicGames" :snapshots="calendarSnapshots" :initial-game-id="calendarGame" :read-errors="calendarReadErrors" :loading="calendarLoading" show-source-status /></section><section v-else-if="page === 'sessions'" class="cap-card"><h1>网站会话</h1><p>撤销会话会立即禁止该设备访问本人数据。</p><article v-for="(session, index) in state.sessions" :key="session.session_id"><p>会话 {{ index + 1 }} · 创建 {{ session.created_at }} · 过期 {{ session.expires_at }}</p><button class="ui-button" @click="revoke(session.session_id)">撤销此会话</button></article><button class="ui-button" @click="dashboard.loadSessions()">刷新会话列表</button></section>
        <template v-else><template v-if="page === 'overview'"><OverviewPage :games="overviewGames" :snapshots="overviewSnapshots" :accounts="overviewAccounts" :read-errors="overviewErrors" :collection="overviewCollection" :now="now" :loading="state.loading || state.overviewLoading" refresh-label="读取总览快照" storage-label="云端本人空间 · 按授权与默认角色显示" @navigate="navigate" @refresh="readOverview" /><details class="cloud-owner-note"><summary>查看总览数据的授权与角色</summary><p>每款游戏使用下列授权的默认角色；终末地两类授权分别查看。</p><p v-for="game in overviewGames" :key="game.game_id">{{ game.display_name }} · {{ providerName(overviewOwners[game.game_id]) }} · {{ overviewOwners[game.game_id].roles?.find(r=>r.is_default)?.display_name || overviewOwners[game.game_id].roles?.[0]?.display_name || '角色名称未提供' }}{{ overviewOwners[game.game_id].roles?.some(r=>r.is_default) ? '（默认）' : '（首个角色，尚未设置默认）' }}</p></details><p v-if="!state.accounts.length">尚未关联游戏账号，请到「账号与授权」完成社区授权。</p></template><template v-else><header class="cloud-game-heading"><p class="cloud-identity">{{ state.selected ? providerName(state.selected) : '本人游戏看板' }}</p><label v-if="state.selected">查看授权<select :value="state.selected.account_id" @change="openAccount(state.accounts.find(a=>a.account_id === $event.target.value))"><option v-for="(account,index) in state.accounts.filter(a=>gameFor(a)===selectedGame)" :key="account.account_id" :value="account.account_id">{{ providerName(account) }} · 授权 {{ index+1 }}</option></select></label><label v-if="state.selected">查看角色<select :value="state.role" @change="dashboard.selectAccount(state.selected, $event.target.value)"><option v-for="(role, index) in state.selected.roles || []" :key="role.role_id" :value="role.role_id">{{ role.display_name || `角色 ${index + 1}` }}{{ role.is_default ? '（默认）' : '' }}</option></select></label></header><p v-if="!state.accounts.length">尚未关联游戏账号，请到「账号与授权」完成社区授权。</p><p v-if="state.selected?.state === 'revoked'">此项授权已撤销，请重新授权后查看数据。</p><template v-else-if="state.selected && state.role"><p v-for="[cap, value] in refreshMessages" :key="cap" role="status">{{ capabilityLabel(cap) }}：{{ value }}</p><CloudGameCard :key="dataKey" :account="state.selected" :role="state.role" :user-id="state.user.user_id" :is-admin="state.user.is_admin" :refreshing="refreshPending" :snapshots="state.snapshots" :public-snapshots="publicSnapshots[selectedGame] || {}" @calendar="openCalendar(selectedGame)" @refresh="refresh" /></template><p v-else-if="state.selected && !state.role">此授权尚无可选角色，请到账号与授权检查角色同步。</p></template></template>
      </main></div>
    </div>
  </div>
</template>
<style scoped>
.cloud-content{display:grid;align-content:start;gap:20px}.cloud-navigation{overflow:auto}.cloud-navigation nav{display:grid;gap:4px}.cloud-navigation nav button{display:flex;align-items:center;gap:10px;text-align:left;padding:11px 14px;border:0;border-radius:9px;background:transparent;color:var(--text-muted);cursor:pointer;font-size:13px}.cloud-navigation nav button[aria-current],.cloud-navigation nav button[aria-pressed=true]{background:var(--button-hover-bg);color:var(--text);font-weight:600}.cloud-navigation small{font-size:11px;color:var(--text-faint)}.cloud-grants{margin-top:16px}.cloud-grants button{flex-wrap:wrap}.cloud-navigation>p{font-size:11px;color:var(--text-faint);padding:12px}.cloud-game-heading{display:flex;flex-wrap:wrap;gap:12px;align-items:end}.cloud-identity{width:100%;color:var(--text-muted);font-size:12px}.cloud-skland,.cloud-skland form{display:grid;gap:14px}.cloud-skland label,.cloud-game-heading label{display:grid;gap:7px}.cloud-content input,.cloud-content select{max-width:100%;box-sizing:border-box;min-width:0;padding:10px;border:1px solid var(--border);border-radius:8px;background:var(--card-bg);color:var(--text)}.cloud-public{display:grid;gap:14px}.cloud-calendar{min-width:0;display:grid;gap:18px}.cloud-calendar-controls{display:flex;gap:12px;align-items:end;flex-wrap:wrap}p[role=alert]{color:var(--danger);overflow-wrap:anywhere}@media(max-width:720px){.cloud-game-heading>label{width:100%}.cloud-game-heading select{width:100%}.cloud-content .cap-card{min-width:0}.topbar-right{gap:8px}}
</style>
