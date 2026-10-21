<script setup>
import {computed,provide} from 'vue'
import RenderRoot from '../components/RenderRoot.vue'
import WuwaCombatRecord from '../components/WuwaCombatRecord.vue'
import Panel from './Panel.vue'
import {prepareReuse} from './reuse-model.js'
import {viewModel,knownRoles} from './models.js'
const props=defineProps({input:Object})
provide('wuwaImageMode',true)
provide('renderRoleCatalog',{nte:knownRoles('nte')})
const snapshot=computed(()=>prepareReuse(props.input)),model=computed(()=>viewModel(props.input))
const cap=computed(()=>snapshot.value.display_data.panels?.length===1?snapshot.value.display_data.panels[0].capability:null)
const special=computed(()=>['calendar','guide','nte_gacha'].includes(snapshot.value.kind)||model.value.panels.every(p=>['cloud_calendar','upcoming','guide_context'].includes(p.type)))
</script>
<template>
 <div class="reuse-content">
  <div v-if="special" class="page-body"><div v-if="snapshot.kind==='guide' && model.hero" class="guide-role-context"><img v-if="model.hero.image" :src="model.hero.image" :alt="model.hero.name" /><div><h2>{{model.hero.name}}</h2><p>{{model.hero.meta.join('　')}}</p></div></div><Panel v-for="(panel,i) in model.panels" :panel="panel" :index="i" scheme="dossier" /></div>
  <div v-else-if="cap==='combat' && snapshot.display_data.panels[0].game==='wuthering_waves'" id="render-content" class="render-image"><WuwaCombatRecord v-for="mode in ['tower','hologram','slash']" :mode="mode" :snap="snapshot.display_data.panels[0].snapshot" /></div>
  <RenderRoot v-else :snapshot="snapshot" />
 </div>
</template>
