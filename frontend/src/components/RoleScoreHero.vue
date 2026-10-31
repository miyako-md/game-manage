<script setup>
import { computed } from 'vue'
import { gradeTier, scoreHero } from '../assessment-display.js'
// The role image's score card: a large grade and the set total, with whose weights they are.
// label names the set ("声骸评分", "驱动评分"); an absent assessment draws nothing.
const props = defineProps({ score: { type: Object, default: null }, label: { type: String, required: true } })
const hero = computed(() => scoreHero(props.score))
const tier = computed(() => gradeTier(hero.value.grade))
</script>
<template>
  <div v-if="hero.kind !== 'absent'" class="role-score-hero" :data-kind="hero.kind" :data-tier="tier ?? undefined">
    <p class="hero-grade" :aria-label="hero.grade ? `等级 ${hero.grade}` : undefined">{{ hero.grade || '—' }}</p>
    <div class="hero-body">
      <p class="rs-label">{{ label }}</p>
      <p v-if="hero.kind === 'scored'" class="hero-total"><b>{{ hero.value }}</b><span v-if="hero.max" class="hero-max"> / {{ hero.max }}</span></p>
      <template v-else-if="hero.kind === 'partial'"><p class="hero-total"><b>{{ hero.value }}</b></p><p class="rs-note">部分可评 · 已评 {{ hero.count }} 件</p></template>
      <p v-else-if="hero.kind === 'none'" class="rs-note">暂无默认权重</p>
      <p v-else class="rs-note">暂不可评分</p>
      <p v-if="hero.source" class="hero-source">{{ hero.source }}</p>
    </div>
  </div>
</template>
<style scoped>
.lab-sheet #render-content .role-score-hero{display:flex;align-items:center;gap:22px;min-width:0;padding:18px 22px;border-radius:var(--radius-tile,16px);background:rgba(var(--skin-tint-rgb,120,130,150),.08);box-shadow:inset 0 0 0 1px rgba(var(--skin-tint-rgb,120,130,150),.22)}
.lab-sheet #render-content .hero-grade{flex:none;display:grid;place-items:center;width:112px;height:112px;margin:0;border:4px solid var(--tier,#9aa3ad);border-radius:50%;color:var(--tier,#9aa3ad);font-size:52px!important;font-weight:800;line-height:1!important;letter-spacing:-.02em!important;font-variant-numeric:tabular-nums}
.lab-sheet #render-content .role-score-hero:not([data-kind="scored"]) .hero-grade{border-style:dashed;color:var(--skin-muted,#8a94a3);border-color:rgba(var(--skin-tint-rgb,120,130,150),.35)}
.lab-sheet #render-content .hero-body{display:grid;gap:4px;min-width:0}
.lab-sheet #render-content .hero-body p{margin:0}
.lab-sheet #render-content .rs-label{color:var(--skin-muted,var(--text-muted));font-size:var(--qq-min-text,17px)!important;letter-spacing:.08em!important}
.lab-sheet #render-content .hero-total{color:var(--skin-ink,var(--text));font-variant-numeric:tabular-nums;line-height:1.1!important}
.lab-sheet #render-content .hero-total b{color:var(--tier,#9aa3ad);font-size:46px!important;font-weight:800}
.lab-sheet #render-content .role-score-hero:not([data-kind="scored"]) .hero-total b{color:var(--skin-ink,var(--text));font-size:36px!important}
.lab-sheet #render-content .hero-max{color:var(--skin-muted,var(--text-muted));font-size:22px!important;font-weight:600}
.lab-sheet #render-content .rs-note{color:var(--skin-ink,var(--text));font-size:var(--qq-body,20px)!important;font-weight:600}
.lab-sheet #render-content .hero-source{color:var(--skin-muted,var(--text-muted));font-size:var(--qq-min-text,17px)!important;overflow-wrap:anywhere}
</style>
