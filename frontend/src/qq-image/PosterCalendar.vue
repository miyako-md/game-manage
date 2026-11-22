<script setup>
import { computed, reactive } from 'vue'
import {
  DAY_MS,
  beijingDayStart,
  calendarDaysRange,
  eventGeometry,
  eventStatus,
  versionCalendarRange,
} from '../calendar.js'
import { calendarCategory } from '../calendar-presentation.js'
import { eventArtwork } from '../event-artwork.js'
import { gameVars } from '../dashboard.js'
import { skinOf } from '../game-themes.js'
import { asset } from './models.js'

const props = defineProps({
  panels: { type: Array, default: () => [] },
})

const BEIJING_OFFSET = 8 * 3600000
const failedArt = reactive(new Set())
const markFailed = url => {
  if (url) failedArt.add(url)
}

const isSingle = computed(() => props.panels.length === 1)
const primaryPanel = computed(() => props.panels[0] || {})

const pad2 = n => String(n).padStart(2, '0')
function fmtMD(ms) {
  if (ms == null || !Number.isFinite(ms)) return ''
  const d = new Date(ms + BEIJING_OFFSET)
  return `${pad2(d.getUTCMonth() + 1)}.${pad2(d.getUTCDate())}`
}

const asOfMs = computed(() => {
  const found = props.panels.map(p => Number(p?.asOf)).find(Number.isFinite)
  return found ?? Date.now()
})

const unifiedRange = computed(() => {
  if (!props.panels.length) return null
  const dayStart = beijingDayStart(asOfMs.value) ?? beijingDayStart(Date.now())
  const fallbackStart = dayStart - 2 * DAY_MS
  const fallback = calendarDaysRange(fallbackStart, fallbackStart + 14 * DAY_MS)

  if (isSingle.value) {
    const p = primaryPanel.value
    if (p.full) {
      const vr = versionCalendarRange(p.events || [], asOfMs.value)
      if (vr && vr.days.length >= 2) return vr
    }
    return fallback
  }

  const anyFull = props.panels.some(p => p.full)
  if (anyFull) {
    const allEvents = props.panels.flatMap(p => p.events || [])
    const vr = versionCalendarRange(allEvents, asOfMs.value)
    if (vr && vr.days.length >= 2 && vr.days.length <= 90) return vr
  }
  return fallback
})

const todayPct = computed(() => {
  const r = unifiedRange.value
  if (!r || r.end <= r.start) return null
  if (asOfMs.value < r.start || asOfMs.value > r.end) return null
  return Math.max(0, Math.min(100, ((asOfMs.value - r.start) / (r.end - r.start)) * 100))
})

const todayPillPct = computed(() => {
  if (todayPct.value == null) return null
  return Math.max(7, Math.min(93, todayPct.value))
})

const monthMarkers = computed(() => {
  const r = unifiedRange.value
  if (!r) return []
  const total = r.days.length
  const out = []
  let lastLeft = -20
  r.days.forEach((d, idx) => {
    if (idx === 0 || d.day === 1) {
      const left = Math.min(92, (idx / total) * 100)
      if (left - lastLeft >= 7) {
        out.push({ key: `${d.month}-${idx}`, label: `${d.month}月`, left })
        lastLeft = left
      }
    }
  })
  return out
})

const rulerTicks = computed(() => {
  const r = unifiedRange.value
  if (!r) return []
  const total = r.days.length
  const step = total <= 14 ? 1 : total <= 22 ? 2 : total <= 35 ? 3 : total <= 50 ? 4 : 5
  const out = []
  r.days.forEach((d, idx) => {
    const isEnd = idx === total - 1
    if (idx % step === 0 || (isEnd && idx % step >= Math.ceil(step / 2))) {
      const pct = ((idx + 0.5) / total) * 100
      const align = pct < 3 ? 'start' : pct > 97 ? 'end' : 'center'
      out.push({
        key: d.timestamp,
        day: d.day,
        pct,
        align,
        weekend: d.weekend,
      })
    }
  })
  return out
})

// As in RenderCalendar.vue, the one picture most activities of a game reuse is
// the version or notice image, not an activity banner. It must be reused by at
// least three activities, so two pools sharing one banner keep it.
const SHARED_ART_LIMIT = 3
function sharedArtwork(events, snapshots) {
  const counts = new Map()
  for (const ev of events || []) {
    for (const url of eventArtwork(ev, snapshots || {})) counts.set(url, (counts.get(url) || 0) + 1)
  }
  const [top] = [...counts].filter(([, count]) => count >= SHARED_ART_LIMIT).sort((a, b) => b[1] - a[1])
  return new Set(top ? [top[0]] : [])
}

function safeEventArt(ev, snapshots, shared) {
  for (const url of eventArtwork(ev, snapshots || {})) {
    if (shared.has(url)) continue
    const cached = asset(url)
    if (cached && !failedArt.has(cached)) return cached
  }
  return ''
}

function dateLabel(ev, geom) {
  if (geom.kind === 'point') {
    const t = geom.start ?? geom.end
    return fmtMD(t) || ev.start_text || ev.end_text || ''
  }
  if (ev.permanent && ev.end_precision === 'permanent') {
    return `${fmtMD(geom.start)} – 常驻`
  }
  const inclusiveEnd = geom.end != null ? geom.end - (!ev.end_at && ev.end_date ? 1 : 0) : null
  const s = fmtMD(geom.start)
  const e = fmtMD(inclusiveEnd)
  if (s && e) return `${s} – ${e}`
  return s || e || ev.start_text || ev.end_text || ''
}

function classifySingleKind(ev) {
  const cat = calendarCategory(ev)
  const text = `${ev.category || ''} ${ev.name || ''}`
  if (cat.key === 'equipment' || /弧盘|武器|兵器|特刊|武器活动唤取/.test(ev.category || '')) {
    return { kind: 'weapon', label: '武器与弧盘', accent: 'weapon' }
  }
  if (cat.key === 'characters') {
    return { kind: 'gacha', label: '寻访与角色', accent: 'gacha' }
  }
  if (/签到|登录|补给|赠礼|七日/.test(text)) {
    return { kind: 'checkin', label: '限时签到', accent: 'checkin' }
  }
  return { kind: 'activity', label: '活动日历', accent: 'activity' }
}

// Rough track width (px) for estimating how much of the ruler a label covers.
const TRACK_PX = 900
const LABEL_GAP = 0.8
// Width of the check-in strip drawn inside wide check-in bars.
const CHECKIN_STRIP_PX = 278
function textPx(text, size = 17) {
  return [...String(text || '')].reduce((sum, ch) => sum + (/[⺀-￿]/.test(ch) ? size : size * 0.56), 0)
}
const chipPx = text => (text ? textPx(text) + 14 + 8 : 0)
function labelPct(name, dateText) {
  return Math.min(60, ((22 + textPx(name) + 8 + textPx(dateText)) / TRACK_PX) * 100 + 1)
}

function packLanes(items) {
  const sorted = [...items].sort((a, b) => a.occStart - b.occStart || b.width - a.width)
  const lanes = []
  for (const item of sorted) {
    let placed = false
    for (const lane of lanes) {
      if (lane.maxRight + 1.4 <= item.occStart) {
        lane.items.push(item)
        lane.maxRight = Math.max(lane.maxRight, item.occEnd)
        placed = true
        break
      }
    }
    if (!placed) {
      lanes.push({ maxRight: item.occEnd, items: [item] })
    }
  }
  return lanes.map(l => l.items)
}

function buildItems(events, snapshots, withCategoryKind = false) {
  const r = unifiedRange.value
  if (!r) return { visible: [], pending: [] }
  const visible = []
  const pending = []
  const shared = sharedArtwork(events, snapshots)

  for (const ev of events || []) {
    const geom = eventGeometry(ev, r)
    const status = eventStatus(ev, asOfMs.value)
    if (!geom.visible) {
      if (geom.kind === 'undated' || geom.kind === 'invalid') {
        pending.push({
          id: ev.id,
          name: ev.name || '未命名活动',
          status,
          category: ev.category || '',
        })
      }
      continue
    }
    const isPoint = geom.kind === 'point'
    const left = Math.max(0, Math.min(99, geom.left))
    const width = isPoint ? 0 : Math.max(1.2, Math.min(100 - left, geom.width))
    const name = `${geom.clippedStart ? '‹ ' : ''}${ev.name || '未命名活动'}${geom.clippedEnd ? ' ›' : ''}`
    const dateText = dateLabel(ev, geom)
    const right = left + width
    const catInfo = withCategoryKind ? classifySingleKind(ev) : { kind: 'activity', label: ev.category || '', accent: 'activity' }
    const stateChip = status === '进行中' || status === '未开始' || status === '已结束' ? status : ''
    // The QQ layout audit rejects clipped or escaping text. A bar keeps its name
    // and date inside, dropping the category and then the status tag when the
    // line is too long; only a bar too narrow for the name or the date itself
    // carries its label beside the bar.
    const tagText = withCategoryKind && catInfo.kind === 'checkin' ? '签到' : ''
    const fit = strip => {
      const copyPx = (width / 100) * TRACK_PX - 24 - (strip ? CHECKIN_STRIP_PX : 0)
      const fitsLine = px => px * 1.08 <= copyPx
      if (!fitsLine(textPx(name, 18)) || !fitsLine(textPx(dateText))) return null
      const tag = strip ? '' : tagText
      const options = withCategoryKind
        ? [{ tag: !!tag, status: !tag && !!stateChip, px: chipPx(tag || stateChip) }]
        : [{ category: true, status: true, px: chipPx(ev.category) + chipPx(stateChip) },
            { category: false, status: true, px: chipPx(stateChip) }]
      return options.find(option => fitsLine(textPx(dateText) + option.px))
        || { category: false, status: false, tag: false }
    }
    const wideCheckin = !isPoint && catInfo.kind === 'checkin' && width >= 68 && !!fit(true)
    const shown = isPoint ? null : fit(wideCheckin)
    const isShort = isPoint || !shown
    // Short bars carry their label beside the bar (never on top of it): after
    // the bar when it fits, otherwise before it if that side has more room.
    const need = labelPct(name, dateText)
    const roomAfter = 100 - right - LABEL_GAP
    const roomBefore = left - LABEL_GAP
    const anchorRight = isPoint ? left > 55 : isShort && roomAfter < need && roomBefore > roomAfter
    let occStart = left
    let occEnd = right
    let shortLabelStyle = null
    if (isPoint) {
      if (anchorRight) occStart = Math.max(0, left - 26)
      else occEnd = Math.min(100, left + 26)
    } else if (isShort && anchorRight) {
      occStart = Math.max(0, left - LABEL_GAP - need)
      shortLabelStyle = { right: `${100 - left + LABEL_GAP}%`, maxWidth: `${roomBefore}%` }
    } else if (isShort) {
      occEnd = Math.min(100, right + LABEL_GAP + need)
      shortLabelStyle = { left: `${right + LABEL_GAP}%`, maxWidth: `${Math.max(0, roomAfter)}%` }
    }
    const art = safeEventArt(ev, snapshots, shared)

    visible.push({
      id: ev.id,
      name,
      dateText,
      category: ev.category || '',
      status,
      isEnded: status === '已结束',
      isPoint,
      isShort,
      anchorRight,
      shortLabelStyle,
      occStart,
      occEnd,
      left,
      width,
      art,
      bandKind: catInfo.kind,
      bandLabel: catInfo.label,
      wideCheckin,
      showCategory: !!shown?.category,
      showStatus: !!shown?.status,
      showTag: !!shown?.tag,
    })
  }
  return { visible, pending }
}

const singleBands = computed(() => {
  if (!isSingle.value) return []
  const p = primaryPanel.value
  const { visible } = buildItems(p.events, p.snapshots, true)
  const defs = [
    ['gacha', '寻访与角色'],
    ['weapon', '武器与弧盘'],
    ['checkin', '限时签到'],
    ['activity', '活动日历'],
  ]
  const active = []
  for (const [kind, label] of defs) {
    const rows = visible.filter(it => it.bandKind === kind)
    if (rows.length) {
      active.push({
        key: kind,
        kind,
        label,
        count: rows.length,
        lanes: packLanes(rows),
      })
    }
  }
  return active.map((b, i) => ({ ...b, indexText: pad2(i + 1) }))
})

const multiBands = computed(() => {
  if (isSingle.value) return []
  return props.panels.map((p, i) => {
    const { visible } = buildItems(p.events, p.snapshots, false)
    const verMatch = p.title?.match(/·\s*([^\s]+)\s*版本/)?.[1]
    return {
      key: p.gameId || String(i),
      gameId: p.gameId,
      skin: skinOf(p.gameId) || undefined,
      style: p.gameId ? gameVars(p.gameId) : undefined,
      title: p.title,
      shortName: p.title?.split('·')?.[0]?.trim() || p.gameId,
      // Numbered versions read "V3.8"; named ones (终末地「丹青渡」) stay as named.
      verTag: !verMatch ? '' : /^\d/.test(verMatch) ? `V${verMatch}` : [...verMatch].length <= 4 ? verMatch : '',
      indexText: pad2(i + 1),
      count: visible.length,
      lanes: packLanes(visible),
    }
  })
})

const pendingList = computed(() => {
  const out = []
  for (const p of props.panels) {
    const { pending } = buildItems(p.events, p.snapshots, false)
    const gameName = !isSingle.value ? (p.title?.split('·')?.[0]?.trim() || '') : ''
    for (const item of pending) {
      out.push({
        ...item,
        prefix: gameName ? `[${gameName}] ` : '',
      })
    }
  }
  return out
})
</script>

<template>
  <div class="ov-pcal-root" :class="isSingle ? 'is-single' : 'is-multi'">
    <!-- Single-game editorial version / 14-day poster calendar -->
    <section
      v-if="isSingle"
      class="ov-cal-group ov-pcal-shell"
      :data-skin="skinOf(primaryPanel.gameId) || undefined"
      :style="primaryPanel.gameId ? gameVars(primaryPanel.gameId) : undefined"
    >
      <header class="ov-pcal-top-meta">
        <strong class="ov-pcal-top-title">{{ primaryPanel.title }}</strong>
        <span v-if="primaryPanel.caption" class="ov-pcal-top-cap">{{ primaryPanel.caption }}</span>
      </header>

      <div v-if="unifiedRange" class="ov-pcal-board">
        <!-- Unified Date Ruler -->
        <div class="ov-pcal-ruler-row">
          <div class="ov-pcal-rail-spacer">排期刻度</div>
          <div class="ov-pcal-ruler-track">
            <div class="ov-pcal-months" aria-hidden="true">
              <span
                v-for="m in monthMarkers"
                :key="m.key"
                class="ov-pcal-month-tag"
                :style="{ left: `${m.left}%` }"
              >{{ m.label }}</span>
            </div>
            <div class="ov-pcal-ticks">
              <span
                v-for="tick in rulerTicks"
                :key="tick.key"
                class="ov-pcal-tick"
                :class="[`is-${tick.align}`, { 'is-weekend': tick.weekend }]"
                :style="tick.align === 'start' ? { left: '0%' } : tick.align === 'end' ? { right: '0%' } : { left: `${tick.pct}%` }"
              >{{ tick.day }}</span>
            </div>
            <div v-if="todayPillPct != null" class="ov-pcal-today-row">
              <span class="ov-pcal-today-pill" :style="{ left: `${todayPillPct}%` }">今天 {{ fmtMD(asOfMs) }}</span>
            </div>
          </div>
        </div>

        <!-- Bands Area with One Continuous Vertical Today Line -->
        <div class="ov-pcal-bands-wrap">
          <div
            v-if="todayPct != null"
            class="ov-pcal-today-rail-line"
            :style="{ left: `calc(var(--pcal-rail) + (100% - var(--pcal-rail)) * ${(todayPct / 100).toFixed(5)})` }"
            aria-hidden="true"
          />

          <p v-if="!singleBands.length" class="ov-empty" style="margin: 8px 0">当前排期窗口暂无可定位的活动。</p>

          <div
            v-for="band in singleBands"
            :key="band.key"
            class="ov-pcal-band"
            :class="`is-${band.kind}`"
            data-render-block
          >
            <aside class="ov-pcal-rail">
              <span class="ov-pcal-rail-title">{{ band.label }}</span>
              <span class="ov-pcal-rail-idx">{{ band.indexText }}</span>
            </aside>
            <div class="ov-pcal-lanes">
              <div v-for="(lane, lIdx) in band.lanes" :key="lIdx" class="ov-pcal-lane">
                <template v-for="item in lane" :key="item.id">
                  <!-- Point Milestone -->
                  <article
                    v-if="item.isPoint"
                    class="ov-pcal-point"
                    :class="{ 'is-ended': item.isEnded, 'is-right': item.anchorRight }"
                    :style="item.anchorRight ? { right: `${Math.max(0, 100 - item.left)}%` } : { left: `${item.left}%` }"
                  >
                    <i class="ov-pcal-point-diamond" aria-hidden="true" />
                    <span class="ov-pcal-point-copy">
                      <strong>{{ item.name }}</strong>
                      <small>{{ item.dateText }}</small>
                    </span>
                  </article>

                  <!-- Range Poster Bar -->
                  <article
                    v-else
                    class="ov-pcal-bar"
                    :class="[
                      `is-${item.bandKind}`,
                      { 'is-ended': item.isEnded, 'is-short': item.isShort, 'has-art': !!item.art, 'has-checkin-strip': item.wideCheckin },
                    ]"
                    :style="{ left: `${item.left}%`, width: `${item.width}%` }"
                  >
                    <img
                      v-if="item.art"
                      :src="item.art"
                      alt=""
                      class="ov-pcal-bar-art"
                      aria-hidden="true"
                      @error="markFailed(item.art)"
                    />
                    <div v-if="item.art" class="ov-pcal-bar-scrim" aria-hidden="true" />

                    <!-- Rich SVG Theme Motifs when no cached banner image -->
                    <svg v-else-if="item.bandKind === 'gacha'" class="ov-pcal-motif" viewBox="0 0 120 72" aria-hidden="true">
                      <circle cx="88" cy="36" r="24" fill="none" stroke="currentColor" stroke-opacity="0.22" stroke-width="1.5" stroke-dasharray="4 3" />
                      <path d="M88 12 L93 31 L112 36 L93 41 L88 60 L83 41 L64 36 L83 31 Z" fill="currentColor" fill-opacity="0.2" />
                    </svg>
                    <svg v-else-if="item.bandKind === 'weapon'" class="ov-pcal-motif is-weapon" viewBox="0 0 120 72" aria-hidden="true">
                      <rect x="64" y="14" width="44" height="44" rx="8" fill="currentColor" fill-opacity="0.14" stroke="currentColor" stroke-opacity="0.32" stroke-width="1.5" />
                      <circle cx="86" cy="36" r="12" fill="none" stroke="currentColor" stroke-opacity="0.4" stroke-width="2" />
                      <circle cx="86" cy="36" r="4" fill="currentColor" fill-opacity="0.45" />
                    </svg>
                    <svg v-else-if="item.wideCheckin" class="ov-pcal-checkin-svg" viewBox="0 0 280 54" aria-hidden="true">
                      <rect v-for="d in 6" :key="d" :x="(d - 1) * 38" y="4" width="32" height="46" rx="6" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.22)" stroke-width="1.2" />
                      <line v-for="d in 6" :key="'l'+d" :x1="(d - 1) * 38 + 8" y1="18" :x2="(d - 1) * 38 + 24" y2="18" stroke="rgba(255,255,255,0.25)" stroke-width="2" stroke-linecap="round" />
                      <circle v-for="d in 6" :key="'c'+d" :cx="(d - 1) * 38 + 16" cy="33" r="5" fill="rgba(255,255,255,0.2)" />
                      <rect x="228" y="2" width="44" height="50" rx="7" fill="rgba(255,209,88,0.24)" stroke="#ffd158" stroke-width="1.6" />
                      <polygon points="250,15 253,23 261,24 255,29 257,37 250,33 243,37 245,29 239,24 247,23" fill="#ffd158" />
                    </svg>

                    <div v-if="!item.isShort" class="ov-pcal-bar-copy">
                      <strong class="ov-pcal-bar-name">{{ item.name }}</strong>
                      <div class="ov-pcal-bar-sub">
                        <span class="ov-pcal-bar-date">{{ item.dateText }}</span>
                        <span v-if="item.showTag" class="ov-pcal-bar-tag">签到</span>
                        <span v-else-if="item.showStatus" class="ov-pcal-bar-state" :class="{ 'is-live': item.status === '进行中' }">{{ item.status }}</span>
                      </div>
                    </div>
                  </article>

                  <!-- Short-bar label, placed beside the bar and bounded inside the track -->
                  <div
                    v-if="!item.isPoint && item.isShort"
                    class="ov-pcal-short-lbl"
                    :class="{ 'is-right': item.anchorRight, 'is-ended': item.isEnded }"
                    :style="item.shortLabelStyle"
                  >
                    <strong>{{ item.name }}</strong>
                    <span>{{ item.dateText }}</span>
                  </div>
                </template>
              </div>
            </div>
          </div>
        </div>

        <!-- Compact Unplaced Footer Bar -->
        <footer v-if="pendingList.length" class="ov-pcal-pending">
          <span class="ov-pcal-pending-lbl">时间待定 · {{ pendingList.length }} 项</span>
          <div class="ov-pcal-pending-pills">
            <span v-for="it in pendingList" :key="it.id" class="ov-pcal-pending-pill">
              {{ it.prefix }}{{ it.name }}
            </span>
          </div>
        </footer>
      </div>
    </section>

    <!-- Multi-game unified poster calendar (keeps one continuous ruler across all games) -->
    <div v-else class="ov-pcal-board is-multi-board">
      <div v-if="unifiedRange" class="ov-pcal-ruler-row">
        <div class="ov-pcal-rail-spacer">游戏 / 排期</div>
        <div class="ov-pcal-ruler-track">
          <div class="ov-pcal-months" aria-hidden="true">
            <span
              v-for="m in monthMarkers"
              :key="m.key"
              class="ov-pcal-month-tag"
              :style="{ left: `${m.left}%` }"
            >{{ m.label }}</span>
          </div>
          <div class="ov-pcal-ticks">
            <span
              v-for="tick in rulerTicks"
              :key="tick.key"
              class="ov-pcal-tick"
              :class="[`is-${tick.align}`, { 'is-weekend': tick.weekend }]"
              :style="tick.align === 'start' ? { left: '0%' } : tick.align === 'end' ? { right: '0%' } : { left: `${tick.pct}%` }"
            >{{ tick.day }}</span>
          </div>
          <div v-if="todayPillPct != null" class="ov-pcal-today-row">
            <span class="ov-pcal-today-pill" :style="{ left: `${todayPillPct}%` }">今天 {{ fmtMD(asOfMs) }}</span>
          </div>
        </div>
      </div>

      <div class="ov-pcal-bands-wrap">
        <div
          v-if="todayPct != null"
          class="ov-pcal-today-rail-line"
          :style="{ left: `calc(var(--pcal-rail) + (100% - var(--pcal-rail)) * ${(todayPct / 100).toFixed(5)})` }"
          aria-hidden="true"
        />

        <section
          v-for="band in multiBands"
          :key="band.key"
          class="ov-cal-group ov-pcal-band is-game-band"
          :data-skin="band.skin"
          :style="band.style"
          data-render-block
        >
          <aside class="ov-pcal-rail">
            <span class="ov-pcal-rail-title">{{ band.shortName }}</span>
            <span v-if="band.verTag" class="ov-pcal-rail-ver">{{ band.verTag }}</span>
            <span class="ov-pcal-rail-idx">{{ band.indexText }}</span>
          </aside>

          <div class="ov-pcal-lanes">
            <p class="ov-pcal-game-subbar">
              <strong>{{ band.title }}</strong>
              <span>{{ band.count }} 项在轴活动</span>
            </p>
            <p v-if="!band.lanes.length" class="ov-pcal-band-empty">当前排期窗口暂无可定位的活动。</p>
            <div v-for="(lane, lIdx) in band.lanes" :key="lIdx" class="ov-pcal-lane">
              <template v-for="item in lane" :key="item.id">
                <article
                  v-if="item.isPoint"
                  class="ov-pcal-point"
                  :class="{ 'is-ended': item.isEnded, 'is-right': item.anchorRight }"
                  :style="item.anchorRight ? { right: `${Math.max(0, 100 - item.left)}%` } : { left: `${item.left}%` }"
                >
                  <i class="ov-pcal-point-diamond" aria-hidden="true" />
                  <span class="ov-pcal-point-copy">
                    <strong>{{ item.name }}</strong>
                    <small>{{ item.dateText }}</small>
                  </span>
                </article>

                <article
                  v-else
                  class="ov-pcal-bar is-activity"
                  :class="{ 'is-ended': item.isEnded, 'is-short': item.isShort, 'has-art': !!item.art }"
                  :style="{ left: `${item.left}%`, width: `${item.width}%` }"
                >
                  <img
                    v-if="item.art"
                    :src="item.art"
                    alt=""
                    class="ov-pcal-bar-art"
                    aria-hidden="true"
                    @error="markFailed(item.art)"
                  />
                  <div v-if="item.art" class="ov-pcal-bar-scrim" aria-hidden="true" />
                  <div v-if="!item.isShort" class="ov-pcal-bar-copy">
                    <strong class="ov-pcal-bar-name">{{ item.name }}</strong>
                    <div class="ov-pcal-bar-sub">
                      <span class="ov-pcal-bar-date">{{ item.dateText }}</span>
                      <span v-if="item.showCategory && item.category" class="ov-pcal-bar-tag">{{ item.category }}</span>
                      <span v-if="item.showStatus" class="ov-pcal-bar-state" :class="{ 'is-live': item.status === '进行中' }">{{ item.status }}</span>
                    </div>
                  </div>
                </article>

                <div
                  v-if="!item.isPoint && item.isShort"
                  class="ov-pcal-short-lbl"
                  :class="{ 'is-right': item.anchorRight, 'is-ended': item.isEnded }"
                  :style="item.shortLabelStyle"
                >
                  <strong>{{ item.name }}</strong>
                  <span>{{ item.dateText }}</span>
                </div>
              </template>
            </div>
          </div>
        </section>
      </div>

      <footer v-if="pendingList.length" class="ov-pcal-pending">
        <span class="ov-pcal-pending-lbl">时间待定 · {{ pendingList.length }} 项</span>
        <div class="ov-pcal-pending-pills">
          <span v-for="it in pendingList" :key="it.id" class="ov-pcal-pending-pill">
            {{ it.prefix }}{{ it.name }}
          </span>
        </div>
      </footer>
    </div>
  </div>
</template>
