<script setup>
import { computed, onBeforeUnmount, ref, useId } from 'vue'
import { fetchedLabel, monthDay } from '../time.js'
import { DAY_MS, beijingDayStart, parseBeijingTime } from '../calendar.js'
import { getMatchDetail } from '../api.js'
import MatchDetailPanel from './MatchDetailPanel.vue'
import RingGauge from './RingGauge.vue'
import { FORM_LABELS, kdaSplit, letterOf } from '../lol-charts.js'

const props = defineProps({
  snap: { type: Object, default: null },
  gameId: { type: String, default: '' },
  // 生涯统计快照：提供名场面标记，并给没有英雄名的旧快照补名（没有就不显示）
  stats: { type: Object, default: null },
})

// 与后端 matches.REMAKE_SECONDS 同一口径：5 分钟内结束的只会是重开或中止。
const REMAKE_SECONDS = 300
// 相邻两场隔了这么多天，就在走势图和卡片上标出这段空档。
const GAP_DAYS = 3

const known = (v) => typeof v === 'number' && Number.isFinite(v)

function fmtDuration(seconds) {
  if (!known(seconds)) return '-'
  return `${Math.round(seconds / 60)}分钟`
}

function fmtDamage(value) {
  if (!known(value)) return null
  return value >= 10000 ? `${(value / 10000).toFixed(1)} 万` : value.toLocaleString('zh-CN')
}

// 结果分四种：重开和结果未知不是负场，用灰色，不进胜率与场均。
function statusOf(it) {
  // 后端给出了判定就用它；旧快照没有这个字段时才按时长推断。
  const remake = typeof it.remake === 'boolean' ? it.remake : known(it.duration_seconds) && it.duration_seconds >= 0 && it.duration_seconds < REMAKE_SECONDS
  if (remake) return 'remake'
  if (it.win === true) return 'win'
  if (it.win === false) return 'loss'
  return 'unknown'
}
const BADGES = {
  win: { text: '胜', cls: 'badge-win' },
  loss: { text: '负', cls: 'badge-danger' },
  remake: { text: '重开', cls: 'badge-muted' },
  unknown: { text: '未知', cls: 'badge-muted' },
}

function dayOf(value) {
  const time = parseBeijingTime(value)
  return time == null ? null : beijingDayStart(time)
}
function agoText(day) {
  if (day == null) return null
  const days = Math.round((beijingDayStart(Date.now()) - day) / DAY_MS)
  return days <= 0 ? '今天' : days === 1 ? '昨天' : `${days} 天前`
}

const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
// 旧快照的对局没有英雄名，退回生涯统计里的常用英雄（只有前 5 个）。
const championNames = computed(() => new Map((props.stats?.top_champions ?? []).map((c) => [c.champion_id, c.champion_name])))
const recordLabels = computed(() => {
  const byMatch = new Map()
  for (const r of props.stats?.records ?? []) {
    if (!r?.match_id || !r.label) continue
    byMatch.set(r.match_id, [...(byMatch.get(r.match_id) ?? []), r.label.replace(/^单场/, '')])
  }
  return byMatch
})

// 从新到旧。快照一般已是这个顺序；时间齐全时仍按开局时间排一次，走势和空档都依赖它。
const rows = computed(() => {
  const payload = props.snap?.payload
  const raw = Array.isArray(payload) ? payload : []
  const items = raw.every((it) => parseBeijingTime(it.start_at) != null)
    ? [...raw].sort((a, b) => parseBeijingTime(b.start_at) - parseBeijingTime(a.start_at))
    : raw
  const played = items.filter((it) => statusOf(it) !== 'remake')
  const maxDamage = Math.max(0, ...played.map((it) => (known(it.damage) ? it.damage : 0)))
  const mapped = items.map((it) => {
    const status = statusOf(it)
    const hasKda = known(it.kills) && known(it.deaths) && known(it.assists)
    return {
      ...it,
      status,
      badge: BADGES[status],
      day: dayOf(it.start_at),
      dateText: monthDay(it.start_at),
      durationText: fmtDuration(it.duration_seconds),
      hasKda,
      ratio: hasKda && status !== 'remake' ? (it.kills + it.assists) / Math.max(it.deaths, 1) : null,
      champion: it.champion_name || championNames.value.get(it.champion_id) || '',
      damageText: status === 'remake' ? null : fmtDamage(it.damage),
      damageShare: known(it.damage) && maxDamage > 0 ? Math.round((it.damage / maxDamage) * 100) : null,
      records: recordLabels.value.get(it.match_id) ?? [],
      split: hasKda && status !== 'remake' ? kdaSplit(it.kills, it.deaths, it.assists) : null,
      gapBefore: null,
    }
  })
  // 每场与它之前（更早）那一场隔了几天；空档挂在较新的那场上。
  for (let i = 0; i < mapped.length - 1; i += 1) {
    const newer = mapped[i].day
    const older = mapped[i + 1].day
    if (newer != null && older != null) {
      const days = Math.round((newer - older) / DAY_MS)
      if (days >= GAP_DAYS) mapped[i].gapBefore = days
    }
  }
  return mapped
})

// 汇总：只用已经渲染出来的这些对局，不另外取数。
const summary = computed(() => {
  const played = rows.value.filter((r) => r.status !== 'remake')
  const decided = played.filter((r) => r.status === 'win' || r.status === 'loss')
  const wins = decided.filter((r) => r.status === 'win').length
  // 当前走势：重开不打断连胜连败，结果未知的对局会打断（无法判断）。
  let streak = 0
  let streakWin = null
  for (const r of rows.value) {
    if (r.status === 'remake') continue
    if (r.status === 'unknown') break
    const win = r.status === 'win'
    if (streakWin === null) streakWin = win
    if (win !== streakWin) break
    streak += 1
  }
  let best = 0
  let run = 0
  for (const r of [...rows.value].reverse()) {
    if (r.status === 'remake') continue
    run = r.status === 'win' ? run + 1 : 0
    best = Math.max(best, run)
  }
  const mean = (values) => (values.length ? values.reduce((a, b) => a + b, 0) / values.length : null)
  const damage = mean(played.map((r) => r.damage).filter(known))
  const durations = played.map((r) => r.duration_seconds).filter(known)
  const duration = mean(durations)
  return {
    wins,
    losses: decided.length - wins,
    remakes: rows.value.length - played.length,
    unknown: played.length - decided.length,
    rate: decided.length ? Math.round((wins / decided.length) * 100) : null,
    streak: streak ? { count: streak, win: streakWin } : null,
    best,
    latest: agoText(rows.value.find((r) => r.day != null)?.day ?? null),
    damage: damage == null ? null : fmtDamage(Math.round(damage)),
    duration: duration == null ? null : fmtDuration(duration),
    durationGames: durations.length,
  }
})

// 零死亡的对局 KDA 会冲到二三十，纵轴封顶 10，超出的柱子顶格并加标记。
const KDA_CAP = 10
// 走势图：从旧到新，柱高 = 单场 KDA，折线 = 截至该场的累计胜率（只算有胜负的对局）。
const trend = computed(() => {
  const list = [...rows.value].reverse()
  const n = list.length
  const ratios = list.filter((r) => r.ratio != null).map((r) => r.ratio)
  const scale = Math.min(KDA_CAP, Math.ceil(Math.max(1, ...ratios)))
  let wins = 0
  let decided = 0
  const points = []
  const gaps = []
  const bars = list.map((r, i) => {
    if (r.status === 'win' || r.status === 'loss') {
      decided += 1
      if (r.status === 'win') wins += 1
      points.push(`${(((i + 0.5) / n) * 100).toFixed(2)},${(100 - (wins / decided) * 100).toFixed(2)}`)
    }
    if (i > 0 && r.gapBefore) gaps.push({ key: r.match_id ?? i, x: (i / n) * 100, days: r.gapBefore })
    const stub = r.status === 'remake' || r.ratio == null
    const note = r.status === 'remake' ? '重开，不计入统计' : r.ratio == null ? '战绩数据缺失' : r.status === 'unknown' ? '结果未知' : r.badge.text
    return {
      key: r.match_id ?? i,
      status: r.status,
      label: FORM_LABELS[r.status] ?? FORM_LABELS.unknown,
      cls: [r.status, stub ? 'stub' : '', r.ratio != null && r.ratio > scale ? 'clipped' : ''],
      height: stub ? 14 : Math.max(3, Math.min(1, r.ratio / scale) * 100),
      tip: [r.dateText, r.champion || r.mode, note, r.hasKda ? `${r.kills}/${r.deaths}/${r.assists}` : null, r.ratio == null ? null : `KDA ${r.ratio.toFixed(1)}`, r.status === 'remake' ? r.durationText : null].filter(Boolean).join(' · '),
    }
  })
  const last = points.length ? Number(points[points.length - 1].split(',')[1]) : null
  return {
    show: ratios.length > 0,
    muted: list.some((r) => r.status === 'remake' || r.status === 'unknown' || r.ratio == null),
    bars,
    gaps,
    scale,
    line: points.join(' '),
    endRate: last == null ? null : Math.round(100 - last),
    endY: last,
    first: list[0]?.dateText || '',
    lastDate: list[n - 1]?.dateText || '',
  }
})

const modes = computed(() => {
  const groups = new Map()
  for (const r of rows.value) {
    const key = r.mode || '其他'
    const g = groups.get(key) ?? { mode: key, games: 0, wins: 0, decided: 0, remakes: 0, k: 0, d: 0, a: 0, kdaGames: 0, seconds: [] }
    groups.set(key, g)
    if (r.status === 'remake') { g.remakes += 1; continue }
    g.games += 1
    if (r.status === 'win' || r.status === 'loss') g.decided += 1
    if (r.status === 'win') g.wins += 1
    if (r.hasKda) { g.k += r.kills; g.d += r.deaths; g.a += r.assists; g.kdaGames += 1 }
    if (known(r.duration_seconds)) g.seconds.push(r.duration_seconds)
  }
  return [...groups.values()].filter((g) => g.games > 0).sort((a, b) => b.games - a.games).map((g) => ({
    ...g,
    rate: g.decided ? Math.round((g.wins / g.decided) * 100) : null,
    detail: [
      g.decided ? `${g.wins} 胜 ${g.decided - g.wins} 负` : null,
      g.kdaGames ? `KDA ${((g.k + g.a) / Math.max(g.d, 1)).toFixed(1)}` : null,
      g.seconds.length ? `场均 ${fmtDuration(g.seconds.reduce((x, y) => x + y, 0) / g.seconds.length)}` : null,
      g.remakes ? `另有 ${g.remakes} 场重开` : null,
    ].filter(Boolean).join(' · '),
  }))
})

// Share of games per mode, in the chart colours' own order.
const modeShare = computed(() => modes.value.map((m, i) => ({ mode: m.mode, games: m.games, color: `var(--chart-${Math.min(i + 1, 8)})` })))

const metaText = computed(() => {
  const parts = []
  if (rows.value.length) {
    parts.push(`近 ${rows.value.length} 场 ${summary.value.wins} 胜`)
    if (summary.value.remakes) parts.push(`${summary.value.remakes} 场重开不计`)
    if (summary.value.unknown) parts.push(`${summary.value.unknown} 场结果未知`)
  }
  if (fetchedAt.value) parts.push(`更新于 ${fetchedAt.value}`)
  return parts.join(' · ')
})
// 对局详情按需展开（同时只展开一场），放在被点卡片那一行的末尾之后，
// 这样阅读和键盘顺序与画面一致（不用 dense 回填）。
const grid = ref(null)
const columns = ref(1)
const detailId = `${useId()}-detail`
function measureColumns() {
  const el = grid.value
  if (!el || typeof getComputedStyle !== 'function') return
  columns.value = Math.max(1, getComputedStyle(el).gridTemplateColumns.split(' ').filter(Boolean).length)
}
const expandedId = ref(null)
const expandedRow = computed(() => rows.value.find((r) => r.match_id === expandedId.value) ?? null)
const detailAfter = computed(() => {
  if (expandedId.value == null) return -1
  const index = rows.value.findIndex((r) => r.match_id === expandedId.value)
  if (index < 0) return -1
  const per = columns.value
  return Math.min(rows.value.length - 1, Math.floor(index / per) * per + per - 1)
})
// The column count follows the grid's own width, which also changes when the
// sidebar or a scrollbar comes and goes. Measuring in the next frame keeps the
// detail's move out of the observer's own delivery.
let widthObserver = null
function watchWidth(on) {
  widthObserver?.disconnect()
  widthObserver = null
  if (!on || typeof ResizeObserver !== 'function' || !grid.value) return
  widthObserver = new ResizeObserver(() => requestAnimationFrame(measureColumns))
  widthObserver.observe(grid.value)
}
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')
let detailGeneration = 0
onBeforeUnmount(() => { detailGeneration += 1; watchWidth(false) })

async function toggleDetail(row) {
  const request = ++detailGeneration
  if (expandedId.value === row.match_id) {
    expandedId.value = null
    detail.value = null
    detailError.value = ''
    detailLoading.value = false
    watchWidth(false)
    return
  }
  measureColumns()
  watchWidth(true)
  expandedId.value = row.match_id
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const data = await getMatchDetail(props.gameId, row.match_id)
    if (request !== detailGeneration) return
    if (data?.error) {
      detailError.value = data.error
    } else {
      detail.value = data?.payload ?? null
    }
  } catch (e) {
    if (request === detailGeneration) detailError.value = e?.message || '请求异常'
  } finally {
    if (request === detailGeneration) detailLoading.value = false
  }
}
</script>

<template>
  <div class="match-panel">
    <div class="mp-head">
      <h3 class="mp-title">近期对局</h3>
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="metaText" class="cap-meta">{{ metaText }}</span>
    </div>

    <p v-if="rows.length === 0" class="empty cap-card">暂无数据</p>
    <template v-else>
      <div v-if="summary.rate != null || summary.streak || summary.damage || summary.duration || trend.show || modes.length" class="mp-bento">
        <section v-if="summary.rate != null || summary.streak || summary.damage || summary.duration" class="cap-card mp-rate">
          <dl class="mp-list">
            <div v-if="summary.rate != null" class="rate-main">
              <RingGauge :value="summary.rate" :max="100" label="近期胜率" :size="148" :stroke="14" color="var(--game-vivid)"><span class="ring-big" aria-hidden="true"><b>{{ summary.rate }}</b><small>%</small></span></RingGauge>
              <div><dt>胜率</dt><dd>{{ summary.wins }} 胜 {{ summary.losses }} 负</dd></div>
            </div>
            <div v-if="summary.streak" class="tile wide">
              <dt>当前走势</dt>
              <dd :class="summary.streak.win ? 'up' : 'down'">{{ summary.streak.count }}<small>{{ summary.streak.win ? '连胜' : '连败' }}</small></dd>
              <p v-if="summary.latest">最近一场 {{ summary.latest }}</p><p>最长连胜 {{ summary.best }} 场</p>
            </div>
            <div v-if="summary.damage" class="tile"><dt>场均伤害</dt><dd>{{ summary.damage }}</dd><p>对英雄伤害</p></div>
            <div v-if="summary.duration" class="tile"><dt>场均时长</dt><dd>{{ summary.duration }}</dd><p>{{ summary.durationGames }} 场平均</p></div>
          </dl>
        </section>

        <figure v-if="trend.show" class="cap-card mp-trend trend" :aria-label="`近 ${rows.length} 场走势：柱高为单场 KDA，折线为累计胜率`">
          <figcaption>
            <span class="chart-title">近 {{ rows.length }} 场走势</span>
            <ul class="legend">
              <li style="--series: var(--success)">胜</li>
              <li style="--series: var(--danger)">负</li>
              <li v-if="trend.muted" style="--series: var(--text-faint)">重开 / 未知</li>
              <li class="line-key">累计胜率</li>
            </ul>
          </figcaption>
          <div class="plot">
            <span class="axis-max">KDA {{ trend.scale }}</span>
            <span v-for="gap in trend.gaps" :key="gap.key" class="gap" :style="{ left: `calc((100% - 30px) * ${gap.x / 100})` }" :title="`隔 ${gap.days} 天`"></span>
            <div class="bars">
              <span v-for="bar in trend.bars" :key="bar.key" class="bar" :class="bar.cls" :style="{ '--h': `${bar.height}%` }" :data-tip="bar.tip"></span>
            </div>
            <span v-if="trend.endRate == null || Math.abs(trend.endRate - 50) > 10" class="half-label">50%</span>
            <svg class="line" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              <line class="half" x1="0" y1="50" x2="100" y2="50" />
              <polyline v-if="trend.line" :points="trend.line" />
            </svg>
            <span v-if="trend.endRate != null" class="line-end" :style="{ top: `calc(14px + (100% - 14px) * ${trend.endY / 100})` }">{{ trend.endRate }}%</span>
          </div>
          <div class="form-pills" aria-hidden="true"><b v-for="bar in trend.bars" :key="bar.key" :class="bar.status">{{ bar.label }}</b></div>
          <div class="axis">
            <span>{{ trend.first }}</span><span>{{ trend.lastDate }}</span>
            <span v-for="gap in trend.gaps" v-show="gap.x > 10 && gap.x < 90" :key="gap.key" class="gap-label" :style="{ left: `${gap.x}%` }">隔 {{ gap.days }} 天</span>
          </div>
        </figure>

        <section v-if="modes.length" class="cap-card mp-modes modes" aria-label="模式分布">
          <p class="chart-title">模式分布</p>
          <div v-if="modeShare.length > 1" class="stack-bar" role="img" aria-label="各模式场次占比"><i v-for="m in modeShare" :key="m.mode" :style="{ flex: m.games, '--series': m.color }"></i></div>
          <ul v-if="modeShare.length > 1" class="legend"><li v-for="m in modeShare" :key="m.mode" :style="{ '--series': m.color }">{{ m.mode }} <b>{{ m.games }}</b></li></ul>
          <ul class="bar-list">
            <li v-for="m in modes" :key="m.mode" class="mode">
              <div class="bar-row" style="--bar-label: 38%">
                <span class="k">{{ m.mode }} <small>{{ m.games }} 场</small></span>
                <span class="meter"><i :style="{ '--pct': `${m.rate ?? 0}%` }"></i></span>
                <span class="v">{{ m.rate == null ? '-' : `${m.rate}%` }}</span>
              </div>
              <p v-if="m.detail" class="mode-detail">{{ m.detail }}</p>
            </li>
          </ul>
          <p class="modes-note">条长为该模式胜率</p>
        </section>
      </div>

      <div ref="grid" class="match-grid">
        <template v-for="(it, i) in rows" :key="it.match_id ?? i">
          <article class="match-item" :class="[`is-${it.status}`, { open: expandedId === it.match_id }]">
            <div class="mi-head">
              <span class="champ-tile" aria-hidden="true">{{ letterOf(it.champion || it.mode) }}</span>
              <span class="mi-name"><strong>{{ it.champion || it.mode || '对局' }}</strong><time>{{ it.dateText || '-' }}</time></span>
              <span class="badge" :class="it.badge.cls">{{ it.badge.text }}</span>
            </div>
            <div class="mi-kda">
              <template v-if="it.hasKda"><b>{{ it.kills }}</b><i>/</i><b class="deaths">{{ it.deaths }}</b><i>/</i><b>{{ it.assists }}</b></template>
              <b v-else>-</b>
              <span v-if="it.ratio != null" class="ratio">KDA {{ it.ratio.toFixed(1) }}</span>
              <span v-else-if="it.status === 'remake'" class="ratio">不计入统计</span>
            </div>
            <span v-if="it.split" class="kda-bar" aria-hidden="true"><i class="k" :style="{ flex: it.split.k }"></i><i class="d" :style="{ flex: it.split.d }"></i><i class="a" :style="{ flex: it.split.a }"></i></span>
            <div v-if="it.damageText" class="mi-damage">
              <span class="meter"><i :style="{ '--pct': `${it.damageShare ?? 0}%` }"></i></span>
              <span>伤害 {{ it.damageText }}</span>
            </div>
            <div class="mi-foot">
              <span class="mi-meta">{{ [it.champion ? it.mode : '', it.durationText].filter(Boolean).join(' · ') }}</span>
              <span v-if="it.gapBefore" class="chip gap-chip" :title="`与上一场相隔 ${it.gapBefore} 天`">隔 {{ it.gapBefore }} 天</span>
              <span v-for="label in it.records" :key="label" class="chip record">{{ label }}</span>
              <button type="button" class="ui-button small-button" :aria-expanded="expandedId === it.match_id" :aria-controls="expandedId === it.match_id ? detailId : undefined" @click="toggleDetail(it)">
                {{ expandedId === it.match_id ? '收起' : '详情' }}
              </button>
            </div>
          </article>
          <div v-if="i === detailAfter" :id="detailId" class="match-detail" :aria-label="`对局详情 ${expandedRow?.dateText ?? ''}`" role="region">
            <MatchDetailPanel :detail="detail" :loading="detailLoading" :error="detailError" :remake="expandedRow?.status === 'remake'" />
          </div>
        </template>
      </div>
    </template>
  </div>
</template>

<style scoped>
.mp-head{display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;margin:0 0 14px}
.mp-title{font-size:18px;line-height:26px;font-weight:600;letter-spacing:-.02em;margin:0}
.chart-title{margin:0;color:var(--text);font-size:16px;font-weight:600;line-height:24px;letter-spacing:-.02em;white-space:nowrap}

/* Overview bento: one tall tone card on the left (win rate and the averages), the form chart and the mode split stacked on the right. */
.mp-bento{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:20px;margin-bottom:20px}
.mp-bento>*{min-width:0;margin:0}
.mp-rate{grid-column:1/span 4;grid-row:1/span 2;border-color:transparent;background:var(--game-tone)}
.mp-trend{grid-column:5/span 8}.mp-modes{grid-column:5/span 8}
.mp-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:0;height:100%;align-content:space-between}
.mp-list>div{min-width:0}
.rate-main{grid-column:1/-1;display:grid;justify-items:center;gap:12px;text-align:center;padding:6px 0 8px}
.mp-rate :deep(.ring-track){stroke:color-mix(in srgb,var(--card-bg) 72%,transparent)}
.ring-big b{display:inline;font-size:40px;line-height:1;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.ring-big small{margin-left:2px;font-size:17px;font-weight:500;color:var(--game-accent)}
.mp-list dt{color:var(--game-accent);font-size:12px;line-height:18px}
.rate-main dt{display:none}.rate-main dd{margin:0;color:var(--text);font-size:13px;font-weight:500}
.tile{padding:12px 14px;border-radius:var(--radius-well);background:var(--card-bg)}
.tile.wide{grid-column:1/-1}
.tile dt{color:var(--text-muted)}
.tile dd{margin:2px 0 0;color:var(--text);font-size:24px;line-height:30px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums;white-space:nowrap}
.tile dd small{margin-left:4px;color:inherit;font-size:13px;font-weight:500;letter-spacing:0}
.tile dd.up{color:var(--success)}.tile dd.down{color:var(--danger)}
.tile p{margin-top:1px;color:var(--text-muted);font-size:12px;line-height:18px}

.trend{margin:0;--line:var(--chart-1)}
.trend figcaption{display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:4px 12px;margin-bottom:12px}
.trend .legend{margin:0}
.legend .line-key::before{width:12px;height:2px;border-radius:1px;background:var(--line)}
.plot{position:relative;height:136px;padding-top:14px;border-bottom:1px solid var(--border)}
.axis-max{position:absolute;top:0;left:0;color:var(--text-faint);font-size:12px;line-height:14px}
.bars{position:absolute;inset:14px 30px 0 0;display:flex;align-items:flex-end;gap:3px}
.bar{position:relative;flex:1;min-width:0;height:var(--h);border-radius:4px 4px 0 0;background:var(--track);transition:opacity var(--duration-quick) var(--ease-smooth-out)}
.bar.win{background:color-mix(in srgb,var(--success) 78%,var(--card-bg))}
.bar.loss{background:color-mix(in srgb,var(--danger) 72%,var(--card-bg))}
/* Not a win or a loss: grey. Remakes and missing stats get a short dashed stub so they read as "no result", not a KDA of zero. */
.bar.unknown{background:color-mix(in srgb,var(--text-faint) 50%,var(--track))}
.bar.stub{border:1.5px dashed var(--text-faint);border-bottom:0;background:transparent}
.bar::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 6px);z-index:3;display:none;padding:4px 10px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--card-bg);box-shadow:var(--popover-shadow);color:var(--text-body);font-size:12px;line-height:16px;white-space:nowrap;transform:translateX(-50%);pointer-events:none}
/* Tips near the edges open inward so they never leave the card. */
.bar:nth-child(-n+3)::after{left:0;transform:none}
.bar:nth-last-child(-n+3)::after{right:0;left:auto;transform:none}
@media(hover:hover) and (pointer:fine){
  .bar:hover::after{display:block}
  .bars:hover .bar:not(:hover){opacity:.5}
}
.line{position:absolute;inset:14px 30px 0 0;width:calc(100% - 30px);height:calc(100% - 14px);overflow:visible;pointer-events:none}
.line polyline{fill:none;stroke:var(--line);stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.line .half{stroke:var(--border-strong);stroke-width:1;stroke-dasharray:3 3;vector-effect:non-scaling-stroke}
/* KDA above the axis cap: the bar stops at the top with a small marker. */
.bar.clipped::before{content:'';position:absolute;left:50%;top:-5px;width:6px;height:6px;border-radius:1px;background:inherit;transform:translateX(-50%) rotate(45deg)}
.half-label{position:absolute;right:0;top:calc(14px + (100% - 14px) * .5);width:30px;color:var(--text-faint);font-size:12px;line-height:14px;text-align:right;transform:translateY(-50%)}
.line-end{position:absolute;right:0;width:34px;color:var(--text);font-size:12px;font-weight:600;line-height:14px;text-align:right;transform:translateY(-50%)}
.form-pills{display:flex;gap:3px;margin:8px 30px 0 0}
.form-pills b{display:grid;place-items:center;flex:1 1 0;min-width:0;height:22px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-muted);font-size:12px;font-weight:600;line-height:1}
.form-pills b.win{background:var(--success-bg);color:var(--success)}.form-pills b.loss{background:var(--danger-bg);color:var(--danger)}
.axis{position:relative;display:flex;justify-content:space-between;margin-right:30px;padding-top:6px;color:var(--text-faint);font-size:12px}
/* A break of several days between two games: dashed divider plus a label. */
.gap{position:absolute;top:14px;bottom:0;width:0;border-left:1px dashed var(--border-strong);pointer-events:none}
.gap-label{position:absolute;top:6px;padding:0 4px;background:var(--card-bg);white-space:nowrap;transform:translateX(-50%)}

.modes{display:flex;flex-direction:column;gap:10px}
.modes .legend{margin:0}
.modes .bar-list{gap:8px}
.mode-detail{margin:-2px 0 0;color:var(--text-faint);font-size:12px;line-height:18px}
.modes .k small{margin-left:4px;color:var(--text-faint);font-size:12px}
.modes-note{margin-top:auto;color:var(--text-faint);font-size:12px}

/* Match cards: white with a hairline; the result is a tag with a word, the champion a tone tile with its first letter. The opened match's details span the full width after the last card of its row. */
.match-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,250px),1fr));gap:16px}
.match-item{display:grid;gap:10px;min-width:0;padding:16px;border:1px solid var(--card-border);border-radius:var(--radius-tile);background:var(--card-bg);box-shadow:var(--card-shadow)}
.match-item.open{border-color:var(--border-strong)}
.is-remake .mi-name strong,.is-remake .mi-kda b,.is-remake .mi-kda b.deaths{color:var(--text-muted)}
.mi-head{display:flex;align-items:center;gap:10px;min-width:0}
.champ-tile{display:grid;place-items:center;flex-shrink:0;width:40px;height:40px;border-radius:30%;background:var(--game-tone);color:var(--game-accent);font-size:17px;font-weight:600}
.mi-name{display:grid;min-width:0;margin-right:auto}
.mi-name strong{overflow:hidden;color:var(--text);font-size:14px;font-weight:600;line-height:20px;text-overflow:ellipsis;white-space:nowrap}
.mi-name time{color:var(--text-faint);font-size:12px;line-height:16px}
.mi-kda{display:flex;align-items:baseline;gap:3px;color:var(--text)}
.mi-kda b{font-size:22px;line-height:28px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.mi-kda i{color:var(--text-faint);font-style:normal;font-size:14px}
.mi-kda .ratio{margin-left:auto;padding:0 8px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-body);font-size:12px;font-weight:500;line-height:20px;white-space:nowrap}
.kda-bar{display:flex;gap:2px;height:6px;border-radius:3px;overflow:hidden;background:var(--track)}
.kda-bar i{display:block;min-width:2px}.kda-bar .k{background:var(--game-vivid)}.kda-bar .d{background:color-mix(in srgb,var(--text-faint) 55%,var(--track))}.kda-bar .a{background:color-mix(in srgb,var(--game-vivid) 55%,var(--card-bg))}
.mi-damage{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;color:var(--text-muted);font-size:12px}
.mi-damage .meter{height:4px}
.mi-foot{display:flex;flex-wrap:wrap;align-items:center;gap:6px;min-width:0;padding-top:10px;border-top:1px solid var(--border)}
.mi-meta{min-width:88px;margin-right:auto;overflow:hidden;color:var(--text-muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.chip.record{background:var(--game-tone);color:var(--game-accent)}
.mi-foot .ui-button{flex-shrink:0}
.mi-foot .ui-button[aria-expanded="true"]{background:var(--accent-soft);border-color:transparent;color:var(--accent)}
.match-detail{grid-column:1/-1;min-width:0;padding:6px 16px 14px;border:1px solid var(--card-border);border-radius:var(--radius-tile);background:var(--card-bg);box-shadow:var(--card-shadow)}

.badge-win{color:var(--success);background:var(--success-bg)}
.badge-muted{color:var(--text-muted);background:var(--control-track)}

@media(max-width:900px){
  .mp-rate,.mp-trend,.mp-modes{grid-column:1/-1;grid-row:auto}
  .mp-list{grid-template-columns:repeat(3,minmax(0,1fr))}.rate-main{grid-column:1/-1}.tile.wide{grid-column:auto}
}
@media(max-width:600px){
  .mp-bento{gap:14px;margin-bottom:14px}.match-grid{gap:12px}
  .form-pills{gap:2px}.form-pills b{height:20px;border-radius:4px;font-size:11px}
  .mp-list{grid-template-columns:repeat(2,minmax(0,1fr))}.tile.wide{grid-column:1/-1}
}
</style>
