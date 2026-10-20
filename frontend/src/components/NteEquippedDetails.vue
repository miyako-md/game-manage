<script setup>
import { displayNteText } from '../nte-display.js'
defineProps({ role:{type:Object,required:true}, imageMode:{type:Boolean,default:false} })
const show = value => value == null || value === '' ? '未提供' : typeof value === 'object' ? JSON.stringify(value) : String(value)
const rows = value => Array.isArray(value) ? value : []
// The source has no awakening name field: keep a short leading title when the
// text carries one, otherwise number the awakening; never show its effect text.
const awakenName = (effect, i) => { const title = displayNteText(effect).split(/[\n：:]/)[0].trim(); return !title || title.length > 12 || title.endsWith('待核验') ? `觉醒 ${i + 1}` : title }
</script>
<template>
  <div class="nte-equipped-details">
    <section><h4>觉醒</h4><p v-if="rows(role.awaken_effects).length">{{ rows(role.awaken_effects).map(awakenName).join(' · ') }}</p><p v-else>未提供</p></section>
    <section v-if="role.weapon"><h4>弧盘资料</h4><p>{{ show(role.weapon.name) }} · 突破 {{ show(role.weapon.breakthrough_level) }}</p><dl><div v-for="(p,i) in rows(role.weapon.properties)" :key="i"><dt>{{ show(p.name) }}</dt><dd>{{ show(p.value) }}</dd></div></dl></section>
    <section class="equipped-suit"><h4>已装备套装</h4><template v-if="role.suit"><p>{{ show(role.suit.name) }} · 激活数 {{ show(role.suit.activation_count) }}</p><div class="equipped-parts"><template v-for="group in ['core','pie']" :key="group"><section v-for="(item,i) in rows(role.suit[group])" :key="group+i" class="equipped-part"><h5>{{ show(item.name) }} · Lv{{ show(item.level) }}</h5><dl v-for="kind in ['main_properties','properties']" :key="kind"><div v-for="(p,j) in rows(item[kind])" :key="j"><dt>{{ kind==='main_properties'?'主':'副' }} · {{ show(p.name) }}</dt><dd>{{ show(p.value) }}</dd></div></dl></section></template></div></template><p v-else>未提供</p></section>
  </div>
</template>
<style scoped>
.nte-equipped-details{display:grid;gap:10px;font-size:13px;line-height:1.6;overflow-wrap:anywhere}
/* Each block is a soft tile with a hairline inside the role's white card. */
.nte-equipped-details>section{margin:0;padding:12px 14px;border-radius:var(--radius-well);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.nte-equipped-details section section{margin-top:8px;padding:0;background:none;box-shadow:none}
.nte-equipped-details h4,.nte-equipped-details h5{margin:0 0 4px;color:var(--text-muted);font-size:12px;font-weight:500}
.nte-equipped-details p{margin:4px 0;white-space:pre-wrap}
.nte-equipped-details dl>div{display:flex;justify-content:space-between;gap:12px}
.nte-equipped-details dd{margin:0}
</style>
