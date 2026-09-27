<script setup>
import { computed } from 'vue'
import { parseBeijingTime } from '../calendar.js'
const props = defineProps({ rows: { type: Array, default: () => [] }, metric: String, label: String, min: { type: Number, default: 0 }, max: { type: Number, default: 100 }, unit: { type: String, default: '' } })
const ordered = computed(() => props.rows.filter(row => parseBeijingTime(row.date) != null).toSorted((a, b) => a.date.localeCompare(b.date)))
const points = computed(() => {
  const rows = ordered.value, first = parseBeijingTime(rows[0]?.date), last = parseBeijingTime(rows.at(-1)?.date)
  return rows.map(row => ({ ...row, value: row[props.metric],
    x: rows.length === 1 ? 240 : 36 + (parseBeijingTime(row.date) - first) / (last - first || 1) * 414,
    y: Number.isFinite(row[props.metric]) ? 138 - (row[props.metric] - props.min) / (props.max - props.min) * 112 : null,
  }))
})
const segments = computed(() => {
  const result = []; let segment = []
  for (const point of points.value) {
    if (point.y == null) { if (segment.length) result.push(segment); segment = [] }
    else segment.push(point)
  }
  if (segment.length) result.push(segment)
  return result
})
const known = computed(() => points.value.filter(p => p.y != null))
const fmt = value => Number.isFinite(value) ? `${Number(value.toFixed(1))}${props.unit}` : '未知'
</script>
<template>
  <section class="lol-trend">
    <div class="chart-heading"><h3>{{ label }}</h3><span>按北京时间 · 每日</span></div>
    <p v-if="metric === 'winrate'" class="chart-method">重开与未知胜负不计入胜率分母；对局数保留全部归档记录。</p>
    <svg v-if="known.length" viewBox="0 0 480 172" role="img" :aria-label="`${label}，${known.length} 个有效日期`">
      <g v-for="tick in [min, (min + max) / 2, max]" :key="tick" class="grid">
        <line x1="36" x2="450" :y1="138 - (tick-min)/(max-min)*112" :y2="138 - (tick-min)/(max-min)*112" />
        <text x="29" :y="142 - (tick-min)/(max-min)*112" text-anchor="end">{{ tick }}</text>
      </g>
      <polyline v-for="(segment, index) in segments" :key="index" :points="segment.map(p => `${p.x},${p.y}`).join(' ')" fill="none" class="trend-line" />
      <circle v-for="p in known" :key="p.date" :cx="p.x" :cy="p.y" r="3.5" class="trend-point"><title>{{ p.date }} · {{ fmt(p.value) }} · {{ p.games }} 场</title></circle>
      <text x="36" y="162">{{ ordered[0]?.date }}</text><text x="450" y="162" text-anchor="end">{{ ordered.at(-1)?.date }}</text>
    </svg>
    <p v-else class="chart-empty">暂无可计算的{{ label }}，缺失指标不会按 0 绘制。</p>
    <details v-if="ordered.length"><summary>查看每日数值</summary><div class="trend-table"><table><thead><tr><th>日期</th><th>对局</th><th>{{ label }}</th></tr></thead><tbody><tr v-for="row in ordered" :key="row.date"><td>{{ row.date }}</td><td>{{ row.games ?? '未知' }}</td><td>{{ fmt(row[metric]) }}</td></tr></tbody></table></div></details>
  </section>
</template>
<style scoped>
.chart-method { margin-top:8px;color:var(--text-muted);font-size:11px;line-height:1.7; }
.lol-trend{min-width:0;border:1px solid var(--border);border-radius:12px;padding:18px;background:var(--card-bg)}.chart-heading{display:flex;flex-wrap:wrap;gap:8px;justify-content:space-between;align-items:baseline}.chart-heading h3{font-size:14px;margin:0}.chart-heading span,summary{font-size:11px;color:var(--text-muted)}svg{width:100%;display:block;margin:14px 0 4px;overflow:visible}svg text{fill:var(--text-muted);font-size:10px}.grid line{stroke:var(--border);stroke-dasharray:3 4}.trend-line{stroke:var(--accent);stroke-width:2}.trend-point{fill:var(--accent);stroke:var(--card-bg);stroke-width:1.5}.chart-empty{min-height:140px;display:grid;align-content:center;color:var(--text-muted);font-size:13px;line-height:1.8}summary{cursor:pointer}.trend-table{max-height:190px;overflow:auto;margin-top:10px}table{width:100%;border-collapse:collapse;font-size:11px}th,td{text-align:left;padding:7px;border-bottom:1px solid var(--border)}
</style>
