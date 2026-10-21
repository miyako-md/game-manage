<script setup>
import {computed} from 'vue'
import {skinOf} from '../game-themes.js'
// 帮助 lists the registry lines exactly as the notice carries them ("说明：指令"); 我的账号 lists
// one card per authorized account (an account title followed by its "字段：值" lines).
const props=defineProps({data:{type:Object,required:true},variant:{type:String,default:'help'}})
const GAMES={wuthering_waves:'鸣潮',nte:'异环',endfield:'终末地'}
const SLOTS={游戏:'换成 鸣潮 / 异环 / 终末地',精确名称:'写角色全名',实际绑定码:'写网站生成的绑定码'}
const split=text=>{const i=typeof text==='string'?text.indexOf('：'):-1;return i>0&&i<text.length-1&&i<=18?[text.slice(0,i),text.slice(i+1)]:null}
const gameOf=title=>Object.keys(GAMES).find(id=>title.startsWith(GAMES[id]))
const pad=n=>String(n).padStart(2,'0')
const groups=computed(()=>(props.data.sections||[]).map(section=>({title:section.title,game:section.game,skin:skinOf(section.game)||undefined,
 items:(section.items||[]).map(text=>{const kv=split(text);return kv?{desc:kv[0],tokens:kv[1].split(/\s+/).filter(Boolean).map(word=>({text:word,slot:word in SLOTS}))}:{text}})})))
const common=computed(()=>groups.value.filter(g=>!g.game))
const games=computed(()=>groups.value.filter(g=>g.game))
const slots=computed(()=>[...new Set(groups.value.flatMap(g=>g.items.flatMap(i=>(i.tokens||[]).filter(t=>t.slot).map(t=>t.text))))])
const accounts=computed(()=>(props.data.sections||[]).map(section=>{
 const cards=[],loose=[]
 for(const text of section.items||[]){
  const kv=split(text)
  if(!kv){const game=gameOf(text);cards.push({title:text,game,skin:skinOf(game)||undefined,fields:[]});continue}
  const field={label:kv[0],value:kv[1],tone:/重新授权|不可用|失效/.test(kv[1])?'warn':kv[1]==='已授权'?'ok':''}
  if(cards.length)cards.at(-1).fields.push(field);else loose.push(field)
 }
 return {title:section.title,cards,loose}
}))
</script>
<template>
 <div class="help-sheet" :class="'hs-'+variant">
  <template v-if="variant==='help'">
   <p v-if="slots.length" class="hs-legend"><span class="hs-legend-key">虚线框需替换</span><span v-for="slot in slots" class="hs-legend-item"><span class="hs-slot">{{slot}}</span>{{SLOTS[slot]}}</span></p>
   <section v-for="(g,i) in common" class="hs-group" data-render-block>
    <header class="hs-head"><span class="hs-index number">{{pad(i+1)}}</span><h2>{{g.title}}</h2><small>{{g.items.length}} 条</small></header>
    <ul class="hs-items">
     <li v-for="item in g.items" class="hs-item"><template v-if="item.tokens"><code class="hs-cmd"><span v-for="t in item.tokens" :class="{'hs-slot':t.slot}">{{t.text}}</span></code><span class="hs-desc">{{item.desc}}</span></template><span v-else class="hs-desc">{{item.text}}</span></li>
    </ul>
   </section>
   <div v-if="games.length" class="hs-games" :class="'count-'+games.length">
    <section v-for="g in games" class="hs-group hs-game" :data-skin="g.skin" data-render-block>
     <header class="hs-head"><span class="hs-mono">{{GAMES[g.game][0]}}</span><h2>{{g.title}}</h2><small>{{g.items.length}} 条</small></header>
     <ul class="hs-items">
      <li v-for="item in g.items" class="hs-item"><template v-if="item.tokens"><code class="hs-cmd"><span v-for="t in item.tokens" :class="{'hs-slot':t.slot}">{{t.text}}</span></code><span class="hs-desc">{{item.desc}}</span></template><span v-else class="hs-desc">{{item.text}}</span></li>
     </ul>
    </section>
   </div>
  </template>
  <template v-else>
   <section v-for="(s,i) in accounts" class="hs-group hs-accounts" data-render-block>
    <header class="hs-head"><span class="hs-index number">{{pad(i+1)}}</span><h2>{{s.title||'账号'}}</h2><small>{{s.cards.length}} 个账号</small></header>
    <dl v-if="s.loose.length" class="hs-fields"><div v-for="f in s.loose"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl>
    <div class="hs-account-grid">
     <article v-for="card in s.cards" class="hs-account" :data-skin="card.skin">
      <header><span class="hs-mono">{{card.game?GAMES[card.game][0]:'号'}}</span><h3>{{card.title}}</h3></header>
      <dl class="hs-fields"><div v-for="f in card.fields" :class="f.tone&&'is-'+f.tone"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl>
     </article>
    </div>
   </section>
  </template>
  <aside v-if="data.notices?.length" class="hs-notes" data-render-block><h2>使用说明</h2><p v-for="n in data.notices">{{n}}</p></aside>
 </div>
</template>
<style>
/* 帮助 / 我的账号: command cards on the sheet's skin. Game groups carry their own
   data-skin; skin.css keeps the shell surfaces and only swaps the accent (D3). */
.help-sheet { display: grid; gap: 18px; margin-top: 22px; }
.help-sheet .hs-group { background: var(--skin-surface); border: 1px solid var(--skin-line); border-radius: var(--skin-radius-card); padding: 18px 22px 20px; }
.help-sheet .hs-head { display: flex; align-items: center; gap: 12px; padding-bottom: 12px; margin-bottom: 14px; border-bottom: 1px solid rgba(var(--skin-tint-rgb), .16); }
.help-sheet .hs-head h2 { font-size: 23px; line-height: 1.35; font-weight: 700; color: var(--skin-ink); margin: 0; }
.help-sheet .hs-head small { margin-left: auto; font-size: 17px; color: var(--skin-muted); }
.help-sheet .hs-index { font-size: 18px; font-weight: 700; letter-spacing: .06em; color: var(--skin-accent); }
.help-sheet .hs-mono { display: inline-grid; place-items: center; width: 34px; height: 34px; flex: none; border-radius: var(--skin-radius-tile); background: var(--skin-accent); color: var(--skin-on-accent); font-size: 19px; font-weight: 700; }
.help-sheet .hs-items { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
.help-sheet .hs-item { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 6px 12px; min-width: 0; padding: 10px 14px; border-radius: var(--skin-radius-tile); background: rgba(var(--skin-tint-rgb), .06); border: 1px solid rgba(var(--skin-tint-rgb), .12); }
.help-sheet .hs-cmd { display: inline-flex; flex-wrap: wrap; gap: 6px; font-family: inherit; font-size: 20px; line-height: 1.4; font-weight: 700; color: var(--skin-accent); }
.help-sheet .hs-desc { font-size: 17px; line-height: 1.45; color: var(--skin-muted); }
.help-sheet .hs-slot { padding: 0 6px; border: 1px dashed var(--skin-line-strong); border-radius: 6px; color: var(--skin-ink); font-weight: 600; }
.help-sheet .hs-legend { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 18px; margin: 0; padding: 12px 18px; font-size: 17px; line-height: 1.5; color: var(--skin-muted); border: 1px solid rgba(var(--skin-tint-rgb), .16); border-radius: var(--skin-radius-tile); }
.help-sheet .hs-legend-key { color: var(--skin-accent); font-weight: 700; }
.help-sheet .hs-legend-item { display: inline-flex; align-items: center; gap: 8px; }
.help-sheet .hs-legend .hs-slot { font-size: 17px; }
.help-sheet .hs-games { display: grid; gap: 18px; grid-template-columns: repeat(var(--hs-cols, 1), minmax(0, 1fr)); }
.help-sheet .hs-games.count-2 { --hs-cols: 2; }
.help-sheet .hs-games.count-3 { --hs-cols: 3; }
.help-sheet .hs-game { box-shadow: inset 0 3px 0 var(--skin-accent); }
.help-sheet .hs-games:not(.count-1) .hs-items { grid-template-columns: minmax(0, 1fr); }
.help-sheet .hs-games:not(.count-1) .hs-item { flex-direction: column; align-items: flex-start; }
.help-sheet .hs-games:not(.count-1) .hs-group { padding: 16px 16px 18px; }
.help-sheet .hs-account-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.help-sheet .hs-account { padding: 16px 18px; border-radius: var(--skin-radius-tile); background: rgba(var(--skin-tint-rgb), .06); border: 1px solid rgba(var(--skin-tint-rgb), .16); border-left: 4px solid var(--skin-accent); }
.help-sheet .hs-account header { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.help-sheet .hs-account h3 { font-size: 21px; line-height: 1.4; font-weight: 700; color: var(--skin-ink); margin: 0; }
.help-sheet .hs-fields { display: grid; gap: 6px; margin: 0; }
.help-sheet .hs-fields > div { display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 6px 0; border-top: 1px solid rgba(var(--skin-tint-rgb), .12); }
.help-sheet .hs-fields dt { font-size: 18px; color: var(--skin-muted); }
.help-sheet .hs-fields dd { margin: 0; font-size: 18px; font-weight: 600; color: var(--skin-ink); text-align: right; }
.help-sheet .hs-fields .is-ok dd { color: var(--skin-accent); }
.help-sheet .hs-fields .is-warn dd { padding: 1px 10px; border-radius: var(--skin-radius-chip); background: #f0b54a; color: #1b1406; }
.help-sheet .hs-notes { display: grid; gap: 6px; padding: 16px 22px; border-radius: var(--skin-radius-card); border: 1px solid var(--skin-line); background: rgba(var(--skin-tint-rgb), .05); }
.help-sheet .hs-notes h2 { font-size: 19px; line-height: 1.4; font-weight: 700; color: var(--skin-accent); margin: 0 0 4px; }
.help-sheet .hs-notes p { font-size: 18px; line-height: 1.6; color: var(--skin-ink); margin: 0; }
</style>
