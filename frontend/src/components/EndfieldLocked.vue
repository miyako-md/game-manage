<script setup>
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import RingGauge from './RingGauge.vue'

// The profile tabs need a connected Skland role. Until then each shows a muted outline of what will
// appear: the same cards and chart shapes with no values, so nothing here can be read as data.
// The cloud page explains the missing authorization in EndfieldAuthGuide and hides this note.
const props = defineProps({ section: { type: String, default: 'operators' }, note: { type: Boolean, default: true } })
const TILES = {
  operators: ['已记录干员', '来源干员数', '已知等级均值', '最高已知等级'],
  honor: ['来源成就总数', '已记录奖章'],
  challenges: ['已记录'],
  ship: ['房间数', '有驻守记录的房间', '驻守席位记录'],
}
const PREVIEWS = {
  operators: { note: '稀有度与精英阶段分布、每名干员的等级与配装', cards: [
    { span: 5, title: '全员练度', kind: 'tiles', cols: 2 }, { span: 4, title: '稀有度分布', kind: 'ring' }, { span: 3, title: '精英阶段', kind: 'stack' }, { span: 12, title: '6★ 干员', kind: 'portraits' }] },
  regions: { note: '各地区调度券、据点与区域收集进度', cards: [{ span: 12, title: '地区建设', kind: 'region' }] },
  ship: { note: '各舱室驻守干员的心情与信赖', cards: [
    { span: 12, title: '帝江号', kind: 'tiles', cols: 3 }, { span: 6, title: '舱室', kind: 'resident' }, { span: 6, title: '舱室', kind: 'resident' }] },
  honor: { note: '已获得的奖章、分类与镀层', cards: [
    { span: 8, title: '光荣之路', kind: 'tiles', cols: 2 }, { span: 4, title: '奖章分类', kind: 'ring' }, { span: 12, title: '最近获得', kind: 'medals' }] },
  challenges: { note: '战争、丰碑与危机三类挑战记录', cards: [
    { span: 12, title: '挑战记录', kind: 'tiles', cols: 1 }, { span: 12, title: '各期星数', kind: 'bars' }] },
}
const preview = computed(() => PREVIEWS[props.section] || PREVIEWS.operators)
const tiles = computed(() => TILES[props.section] || TILES.operators)
</script>

<template>
  <section class="ef-locked" aria-label="连接后可查看的内容">
    <p v-if="note" class="locked-note" role="note"><AppIcon name="shield" :size="16" />连接森空岛并选择角色后，这里显示{{ preview.note }}。</p>
    <div class="locked-grid" aria-hidden="true">
      <div v-for="(card, index) in preview.cards" :key="index" class="locked-card" :style="{ '--span': card.span }">
        <h2 class="locked-title">{{ card.title }}</h2>
        <ul v-if="card.kind === 'tiles'" class="locked-tiles" :style="{ '--cols': card.cols }"><li v-for="label in tiles" :key="label"><span>{{ label }}</span><b>—</b></li></ul>
        <div v-else-if="card.kind === 'ring'" class="locked-ring"><RingGauge :value="null" :max="null" label="" :size="112" :stroke="14" color="var(--game-vivid, var(--game-endfield-vivid))"><b>—</b></RingGauge><div class="locked-lines"><i></i><i></i><i></i></div></div>
        <div v-else-if="card.kind === 'stack'" class="locked-stack"><i class="locked-bar"></i><div class="locked-lines"><i></i><i></i><i></i><i></i></div></div>
        <div v-else-if="card.kind === 'portraits'" class="locked-rail"><div v-for="n in 6" :key="n" class="locked-portrait"><i></i><span></span><span></span></div></div>
        <div v-else-if="card.kind === 'medals'" class="locked-rail small"><div v-for="n in 8" :key="n" class="locked-portrait small"><i></i><span></span></div></div>
        <div v-else-if="card.kind === 'region'" class="locked-region">
          <div class="locked-tile"><RingGauge :value="null" :max="null" label="" :size="96" :stroke="11" color="var(--game-vivid, var(--game-endfield-vivid))"><b>—</b></RingGauge></div>
          <div class="locked-areas"><div v-for="n in 3" :key="n" class="locked-tile"><span class="locked-line short"></span><template v-for="m in 4" :key="m"><span class="locked-line"></span><i class="locked-bar thin"></i></template></div></div>
        </div>
        <div v-else-if="card.kind === 'resident'" class="locked-residents"><div v-for="n in 2" :key="n" class="locked-resident"><i class="locked-avatar"></i><div><span class="locked-line short"></span><div class="locked-pair"><RingGauge :value="null" :max="null" label="" :size="48" :stroke="6" color="var(--game-vivid, var(--game-endfield-vivid))" /><RingGauge :value="null" :max="null" label="" :size="48" :stroke="6" color="var(--game-vivid, var(--game-endfield-vivid))" /></div></div></div></div>
        <div v-else class="locked-bars"><i v-for="h in [38, 64, 48, 80, 56, 30]" :key="h" :style="{ height: `${h}%` }"></i></div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* An outline of what will appear: dashed cards, flat grey fills, and a dash where a number will be. */
.ef-locked { display:grid; gap:14px; min-width:0; }
.locked-note { display:flex; align-items:center; gap:8px; margin:0; padding:0 4px; color:var(--text-muted); font-size:13px; line-height:1.6; }
.locked-note svg { flex:0 0 auto; color:var(--game-accent,var(--game-endfield)); }
.locked-grid { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:16px; }
.locked-card { grid-column:span var(--span,12); min-width:0; padding:20px; border:1px dashed var(--border-strong); border-radius:var(--radius-card); background:var(--panel-bg); }
.locked-title { margin:0 0 14px; color:var(--text-muted); font-size:16px; line-height:24px; font-weight:600; letter-spacing:-.02em; }
.locked-tiles { display:grid; grid-template-columns:repeat(var(--cols,2),minmax(0,1fr)); gap:10px; max-width:calc(var(--cols,2) * 320px); }
.locked-tiles li { display:grid; gap:2px; padding:12px 14px; border:1px solid var(--border); border-radius:var(--radius-well); background:var(--card-bg); }
.locked-tiles span { color:var(--text-muted); font-size:12px; line-height:18px; }
.locked-tiles b, .locked-ring b { color:var(--text-faint); font-size:26px; line-height:32px; font-weight:550; letter-spacing:-.03em; }
.locked-ring { display:flex; align-items:center; gap:18px; flex-wrap:wrap; }
.locked-lines { display:grid; gap:10px; flex:1 1 90px; min-width:80px; }
.locked-lines i, .locked-line { display:block; height:8px; border-radius:6px; background:var(--track); }
.locked-lines i:nth-child(2), .locked-line.short { width:62%; }
.locked-lines i:nth-child(3) { width:78%; }
.locked-stack { display:grid; gap:14px; }
.locked-bar { display:block; height:14px; border-radius:6px; background:var(--track); }
.locked-bar.thin { height:8px; }
.locked-rail { display:flex; gap:12px; overflow:hidden; }
.locked-portrait { flex:0 0 auto; display:grid; gap:8px; align-content:start; width:150px; padding:10px 10px 14px; border:1px solid var(--border); border-radius:var(--radius-tile); background:var(--card-bg); }
.locked-portrait i { display:block; height:150px; border-radius:var(--radius-well); background:var(--control-track); }
.locked-portrait span { display:block; height:8px; border-radius:6px; background:var(--track); }
.locked-portrait span:last-child { width:60%; }
.locked-portrait.small { width:104px; }
.locked-portrait.small i { height:64px; }
.locked-region { display:grid; grid-template-columns:auto minmax(0,1fr); gap:12px; }
.locked-tile { display:grid; gap:10px; align-content:center; justify-items:center; padding:16px; border:1px solid var(--border); border-radius:var(--radius-tile); background:var(--card-bg); }
.locked-areas { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }
.locked-areas .locked-tile { justify-items:stretch; }
.locked-residents { display:grid; gap:10px; }
.locked-resident { display:flex; gap:14px; align-items:center; padding:12px; border:1px solid var(--border); border-radius:var(--radius-tile); background:var(--card-bg); }
.locked-avatar { flex:0 0 auto; width:56px; height:64px; border-radius:var(--radius-control); background:var(--control-track); }
.locked-resident > div { display:grid; gap:8px; min-width:0; flex:1; }
.locked-pair { display:flex; gap:12px; }
.locked-bars { display:flex; align-items:flex-end; justify-content:space-around; height:96px; border-bottom:1px solid var(--border); }
.locked-bars i { width:24px; border-radius:4px 4px 0 0; background:var(--track); }
@media (max-width:900px) { .locked-card { grid-column:1 / -1; } }
@media (max-width:600px) { .locked-card { padding:16px; border-radius:22px; } .locked-region { grid-template-columns:1fr; } .locked-portrait { width:128px; } }
</style>
