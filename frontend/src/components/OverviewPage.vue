<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import { gameStyle, summaryFor, upcomingEvents, recentNews, formatTime } from '../dashboard.js'
import { sourceForGame } from '../source-status.js'

const props = defineProps({ games: { type: Array, default: () => [] }, snapshots: { type: Object, default: () => ({}) },
  accounts: { type: Object, default: () => ({}) }, readErrors: { type: Object, default: () => ({}) }, refreshErrors: { type: Object, default: () => ({}) },
  refreshing: { type: Object, default: () => ({}) }, collection: { type: Array, default: () => [] }, now: { type: Number, required: true }, loading: Boolean })
const emit = defineEmits(['navigate', 'refresh'])
const newsFilter = ref('')
const sourceFilter = ref('')
const cards = computed(() => props.games.map(game => ({ ...game, style: gameStyle(game.game_id), summary: summaryFor(game, props.snapshots[game.game_id]), auth: props.accounts[game.game_id], source: sourceForGame(game.game_id, props.collection) })))
const events = computed(() => upcomingEvents(props.games, props.snapshots, props.now))
const nearEvents = computed(() => events.value.filter(event => event.remainingDays <= 3))
const fullGames = computed(() => cards.value.filter(card => card.summary.hasStamina && card.summary.percent >= 90 && !card.summary.stale && !props.readErrors[card.game_id] && (!card.source || card.source.state === 'ok')))
const news = computed(() => recentNews(props.games, props.snapshots).filter(item => (!newsFilter.value || item.gameId === newsFilter.value) && (!sourceFilter.value || item.source === sourceFilter.value)).slice(0, 5))
const anyRefreshing = computed(() => Object.values(props.refreshing).some(Boolean))
const notices = computed(() => cards.value.filter(g => props.readErrors[g.game_id] || props.refreshErrors[g.game_id]))
function status(card) {
  if (props.readErrors[card.game_id]) return '读取异常'
  if (card.source && card.source.state !== 'ok') return card.source.label
  if (card.auth?.state === 'expired') return '登录已失效'
  if (card.summary.stale) return '旧快照'
  if (card.game_id === 'league_of_legends') return '本机客户端'
  return ({ connected: '已连接', configured: '已配置', unconfigured: '未登录' })[card.auth?.state] || (card.credentials_configured ? '已配置' : '未登录')
}
const METRIC_UNITS = { stats: '%', gacha: '抽' }
function metricLabel(card) {
  return ({ stamina: card.style.resource, gacha: '特许寻访 · 距上次 6★' })[card.summary.metric] || '最近对局胜率'
}
function resourceNote(card) {
  const s = card.summary
  if (s.metric === 'gacha') return s.value == null ? '等待寻访记录同步' : s.pityStatus === 'exact' ? '按连续的寻访记录计算' : '记录有断档或含免费寻访，这是最少抽数'
  if (!s.hasStamina) return s.totalGames == null ? '等待对局数据' : `最近 ${s.totalGames} 场 · ${s.wins == null ? '胜场未知' : `${s.wins} 胜`}`
  if (card.game_id === 'nte') return '塔吉多体力快照 · 可能有同步延迟'
  if (s.percent >= 100) return '快照显示体力已满'
  if (s.expectedFullAt) return `预计 ${formatTime(s.expectedFullAt)} 回满`
  return '恢复时间未提供'
}
</script>

<template>
  <div class="overview-page">
    <header class="overview-hero">
      <div class="hero-copy"><p class="eyebrow">YOUR DAILY CHECK-IN</p><h1>今晚，先看这里。</h1><p class="page-description">你的游戏、活动与进度，都在这张工作台。</p></div>
      <div class="hero-actions"><span class="hero-count"><b>{{ String(games.length).padStart(2, '0') }}</b><span>个游戏<br>正在关注</span></span><button class="ui-button" :disabled="loading || anyRefreshing || !games.length" @click="emit('refresh')"><AppIcon name="refresh" :class="{ spinning: anyRefreshing }" />{{ anyRefreshing ? '同步中…' : '刷新数据' }}</button></div>
    </header>

    <div v-if="fullGames.length || nearEvents.length" class="attention-strip">
      <AppIcon name="clock" /><p><span v-if="fullGames.length">{{ fullGames.map(g => g.display_name).join('、') }}体力已达 90%</span><span v-if="fullGames.length && nearEvents.length"> · </span><span v-if="nearEvents.length">{{ nearEvents.length }} 项活动将在 3 天内结束</span></p>
      <button class="text-link" @click="emit('navigate', 'calendar')">查看日历 <AppIcon name="arrow" :size="15" /></button>
    </div>
    <div v-for="game in notices" :key="game.game_id" class="inline-warning" role="status"><strong>{{ game.display_name }}</strong> · {{ refreshErrors[game.game_id] || readErrors[game.game_id] }}</div>

    <div class="section-heading"><h2>我的游戏 <span class="count-label">/ {{ String(games.length).padStart(2, '0') }}</span></h2><span class="muted small">各游戏独立同步</span></div>
    <div class="game-summary-grid">
      <button v-for="card in cards" :key="card.game_id" class="game-summary" :style="{ '--game-color': card.style.color }" @click="emit('navigate', 'game', card.game_id)">
        <div class="summary-header"><div class="game-identity"><GameIcon class="game-monogram" :game-id="card.game_id" :name="card.display_name" /><div><h3>{{ card.display_name }}</h3><p>{{ card.game_id === 'league_of_legends' ? 'PC / 国服' : '手游 / 社区数据' }}</p></div></div><span class="summary-state" :class="{ warn: card.summary.stale || card.auth?.state === 'expired' || readErrors[card.game_id] || card.source?.tone === 'danger' }"><i></i>{{ status(card) }}</span></div>
        <div class="summary-metric"><p>{{ metricLabel(card) }}</p><div class="summary-number">{{ card.summary.metric === 'gacha' && card.summary.pityStatus === 'lower_bound' && card.summary.value != null ? '≥' : '' }}{{ card.summary.value ?? '—' }}<small>{{ card.summary.hasStamina ? `/ ${card.summary.maximum ?? '—'}` : METRIC_UNITS[card.summary.metric] }}</small></div></div>
        <div v-if="card.summary.percent != null" class="summary-meter" role="meter" :aria-label="card.summary.hasStamina ? card.style.resource : '胜率'" :aria-valuenow="card.summary.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${Math.min(100, card.summary.percent)}%` }"></i></div>
        <div v-else class="summary-meter unknown"></div>
        <p class="summary-note">{{ resourceNote(card) }}</p>
        <div class="summary-account"><span>{{ card.summary.nickname || '暂无账号数据' }}<small v-if="card.summary.level != null">Lv.{{ card.summary.level }}</small></span><AppIcon name="arrow" :size="17" /></div>
        <p class="summary-updated">{{ card.summary.fetchedAt ? `更新于 ${formatTime(card.summary.fetchedAt)}` : '尚无成功快照' }}</p>
      </button>
    </div>
    <p v-if="!games.length" class="empty-page">{{ loading ? '正在读取游戏数据…' : '暂无已启用的游戏。' }}</p>

    <div class="overview-lower">
      <section><div class="section-heading"><h2>临近截止</h2><button class="text-link" @click="emit('navigate', 'calendar')">全部活动 <AppIcon name="arrow" :size="15" /></button></div>
        <div class="overview-list"><p v-if="!events.length" class="empty-page">{{ loading ? '正在读取活动…' : '当前没有已知截止时间的待结束活动。' }}</p><button v-for="event in events.slice(0, 5)" :key="event.id" class="event-summary" @click="emit('navigate', 'calendar', event.gameId)"><span class="event-date"><b>{{ formatTime(event.end_at, { day: '2-digit', month: undefined, hour: undefined, minute: undefined }).replace('日', '') }}</b><small>截止日</small></span><span class="event-copy"><strong>{{ event.name }}</strong><small>{{ event.gameName }} · {{ event.category || '限时活动' }}</small><small>{{ formatTime(event.end_at) }} 截止<span v-if="event.stale"> · 数据可能过期</span></small></span><span class="deadline-label" :class="{ urgent: event.remainingDays <= 3 }">{{ event.upcoming ? '未开始 · ' : '' }}剩 {{ event.remainingDays }} 天</span></button></div>
      </section>
      <section><div class="section-heading"><h2>公告与资讯</h2><label class="sr-only" for="news-game-filter">公告游戏筛选</label><select id="news-game-filter" v-model="newsFilter" class="quiet-select"><option value="">全部游戏</option><option v-for="g in games" :key="g.game_id" :value="g.game_id">{{ g.display_name }}</option></select><label class="sr-only" for="news-source-filter">资讯来源</label><select id="news-source-filter" v-model="sourceFilter" class="quiet-select"><option value="">全部来源</option><option value="bilibili">B站官方动态</option></select></div>
        <div class="overview-list news-list"><p v-if="!news.length" class="empty-page">{{ loading ? '正在读取公告…' : '暂无公告快照。' }}</p><article v-for="(item, i) in news" :key="`${item.gameId}:${item.title}:${i}`" class="news-summary"><div class="news-source"><i :style="{ background: gameStyle(item.gameId).color }"></i>{{ item.gameName }}<span> / {{ item.source_name || (item.capability === 'news' ? '资讯' : '官方公告') }}<span v-if="item.stale"> · 旧快照</span></span></div><a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }} <span>↗</span></a><p v-else>{{ item.title }}</p><time v-if="item.published_at">{{ formatTime(item.published_at) }}</time></article></div>
      </section>
    </div>
    <footer class="overview-footer"><span><AppIcon name="shield" :size="14" />数据保存在本机</span><span>日期与时间均为北京时间</span></footer>
  </div>
</template>

<style scoped>
.overview-hero { display:flex; justify-content:space-between; align-items:center; gap:25px; min-height:166px; padding:18px 0 28px; position:relative; }
.hero-copy h1 { font-size:34px; font-weight:550; letter-spacing:-1px; margin:12px 0 9px; }
.hero-actions { display:flex; align-items:center; gap:24px; }
.hero-count { display:flex; align-items:center; gap:12px; color:var(--text-muted); }
.hero-count b { font-size:58px; line-height:1; font-weight:300; letter-spacing:-3px; color:var(--accent); }
.hero-count span { font-size:11px; line-height:1.8; }
.attention-strip { display:flex; align-items:center; gap:12px; padding:14px 17px; background:#2d2c27; border:1px solid #4c4537; border-radius:8px; color:#ddc99f; }
.attention-strip p { flex:1; font-size:12px; }.attention-strip .text-link { color:#ddc99f; }
.section-heading { margin:27px 0 13px; }
.game-summary-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }
.game-summary { text-align:left; border:1px solid var(--border); border-radius:12px; padding:20px; background:var(--card-bg); color:var(--text); min-width:0; position:relative; transition:border-color .15s,transform .15s; cursor:pointer; }
.game-summary:hover { border-color:var(--game-color); transform:translateY(-2px); }
.game-summary:before { content:''; position:absolute; inset:0 26px auto; height:1px; background:var(--game-color); opacity:.35; }
.summary-header { display:flex; align-items:center; justify-content:space-between; gap:8px; flex-wrap:wrap; }
.game-identity { display:flex; align-items:center; gap:10px; }.game-monogram { display:grid; place-items:center; width:38px; height:38px; border:1px solid var(--border); border-radius:9px; background:var(--bg); color:var(--game-color); font-size:20px; }
.game-identity h3 { font-size:15px; font-weight:550; }.game-identity p { color:var(--text-muted); font-size:10px; margin-top:3px; }
.summary-state { font-size:10px; color:var(--success); display:flex; align-items:center; gap:5px; }.summary-state.warn { color:var(--stale-text); }.summary-state i { width:4px; height:4px; background:currentColor; border-radius:50%; }
.summary-metric { margin-top:26px; }.summary-metric>p { font-size:11px; color:var(--text-muted); }.summary-number { margin-top:4px; font-size:37px; font-weight:500; font-variant-numeric:tabular-nums; letter-spacing:-1px; }.summary-number small { font-size:13px; color:var(--text-muted); font-weight:400; margin-left:5px; letter-spacing:0; }
.summary-meter { height:4px; border-radius:9px; background:#293440; margin:13px 0 10px; overflow:hidden; }.summary-meter i { display:block; height:100%; background:var(--game-color); }.summary-meter.unknown { background:repeating-linear-gradient(120deg,#293440 0 4px,transparent 4px 8px); }
.summary-note { font-size:10px; color:var(--text-muted); min-height:30px; }.summary-account { border-top:1px solid var(--border); padding-top:14px; margin-top:12px; display:flex; justify-content:space-between; align-items:center; color:var(--text); font-size:12px; gap:8px; }.summary-account>span { min-width:0; overflow-wrap:anywhere; }.summary-account small { margin-left:8px; color:var(--text-muted); font-size:10px; }.summary-account svg { color:var(--game-color); }.summary-updated { font-size:10px; color:var(--text-muted); margin-top:8px; }
.overview-lower { display:grid; grid-template-columns:1.1fr 1fr; gap:24px; }.overview-lower>section { min-width:0; }.overview-list { border:1px solid var(--border); border-radius:10px; background:var(--card-bg); padding:0 18px; }
.event-summary { width:100%; display:flex; align-items:center; gap:13px; border:0; border-bottom:1px solid var(--border); background:transparent; color:var(--text); text-align:left; padding:18px 0; cursor:pointer; }.event-summary:last-child { border:0; }.event-summary:hover strong { color:var(--accent); }
.event-date { width:37px; flex-shrink:0; text-align:center; border-right:1px solid var(--border); padding-right:10px; }.event-date b { font-size:24px; font-weight:400; color:var(--accent); }.event-date small { display:block; font-size:9px; color:var(--text-muted); }.event-copy { flex:1; min-width:0; }.event-copy strong { font-size:12px; font-weight:500; display:block; overflow-wrap:anywhere; }.event-copy small { display:block; font-size:10px; color:var(--text-muted); margin-top:5px; }.deadline-label { font-size:10px; color:var(--text-muted); white-space:nowrap; }.deadline-label.urgent { color:var(--stale-text); }
.news-summary { border-bottom:1px solid var(--border); padding:15px 0; }.news-summary:last-child { border:0; }.news-source { display:flex; align-items:center; gap:5px; color:var(--text-muted); font-size:10px; margin-bottom:7px; }.news-source i { width:5px; height:5px; border-radius:50%; }.news-source span { opacity:.8; }.news-summary a,.news-summary>p { display:block; color:var(--text); text-decoration:none; font-size:12px; line-height:1.75; }.news-summary a:hover { color:var(--accent); }.news-summary a span { color:var(--accent); }.news-summary time { display:block; color:var(--text-muted); font-size:10px; margin-top:5px; }
.overview-footer { margin-top:28px; padding-top:16px; border-top:1px solid var(--border); display:flex; justify-content:space-between; gap:12px; color:var(--text-muted); font-size:10px; }.overview-footer>span { display:flex; align-items:center; gap:7px; }
@media(max-width:1200px) { .game-summary { padding:17px; }.hero-count { display:none; }.overview-lower { gap:16px; }.event-summary { gap:9px; }.event-date { display:none; } }
@media(max-width:940px) { .game-summary-grid { grid-template-columns:1fr; }.game-summary { display:grid; grid-template-columns:1fr 1fr; column-gap:20px; }.summary-header { grid-column:1/-1; }.summary-metric { grid-row:2/5; }.summary-meter { margin-top:26px; }.summary-note { grid-column:2; }.summary-account { grid-column:2; margin-top:0; }.summary-updated { grid-column:1/-1; }.overview-lower { grid-template-columns:1fr; } }
@media(max-width:600px) { .overview-hero { align-items:flex-start; gap:13px; min-height:0; padding:10px 0 22px; }.hero-copy h1 { font-size:27px; }.hero-copy .eyebrow { font-size:9px; letter-spacing:1px; }.hero-actions { padding-top:30px; }.hero-actions button { font-size:11px; padding:8px; }.hero-actions svg { display:none; }.page-description { font-size:11px; }.attention-strip { flex-wrap:wrap; gap:9px; padding:13px; }.attention-strip p { flex-basis:80%; }.attention-strip .text-link { margin-left:27px; }.summary-number { font-size:32px; }.game-summary { column-gap:12px; }.overview-footer { flex-wrap:wrap; } }
</style>
