<script setup>
import {gameVars} from '../dashboard.js'
import {skinOf} from '../game-themes.js'
import CloudCalendar from './CloudCalendar.vue'
import NteCommunityGacha from '../components/NteCommunityGacha.vue'
import EndfieldGachaPanel from '../components/EndfieldGachaPanel.vue'
import EndfieldChallenges from '../components/EndfieldChallenges.vue'
import NteAssetsPanel from '../components/NteAssetsPanel.vue'
import WuwaGuideVisual from '../components/WuwaGuideVisual.vue'
import NteGuideVisual from '../components/NteGuideVisual.vue'
import EndfieldArtwork from '../components/EndfieldArtwork.vue'
import {guideLines} from './guide-presentation.js'
defineProps({panel:Object})
const percent=v=>v==null?'—':Math.round(v)+'%'
const ringStyle=p=>({'--pct':(p??0)+'%'})
</script>
<template>
 <section class="block" :class="['kind-'+panel.type,{'long-title':panel.title.length>4}]" :data-kind="panel.type" :style="(panel.gameId||panel.game)?gameVars(panel.gameId||panel.game):undefined" :data-skin="skinOf(panel.gameId||panel.game)||undefined">
  <header class="block-cap"><span class="chapter-mark" aria-hidden="true"></span><h2>{{panel.title}}</h2></header>
  <div class="block-content">
   <p v-if="panel.caption" class="caption">{{panel.caption}}</p>
   <p v-for="n in panel.notices||[]" class="status-note">{{n}}</p>
   <div v-if="panel.type==='cloud_gacha'" class="cloud-gacha"><NteCommunityGacha :snap="panel.snapshot" :roles="panel.roles" image-mode /></div>
   <div v-else-if="panel.type==='cloud_teams'" class="cloud-teams render-image"><NteAssetsPanel capability="teams" :snap="panel.snapshot" :roles="panel.roles" image-mode /></div>
   <div v-else-if="panel.type==='cloud_endfield_gacha'" class="cloud-endfield cloud-gacha render-image"><EndfieldGachaPanel :snap="panel.snapshot" image-mode /></div>
   <div v-else-if="panel.type==='cloud_endfield_challenge'" class="cloud-endfield render-image"><EndfieldChallenges :kind="panel.report.kind" :value="{report:panel.report}" image-mode /></div>
   <CloudCalendar v-else-if="panel.type==='cloud_calendar'" :events="panel.events" :snapshots="panel.snapshots" :as-of="panel.asOf" :full="panel.full" />
   <div v-else-if="panel.type==='upcoming'" class="upcoming-list">
    <article v-for="r in panel.rows" class="upcoming-row" :class="{'has-game':r.game}" :style="r.game?gameVars(r.gameId):undefined" :data-skin="r.game&&skinOf(r.gameId)||undefined"><span v-if="r.game" class="upcoming-game">{{r.game}}</span><div class="upcoming-name"><h3>{{r.name}}</h3><small>{{r.category}}</small></div><span class="upcoming-time number">{{r.time}}</span><strong class="upcoming-countdown" :class="{urgent:r.urgent}">{{r.countdown}}</strong></article>
    <p v-if="!panel.rows.length" class="upcoming-empty">{{panel.empty}}</p>
    <p v-if="panel.note" class="upcoming-note">{{panel.note}}</p>
   </div>
   <template v-else-if="panel.type==='metrics'">
    <div v-if="panel.metrics?.length" class="metric-grid">
     <div v-for="m in panel.metrics" class="metric" :class="{'has-ring':m.pct!=null}">
      <div v-if="m.pct!=null" class="ring" :style="ringStyle(m.pct)" role="img" :aria-label="m.label+' '+percent(m.pct)"><span class="ring-center">{{percent(m.pct)}}</span></div>
      <div class="metric-copy"><span class="metric-label">{{m.label}}</span><div class="metric-values"><strong class="number">{{m.cur}}</strong><span v-if="m.max!==null" class="metric-max">/ {{m.max}}</span></div><small v-if="m.extra">{{m.extra}}</small></div>
     </div>
    </div>
    <dl v-if="panel.fields?.length" class="attribute-grid"><div v-for="f in panel.fields" :class="{'long-label':f.label.length>9}"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl>
   </template>
   <dl v-else-if="panel.type==='attributes'" class="attribute-grid"><div v-for="f in panel.fields" :class="{'long-label':f.label.length>9||f.value.length>10}"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl>
   <div v-else-if="panel.type==='bars'" class="bar-list">
    <div v-for="b in panel.bars" class="bar-row"><div class="bar-info"><strong>{{b.label}}</strong><small v-if="b.extra">{{b.extra}}</small></div><div class="bar-track"><i :style="{width:(b.pct??0)+'%'}" :class="{'no-max':b.pct==null}"></i></div><span class="bar-value number">{{b.cur}}<small v-if="b.max!==null"> / {{b.max}}</small></span></div>
   </div>
   <table v-else-if="panel.type==='table'" class="data-table" :class="{'four-cols':panel.headers.length===4}"><thead><tr><th v-for="h in panel.headers">{{h}}</th></tr></thead><tbody><tr v-for="row in panel.rows"><td v-for="cell in row">{{cell}}</td></tr><tr v-if="!panel.rows.length"><td :colspan="panel.headers.length">暂无已挑战记录</td></tr></tbody></table>
   <div v-else-if="panel.type==='portraits'" class="portrait-grid"><article v-for="r in panel.roles" class="portrait-card" :class="{'no-portrait':!r.image}"><img v-if="r.image" :src="r.image" alt="" /><div><h3 class="role-name">{{r.name}}</h3><p>{{r.meta}}</p></div></article></div>
   <div v-else-if="panel.type==='equipment'" class="equipment-grid"><article v-for="e in panel.entries" class="equip-card"><header><img v-if="e.image" :src="e.image" alt="" /><div><h3>{{e.name}}</h3><div class="equip-meta"><span v-for="m in e.meta">{{m}}</span></div></div></header><h4 v-if="e.subfields?.length">主词条</h4><dl class="equip-attrs"><div v-for="f in e.fields"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl><template v-if="e.subfields?.length"><h4>副词条</h4><dl class="equip-attrs"><div v-for="f in e.subfields"><dt>{{f.label}}</dt><dd>{{f.value}}</dd></div></dl></template><p v-if="e.text" class="equip-text">{{e.text}}</p></article></div>
   <div v-else-if="panel.type==='sea'" class="sea-grid"><article v-for="ch in panel.challenges" class="sea-card"><header><h3>{{ch.name}}</h3><strong class="number">{{ch.score}}</strong><span class="tag">{{ch.rank}}</span></header><div class="half-score-bar"><i v-for="h in ch.halves" :style="{flex:h.pct??1}"></i></div><div v-for="h in ch.halves" class="half-row"><div><strong>{{h.name}}</strong><b class="number">{{h.score}}</b></div><p class="team-names">{{h.team}}</p></div></article></div>
   <div v-else-if="panel.type==='draws'" class="draw-list"><article v-for="r in panel.draws" class="draw-row"><img v-if="r.image" :src="r.image" alt="" /><div class="draw-name"><h3>{{r.name}}</h3><small>{{r.date}}</small></div><div class="draw-meter"><i :style="{width:(r.pct??0)+'%'}"></i></div><b class="number">{{r.pity}} 抽</b></article></div>
   <div v-else-if="panel.type==='timeline'" class="timeline">
    <div class="timeline-range"><strong>{{panel.range}}</strong><span>{{panel.events.length}} 项活动</span></div>
    <div class="timeline-head"><span>活动与时间</span><div class="axis"><span v-for="(t,i) in panel.ticks" :style="{left:t.left+'%'}" :class="{'axis-first':i===0,'axis-last':i===panel.ticks.length-1}">{{t.label}}</span></div></div>
    <article v-for="e in panel.events" class="timeline-row" :class="{'undated':!e.valid}" data-calendar-event>
     <div class="event-copy"><h3>{{e.name}}</h3><p class="event-type">{{e.category}}</p><p class="event-date">{{e.start}}<br />{{e.end}}</p></div>
     <div v-if="e.valid" class="event-track"><div v-for="t in panel.ticks" class="axis-line" :style="{left:t.left+'%'}"></div><i class="today-line" v-if="panel.now>0&&panel.now<100" :style="{left:panel.now+'%'}"></i><div class="event-bar" :class="{'estimated':!e.precise,'bar-ended':e.status==='已结束','bar-short':e.width<15}" :style="{left:e.left+'%',width:e.width+'%',backgroundImage:e.image&&e.width>14?'linear-gradient(90deg,rgba(9,25,42,.8),rgba(9,25,42,.24)),url('+e.image+')':null}"><span v-if="e.width>26">{{e.status}}</span></div><span v-if="e.width<=26" class="event-out-status">{{e.status}}</span></div>
     <div v-else class="event-unplaced"><span class="tag">{{e.status}}</span><p>{{e.time||'日期尚未确认，暂不定位时间条。'}}</p></div>
    </article>
   </div>
   <div v-else-if="panel.type==='guide_visual'" class="guide-visual"><div v-for="(line,i) in guideLines(panel)" :key="i" class="guide-source-line"><WuwaGuideVisual v-if="panel.game==='wuthering_waves'" :text="line" :section-key="panel.sectionKey" :character-id="panel.characterId" image-mode /><NteGuideVisual v-else :text="line" :section-key="panel.sectionKey" :role-name="panel.roleName" image-mode /></div></div>
   <div v-else-if="panel.type==='guide_context'" class="guide-empty"><p>{{panel.text}}</p><div v-if="panel.role" class="guide-role-context"><EndfieldArtwork :src="panel.role.avatar_url" :name="panel.role.name" role /><div><h3>{{panel.role.name}}</h3><p>角色资料已收录</p><p>查看本人面板：{{panel.command}}</p></div></div></div>
   <div v-else-if="panel.type==='textlines'" class="text-lines"><article v-for="line in panel.lines"><h3 v-if="line.name">{{line.name}}</h3><p>{{line.text}}</p></article></div>
   <p v-else class="prose">{{panel.text}}</p>
   <p v-if="panel.source" class="source-line">来源：{{panel.source}}</p>
  </div>
 </section>
</template>
