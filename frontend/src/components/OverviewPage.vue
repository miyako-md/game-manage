<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import MenuSelect from './MenuSelect.vue'
import { gameStyle, summaryFor, upcomingEvents, recentNews, formatTime } from '../dashboard.js'
import { sourceForGame } from '../source-status.js'
import { vPop } from '../motion.js'

const props = defineProps({ games: { type: Array, default: () => [] }, snapshots: { type: Object, default: () => ({}) },
  accounts: { type: Object, default: () => ({}) }, readErrors: { type: Object, default: () => ({}) }, refreshErrors: { type: Object, default: () => ({}) },
  refreshing: { type: Object, default: () => ({}) }, collection: { type: Array, default: () => [] }, now: { type: Number, required: true }, loading: Boolean })
const emit = defineEmits(['navigate', 'refresh'])
const newsFilter = ref('')
const sourceFilter = ref('')
const newsGameOptions = computed(() => [{ value: '', label: '全部游戏' }, ...props.games.map(g => ({ value: g.game_id, label: g.display_name }))])
const newsSourceOptions = [{ value: '', label: '全部来源' }, { value: 'bilibili', label: 'B站官方动态' }]
const cards = computed(() => props.games.map(game => ({ ...game, style: gameStyle(game.game_id), summary: summaryFor(game, props.snapshots[game.game_id]), auth: props.accounts[game.game_id], source: sourceForGame(game.game_id, props.collection) })))
const events = computed(() => upcomingEvents(props.games, props.snapshots, props.now))
const nearEvents = computed(() => events.value.filter(event => event.remainingDays <= 3))
const fullGames = computed(() => cards.value.filter(card => card.summary.hasStamina && card.summary.percent >= 90 && !card.summary.stale && !props.readErrors[card.game_id] && (!card.source || card.source.state === 'ok')))
const news = computed(() => recentNews(props.games, props.snapshots).filter(item => (!newsFilter.value || item.gameId === newsFilter.value) && (!sourceFilter.value || item.source === sourceFilter.value)).slice(0, 6))
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
const PLATFORMS = { league_of_legends: 'PC / 国服', endfield: '官服 / 鹰角通行证' }
const platform = id => PLATFORMS[id] || '手游 / 社区数据'
function metricLabel(card) {
  return ({ stamina: card.style.resource, gacha: '特许寻访 · 距上次 6★' })[card.summary.metric] || '最近对局胜率'
}
function resourceNote(card) {
  const s = card.summary
  if (s.metric === 'gacha') return s.value == null ? '等待寻访记录同步' : s.pityStatus === 'exact' ? '按连续的寻访记录计算' : '记录有断档或含免费寻访，这是最少抽数'
  // 胜率不含重开和结果未知的对局；分母和总场数不同时写出来，免得按总场数去算。
  if (!s.hasStamina) return s.totalGames == null ? '等待对局数据' : `最近 ${s.totalGames} 场 · ${s.wins == null ? '胜场未知' : `${s.wins} 胜`}${s.decided != null && s.decided !== s.totalGames ? ` · 胜率按 ${s.decided} 场计` : ''}`
  if (card.game_id === 'nte') return '塔吉多体力快照 · 可能有同步延迟'
  if (s.percent >= 100) return '快照显示体力已满'
  if (s.expectedFullAt) return `预计 ${formatTime(s.expectedFullAt)} 回满`
  return '恢复时间未提供'
}
</script>

<template>
  <div class="overview-page">
    <header class="page-heading">
      <div class="page-heading-copy"><p class="page-kicker"><span class="section-no">§01</span><span class="eyebrow">Your daily check-in</span></p><h1>今日总览</h1><p class="page-description">你的游戏、活动与进度，都在这张工作台。</p></div>
      <div class="page-meta"><span class="hero-count"><b>{{ String(games.length).padStart(2, '0') }}</b>个游戏正在关注</span><button class="ui-button" :disabled="loading || anyRefreshing || !games.length" @click="emit('refresh')"><AppIcon name="refresh" :size="15" :class="{ spinning: anyRefreshing }" /><span :class="{ 't-shimmer': anyRefreshing }">{{ anyRefreshing ? '同步中…' : '刷新数据' }}</span></button></div>
    </header>

    <div v-if="fullGames.length || nearEvents.length" class="attention-strip">
      <AppIcon name="clock" /><p><span v-if="fullGames.length">{{ fullGames.map(g => g.display_name).join('、') }}体力已达 90%</span><span v-if="fullGames.length && nearEvents.length"> · </span><span v-if="nearEvents.length">{{ nearEvents.length }} 项活动将在 3 天内结束</span></p>
      <button class="text-link" @click="emit('navigate', 'calendar')">查看日历 <AppIcon name="arrow" :size="15" /></button>
    </div>
    <div v-for="game in notices" :key="game.game_id" class="inline-warning" role="status"><strong>{{ game.display_name }}</strong> · {{ refreshErrors[game.game_id] || readErrors[game.game_id] }}</div>

    <div class="section-heading"><h2>我的游戏 <span class="count-label">/ {{ String(games.length).padStart(2, '0') }}</span></h2><span class="muted small">各游戏独立同步</span></div>
    <div class="game-summary-grid">
      <button v-for="(card, index) in cards" :key="card.game_id" class="game-summary t-item t-glare" :style="{ '--game-color': card.style.color, '--i': index }" @click="emit('navigate', 'game', card.game_id)">
        <div class="summary-header"><GameIcon class="game-monogram" :game-id="card.game_id" :name="card.display_name" /><div class="game-identity"><h3>{{ card.display_name }}</h3><p>{{ platform(card.game_id) }}</p></div><span class="summary-state" :class="{ warn: card.summary.stale || card.auth?.state === 'expired' || readErrors[card.game_id] || card.source?.tone === 'danger' }"><i></i>{{ status(card) }}</span></div>
        <div class="summary-metric"><div><p>{{ metricLabel(card) }}</p><div class="summary-number" v-pop>{{ card.summary.metric === 'gacha' && card.summary.pityStatus === 'lower_bound' && card.summary.value != null ? '≥' : '' }}{{ card.summary.value ?? '—' }}<small>{{ card.summary.hasStamina ? `/ ${card.summary.maximum ?? '—'}` : METRIC_UNITS[card.summary.metric] }}</small></div></div><p class="summary-note">{{ resourceNote(card) }}</p></div>
        <div v-if="card.summary.percent != null" class="summary-meter" role="meter" :aria-label="metricLabel(card)" :aria-valuenow="card.summary.percent" aria-valuemin="0" aria-valuemax="100"><i :style="{ width: `${Math.min(100, card.summary.percent)}%` }"></i></div>
        <div v-else class="summary-meter unknown"></div>
        <div class="summary-account"><span>{{ card.summary.nickname || '暂无账号数据' }}<small v-if="card.summary.level != null">Lv.{{ card.summary.level }}</small></span><span class="summary-updated">{{ card.summary.fetchedAt ? `更新于 ${formatTime(card.summary.fetchedAt)}` : '尚无成功快照' }}</span><AppIcon name="arrow" :size="15" /></div>
      </button>
    </div>
    <div v-if="!games.length && loading" class="game-summary-grid" aria-busy="true"><span class="sr-only">正在读取游戏数据…</span><div v-for="n in 3" :key="n" class="game-summary is-skeleton" aria-hidden="true"><span class="t-skel-block" style="width:42%;height:16px"></span><span class="t-skel-block" style="width:36%;height:30px;margin-top:18px"></span><span class="t-skel-block" style="width:100%;height:6px;margin-top:12px"></span><span class="t-skel-block" style="width:64%;height:12px;margin-top:16px"></span></div></div>
    <p v-else-if="!games.length" class="empty-page">暂无已启用的游戏。</p>

    <div class="overview-lower">
      <section><div class="section-heading"><h2>临近截止</h2><button class="text-link" @click="emit('navigate', 'calendar')">全部活动 <AppIcon name="arrow" :size="15" /></button></div>
        <div class="overview-list"><p v-if="!events.length" class="empty-page">{{ loading ? '正在读取活动…' : '当前没有已知截止时间的待结束活动。' }}</p><button v-for="event in events.slice(0, 6)" :key="event.id" class="event-summary t-row" :style="{ '--game-color': gameStyle(event.gameId).color }" @click="emit('navigate', 'calendar', event.gameId)"><i class="event-mark" aria-hidden="true"></i><span class="event-copy"><strong>{{ event.name }}</strong><small>{{ event.gameName }} · {{ event.category || '限时活动' }} · {{ formatTime(event.end_at) }} 截止<span v-if="event.stale"> · 数据可能过期</span></small></span><span class="deadline-label" :class="{ urgent: event.remainingDays <= 3 }">{{ event.upcoming ? '未开始 · ' : '' }}剩 {{ event.remainingDays }} 天</span></button></div>
      </section>
      <section><div class="section-heading"><h2>公告与资讯</h2><div class="news-filters"><MenuSelect v-model="newsFilter" label="公告游戏筛选" :options="newsGameOptions" /><MenuSelect v-model="sourceFilter" label="资讯来源" align="end" :options="newsSourceOptions" /></div></div>
        <div class="overview-list news-list"><p v-if="!news.length" class="empty-page">{{ loading ? '正在读取公告…' : '暂无公告快照。' }}</p><article v-for="(item, i) in news" :key="`${item.gameId}:${item.title}:${i}`" class="news-summary t-row"><a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }} <span>↗</span></a><p v-else>{{ item.title }}</p><div class="news-source"><i :style="{ background: gameStyle(item.gameId).color }"></i>{{ item.gameName }}<span> / {{ item.source_name || (item.capability === 'news' ? '资讯' : '官方公告') }}<span v-if="item.stale"> · 旧快照</span></span><time v-if="item.published_at">{{ formatTime(item.published_at) }}</time></div></article></div>
      </section>
    </div>
    <footer class="overview-footer"><span><AppIcon name="shield" :size="14" />数据保存在本机</span><span>日期与时间均为北京时间</span></footer>
  </div>
</template>

<style scoped>
.hero-count { display:flex; align-items:baseline; gap:6px; color:var(--text-muted); font-size:12px; }
.hero-count b { font-size:18px; line-height:1; font-weight:600; letter-spacing:-.02em; color:var(--text); }
.attention-strip { display:flex; align-items:center; gap:10px; padding:9px 14px; margin-bottom:4px; background:var(--attention-bg); border:1px solid var(--attention-border); border-radius:10px; color:var(--attention-text); }
.attention-strip p { flex:1; font-size:13px; }.attention-strip .text-link { color:var(--attention-text); }
.section-heading { margin:20px 0 10px; }.page-heading + .section-heading { margin-top:0; }
.game-summary-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.game-summary { display:flex; flex-direction:column; text-align:left; border:1px solid var(--border); border-radius:12px; padding:14px 16px; background:var(--card-bg); color:var(--text); min-width:0; box-shadow:var(--card-shadow); transition:border-color var(--duration-fast) var(--ease-smooth-out),transform var(--duration-fast) var(--ease-smooth-out),box-shadow var(--duration-fast) var(--ease-smooth-out); cursor:pointer; }
@media(hover:hover) and (pointer:fine) { .game-summary:hover { border-color:color-mix(in srgb, var(--game-color) 40%, var(--border)); transform:translateY(-2px); box-shadow:var(--card-hover-shadow); } }
.game-summary:active { transform:scale(var(--scale-small)); }.game-summary.is-skeleton { pointer-events:none; }
.summary-header { display:flex; align-items:center; gap:10px; }
.game-monogram { display:grid; place-items:center; flex-shrink:0; width:32px; height:32px; border-radius:8px; color:var(--game-color); font-size:17px; box-shadow:0 1px 2px rgba(16, 24, 40, .06); }
.game-identity { min-width:0; margin-right:auto; }.game-identity h3 { font-size:14px; line-height:20px; font-weight:600; }.game-identity p { color:var(--text-faint); font-size:11px; line-height:15px; }
.summary-state { display:flex; align-items:center; gap:5px; flex-shrink:0; padding:1px 7px 1px 6px; border-radius:5px; background:var(--success-bg); color:var(--success); font-size:11px; font-weight:500; line-height:18px; }.summary-state.warn { background:var(--stale-bg); color:var(--stale-text); }.summary-state i { width:5px; height:5px; background:currentColor; border-radius:50%; }
.summary-metric { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin-top:14px; }.summary-metric p { font-size:11px; color:var(--text-muted); }.summary-number { font-size:28px; line-height:32px; font-weight:600; letter-spacing:-.035em; }.summary-number small { font-size:12px; color:var(--text-muted); font-weight:400; margin-left:4px; letter-spacing:0; }
.summary-note { max-width:52%; padding-bottom:3px; text-align:right; font-size:11px; line-height:16px; color:var(--text-muted); }
.summary-meter { height:6px; border-radius:999px; background:var(--track); margin:10px 0 12px; overflow:hidden; }.summary-meter i { display:block; height:100%; border-radius:inherit; background:var(--game-color); }.summary-meter.unknown { background:repeating-linear-gradient(120deg,var(--track) 0 4px,transparent 4px 8px); }
.summary-account { display:flex; align-items:center; gap:8px; margin-top:auto; padding-top:10px; border-top:1px solid var(--border); color:var(--text); font-size:12px; font-weight:500; }.summary-account>span:first-child { min-width:0; margin-right:auto; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.summary-account small { margin-left:6px; color:var(--text-muted); font-size:11px; font-weight:400; }.summary-updated { color:var(--text-faint); font-size:11px; font-weight:400; white-space:nowrap; }.summary-account svg { color:var(--text-faint); transition:transform 350ms var(--ease-smooth-out), color var(--duration-quick) var(--ease-smooth-out); }
@media(hover:hover) and (pointer:fine) { .game-summary:hover .summary-account svg { color:var(--accent); transform:translateX(2px); } }
.overview-lower { display:grid; grid-template-columns:1.1fr 1fr; gap:16px; }.overview-lower>section { min-width:0; }.overview-list { border:1px solid var(--border); border-radius:12px; background:var(--card-bg); padding:4px 16px; box-shadow:var(--card-shadow); }
.news-filters { display:flex; gap:8px; margin-left:auto; min-width:0; }
.event-summary { width:100%; display:flex; align-items:center; gap:10px; border:0; border-bottom:1px solid var(--border); background:transparent; color:var(--text); text-align:left; padding:9px 0; cursor:pointer; }.event-summary:last-child { border:0; }
@media(hover:hover) and (pointer:fine) { .event-summary:hover strong { color:var(--accent); } }
.event-mark { align-self:stretch; width:3px; flex-shrink:0; margin:2px 0; border-radius:2px; background:var(--game-color); }
.event-copy { flex:1; min-width:0; }.event-copy strong { display:block; font-size:13px; line-height:19px; font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.event-copy small { display:block; margin-top:1px; font-size:11px; line-height:16px; color:var(--text-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.deadline-label { flex-shrink:0; padding:1px 7px; border-radius:5px; background:var(--overlay-3); font-size:11px; font-weight:500; line-height:18px; color:var(--text-body); white-space:nowrap; }.deadline-label.urgent { background:var(--stale-bg); color:var(--stale-text); }
.news-summary { border-bottom:1px solid var(--border); padding:9px 0; }.news-summary:last-child { border:0; }.news-summary a,.news-summary>p { display:block; color:var(--text); text-decoration:none; font-size:13px; line-height:19px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.news-summary a span { color:var(--text-faint); }
.news-source { display:flex; align-items:center; gap:5px; margin-top:1px; color:var(--text-muted); font-size:11px; line-height:16px; min-width:0; }.news-source i { width:6px; height:6px; flex-shrink:0; border-radius:50%; }.news-source>span { color:var(--text-faint); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.news-source time { margin-left:auto; flex-shrink:0; color:var(--text-faint); }
@media(hover:hover) and (pointer:fine) { .news-summary a:hover,.news-summary a:hover span { color:var(--accent); } }
.overview-footer { margin-top:24px; padding-top:12px; border-top:1px solid var(--border); display:flex; justify-content:space-between; gap:12px; color:var(--text-faint); font-size:11px; }.overview-footer>span { display:flex; align-items:center; gap:7px; }
@media(max-width:1200px) { .hero-count { display:none; } }
@media(max-width:940px) { .game-summary-grid { grid-template-columns:1fr; }.overview-lower { grid-template-columns:1fr; } }
@media(max-width:600px) { .attention-strip { flex-wrap:wrap; gap:8px; padding:10px 12px; }.attention-strip p { flex-basis:80%; }.attention-strip .text-link { margin-left:26px; }.summary-number { font-size:26px; line-height:30px; }.overview-footer { flex-wrap:wrap; } }
</style>
