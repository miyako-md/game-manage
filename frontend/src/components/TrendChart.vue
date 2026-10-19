<script setup>
import { computed, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import { smoothPath } from '../chart-math.js'

const props = defineProps({
  // [{ label, value }] in time order; unknown values leave a gap in the data, not a zero.
  points: { type: Array, default: () => [] },
  label: { type: String, required: true },
  unit: { type: String, default: '' },
  height: { type: Number, default: 96 },
  color: { type: String, default: 'var(--game-vivid, var(--chart-1))' },
  area: { type: Boolean, default: true },
  // A fixed domain (0–100 for a rate) keeps small swings from looking dramatic.
  min: { type: Number, default: null },
  max: { type: Number, default: null },
  digits: { type: Number, default: 1 },
})
const gradient = `trend-${useId()}`
const plot = ref(null)
const width = ref(320)
const inset = 6
const known = computed(() => props.points.map((point, i) => ({ ...point, i })).filter(point => typeof point.value === 'number' && Number.isFinite(point.value)))
const domain = computed(() => {
  const values = known.value.map(point => point.value)
  let low = props.min ?? Math.min(...values), high = props.max ?? Math.max(...values)
  if (!(high > low)) { low -= 1; high += 1 }
  return [low, high]
})
const coords = computed(() => {
  const [low, high] = domain.value, span = Math.max(1, props.points.length - 1)
  return known.value.map(point => ({
    ...point,
    x: props.points.length > 1 ? inset + (point.i / span) * (width.value - inset * 2) : width.value / 2,
    y: inset + (1 - (point.value - low) / (high - low)) * (props.height - inset * 2),
  }))
})
const line = computed(() => smoothPath(coords.value))
const fill = computed(() => coords.value.length > 1 ? `${line.value}L${coords.value.at(-1).x},${props.height}L${coords.value[0].x},${props.height}Z` : '')
const active = ref(-1)
const shown = computed(() => coords.value[active.value >= 0 ? active.value : coords.value.length - 1])
const format = value => `${value.toLocaleString('zh-CN', { maximumFractionDigits: props.digits })}${props.unit}`

function pointAt(event) {
  if (!coords.value.length || !plot.value?.getBoundingClientRect) return
  const x = event.clientX - plot.value.getBoundingClientRect().left
  active.value = coords.value.reduce((best, point, i) => Math.abs(point.x - x) < Math.abs(coords.value[best].x - x) ? i : best, 0)
}
function step(event) {
  const move = { ArrowLeft: -1, ArrowRight: 1 }[event.key]
  if (!move || !coords.value.length) return
  event.preventDefault()
  const from = active.value >= 0 ? active.value : coords.value.length - 1
  active.value = Math.max(0, Math.min(coords.value.length - 1, from + move))
}

let resizer = null
onMounted(() => {
  const el = plot.value
  if (!el?.getBoundingClientRect || typeof ResizeObserver !== 'function') return
  resizer = new ResizeObserver(() => { if (el.clientWidth) width.value = el.clientWidth })
  resizer.observe(el)
})
onBeforeUnmount(() => resizer?.disconnect())
</script>

<template>
  <figure class="trend-chart" :style="{ '--plot-height': `${height}px`, '--series': color }">
    <div
      ref="plot" class="trend-plot" tabindex="0"
      :aria-label="`${label}：${known.length} 个数据点，最新 ${shown ? format(shown.value) : '未知'}`"
      @pointermove="pointAt" @pointerleave="active = -1" @keydown="step" @blur="active = -1"
    >
      <svg :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
        <defs><linearGradient :id="gradient" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--series)" stop-opacity=".22" /><stop offset="1" stop-color="var(--series)" stop-opacity="0" /></linearGradient></defs>
        <path v-if="area && fill" class="trend-area" :d="fill" :fill="`url(#${gradient})`" />
        <path v-if="coords.length > 1" class="trend-line t-draw" :d="line" pathLength="1" />
      </svg>
      <template v-if="shown">
        <span v-if="active >= 0" class="trend-cursor" :style="{ left: `${shown.x}px` }" aria-hidden="true"></span>
        <span class="trend-dot" :style="{ left: `${shown.x}px`, top: `${shown.y}px` }" aria-hidden="true"></span>
        <span class="trend-tip" :class="{ start: shown.x < width * .25, end: shown.x > width * .75, below: shown.y < 36 }" :style="{ left: `${shown.x}px`, top: `${shown.y}px` }" aria-hidden="true"><b>{{ format(shown.value) }}</b><small>{{ shown.label }}</small></span>
      </template>
    </div>
    <ol class="sr-only"><li v-for="point in known" :key="point.i">{{ point.label }}：{{ format(point.value) }}</li></ol>
  </figure>
</template>

<style scoped>
.trend-chart { margin:0; min-width:0; }
.trend-plot { position:relative; height:var(--plot-height); border-radius:var(--radius-control); touch-action:pan-y; }
.trend-plot:focus-visible { outline:2px solid var(--accent); outline-offset:4px; }
.trend-plot svg { display:block; width:100%; height:100%; overflow:visible; }
.trend-line { fill:none; stroke:var(--series); stroke-width:2; stroke-linecap:round; stroke-linejoin:round; stroke-dasharray:1; animation:trend-draw 1100ms var(--ease-smooth-out) backwards; }
@keyframes trend-draw { from { stroke-dashoffset:1; } }
.trend-cursor { position:absolute; top:0; bottom:0; width:1px; margin-left:-.5px; background:var(--border-strong); pointer-events:none; }
/* End dot: 8px in the series colour with a 2px ring in the card colour. */
.trend-dot { position:absolute; width:12px; height:12px; margin:-6px 0 0 -6px; border:2px solid var(--card-bg); border-radius:50%; background:var(--series); pointer-events:none; transition:left var(--duration-quick) var(--ease-smooth-out), top var(--duration-quick) var(--ease-smooth-out); }
.trend-tip { position:absolute; z-index:3; display:grid; justify-items:center; gap:1px; transform:translate(-50%, calc(-100% - 12px)); padding:4px 8px; border-radius:var(--radius-control); background:var(--text); color:var(--bg); white-space:nowrap; pointer-events:none; line-height:1.25; transition:left var(--duration-quick) var(--ease-smooth-out), top var(--duration-quick) var(--ease-smooth-out); }
.trend-tip.start { transform:translate(-12px, calc(-100% - 12px)); justify-items:start; }
.trend-tip.end { transform:translate(calc(-100% + 12px), calc(-100% - 12px)); justify-items:end; }
/* A point near the top takes its label below, so it never covers what sits above the chart. */
.trend-tip.below { transform:translate(-50%, 12px); }
.trend-tip.below.start { transform:translate(-12px, 12px); }
.trend-tip.below.end { transform:translate(calc(-100% + 12px), 12px); }
.trend-tip b { font-size:13px; font-weight:600; }
.trend-tip small { font-size:11px; opacity:.72; }
</style>
