<script setup>
import { computed, ref } from 'vue'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import ArtworkImage from './ArtworkImage.vue'
import { articleArtwork, gameBanner, gameRoster, roleArtwork } from '../game-visuals.js'
import { eventArtwork } from '../event-artwork.js'
import HRail from './HRail.vue'
import RingGauge from './RingGauge.vue'
import BarChart from './BarChart.vue'
import MenuSelect from './MenuSelect.vue'
import { gameStyle, gameVars, summaryFor, upcomingEvents, recentNews, formatTime } from '../dashboard.js'
import { parseBeijingTime } from '../calendar.js'
import { sourceForGame } from '../source-status.js'
import { friendlyDataError, capabilityLabel } from '../cloud-display.js'
import { share } from '../chart-math.js'
import { dailyTasks, deadlineDays, gachaDigests } from '../overview-data.js'
import { gameHref, sectionsFor } from '../search-index.js'
import { vGlide, vParallax, vPop, vReveal } from '../motion.js'
import { vRefreshFeedback } from '../refresh-feedback.js'

const props = defineProps({ games: { type: Array, default: () => [] }, snapshots: { type: Object, default: () => ({}) },
  accounts: { type: Object, default: () => ({}) }, readErrors: { type: Object, default: () => ({}) }, publicErrors: { type:Object, default:()=>({}) }, refreshErrors: { type: Object, default: () => ({}) },
  refreshing: { type: Object, default: () => ({}) }, collection: { type: Array, default: () => [] }, now: { type: Number, required: true }, loading: Boolean, refreshLabel: {type:String,default:'刷新数据'} })
const emit = defineEmits(['navigate', 'refresh'])
const newsFilter = ref('')
const sourceFilter = ref('')
const newsGameOptions = computed(() => [{ value: '', label: '全部游戏' }, ...props.games.map(g => ({ value: g.game_id, label: g.display_name }))])
const newsSourceOptions = [{ value: '', label: '全部来源' }, { value: 'bilibili', label: 'B站官方动态' }]
const cards = computed(() => props.games.map(game => ({ ...game, style: gameStyle(game.game_id), summary: summaryFor(game, props.snapshots[game.game_id]), auth: props.accounts[game.game_id], source: sourceForGame(game.game_id, props.collection) })))
const events = computed(() => upcomingEvents(props.games, props.snapshots, props.now))
const nearEvents = computed(() => events.value.filter(event => event.remainingDays <= 3))
const fullGames = computed(() => cards.value.filter(card => card.summary.hasStamina && card.summary.percent >= 90 && !card.summary.stale && !props.readErrors[card.game_id] && (!card.source || card.source.state === 'ok')))
const allNews = computed(() => recentNews(props.games, props.snapshots))
const news = computed(() => allNews.value.filter(item => (!newsFilter.value || item.gameId === newsFilter.value) && (!sourceFilter.value || item.source === sourceFilter.value)).slice(0, 6))
const anyRefreshing = computed(() => Object.values(props.refreshing).some(Boolean))
const notices = computed(() => cards.value.filter(g => props.readErrors[g.game_id] || props.refreshErrors[g.game_id]))
const dateFormatter = new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: 'long', day: 'numeric', weekday: 'long' })
const dateLabel = computed(() => dateFormatter.format(props.now))

function status(card) {
  if (props.readErrors[card.game_id]) return '读取异常'
  if (card.auth?.state === 'expired') return '登录已失效'
  if (card.summary.stale) return '待更新'
  if (card.game_id === 'league_of_legends') return '本机客户端'
  return ({ connected: '已登录', configured: '已登录', unconfigured: '未登录' })[card.auth?.state] || (card.credentials_configured ? '已登录' : '未登录')
}
const warned = card => !!(card.summary.stale || card.auth?.state === 'expired' || props.readErrors[card.game_id] || card.source?.tone === 'danger')
const METRIC_UNITS = { stats: '%', gacha: '抽' }
const PLATFORMS = { league_of_legends: 'PC / 国服', endfield: '官服 / 鹰角通行证' }
const identity = card => card.summary.nickname ? `${card.summary.nickname}${card.summary.level != null ? ` · Lv.${card.summary.level}` : ''}` : card.platform || PLATFORMS[card.game_id] || '手游 / 社区数据'
function metricLabel(card) {
  return ({ stamina: card.style.resource, gacha: '距上次 6★' })[card.summary.metric] || '最近对局胜率'
}
const metricValue = card => `${card.summary.metric === 'gacha' && card.summary.pityStatus === 'lower_bound' && card.summary.value != null ? '≥' : ''}${card.summary.value ?? '—'}`
const metricUnit = card => card.summary.hasStamina ? `/ ${card.summary.maximum ?? '—'}` : METRIC_UNITS[card.summary.metric]
function resourceNote(card) {
  const s = card.summary
  if (s.metric === 'gacha') return `特许寻访 · ${s.value == null ? '等待更新' : s.pityStatus === 'exact' ? '按连续记录计算' : '含缺口或免费寻访，为下限'}`
  // 胜率不含重开和结果未知的对局；分母和总场数不同时写出来，免得按总场数去算。
  if (!s.hasStamina) return s.totalGames == null ? '等待对局数据' : `最近 ${s.totalGames} 场 · ${s.wins == null ? '胜场未知' : `${s.wins} 胜`}${s.decided != null && s.decided !== s.totalGames ? ` · 胜率按 ${s.decided} 场计` : ''}`
  if (s.percent >= 100) return '体力已满'
  if (s.expectedFullAt) return `预计 ${formatTime(s.expectedFullAt)} 回满`
  return '回满时间未知'
}
// The highest-level roles that come with a picture: the avatar row on each game card and the hero's art.
const failedAvatars = ref(new Set())
function roster(card) {
  const list = gameRoster(props.snapshots[card.game_id])
  const picture = role => roleArtwork(role).find(url => !failedAvatars.value.has(url))
  const pictured = list.filter(role => picture(role))
  return { total: list.length, shown: pictured.sort((a, b) => (Number(b.level) || 0) - (Number(a.level) || 0)).slice(0, 5).map(role => ({ key: role.role_id ?? role.id ?? role.name, src: picture(role), name: typeof role.name === 'string' ? role.name : '' })) }
}
function avatarFailed(src) { failedAvatars.value = new Set([...failedAvatars.value, src]) }

// Hero: one game at a time. It opens on the game whose stamina is closest to full; the row of names under it switches.
const featuredId = ref('')
const featured = computed(() => cards.value.find(card => card.game_id === featuredId.value)
  || [...cards.value].filter(card => card.summary.metric === 'stamina' && card.summary.percent != null && !warned(card)).sort((a, b) => b.summary.percent - a.summary.percent)[0]
  || cards.value[0] || null)
const heroArt = computed(() => featured.value ? roster(featured.value).shown.slice(0, 3) : [])
const heroBanner = computed(() => featured.value ? gameBanner(featured.value.game_id, props.snapshots[featured.value.game_id], props.now) : [])

// Daily and weekly progress, read-only.
const tasks = computed(() => dailyTasks(props.games, props.snapshots, props.now))
const tasksDone = computed(() => tasks.value.filter(task => task.done).length)
// How full each row's little ring is, 0–100; a countdown without a total is empty until it reaches zero.
const taskShare = task => task.done ? 100 : task.total ? Math.round(Math.min(1, task.current / task.total) * 100) : 0

// Deadlines for the next 7 or 30 days, and the one that comes first.
const range = ref(7)
const days = computed(() => deadlineDays(events.value, props.now, range.value))
const rangeTotal = computed(() => days.value.reduce((sum, day) => sum + day.value, 0))
const next = computed(() => events.value[0] || null)
// How far through its window an event is (0–1); unknown without a start time.
function elapsed(event) {
  const start = parseBeijingTime(event.start_at || event.start_date)
  return start == null || event.upcoming ? null : share(props.now - start, event.endTime - start)
}

// Pull records, one game at a time.
const digests = computed(() => gachaDigests(props.games, props.snapshots, props.accounts))
const gachaId = ref('')
const digest = computed(() => digests.value.find(item => item.gameId === gachaId.value) || digests.value[0] || null)
const shortDate = time => time == null ? '' : formatTime(time, { hour: undefined, minute: undefined })

// Two tabs of each game page, by the names those tabs carry, then its calendar.
const QUICK_TABS = { wuthering_waves: ['roles', 'gacha'], nte: ['characters', 'gacha'], endfield: ['operators', 'gacha'], league_of_legends: ['history', 'esports'] }
function quickLinks(card) {
  const tabs = sectionsFor(card).filter(([id]) => (QUICK_TABS[card.game_id] || []).includes(id)).map(([id, label]) => ({ label, href: gameHref(card.game_id, id) }))
  return card.capabilities.includes('events') ? [...tabs, { label: '活动日历', href: `#/calendar?game=${encodeURIComponent(card.game_id)}` }] : tabs
}
</script>

<template>
  <div class="overview-page">
    <header class="page-heading ov-heading">
      <div class="page-heading-copy">
        <h1>今日总览</h1>
        <ul class="ov-stats">
          <li class="ov-today">{{ dateLabel }}</li>
          <li><b v-pop>{{ games.length }}</b><span>游戏</span></li>
          <li><b v-pop>{{ events.length }}</b><span>进行中的活动</span></li>
          <li :class="{ hot: nearEvents.length }"><b v-pop>{{ nearEvents.length }}</b><span>3 天内截止</span></li>
        </ul>
      </div>
      <div class="ov-actions">
        <button class="ui-button ov-refresh" :disabled="loading || anyRefreshing || !games.length" :aria-busy="anyRefreshing || undefined" @click="emit('refresh')"><AppIcon v-refresh-feedback="anyRefreshing" name="refresh" :size="15" data-icon-motion="off" /><span :class="{ 't-shimmer': anyRefreshing }">{{ anyRefreshing ? '刷新中…' : refreshLabel }}</span></button>
        <button class="ui-button soft" @click="emit('navigate', 'calendar')"><AppIcon name="calendar" :size="15" />活动日历</button>
      </div>
    </header>

    <p v-if="fullGames.length" class="ov-alert" role="status"><AppIcon name="clock" :size="16" />{{ fullGames.map(g => g.display_name).join('、') }}体力已达 90%</p>
    <div v-for="game in notices" :key="game.game_id" class="inline-warning" role="status"><strong>{{ game.display_name }}</strong> · {{ friendlyDataError(refreshErrors[game.game_id] || readErrors[game.game_id],accounts[game.game_id]?.state) }}</div>
    <template v-for="game in games" :key="`public-${game.game_id}`"><p v-for="issue in publicErrors[game.game_id] || []" :key="issue.capability" class="inline-warning" role="status">{{ game.display_name }} · {{ capabilityLabel(issue.capability) }}：{{ issue.message }}<span v-if="issue.retained">正在显示已有资料。</span></p></template>

    <div class="ov-top">
      <section v-if="featured" v-parallax class="ov-hero" :style="gameVars(featured.game_id)" aria-labelledby="ov-hero-title">
        <div class="hero-inner">
          <ArtworkImage :key="`banner:${featured.game_id}`" class="hero-backdrop" :candidates="heroBanner" decorative loading="eager" />
          <div :key="featured.game_id" class="hero-copy t-panel">
            <p class="hero-eyebrow"><GameIcon class="hero-mark" :game-id="featured.game_id" :name="featured.display_name" />{{ featured.display_name }}<span>· {{ status(featured) }}</span></p>
            <h2 id="ov-hero-title" class="hero-title"><span>{{ metricLabel(featured) }}</span><b>{{ metricValue(featured) }}<small>{{ metricUnit(featured) }}</small></b></h2>
            <p class="hero-note">{{ resourceNote(featured) }}<template v-if="featured.summary.nickname"> · {{ identity(featured) }}</template></p>
            <button class="hero-cta" @click="emit('navigate', 'game', featured.game_id)">打开{{ featured.display_name }}<span><AppIcon name="arrow" :size="16" /></span></button>
          </div>
          <div v-if="heroArt.length" :key="`art:${featured.game_id}`" class="hero-art plx-layer" aria-hidden="true">
            <img v-for="(role, index) in heroArt" :key="role.key" :class="`hero-face face-${index}`" :src="role.src" alt="" decoding="async" referrerpolicy="no-referrer" @error="avatarFailed(role.src)" />
          </div>
          <div v-else :key="`mark:${featured.game_id}`" class="hero-art is-mark plx-layer" aria-hidden="true"><GameIcon class="hero-big-mark" :game-id="featured.game_id" /><span class="hero-en">{{ featured.style.english }}</span></div>
          <div v-if="cards.length > 1" v-glide class="hero-index" role="group" aria-label="主卡显示的游戏">
            <button v-for="card in cards" :key="card.game_id" type="button" :aria-pressed="card.game_id === featured.game_id" @click="featuredId = card.game_id">{{ card.display_name }}</button>
          </div>
        </div>
      </section>
      <section v-else class="ov-hero is-empty" :aria-busy="loading || undefined"><div class="hero-inner"><p>{{ loading ? '加载中…' : '暂无已启用的游戏。' }}</p></div></section>

      <section class="ov-tasks cap-card" aria-labelledby="ov-tasks-title">
        <div class="card-heading"><div><h2 id="ov-tasks-title">日常进度</h2></div></div>
        <template v-if="tasks.length">
          <div class="tasks-progress">
            <RingGauge :value="tasksDone" :max="tasks.length" label="已完成的日常进度" :size="72" :stroke="7"><span class="tasks-count"><b>{{ tasksDone }}</b><small>/{{ tasks.length }}</small></span></RingGauge>
            <span>已完成</span>
          </div>
          <ul class="task-list">
            <li v-for="task in tasks.slice(0, 6)" :key="task.key" class="task" :class="{ done: task.done }" :style="gameVars(task.gameId)">
              <span class="task-mark" aria-hidden="true"><AppIcon v-if="task.done" name="check" :size="11" /><RingGauge v-else :value="taskShare(task)" :max="100" :label="task.name" :size="18" :stroke="4" color="var(--game-vivid)" /></span>
              <span class="task-name">{{ task.name }}<small>{{ task.gameName }}<template v-if="task.reset"> · {{ task.reset }}</template></small></span>
              <span class="task-value">{{ task.total == null ? `${task.current} ${task.unit}` : `${task.current}/${task.total}` }}<span class="sr-only">，{{ task.done ? '已完成' : '未完成' }}</span></span>
            </li>
          </ul>
        </template>
        <p v-else class="ov-empty">{{ loading ? '加载中…' : '暂无日常或周常进度，刷新后显示。' }}</p>
      </section>
    </div>

    <section v-reveal class="ov-section ov-games" aria-labelledby="ov-games-title">
      <HRail label="游戏状态">
        <template #head><h2 id="ov-games-title">游戏状态</h2><span class="count-badge">{{ cards.length }}</span></template>
        <article v-for="card in cards" :key="card.game_id" class="ov-game" :style="gameVars(card.game_id)">
          <button class="game-summary" type="button" @click="emit('navigate', 'game', card.game_id)">
            <GameIcon class="ov-avatar" :game-id="card.game_id" :name="card.display_name" />
            <span class="ov-game-id"><strong>{{ card.display_name }}</strong><small>{{ identity(card) }}</small></span>
            <span class="ov-arrow" aria-hidden="true"><AppIcon name="arrow" :size="13" /></span>
          </button>
          <p class="ov-energy"><strong v-pop>{{ metricValue(card) }}</strong><span class="total">{{ metricUnit(card) }}</span><span class="resource">{{ metricLabel(card) }}</span></p>
          <span class="meter ov-meter" :class="{ unknown: card.summary.percent == null }" aria-hidden="true"><i :style="{ '--pct': `${card.summary.percent ?? 0}%` }"></i></span>
          <p class="ov-note">{{ resourceNote(card) }}</p>
          <div v-if="roster(card).shown.length" class="summary-roster"><span class="roster-faces"><img v-for="role in roster(card).shown" :key="role.key" :src="role.src" :alt="role.name" decoding="async" referrerpolicy="no-referrer" @error="avatarFailed(role.src)" /></span><span>{{ roster(card).total }} 名角色</span></div>
          <p class="ov-game-foot"><span class="summary-state" :class="{ warn: warned(card) }"><i></i>{{ status(card) }}</span><span class="summary-updated">{{ card.summary.fetchedAt ? `更新于 ${formatTime(card.summary.fetchedAt)}` : '尚未更新' }}</span></p>
          <nav v-if="quickLinks(card).length" class="ov-quick" :aria-label="`${card.display_name}的常用页面`"><a v-for="link in quickLinks(card)" :key="link.href" :href="link.href">{{ link.label }}</a></nav>
        </article>
        <template v-if="!games.length && loading"><div v-for="n in 3" :key="n" class="ov-game is-skeleton" aria-hidden="true"><span class="t-skel-block" style="width:52%;height:18px"></span><span class="t-skel-block" style="width:36%;height:30px;margin-top:22px"></span><span class="t-skel-block" style="width:100%;height:6px;margin-top:14px"></span><span class="t-skel-block" style="width:64%;height:12px;margin-top:16px"></span></div></template>
      </HRail>
      <p v-if="!games.length && !loading" class="empty-page">暂无已启用的游戏。</p>
    </section>

    <div class="ov-analytics">
      <section v-reveal class="ov-deadlines cap-card" aria-labelledby="ov-deadline-title">
        <div class="card-heading">
          <div><h2 id="ov-deadline-title">活动截止</h2></div>
          <div v-glide class="segmented" role="group" aria-label="时间范围"><button v-for="n in [7, 30]" :key="n" type="button" :aria-pressed="range === n" @click="range = n">{{ n }} 天</button></div>
        </div>
        <p class="chart-summary"><b v-pop>{{ rangeTotal }}</b><small>项</small><span>{{ range }} 天内结束</span></p>
        <BarChart v-if="rangeTotal" :key="range" :items="days" :label="`未来 ${range} 天每天截止的活动数`" unit=" 项" :highlight="days[0].value ? 0 : -1" :height="112" color="var(--accent-fill)" />
        <p v-else class="ov-empty chart-empty">{{ loading ? '加载中…' : `未来 ${range} 天没有活动截止。` }}</p>
        <button v-if="next" class="ov-next" :style="gameVars(next.gameId)" @click="emit('navigate', 'calendar', next.gameId)">
          <RingGauge v-if="elapsed(next) != null" class="ov-next-ring" :value="Math.round(elapsed(next) * 100)" :max="100" label="活动已进行" :size="44" :stroke="5" :color="gameStyle(next.gameId).vivid"><small>{{ Math.round(elapsed(next) * 100) }}%</small></RingGauge>
          <span class="ov-next-copy"><span class="ov-kicker">最近截止</span><strong>{{ next.name }}</strong><small>{{ next.gameName }} · {{ next.category || '限时活动' }} · {{ formatTime(next.end_at) }} 截止<template v-if="next.stale"> · 待更新</template></small></span>
          <span class="ov-next-days"><b>{{ next.remainingDays }}</b><small>{{ next.upcoming ? '天 · 未开始' : '天后结束' }}</small></span>
        </button>
      </section>

      <section v-reveal class="ov-gacha" :class="{ 'is-empty': !digest }" :style="digest ? gameVars(digest.gameId) : undefined" aria-labelledby="ov-gacha-title">
        <div class="card-heading">
          <div><h2 id="ov-gacha-title">抽卡概况</h2><p v-if="digest" class="sub">{{ digest.gameName }} · {{ digest.scope || '全部卡池' }}</p></div>
          <div v-if="digests.length > 1" v-glide class="segmented" role="group" aria-label="抽卡记录的游戏"><button v-for="item in digests" :key="item.gameId" type="button" :aria-pressed="item.gameId === digest.gameId" @click="gachaId = item.gameId">{{ item.gameName }}</button></div>
        </div>
        <template v-if="digest">
          <p :key="digest.gameId" class="gacha-number t-panel"><b>{{ digest.total.toLocaleString('zh-CN') }}</b><small>抽</small></p>
          <dl class="gacha-mini"><div v-for="stat in digest.stats" :key="stat.label"><dt>{{ stat.label }}</dt><dd>{{ stat.value ?? '—' }}</dd></div></dl>
          <a class="gacha-latest" :href="gameHref(digest.gameId, digest.tab)">
            <GameIcon class="latest-mark" :game-id="digest.gameId" />
            <span v-if="digest.latest" class="latest-copy"><strong>{{ digest.latest.name }}</strong><small>{{ digest.latest.detail }}<template v-if="digest.latest.time"> · {{ shortDate(digest.latest.time) }}</template></small></span>
            <span v-else class="latest-copy"><strong>查看抽卡记录</strong><small>暂无最高稀有度记录</small></span>
            <AppIcon name="arrow" :size="15" />
          </a>
        </template>
        <p v-else class="ov-empty">{{ loading ? '加载中…' : '同步抽卡记录后显示总抽数与最近出货。' }}</p>
      </section>
    </div>

    <section v-reveal class="ov-section ov-events" aria-labelledby="ov-events-title">
      <HRail label="近期活动">
        <template #head><h2 id="ov-events-title">近期活动</h2><span class="count-badge">{{ events.length }}</span><button class="text-link" @click="emit('navigate', 'calendar')">全部活动 <AppIcon name="arrow" :size="15" /></button></template>
        <button v-for="event in events.slice(0, 12)" :key="event.id" class="event-card" :class="{ urgent: event.remainingDays <= 3 }" :style="gameVars(event.gameId)" @click="emit('navigate', 'calendar', event.gameId)">
          <ArtworkImage class="event-card-art" :candidates="eventArtwork(event, snapshots)" decorative />
          <span class="event-pill">{{ event.gameName }} · {{ event.category || '限时活动' }}</span>
          <strong class="event-card-name">{{ event.name }}</strong>
          <span class="event-card-days"><b>{{ event.remainingDays }}</b><small>{{ event.upcoming ? '天 · 未开始' : '天后结束' }}</small><span v-if="!event.upcoming && event.remainingDays <= 3" class="deadline-label">即将截止</span></span>
          <span v-if="elapsed(event) != null" class="event-card-track" aria-hidden="true"><i :style="{ width: `${Math.round(elapsed(event) * 100)}%` }"></i></span>
          <span class="event-card-end"><AppIcon name="clock" :size="13" />{{ formatTime(event.end_at) }} 截止<template v-if="event.stale"> · 待更新</template></span>
          <GameIcon class="event-watermark" :game-id="event.gameId" aria-hidden="true" />
        </button>
      </HRail>
      <p v-if="!events.length" class="empty-page">{{ loading ? '加载中…' : '暂无进行中的活动。' }}</p>
    </section>

    <section v-reveal class="ov-news cap-card">
      <div class="section-heading"><h2>公告与资讯</h2><div class="news-filters"><MenuSelect v-model="newsFilter" label="公告游戏筛选" :options="newsGameOptions" /><MenuSelect v-model="sourceFilter" label="资讯来源" align="end" :options="newsSourceOptions" /></div></div>
      <div class="news-list"><p v-if="!news.length" class="empty-page">{{ loading ? '加载中…' : '暂无公告。' }}</p><article v-for="(item, i) in news" :key="`${item.gameId}:${item.title}:${i}`" class="news-summary t-row" :style="gameVars(item.gameId)"><span class="news-visual"><ArtworkImage class="news-cover" :candidates="articleArtwork(item)" decorative /><GameIcon class="news-mark" :game-id="item.gameId" :name="item.gameName" /></span><div class="news-copy"><a v-if="item.url" :href="item.url" target="_blank" rel="noopener noreferrer">{{ item.title }} <span>↗</span></a><p v-else>{{ item.title }}</p><div class="news-source">{{ item.gameName }}<span> / {{ item.source_name || (item.capability === 'news' ? '资讯' : '官方公告') }}</span><time v-if="item.published_at">{{ formatTime(item.published_at) }}</time></div></div></article></div>
    </section>
  </div>
</template>

<style scoped>
/* Page heading: the title, then today's counts in one quiet line. */
.ov-stats { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 18px; margin-top:6px; color:var(--text-muted); font-size:13px; }
.ov-stats li { display:inline-flex; align-items:baseline; gap:5px; }
.ov-stats b { color:var(--text); font-size:15px; font-weight:600; font-variant-numeric:tabular-nums; }
.ov-stats li.hot b { color:var(--danger); }
/* The date is in the top bar; phones hide that, so it joins the counts there. */
.ov-today { display:none !important; }
.ov-actions { display:flex; flex-wrap:wrap; gap:10px; }
.ov-alert { display:flex; align-items:center; gap:8px; margin:-8px 0 18px; padding:10px 14px; border:1px solid var(--attention-border); border-radius:var(--radius-well); background:var(--attention-bg); color:var(--attention-text); font-size:13px; }
.inline-warning { margin:0 0 16px; }

/* Row one: the hero beside today's progress. */
.ov-top { display:grid; grid-template-columns:minmax(0, 1.95fr) minmax(290px, 1fr); gap:20px; align-items:stretch; }
/* Hero: a white frame around the featured game's pale tone (mockup .hero-card). */
.ov-hero { display:flex; flex-direction:column; min-width:0; min-height:300px; padding:6px; overflow:hidden; border:1px solid var(--card-border); border-radius:26px; background:var(--card-bg); box-shadow:var(--card-shadow); }
.hero-inner { position:relative; isolation:isolate; flex:1; overflow:hidden; padding:24px 28px 62px; border-radius:20px; background:var(--game-tone, var(--control-track)); container-type:inline-size; }
.hero-backdrop { position:absolute; inset:0 0 0 auto; width:88%; height:100%; object-position:65% center; z-index:-2; }
.hero-inner:has(.hero-backdrop)::after { content:''; position:absolute; inset:0; z-index:-1; background:linear-gradient(90deg,var(--game-tone) 6%,color-mix(in srgb,var(--game-tone) 94%,transparent) 30%,color-mix(in srgb,var(--game-tone) 18%,transparent) 75%),linear-gradient(0deg,var(--game-tone),transparent 26%); }
.hero-inner:has(.hero-backdrop) .hero-art { display:none; }
.ov-hero.is-empty .hero-inner { display:grid; place-items:center; color:var(--text-muted); padding:24px; }
.hero-copy { position:relative; z-index:3; max-width:min(58%, 420px); }
.hero-eyebrow { display:flex; align-items:center; gap:8px; color:var(--game-accent); font-size:12px; font-weight:500; white-space:nowrap; }
.hero-eyebrow span { color:var(--game-accent); opacity:.8; font-weight:400; }
.hero-mark { width:24px; height:24px; border-radius:7px; background:var(--card-bg); box-shadow:inset 0 0 0 1px var(--card-border); font-size:12px; font-weight:600; }
.hero-title { display:grid; gap:0; margin:10px 0 4px; color:var(--text); font-weight:600; }
.hero-title span { font-size:15px; line-height:22px; letter-spacing:-.01em; }
.hero-title b { font-size:40px; line-height:44px; font-weight:600; letter-spacing:-.04em; font-variant-numeric:tabular-nums; white-space:nowrap; }
.hero-title small { margin-left:6px; color:var(--game-accent); font-size:16px; font-weight:500; letter-spacing:0; }
.hero-note { color:var(--game-accent); font-size:13px; line-height:1.6; text-wrap:pretty; }
.hero-cta { display:inline-flex; align-items:center; gap:12px; min-height:44px; margin-top:12px; padding:5px 5px 5px 14px; border:1px solid var(--accent-fill); border-radius:11px; background:var(--accent-fill); color:var(--accent-ink); font-size:13px; font-weight:500; }
.hero-cta span { display:grid; place-items:center; width:32px; height:32px; border-radius:8px; background:rgba(255, 255, 255, .14); transition:transform var(--duration-fast) var(--ease-smooth-out); }
@media(hover:hover) and (pointer:fine) { .hero-cta:hover span { transform:translateX(2px); } .hero-cta:hover { filter:brightness(1.06); } }
.hero-cta:active { transform:translateY(1px); }
/* Art: the top roles' pictures fanned at the right, or the game's mark when there are none. It drifts a little against the scroll. */
.hero-art { --plx-range:-14px; position:absolute; right:6%; bottom:30px; z-index:1; width:250px; height:210px; pointer-events:none; transform-origin:100% 100%; }
/* The art steps down as the hero narrows, so it never runs into the text. `scale` composes with the parallax transform. */
@container (max-width:760px) { .hero-art { scale:.82; } }
@container (max-width:600px) { .hero-art { scale:.7; right:2%; } .hero-copy { max-width:62%; } }
@container (max-width:480px) { .hero-art { scale:.6; right:-10px; bottom:38px; } .hero-copy { max-width:66%; } .hero-eyebrow { flex-wrap:wrap; white-space:normal; } .hero-title b { white-space:normal; } }
.hero-face { position:absolute; object-fit:cover; background:var(--card-bg); border:5px solid var(--card-bg); box-shadow:0 18px 40px -22px rgba(38, 40, 46, .45); }
.face-0 { right:24px; bottom:0; z-index:3; width:172px; height:172px; border-radius:40px; transform:rotate(5deg); }
.face-1 { right:170px; bottom:22px; z-index:2; width:96px; height:96px; border-radius:26px; transform:rotate(-9deg); }
.face-2 { right:0; top:-6px; z-index:1; width:74px; height:74px; border-radius:22px; transform:rotate(12deg); }
.hero-art.is-mark { display:flex; align-items:flex-end; justify-content:flex-end; gap:18px; }
.hero-big-mark { width:150px; height:150px; border-radius:38px; background:var(--card-bg); box-shadow:0 18px 40px -22px rgba(38, 40, 46, .45); transform:rotate(-9deg); color:var(--game-accent); font-size:64px; font-weight:600; }
.hero-en { writing-mode:vertical-rl; transform:rotate(180deg); max-height:200px; overflow:hidden; color:var(--game-accent); font-size:20px; font-weight:600; letter-spacing:2px; opacity:.38; white-space:nowrap; }
/* Game switcher at the foot of the hero: plain names, a white slip under the shown one. */
.hero-index { position:absolute; left:22px; bottom:8px; z-index:4; display:flex; gap:2px; max-width:calc(100% - 32px); overflow-x:auto; scrollbar-width:none; }
.hero-index::-webkit-scrollbar { display:none; }
.hero-index button { position:relative; z-index:1; flex-shrink:0; min-width:58px; min-height:44px; padding:8px 12px; border:0; border-radius:10px; background:transparent; color:var(--game-accent); font-size:12px; }
.hero-index button[aria-pressed="true"] { color:var(--text); font-weight:600; }
.hero-index:not([data-glide]) button[aria-pressed="true"] { background:var(--card-bg); }
.hero-index > :deep(.t-glide) { background:var(--card-bg); box-shadow:none; border-radius:10px; }
@media(hover:hover) and (pointer:fine) { .hero-index button[aria-pressed="false"]:hover { background:rgba(255, 255, 255, .45); } }

/* Daily progress: a ring of how many are done, then the rows. */
.ov-tasks { display:grid; grid-template-columns:76px minmax(0, 1fr); column-gap:16px; align-content:start; padding:20px 18px; }
.card-heading { display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.card-heading h2 { font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.02em; }
.card-heading .sub { margin-top:2px; color:var(--text-muted); font-size:12px; }
.ov-tasks > .card-heading { grid-column:1 / -1; margin-bottom:12px; }
.tasks-progress { display:flex; flex-direction:column; align-items:center; gap:6px; color:var(--text-muted); font-size:12px; }
.tasks-count { display:flex; align-items:baseline; }
.tasks-count b { font-size:22px; font-weight:600; letter-spacing:-.04em; }
.tasks-count small { color:var(--text-muted); font-size:12px; }
.task-list { min-width:0; }
.task { display:flex; align-items:center; gap:10px; min-height:44px; padding:6px 0; border-top:1px solid var(--border); font-size:13px; }
.task:first-child { border-top:0; padding-top:0; }
/* A small progress ring per row, not a checkbox: the rows are read-only. Done rows show a check. */
.task-mark { display:grid; place-items:center; flex-shrink:0; width:18px; height:18px; border-radius:50%; }
.task.done .task-mark { background:var(--success-bg); color:var(--success); }
.task-mark > svg { grid-area:1 / 1; }
.task-name { display:grid; flex:1; min-width:0; color:var(--text); font-weight:500; }
.task-name small { overflow:hidden; color:var(--text-muted); font-size:12px; font-weight:400; white-space:nowrap; text-overflow:ellipsis; }
.task.done .task-name { color:var(--text-muted); }
.task-value { flex-shrink:0; color:var(--text-body); font-size:12px; font-variant-numeric:tabular-nums; }
.ov-empty { color:var(--text-muted); font-size:13px; }
.ov-tasks > .ov-empty { grid-column:1 / -1; margin:auto 0; padding:24px 0; }

/* Sections: the heading carries a count and the rail's arrows. */
.ov-section { margin-top:28px; }
.ov-section :deep(.h-rail-title) h2 { font-size:18px; line-height:26px; font-weight:600; letter-spacing:-.02em; }
.ov-section :deep(.h-rail-title) .text-link { margin-left:8px; }
.ov-games .h-rail,.ov-events .h-rail { --rail-gap:16px; --rail-pad:2px; --rail-pad-block:4px; }

/* Game cards (mockup .game-card): identity, the main number and its bar, then shortcuts. */
.ov-game { display:flex; flex-direction:column; width:clamp(272px, calc((100% - 32px) / 3), 360px); min-height:100%; padding:16px 18px 10px; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); box-shadow:var(--card-shadow); }
.ov-game.is-skeleton { padding:20px; }
.game-summary { display:flex; align-items:center; gap:11px; width:100%; min-height:52px; padding:0; border:0; border-radius:12px; background:none; color:var(--text); text-align:left; }
.ov-avatar { width:44px; height:44px; border:3px solid var(--card-bg); border-radius:15px; background:var(--game-tone); box-shadow:0 0 0 1px var(--card-border); font-size:17px; font-weight:600; }
.ov-game-id { display:grid; flex:1; min-width:0; }
.ov-game-id strong { font-size:16px; font-weight:600; }
.ov-game-id small { overflow:hidden; color:var(--text-muted); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.ov-arrow { display:grid; place-items:center; flex-shrink:0; width:29px; height:29px; border-radius:9px; background:var(--panel-bg); color:var(--text-muted); transition:background-color var(--duration-quick) var(--ease-smooth-out), color var(--duration-quick) var(--ease-smooth-out), transform var(--duration-fast) var(--ease-smooth-out); }
@media(hover:hover) and (pointer:fine) { .game-summary:hover .ov-arrow { background:var(--accent-soft); color:var(--accent); transform:translateX(2px); } }
.game-summary:active .ov-arrow { transform:translateY(1px); }
.ov-energy { display:flex; align-items:baseline; gap:6px; margin-top:16px; }
.ov-energy strong { font-size:28px; line-height:1.1; font-weight:550; letter-spacing:-.05em; font-variant-numeric:tabular-nums; }
.ov-energy .total { color:var(--text-muted); font-size:12px; }
.ov-energy .resource { margin-left:auto; color:var(--text-muted); font-size:12px; }
.ov-meter { height:5px; margin:12px 0 10px; }
.ov-meter > i { background:var(--game-vivid); }
.ov-meter.unknown { opacity:.6; }
.ov-note { color:var(--text-muted); font-size:12px; line-height:18px; }
/* Overlapping avatars of the highest-level roles: the pictures bring the game's colour. */
.summary-roster { display:flex; align-items:center; gap:10px; margin-top:12px; color:var(--text-muted); font-size:12px; }
.roster-faces { display:flex; padding-left:8px; }
.roster-faces img { width:28px; height:28px; margin-left:-8px; border-radius:9px; object-fit:cover; background:var(--game-tone); box-shadow:0 0 0 2px var(--card-bg); }
.ov-game-foot { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:12px 0 14px; color:var(--text-muted); font-size:12px; }
.summary-state { display:inline-flex; align-items:center; gap:5px; flex-shrink:0; padding:1px 8px 1px 7px; border-radius:var(--radius-chip); background:var(--success-bg); color:var(--success); font-size:12px; font-weight:500; line-height:20px; }
.summary-state i { width:6px; height:6px; border-radius:50%; background:currentColor; }
.summary-state.warn { background:var(--stale-bg); color:var(--stale-text); }
.summary-updated { overflow:hidden; white-space:nowrap; text-overflow:ellipsis; }
.ov-quick { display:grid; grid-auto-columns:minmax(0, 1fr); grid-auto-flow:column; margin-top:auto; padding-top:8px; border-top:1px solid var(--border); }
.ov-quick a { display:grid; place-items:center; min-height:44px; padding:6px 4px; border-radius:8px; color:var(--text-muted); font-size:13px; text-decoration:none; white-space:nowrap; }
.ov-quick a + a { border-left:1px solid var(--border); border-radius:0 8px 8px 0; }
@media(hover:hover) and (pointer:fine) { .ov-quick a:hover { background:var(--accent-soft); color:var(--accent); } }
.ov-quick a:active { transform:translateY(1px); }

/* Row three: deadlines and pulls (mockup .analytics-grid). */
.ov-analytics { display:grid; grid-template-columns:minmax(0, 1.8fr) minmax(305px, 1fr); gap:20px; margin-top:28px; }
.ov-deadlines { display:flex; flex-direction:column; min-width:0; padding:22px 24px 16px; }
.chart-summary { display:flex; align-items:baseline; gap:6px; margin-top:16px; }
.chart-summary b { font-size:32px; line-height:1; font-weight:550; letter-spacing:-.05em; }
.chart-summary small { color:var(--text-muted); font-size:14px; }
.chart-summary span { margin-left:6px; color:var(--text-muted); font-size:12px; }
.ov-deadlines :deep(.bar-plot) { padding-top:26px; }
.chart-empty { padding:40px 0; text-align:center; }
.ov-next { display:flex; align-items:center; gap:12px; width:100%; min-height:60px; margin-top:12px; padding:10px 12px; border:1px solid var(--border); border-radius:var(--radius-well); background:var(--panel-bg); color:var(--text); text-align:left; }
@media(hover:hover) and (pointer:fine) { .ov-next:hover { border-color:var(--border-strong); background:var(--card-bg); } }
.ov-next:active { transform:translateY(1px); }
.ov-next-ring small { font-size:11px; font-weight:600; }
.ov-next-copy { display:grid; flex:1; min-width:0; }
.ov-kicker { color:var(--text-muted); font-size:12px; }
.ov-next-copy strong { overflow:hidden; font-size:14px; font-weight:600; white-space:nowrap; text-overflow:ellipsis; }
.ov-next-copy small { overflow:hidden; color:var(--text-muted); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.ov-next-days { display:flex; align-items:baseline; gap:4px; flex-shrink:0; }
.ov-next-days b { font-size:24px; font-weight:600; letter-spacing:-.04em; }
.ov-next-days small { color:var(--text-muted); font-size:12px; }
/* Pulls: the one lavender card on the page (mockup .gacha-summary-card), in the game's tone when it has one. */
.ov-gacha { position:relative; display:flex; flex-direction:column; min-width:0; padding:22px 23px; border:1px solid var(--card-border); border-radius:var(--radius-card); background:color-mix(in srgb, var(--game-tone, #e9edf7) 55%, var(--card-bg)); box-shadow:var(--card-shadow); }
.ov-gacha.is-empty { background:var(--card-bg); }
.ov-gacha .segmented { background:color-mix(in srgb, var(--card-bg) 55%, transparent); }
.gacha-number { display:flex; align-items:baseline; gap:7px; margin-top:20px; }
.gacha-number b { font-size:44px; line-height:1.1; font-weight:500; letter-spacing:-.06em; font-variant-numeric:tabular-nums; }
.gacha-number small { color:var(--text-muted); font-size:12px; }
.gacha-mini { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); margin:18px 0 0; }
.gacha-mini > div { min-width:0; padding-left:14px; border-left:1px solid color-mix(in srgb, var(--game-accent, var(--text)) 18%, transparent); }
.gacha-mini > div:first-child { padding-left:0; border-left:0; }
.gacha-mini dt { overflow:hidden; color:var(--text-muted); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.gacha-mini dd { margin:2px 0 0; overflow:hidden; color:var(--text); font-size:19px; font-weight:500; letter-spacing:-.03em; white-space:nowrap; text-overflow:ellipsis; }
.gacha-latest { display:flex; align-items:center; gap:10px; min-height:58px; margin-top:auto; padding:11px; border:1px solid var(--card-border); border-radius:14px; background:var(--card-bg); color:var(--text); text-decoration:none; }
.ov-gacha .gacha-mini + .gacha-latest { margin-top:20px; }
.latest-mark { flex-shrink:0; width:34px; height:34px; border-radius:9px; background:var(--game-tone); font-size:14px; font-weight:600; }
.latest-copy { display:grid; flex:1; min-width:0; }
.gacha-latest strong { font-size:13px; font-weight:600; }
.gacha-latest small { overflow:hidden; color:var(--text-muted); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.gacha-latest > svg { flex-shrink:0; color:var(--accent); }
@media(hover:hover) and (pointer:fine) { .gacha-latest:hover { background:var(--panel-bg); } }
.ov-gacha > .ov-empty { margin:auto 0; padding:24px 0 8px; }

/* Events (mockup .event-card): each in its game's tone, the days left large. */
.event-card { position:relative; display:flex; flex-direction:column; align-items:flex-start; gap:8px; width:clamp(272px, calc((100% - 32px) / 3), 340px); min-height:206px; padding:20px 22px 18px; overflow:hidden; isolation:isolate; border:0; border-radius:var(--radius-card); background:var(--game-tone); color:var(--game-accent); text-align:left; }
.event-card-art { position:absolute; inset:0; z-index:-2; width:100%; height:100%; object-position:65% center; }
.event-card:has(.event-card-art)::after { content:''; position:absolute; inset:0; z-index:-1; background:linear-gradient(0deg,var(--game-tone) 5%,color-mix(in srgb,var(--game-tone) 92%,transparent) 42%,color-mix(in srgb,var(--game-tone) 15%,transparent)),linear-gradient(90deg,color-mix(in srgb,var(--game-tone) 88%,transparent),transparent); }
.event-card:has(.event-card-art) .event-watermark { display:none; }
.event-pill { max-width:100%; overflow:hidden; padding:3px 8px; border-radius:var(--radius-chip); background:color-mix(in srgb, var(--card-bg) 60%, transparent); color:var(--game-accent); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.event-card-name { display:-webkit-box; max-width:82%; margin-top:6px; overflow:hidden; color:var(--text); font-size:17px; line-height:1.45; font-weight:600; letter-spacing:-.02em; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.event-card-days { display:flex; align-items:baseline; gap:4px; width:100%; margin-top:auto; }
.event-card-days b { color:var(--text); font-size:28px; line-height:32px; font-weight:550; letter-spacing:-.05em; }
.event-card-days small { font-size:12px; }
.deadline-label { margin-left:auto; padding:1px 8px; border-radius:var(--radius-chip); background:var(--card-bg); color:var(--danger); font-size:12px; font-weight:500; line-height:20px; white-space:nowrap; }
.event-card-track { width:100%; height:4px; border-radius:4px; background:color-mix(in srgb, var(--card-bg) 60%, transparent); overflow:hidden; }
.event-card-track i { display:block; height:100%; border-radius:inherit; background:var(--game-vivid); }
.event-card-end { display:inline-flex; align-items:center; gap:5px; font-size:12px; }
.event-watermark { position:absolute; right:-22px; top:-18px; z-index:-1; width:120px; height:120px; border-radius:34px; opacity:.16; transform:rotate(-9deg); font-size:52px; font-weight:600; filter:grayscale(.2); }
@media(hover:hover) and (pointer:fine) { .event-card:hover { box-shadow:var(--card-hover-shadow); } .event-card:hover .event-watermark { transform:rotate(-4deg) scale(1.04); } }
.event-watermark { transition:transform var(--duration-medium) var(--ease-smooth-out); }

.ov-news { margin-top:28px; padding:22px 24px 12px; }
.ov-news .section-heading { margin-bottom:8px; }
.news-filters { display:flex; gap:8px; margin-left:auto; min-width:0; }
.news-list { display:grid; grid-template-columns:repeat(auto-fill, minmax(min(420px, 100%), 1fr)); column-gap:28px; }
.news-summary { display:flex; align-items:center; gap:12px; min-width:0; padding:12px 8px; margin:0 -8px; border-bottom:1px solid var(--border); border-radius:var(--radius-control); }
.news-mark { width:34px; height:34px; border-radius:10px; background:var(--game-tone); font-size:14px; font-weight:600; }
.news-visual { display:block; flex:none; border-radius:10px; overflow:hidden; }
.news-cover { width:112px; height:70px; }
.news-visual:has(.news-cover) .news-mark { display:none; }
.news-summary:has(.news-cover) .news-source { flex-wrap:wrap; gap:2px 6px; }
.news-summary:has(.news-cover) .news-source time { margin-left:0; }
.news-summary:has(.news-cover) .news-copy>:is(a, p) { white-space:normal; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; }
.news-copy { flex:1; min-width:0; }
.news-summary a,.news-summary .news-copy>p { display:block; color:var(--text); text-decoration:none; font-size:14px; font-weight:500; line-height:20px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.news-summary a span { color:var(--text-faint); }
.news-source { display:flex; align-items:center; gap:6px; margin-top:2px; color:var(--text-muted); font-size:12px; line-height:18px; min-width:0; }.news-source>span { color:var(--text-faint); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.news-source time { margin-left:auto; flex-shrink:0; }
@media(hover:hover) and (pointer:fine) { .news-summary a:hover,.news-summary a:hover span { color:var(--accent); } }

@media(max-width:1250px) { .ov-top { grid-template-columns:minmax(0, 1.6fr) minmax(270px, 1fr); gap:16px; } .hero-inner { padding-left:22px; } .hero-index { left:16px; } .ov-analytics { grid-template-columns:minmax(0, 1.5fr) minmax(280px, 1fr); gap:16px; } }
@media(max-width:1180px) { .ov-top,.ov-analytics { grid-template-columns:minmax(0, 1fr); } .ov-tasks .task-list { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); column-gap:18px; } .task:nth-child(2) { border-top:0; padding-top:0; } }
@media(max-width:960px) { .ov-today { display:inline-flex !important; color:var(--text-body); } }
@media(max-width:720px) {
  .ov-actions { width:100%; } .ov-actions .ui-button { flex:1; }
  .ov-hero { border-radius:24px; } .hero-inner { padding:22px 20px 62px; border-radius:18px; }
  .hero-title b { font-size:36px; line-height:42px; }
  .ov-tasks .task-list { grid-template-columns:minmax(0, 1fr); } .task:nth-child(2) { border-top:1px solid var(--border); padding-top:6px; }
  .ov-game,.event-card { width:280px; }
  .ov-deadlines,.ov-gacha { padding:20px 18px 14px; }
  .gacha-number b { font-size:40px; }
}
@media(max-width:600px) {
  .hero-inner:has(.hero-backdrop)::after { background:linear-gradient(90deg,var(--game-tone),color-mix(in srgb,var(--game-tone) 84%,transparent) 46%,color-mix(in srgb,var(--game-tone) 25%,transparent)),linear-gradient(0deg,var(--game-tone),transparent 24%); }
  .news-cover { width:86px; height:72px; }
  .ov-news .section-heading { flex-wrap:wrap; gap:8px; }
  .news-filters { width:100%; margin-left:0; }
  .news-filters :deep(.menu-select) { flex:1; }
}
@media(max-width:420px) { .hero-index button { min-width:0; padding:8px 9px; } }
@media(prefers-reduced-motion:reduce) { .ov-next:active,.hero-cta:active { transform:none; } }
</style>
