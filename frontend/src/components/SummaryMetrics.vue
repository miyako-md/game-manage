<script setup>
import AppIcon from './AppIcon.vue'
defineProps({ metrics: { type: Array, default: () => [] }, compact: Boolean, rows: Boolean })
const display = value => value == null || value === '' || (typeof value === 'number' && !Number.isFinite(value)) ? '未知' : value
const ratio = metric => Object.hasOwn(metric, 'current')
const measurable = metric => Number.isFinite(metric.current) && metric.current >= 0 && Number.isFinite(metric.total) && metric.total > 0
const percentage = metric => Math.min(100, Math.max(0, metric.current / metric.total * 100))
</script>

<template>
  <div class="summary-metrics" :class="{ compact, rows }">
    <div v-for="metric in metrics" :key="metric.label" class="summary-metric" :class="{ measured: measurable(metric) }">
      <div class="metric-symbol" :class="{ ring: measurable(metric) }" :style="measurable(metric) ? { '--fill': `${percentage(metric)}%` } : {}" aria-hidden="true">
        <AppIcon :name="metric.icon || (ratio(metric) ? 'refresh' : 'chart')" :size="19" />
      </div>
      <div class="metric-copy"><span>{{ metric.label }}</span>
        <strong v-if="ratio(metric)">{{ display(metric.current) }} <small>/ {{ display(metric.total) }}</small></strong>
        <strong v-else>{{ display(metric.value) }}</strong>
        <p v-if="metric.note">{{ metric.note }}</p>
      </div>
      <progress v-if="measurable(metric)" :value="metric.current" :max="metric.total" :aria-label="metric.label" />
      <div v-else-if="ratio(metric)" class="unknown-track" aria-hidden="true" />
    </div>
  </div>
</template>

<style scoped>
.summary-metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(180px,100%),1fr));gap:12px;margin:20px 0 6px}
.summary-metric{display:grid;grid-template-columns:44px minmax(0,1fr);align-content:start;align-items:center;gap:12px;padding:16px;background:linear-gradient(125deg,var(--accent-dim),transparent 85%);border:1px solid var(--border-soft);border-radius:10px;min-width:0}
.metric-symbol{height:44px;width:44px;border-radius:12px;display:grid;place-items:center;color:var(--accent);background:var(--accent-dim);border:1px solid var(--border)}
.metric-symbol.ring{border:0;border-radius:50%;background:conic-gradient(var(--accent) var(--fill),var(--border) 0);position:relative}
.ring:before{content:'';position:absolute;inset:4px;border-radius:50%;background:var(--card-bg)}.ring svg{position:relative}
.metric-copy{min-width:0}.metric-copy>span{display:block;color:var(--text-muted);font-size:11px;margin-bottom:7px}.metric-copy>strong{display:block;font-size:23px;font-weight:600;line-height:1.25;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}.metric-copy small{font-size:13px;font-weight:400;color:var(--text-muted)}.metric-copy p{font-size:10px;color:var(--text-muted);margin-top:7px;line-height:1.6}
progress,.unknown-track{grid-column:1/-1;width:100%;height:5px;border:0;border-radius:4px;overflow:hidden;background:var(--border);appearance:none}progress::-webkit-progress-bar{background:var(--border)}progress::-webkit-progress-value{background:linear-gradient(90deg,var(--accent),var(--mint,var(--accent)));border-radius:4px}progress::-moz-progress-bar{background:var(--accent);border-radius:4px}.unknown-track{background:repeating-linear-gradient(110deg,var(--border),var(--border) 4px,transparent 4px,transparent 8px)}
.compact{grid-template-columns:repeat(auto-fit,minmax(min(145px,100%),1fr))}.compact .summary-metric{padding:12px;gap:9px}.compact .metric-copy>strong{font-size:19px}
.rows{grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr))}.rows .summary-metric{grid-template-columns:32px minmax(0,1fr);padding:12px;gap:9px}.rows .metric-symbol{width:32px;height:32px}.rows .metric-copy{display:flex;align-items:baseline;justify-content:space-between;gap:6px;flex-wrap:wrap}.rows .metric-copy>span{margin:0;flex:1;min-width:95px}.rows .metric-copy strong{font-size:17px}.rows .metric-copy p{width:100%;margin:0}.rows progress,.rows .unknown-track{margin-top:2px}
@media(max-width:500px){.summary-metrics{grid-template-columns:1fr}.compact{grid-template-columns:repeat(2,minmax(0,1fr))}.compact .summary-metric{grid-template-columns:1fr}.summary-metric{padding:13px}}
</style>
