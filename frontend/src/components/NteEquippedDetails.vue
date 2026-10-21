<script setup>
import { displayNteText } from '../nte-display.js'
import { nteNamedIcon } from '../nte-icons.js'
import NteIcon from './NteIcon.vue'
defineProps({ role:{type:Object,required:true}, imageMode:{type:Boolean,default:false} })
const show = value => value == null || value === '' ? '未提供' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const rows = value => Array.isArray(value) ? value : []
// The source has no awakening name field: keep a short leading title when the
// text carries one, otherwise number the awakening; never show its effect text.
const awakenName = (effect, i) => { const title = displayNteText(effect).split(/[\n：:]/)[0].trim(); return !title || title.length > 12 || title.endsWith('待核验') ? `觉醒 ${i + 1}` : title }
// The upstream groups are only `core` and `pie`; the game calls them 空幕 and 驱动.
const GROUPS = [{ key:'core', label:'空幕' }, { key:'pie', label:'驱动' }]
// Real piece counts are unverified (the samples used 4 + 2): any count fills the grid in order,
// a group without pieces has no heading, and malformed entries are skipped rather than shown.
const parts = (suit, key) => rows(suit?.[key]).filter(item => item && typeof item === 'object')
const pieces = suit => GROUPS.reduce((n, g) => n + parts(suit, g.key).length, 0)
</script>
<template>
  <div class="nte-equipped-details" :class="{ 'is-image': imageMode }">
    <section><h4>觉醒</h4><p v-if="rows(role.awaken_effects).length">{{ rows(role.awaken_effects).map(awakenName).join(' · ') }}</p><p v-else>未提供</p></section>
    <section v-if="role.weapon"><h4>弧盘资料</h4><p>{{ show(role.weapon.name) }} · 突破 {{ show(role.weapon.breakthrough_level) }}</p><dl><div v-for="(p,i) in rows(role.weapon.properties)" :key="i"><dt>{{ show(p.name) }}</dt><dd>{{ show(p.value) }}</dd></div></dl></section>
    <section class="equipped-suit"><h4>已装备套装</h4>
      <template v-if="role.suit">
        <header class="nte-suit-head"><NteIcon :src="nteNamedIcon('sets', role.suit.name)" :name="show(role.suit.name)" size="large" /><div><strong>{{ show(role.suit.name) }}</strong><span class="nte-suit-count">激活数 <b>{{ show(role.suit.activation_count) }}</b></span></div></header>
        <template v-for="group in GROUPS" :key="group.key"><div v-if="parts(role.suit, group.key).length" class="nte-drive-group"><h5 class="nte-drive-group-title">{{ group.label }}<span>{{ parts(role.suit, group.key).length }} 件</span></h5>
          <div class="nte-drives"><article v-for="(item,i) in parts(role.suit, group.key)" :key="i" class="nte-drive">
            <h6 class="nte-drive-name">{{ show(item.name) }} · Lv{{ show(item.level) }}</h6>
            <template v-for="kind in [{ key:'main_properties', label:'主属性' }, { key:'properties', label:'副属性' }]" :key="kind.key"><p class="nte-drive-kind">{{ kind.label }}</p><dl v-if="rows(item[kind.key]).length"><div v-for="(p,j) in rows(item[kind.key])" :key="j"><dt>{{ show(p.name) }}</dt><dd>{{ show(p.value) }}</dd></div></dl><p v-else class="nte-drive-empty">未提供</p></template>
            <!-- D6: no built-in weights yet. The website shows the reserved slot; QQ images hide it (no height). -->
            <p class="nte-drive-score" :hidden="imageMode">评分待接入</p>
          </article></div></div></template>
        <p v-if="!pieces(role.suit)">驱动件 未提供</p>
      </template><p v-else>未提供</p></section>
  </div>
</template>
<style scoped>
.nte-equipped-details{display:grid;gap:10px;font-size:13px;line-height:1.6;overflow-wrap:anywhere}
/* Each block is a soft tile with a hairline inside the role's white card. */
.nte-equipped-details>section{margin:0;padding:12px 14px;border-radius:var(--radius-well);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.nte-equipped-details h4,.nte-equipped-details h5{margin:0 0 4px;color:var(--text-muted);font-size:12px;font-weight:500}
.nte-equipped-details p{margin:4px 0;white-space:pre-wrap}
.nte-equipped-details dl>div{display:flex;justify-content:space-between;gap:12px}
.nte-equipped-details dd{margin:0}
/* Set header: its icon, name and active count, like an echo set line. */
.nte-suit-head{display:flex;align-items:center;gap:12px;margin:6px 0 4px}
.nte-suit-head>div{display:grid;min-width:0}
.nte-suit-head strong{color:var(--text);font-size:15px;font-weight:600;line-height:22px}
.nte-suit-count{color:var(--text-muted);font-size:12px}
.nte-suit-count b{color:var(--text);font-weight:600}
/* One cell per piece, grouped 空幕 / 驱动; the grid follows .wuwa-echoes. */
.nte-drive-group{margin-top:10px}
.nte-drive-group-title{display:flex;align-items:baseline;gap:8px}
.nte-drive-group-title span{font-size:12px;font-variant-numeric:tabular-nums}
.nte-drives{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,240px),1fr));gap:10px}
.nte-drive{min-width:0;padding:12px 14px;border-radius:var(--radius-well);background:var(--card-bg);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.nte-drive-name{margin:0 0 4px;color:var(--text);font-size:14px;font-weight:600;line-height:20px}
.nte-drive-kind{margin:6px 0 0!important;color:var(--text-muted);font-size:12px}
.nte-drive dl{margin:0}
.nte-drive dl>div{padding:2px 0;border-bottom:1px solid var(--border)}
.nte-drive dt{color:var(--text-muted)}
.nte-drive dd{color:var(--text);font-weight:500;font-variant-numeric:tabular-nums}
.nte-drive-empty{color:var(--text-muted)}
.nte-drive-score{display:block;margin:8px 0 0!important;padding:4px 8px;border-radius:var(--radius-chip);background:var(--control-track);color:var(--text-muted);font-size:12px}
.nte-drive-score[hidden]{display:none}
</style>
