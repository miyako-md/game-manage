<script setup>
import {computed} from 'vue'
import {gameVars} from '../dashboard.js'
import {viewModel} from './models.js'
import {imageWidth} from './designs.js'
import ReuseBody from './ReuseBody.vue'
import AccountOverviewSheet from './AccountOverviewSheet.vue'
const props=defineProps({input:Object})
const model=computed(()=>viewModel(props.input))
const isExample=computed(()=>/合成|反馈示例|未绑定|未收录|无登录/.test(model.value.origin))
const isAccountOverview=computed(()=>props.input?.snapshot?.kind==='game_snapshot'&&(props.input?.snapshot?.display_data?.panels||[]).some(p=>p.capability==='account'))
</script>
<template>
 <article class="lab-sheet dossier reuse" :class="['page-'+input.snapshot.kind,{'is-account-overview':isAccountOverview}]" :data-game="input.snapshot.game||'all'" :style="{width:imageWidth(input)+'px',...gameVars(input.snapshot.game)}">
  <AccountOverviewSheet v-if="isAccountOverview" :input="input" />
  <template v-else>
   <header class="page-head head-dossier">
    <div class="dossier-brand">
     <span class="brand-badge">游戏管家</span>
     <span v-if="model.game && model.game !== '游戏管家'" class="game-badge">{{model.game}}</span>
     <span class="as-of">更新于 {{model.asOf}}</span>
    </div>
    <div class="head-main">
     <h1>{{model.title}}</h1>
     <div class="head-meta">
      <span class="command">{{model.command}}</span>
     </div>
    </div>
   </header>
   <p v-if="isExample" class="example-label">{{model.origin}}</p>
   <ReuseBody :input="input" />
   <footer class="page-footer"><span>{{model.game && model.game !== '游戏管家' ? `游戏管家 · ${model.game}` : '游戏管家'}}</span><span>发送“帮助”查看全部指令</span></footer>
  </template>
 </article>
</template>
