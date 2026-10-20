<script setup>
import { computed } from 'vue'
import { shipPercent, trustStage } from '../endfield-ship.js'
import { displayValue as display } from '../endfield-reports.js'
import EndfieldArtwork from './EndfieldArtwork.vue'
import AppIcon from './AppIcon.vue'
import RingGauge from './RingGauge.vue'
const props = defineProps({ operator: {type:Object,required:true}, imageMode:Boolean })
const stage = computed(() => trustStage(props.operator.trust_percent, props.operator.trust_level_name))
// The bot image lists each resident as one compact row; the website keeps the card.
const ring = computed(() => props.imageMode ? { size: 44, stroke: 5 } : { size: 54, stroke: 6 })
</script>
<template>
  <article class="ef-resident" :class="{ compact: imageMode }">
    <EndfieldArtwork role :operator-id="operator.id || operator.charId" :src="operator.avatar_url" :name="operator.name || operator.id || operator.charId || '干员'" />
    <div class="resident-copy"><h3>{{ operator.name || operator.id || operator.charId || '驻守干员' }}</h3>
      <div class="resident-meters">
        <!-- The rings are the picture; the native progress element stays as the accessible value. -->
        <div class="resident-meter mood"><RingGauge aria-hidden="true" :value="operator.mood_percent" :max="100" label="心情" :size="ring.size" :stroke="ring.stroke" color="var(--ef-vivid, var(--game-endfield-vivid))"><AppIcon name="sun" :size="15" /></RingGauge>
          <div class="meter-copy"><span class="meter-label">心情</span><strong>{{ shipPercent(operator.mood_percent) }}</strong></div>
          <progress v-if="operator.mood_percent != null" class="sr-only" :value="operator.mood_percent" max="100" :aria-label="`${operator.name || '驻守干员'}心情`" /><span v-else class="unknown-meter">{{ operator.mood_raw > 10000 ? '超出模型范围' : '观测值未知' }}</span></div>
        <div class="resident-meter trust"><RingGauge aria-hidden="true" :value="stage?.value" :max="100" :label="`信赖${stage ? stage.level + '阶段' : ''}`" :size="ring.size" :stroke="ring.stroke" color="var(--ef-vivid, var(--game-endfield-vivid))"><AppIcon name="shield" :size="15" /></RingGauge>
          <div class="meter-copy"><span class="meter-label">信赖 <small>{{ operator.trust_level_name || '阶段未知' }}</small></span><strong>{{ shipPercent(operator.trust_percent) }}</strong></div>
          <progress v-if="stage" class="sr-only" :value="stage.value" max="100" :aria-label="`${operator.name || '驻守干员'}信赖${stage.level}阶段进度`" /><span v-else class="unknown-meter">观测值未知</span></div>
      </div>
      <details v-if="!imageMode" class="resident-raw"><summary>查看原始观测值</summary><dl><div><dt>心情观测值</dt><dd>{{ display(operator.mood_raw) }}</dd></div><div><dt>信赖观测值</dt><dd>{{ display(operator.trust_raw) }}</dd></div></dl></details>
    </div>
  </article>
</template>
<style scoped>
.ef-resident{display:flex;gap:16px;align-items:flex-start;padding:14px;border-radius:var(--radius-tile);background:var(--surface-soft);min-width:0}
.ef-resident>.endfield-artwork{width:64px;height:72px;border-radius:var(--radius-control)}
.resident-copy{flex:1;min-width:0}
.resident-copy h3{font-size:15px;font-weight:600;line-height:1.5;letter-spacing:-.01em;overflow-wrap:anywhere;margin-bottom:8px}
.resident-meters{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 14px}
.resident-meter{position:relative;display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-width:0}
.resident-meter :deep(.ring-gauge){color:var(--text-muted)}
.meter-copy{display:grid;min-width:0}
.meter-label{display:inline-flex;gap:4px;align-items:baseline;flex-wrap:wrap;font-size:12px;line-height:1.5;color:var(--text-muted)}
.meter-label small{font-size:12px;color:var(--text-muted)}
.resident-meter strong{font-size:20px;line-height:26px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums;color:var(--text);white-space:nowrap}
/* An unobserved value keeps its place as a dashed note instead of a ring that could read as zero. */
.unknown-meter{flex-basis:100%;font-size:12px;color:var(--text-muted);border-top:1px dashed var(--border-strong);padding:5px 0 0;line-height:1.6}
.resident-raw{margin-top:8px;font-size:12px;color:var(--text-muted)}
.resident-raw summary{cursor:pointer;padding:6px 0;min-height:28px}
.resident-raw dl{display:flex;gap:6px 12px;flex-wrap:wrap;margin:6px 0 0}
.resident-raw dl>div{display:flex;gap:6px}
.resident-raw dd{margin:0;overflow-wrap:anywhere}
.resident-raw dt{font-weight:400}
.ef-resident.compact{display:grid;grid-template-columns:48px minmax(0,1fr);align-items:center;gap:12px;padding:8px 12px}
.ef-resident.compact>.endfield-artwork{width:48px;height:48px}
.ef-resident.compact .resident-copy{display:grid;grid-template-columns:minmax(0,5em) minmax(0,1fr);align-items:center;gap:10px}
.ef-resident.compact .resident-copy h3{margin:0}
.ef-resident.compact .resident-meter{flex-wrap:nowrap;gap:8px}
.ef-resident.compact .resident-meter strong{font-size:17px;line-height:22px}
.ef-resident.compact .unknown-meter{flex-basis:auto;border-top:0;padding:0}
@media(max-width:600px){.ef-resident{gap:12px;padding:12px}.ef-resident>.endfield-artwork{width:48px;height:58px}.resident-meters{grid-template-columns:1fr}}
</style>
