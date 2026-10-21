<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, ref, watch } from 'vue'
import { requestJson, getAccountScope, isCloudMode, subscribeSessionInvalidation } from '../http-client.js'
import { attributionLabel, gradeLabel, isDefaultScore } from '../assessment-display.js'
import { onUnmounted } from 'vue'
// autoLoad: the website shows the score of the equipped echoes without a click (the live role detail only, never history entries).
const props=defineProps({game:{type:String,required:true},characterId:{type:String,default:''},scopeKey:{type:[String,Object],default:''},imageMode:{type:Boolean,default:false},initialAssessment:{type:Object,default:null},autoLoad:{type:Boolean,default:false}})
const emit=defineEmits(['assessment'])
const opened=ref(false),busy=ref(false),error=ref(''),modelJson=ref(''),itemsJson=ref('[]'),name=ref('配置 A'),saved=ref([]),a=ref(''),b=ref(''),result=ref(null),comparison=ref(null),observedAt=ref(null)
// generation: the character, game or session on screen. revision: the model and equipment input. A response lands only while the one it answers is still current.
let generation=0,revision=0,loads=0
// The equipped score read on mount has its own loading state, so it never holds the editor's busy flag.
const equipped=ref(null),loading=ref(false),loadError=ref(''),userModel=ref(false)
const superseded=new DOMException('输入已变化','AbortError')
const reasons={NO_MODEL:'请先配置评分模型',NO_WEIGHTS:'请先填写偏好权重',NO_EQUIPMENT:'没有可评分的装备输入',UNKNOWN_STAT_COMPLETENESS:'尚未核对完整词条列表',NO_POSITIVE_ELIGIBLE_WEIGHTS:'请配置有效副词条的正权重',MISSING_EXPLICIT_NTE_INPUT:'请补充装备类型、品质、面积及完整词条输入',UNKNOWN_QUALITY:'装备品质未提供或未配置品质因子',UNKNOWN_AREA:'驱动面积未提供或无效',UNKNOWN_SUBSTATS:'副词条列表及完整性未确认',UNKNOWN_STAT:'词条尚未映射或未提供数值',UNKNOWN_VALUE:'词条数值未提供',INVALID_VALUE:'词条数值格式无效',UNIT_MISMATCH:'词条单位与模型不一致',UNKNOWN_UNIT:'词条单位未提供',INELIGIBLE_SUBSTAT:'词条不适用于已声明的装备类型',UNKNOWN_MAINSTAT:'卡带主词条未提供或未声明',UNKNOWN_MAIN_VALUE:'主词条值未提供',UNKNOWN_MAIN_REFERENCE:'主词条参考值未配置',REFERENCE_CONTEXT_MISMATCH:'主词条与参考上下文不一致',CONFLICTING_OBSERVATION:'同一观察记录出现不同词条值',AMBIGUOUS_DUPLICATE_STAT:'主副词条身份重复或不明确',AMBIGUOUS_DUPLICATE_SUBSTAT:'副词条身份重复或不明确',DUPLICATE_ITEM:'装备标识重复',BOTH_CONFIGURATIONS_REQUIRE_SCORE:'双方都可评分后才能计算差值',ZERO_BASELINE:'A 的精确分数为零，百分比无法计算',NO_STAT_VALUES:'未提供可验证的词条值'}
const reason=code=>code?(reasons[code]||'输入资料不足或不一致，请核对') : ''
// Once the editor is open the result is the one of its input; before that, the equipped score.
const visibleScore=computed(()=>props.imageMode?props.initialAssessment:opened.value?result.value:equipped.value)
// No stored model and no default weights for this character: the backend answers with its empty stub.
const noDefault=computed(()=>props.game==='wuthering_waves'&&visibleScore.value?.status==='unconfigured'&&visibleScore.value?.model_version==='unconfigured')
const sources={user_configured:'用户配置',builtin_default:'内置默认（非官方）'}
const contributionRows=computed(()=>visibleScore.value?.contributions?.length?visibleScore.value.contributions:(visibleScore.value?.item_results||[]).flatMap(item=>item.contributions||[]))
const status=value=>({scored:'已评分',unconfigured:'未配置',unscorable:'不可评分'})[value]||'未配置'
const base=()=>{
 const scope=getAccountScope()
 if(isCloudMode()){
  if(!scope?.account_id||!scope?.role_id)throw new Error('请先选择已授权账号')
  return `/api/accounts/${encodeURIComponent(scope.account_id)}/roles/${encodeURIComponent(scope.role_id)}/assessment/${props.game}/${encodeURIComponent(props.characterId)}`
 }
 return `/api/assessment/${props.game}/${encodeURIComponent(props.characterId)}`
}
const template=()=>({game:props.game,character_id:props.characterId,version:'personal-v1',source:'user_configured',...(props.game==='nte'?{nte_profile:{character_id:props.characterId,version:'weights-v1',source:'user_configured',substat_weights:{},mainstat_weights:{}},nte_spec:{version:'nte-custom-weighting-v1',quality_factors:{},eligible_substats:[],mainstat_reference_values:[],catalog:[],aliases:{}}}:{wuwa_weights:{}})})
function edited(){revision++;result.value=null;comparison.value=null}
function clear(){generation++;edited();opened.value=false;saved.value=[];a.value='';b.value='';itemsJson.value='[]';observedAt.value=null;modelJson.value='';error.value='';busy.value=false;equipped.value=null;loading.value=false;loadError.value='';userModel.value=false}
async function loadEquipped(){
 if(props.imageMode||!props.autoLoad||!props.characterId)return
 const version=generation,mine=++loads,current=()=>version===generation&&mine===loads
 loading.value=true;loadError.value=''
 try{const data=await requestJson(base()+'/equipped');if(current())equipped.value=data?.assessment||null}
 catch(e){if(current())loadError.value=e?.message||'评分读取失败'}
 finally{if(current())loading.value=false}
}
watch(()=>[props.game,props.characterId,props.imageMode,props.scopeKey,props.autoLoad],()=>{clear();loadEquipped()},{flush:'sync'})
watch(equipped,value=>emit('assessment',value))
// The comparison names no configuration, so it belongs to the A/B pair it was computed for.
watch([a,b],()=>{comparison.value=null},{flush:'sync'})
const wuwaStats={attack_flat:'攻击平值',attack_ratio:'攻击百分比',health_flat:'生命平值',health_ratio:'生命百分比',defense_flat:'防御平值',defense_ratio:'防御百分比',crit_rate:'暴击率',crit_damage:'暴击伤害',energy_regen:'共鸣效率',basic_damage:'普攻伤害加成',heavy_damage:'重击伤害加成',skill_damage:'共鸣技能伤害加成',liberation_damage:'共鸣解放伤害加成',aero_damage:'气动伤害加成',glacio_damage:'冷凝伤害加成',fusion_damage:'热熔伤害加成',electro_damage:'导电伤害加成',spectro_damage:'衍射伤害加成',havoc_damage:'湮灭伤害加成',healing_bonus:'治疗效果加成'}
const newStat=ref(''),newQuality=ref('')
const editedModel=computed(()=>{try{const model=JSON.parse(modelJson.value);return props.game==='nte'?{...model,nte_profile:model.nte_profile||template().nte_profile,nte_spec:model.nte_spec||template().nte_spec}:model}catch{return template()}})
const editedItems=computed(()=>{try{return JSON.parse(itemsJson.value)}catch{return []}})
const statOptions=computed(()=>props.game==='nte'?(editedModel.value.nte_spec?.catalog||[]).map(s=>({id:s.canonical_id,label:s.label})) : Object.entries(wuwaStats).map(([id,label])=>({id,label})))
function equipmentStatOptions(stat){return [{value:'',label:'未提供'},...(stat.canonical_id&&!statOptions.value.some(o=>o.id===stat.canonical_id)?[{value:stat.canonical_id,label:stat.canonical_id+'（来源词条，待声明）'}]:[]),...statOptions.value.map(o=>({value:o.id,label:o.label}))]}
const weightRows=computed(()=>props.game==='nte'?(editedModel.value.nte_spec?.catalog||[]):Object.keys(editedModel.value.wuwa_weights||{}).map(canonical_id=>({canonical_id,label:wuwaStats[canonical_id]})))
function changeModel(fn){const value=structuredClone(editedModel.value);fn(value);modelJson.value=json(value);edited()}
function changeItems(fn){const value=structuredClone(editedItems.value);fn(value);itemsJson.value=json(value);edited()}
function weight(id,role){return props.game==='nte'?editedModel.value.nte_profile?.[role+'_weights']?.[id]??'':editedModel.value.wuwa_weights?.[id]??''}
function setWeight(id,value,role='substat'){changeModel(m=>{const weights=props.game==='nte'?m.nte_profile[role+'_weights']:m.wuwa_weights;if(value==='')delete weights[id];else weights[id]=value})}
function addWeight(){if(!newStat.value)return;changeModel(m=>{if(props.game==='nte'){if(!m.nte_spec.catalog.some(s=>s.canonical_id===newStat.value)){m.nte_spec.catalog.push({canonical_id:newStat.value,label:newStat.value,kinds:['drive','cartridge'],main:false,sub:true,unit:'flat'});m.nte_spec.eligible_substats.push(newStat.value)}}else m.wuwa_weights[newStat.value]=''});newStat.value=''}
function removeWeight(id){changeModel(m=>{if(props.game==='nte'){m.nte_spec.catalog=m.nte_spec.catalog.filter(s=>s.canonical_id!==id);m.nte_spec.eligible_substats=m.nte_spec.eligible_substats.filter(s=>s!==id);delete m.nte_profile.substat_weights[id];delete m.nte_profile.mainstat_weights[id]}else delete m.wuwa_weights[id]})}
function setCatalog(id,key,value){changeModel(m=>{m.nte_spec.catalog.find(s=>s.canonical_id===id)[key]=value;if(key==='sub'){m.nte_spec.eligible_substats=m.nte_spec.catalog.filter(s=>s.sub).map(s=>s.canonical_id)}})}
function addQuality(){if(newQuality.value)changeModel(m=>{m.nte_spec.quality_factors[newQuality.value]=''});newQuality.value=''}
function addReference(){changeModel(m=>m.nte_spec.mainstat_reference_values.push({canonical_id:'',value:'',unit:'flat',context:{kind:'cartridge',scope:''}}))}
function setReference(index,key,value){changeModel(m=>{const r=m.nte_spec.mainstat_reference_values[index];if(key==='scope')r.context.scope=value;else r[key]=value})}
function addItem(){changeItems(items=>items.push({id:'manual:'+crypto.randomUUID(),kind:props.game==='nte'?null:'echo',stats:[],stats_complete:null}))}
function setItem(index,key,value){changeItems(items=>{const item=items[index];if(props.game==='nte'&&['kind','quality','area','substats_complete'].includes(key)){if(key==='kind'){item.kind=value||null;item.nte=value?{kind:value,quality:null,area:null,substats:(item.nte?.substats||item.stats||[]).map(s=>({canonical_id:s.canonical_id,observation_id:s.observation_id||'manual:'+crypto.randomUUID(),value:s.value,unit:s.unit,context:s.context||{}})),substats_complete:null}:null}else if(item.nte)item.nte[key]=value}else item[key]=value})}
const itemStats=item=>props.game==='nte'?item.nte?.substats||item.stats||[]:item.stats||[]
function addItemStat(index){changeItems(items=>{const item=items[index],rows=props.game==='nte'&&item.nte?item.nte.substats:item.stats;rows.push({canonical_id:null,observation_id:'manual:'+crypto.randomUUID(),value:null,unit:null,...(props.game==='nte'?{}:{role:'sub'})})})}
function setStat(index,statIndex,key,value){changeItems(items=>{const item=items[index];const rows=props.game==='nte'&&item.nte?item.nte.substats:item.stats;rows[statIndex][key]=value||null})}
function removeStat(index,statIndex){changeItems(items=>{const item=items[index];const rows=props.game==='nte'&&item.nte?item.nte.substats:item.stats;rows.splice(statIndex,1)})}
function setMain(index,key,value){changeItems(items=>{const item=items[index];if(!item.nte)return;if(!item.nte.mainstat)item.nte.mainstat={canonical_id:null,value:null,unit:null,context:{kind:'cartridge',scope:''}};if(key==='scope')item.nte.mainstat.context.scope=value;else item.nte.mainstat[key]=value||null})}
const unsubscribe=subscribeSessionInvalidation(clear);onUnmounted(unsubscribe)
loadEquipped()
async function run(action){if(props.imageMode||busy.value)return;const version=generation;busy.value=true;error.value='';try{await action()}catch(e){if(e!==superseded&&version===generation)error.value=e?.message||'操作失败'}finally{if(version===generation)busy.value=false}}
async function call(path,options,fromInput){const version=generation,input=revision;const data=await requestJson(path,options);if(version!==generation||fromInput&&input!==revision)throw superseded;return data}
const json=value=>JSON.stringify(value,null,2)
function parseJson(raw){try{return JSON.parse(raw)}catch{throw new Error('JSON 格式无效，请检查后再保存')}}
// The default model is the template of a new personal model; saving it makes it the user's own.
async function read(){const data=await call(base()),model=data.model;userModel.value=model.source==='user_configured'&&model.version!=='unconfigured';modelJson.value=json(model.version==='unconfigured'?template():{...model,source:'user_configured'});saved.value=data.configurations; if(!a.value)a.value=saved.value[0]?.id||'';if(!b.value)b.value=saved.value[1]?.id||''}
async function open(){opened.value=true;await run(read)}
function configuration(){return {game:props.game,character_id:props.characterId,name:name.value,source:'user_configured',observed_at:observedAt.value,items:parseJson(itemsJson.value)}}
async function useEquipped(){await run(async()=>{const data=await call(base()+'/equipped');edited();itemsJson.value=json(data.configuration.items);observedAt.value=data.configuration.observed_at||null;name.value='当前装备副本';result.value=data.assessment})}
async function saveModel(){await run(async()=>{await call(base()+'/model',{method:'PUT',body:parseJson(modelJson.value)});result.value=null;comparison.value=null;await read()})}
// Deleting the personal model brings the default back: close the editor and read the equipped score again.
async function restoreDefault(){await run(async()=>{await call(base()+'/model',{method:'DELETE'});edited();userModel.value=false;opened.value=false;loadEquipped()})}
async function saveConfig(){await run(async()=>{const data=await call(base()+'/configurations',{method:'POST',body:configuration()});await read();b.value=data.id})}
async function score(){await run(async()=>{result.value=await call(base()+'/score',{method:'POST',body:{configuration:configuration()}},true)})}
async function compareSaved(){await run(async()=>{comparison.value=await call(base()+'/compare',{method:'POST',body:{a:a.value,b:b.value}},true)})}
async function remove(id){await run(async()=>{await call(base()+'/configurations/'+encodeURIComponent(id),{method:'DELETE'});a.value='';b.value='';await read();comparison.value=null})}
function load(row){name.value=row.data.name;itemsJson.value=json(row.data.items);observedAt.value=row.data.observed_at||null;edited()}
</script>
<template>
 <section v-if="!imageMode || initialAssessment?.status === 'scored'" class="personal-assessment">
  <h4>{{ isDefaultScore(visibleScore) ? '默认评分 · 非官方' : '个人权重评分' }}</h4>
  <p v-if="!imageMode && !opened && loading" role="status">正在读取当前装备评分…</p>
  <p v-if="!imageMode && !opened && loadError" role="alert">{{ loadError }}</p>
  <button v-if="!imageMode && !opened" type="button" :disabled="!characterId" @click="open">配置权重与 A/B 对比</button>
  <div v-if="!imageMode && opened" class="assessment-editor">
   <p role="alert" v-if="error">{{ error }}</p>
   <details><summary>输入单位与公式</summary><p v-if="game==='wuthering_waves'">鸣潮公式：Σ(规范值×自定义权重)。flat 是平值；ratio 是小数比例；percent_points 是百分数的数值部分，10% 填 "10"。attack_flat/attack_ratio、health_flat/health_ratio、defense_flat/defense_ratio、crit_rate、crit_damage、energy_regen、basic_damage、heavy_damage、skill_damage、liberation_damage、aero_damage、glacio_damage、fusion_damage、electro_damage、spectro_damage、havoc_damage、healing_bonus。未提供已配置词条值保持不可评分。</p><p v-else>NTE：D 是最高四项正副词条权重和；驱动副项=10×面积×品质因子×权重/D；卡带副项=100×品质因子×权重/D；卡带主项=50×主项权重×当前值/参考值。需显式声明词条 catalog（ID、label、kinds、main/sub、unit），eligible_substats、quality_factors 与 mainstat_reference_values（canonical_id、正 value、unit、含 kind 的 context）。每件 nte 输入需 kind、quality、area（驱动）、substats、substats_complete:true，卡带还需 mainstat。core/pie 来源分组不代表 kind。百分数使用 percent_points，比例使用 ratio，平值使用 flat。未知品质/面积/完成标记请保留 null；用户补充资料须自己确认来源。</p><p>所有数值填十进制定点字符串（如 "0.5"），版本/来源与逐项贡献保留。更改模型后双方重新评分。</p></details>
   <label>模型版本<input aria-label="模型版本" :value="editedModel.version" @input="changeModel(m=>m.version=$event.target.value)" /></label>
   <div class="field-row"><label>新增词条<input v-if="game==='nte'" aria-label="新增词条 ID" :value="newStat" @input="newStat=$event.target.value" placeholder="填写来源词条 ID" /><MenuSelect v-else label="新增权重词条" :model-value="newStat" @change="newStat=$event" :options="[{value:'',label:'请选择词条'},...Object.entries(wuwaStats).map(([value,label])=>({value,label}))]" /></label><button type="button" @click="addWeight">添加权重词条</button></div>
   <div v-for="row in weightRows" :key="row.canonical_id" class="stat-row"><strong>{{ row.label }}</strong><template v-if="game==='nte'"><label>显示名称<input :value="row.label" @input="setCatalog(row.canonical_id,'label',$event.target.value)" /></label><label>单位<MenuSelect :model-value="row.unit" @change="setCatalog(row.canonical_id,'unit',$event)" :label="row.label+'单位'" :options="[{value:'flat',label:'平值'},{value:'ratio',label:'比例'}]" /></label><label><input type="checkbox" :checked="row.sub" @change="setCatalog(row.canonical_id,'sub',$event.target.checked)" />副词条</label><label><input type="checkbox" :checked="row.main" @change="setCatalog(row.canonical_id,'main',$event.target.checked)" />主词条</label></template><label>{{ game==='nte'?'副词条权重':'偏好权重' }}<input :aria-label="row.label+'权重'" type="number" min="0" max="100" step="any" :value="weight(row.canonical_id,'substat')" @input="setWeight(row.canonical_id,$event.target.value)" placeholder="未配置" /></label><label v-if="game==='nte'">主词条权重<input type="number" min="0" max="100" step="any" :value="weight(row.canonical_id,'mainstat')" @input="setWeight(row.canonical_id,$event.target.value,'mainstat')" placeholder="未配置" /></label><button type="button" @click="removeWeight(row.canonical_id)">移除词条</button></div>
   <template v-if="game==='nte'"><h5>自定义品质因子</h5><label>品质标识<input :value="newQuality" @input="newQuality=$event.target.value" placeholder="使用自己的来源标识" /></label><button type="button" @click="addQuality">添加品质</button><label v-for="(factor,key) in editedModel.nte_spec.quality_factors" :key="key">{{ key }} 因子<input type="number" min="0" step="any" :value="factor" @input="changeModel(m=>m.nte_spec.quality_factors[key]=$event.target.value)" /></label><h5>卡带主属性参考值</h5><button type="button" @click="addReference">添加主属性参考</button><div v-for="(reference,i) in editedModel.nte_spec.mainstat_reference_values" :key="i" class="field-row"><MenuSelect label="参考词条" :model-value="reference.canonical_id" @change="setReference(i,'canonical_id',$event)" :options="[{value:'',label:'请选择词条'},...statOptions.map(o=>({value:o.id,label:o.label}))]" /><input aria-label="参考值" type="number" min="0" step="any" :value="reference.value" @input="setReference(i,'value',$event.target.value)" placeholder="正参考值" /><MenuSelect label="参考单位" :model-value="reference.unit" @change="setReference(i,'unit',$event)" :options="[{value:'flat',label:'平值'},{value:'ratio',label:'比例'}]" /><input aria-label="参考上下文" :value="reference.context.scope" @input="setReference(i,'scope',$event.target.value)" placeholder="自定义参考上下文名称" /></div></template>
   <button type="button" :disabled="busy" @click="saveModel">保存权重模型</button><button v-if="game==='wuthering_waves' && userModel" type="button" :disabled="busy" @click="restoreDefault">恢复默认</button>
   <button type="button" :disabled="busy" @click="useEquipped">导入已同步装备</button>
   <label>配置名称<input aria-label="配置名称" :value="name" @input="name=$event.target.value" maxlength="80" /></label>
   <p v-if="observedAt">装备数据时间：{{ observedAt }}</p><button type="button" @click="addItem">添加装备</button>
   <section v-for="(item,i) in editedItems" :key="item.id" class="equipment-input"><h5>装备 {{ i+1 }} <span v-if="item.source_group">来源分组 {{ item.source_group }}</span></h5><button type="button" @click="changeItems(items=>items.splice(i,1))">移除装备</button>
   <template v-if="game==='nte'"><label>装备类型<MenuSelect label="装备类型" :model-value="item.nte?.kind||''" @change="setItem(i,'kind',$event)" :options="[{value:'',label:'未提供'},{value:'drive',label:'驱动'},{value:'cartridge',label:'卡带'}]" /></label><label>品质<MenuSelect label="装备品质" :disabled="!item.nte" :model-value="item.nte?.quality||''" @change="setItem(i,'quality',$event)" :options="[{value:'',label:'未提供'},...Object.keys(editedModel.nte_spec.quality_factors).map(value=>({value,label:value}))]" /></label><label v-if="item.nte?.kind==='drive'">驱动面积<input aria-label="驱动面积" type="number" min="1" step="1" :value="item.nte.area" @input="setItem(i,'area',$event.target.value||null)" placeholder="未提供" /></label><label><input type="checkbox" :checked="item.nte?.substats_complete===true" :disabled="!item.nte" @change="setItem(i,'substats_complete',$event.target.checked?true:null)" />已核对完整副词条列表</label></template>
   <label v-else><input type="checkbox" :checked="item.stats_complete===true" @change="setItem(i,'stats_complete',$event.target.checked?true:null)" />已核对完整主副词条列表（未出现词条按零计）</label>
   <button type="button" :disabled="game==='nte'&&!item.nte" @click="addItemStat(i)">添加词条</button>
   <div v-for="(stat,j) in itemStats(item)" :key="stat.observation_id||j" class="stat-row"><label>词条<MenuSelect :label="'装备'+(i+1)+'词条'+(j+1)" :model-value="stat.canonical_id||''" @change="setStat(i,j,'canonical_id',$event)" :options="equipmentStatOptions(stat)" /></label><label v-if="game!=='nte'">位置<MenuSelect :model-value="stat.role||''" @change="setStat(i,j,'role',$event)" :label="'装备'+(i+1)+'词条位置'+(j+1)" :options="[{value:'',label:'未提供'},{value:'main',label:'主词条'},{value:'sub',label:'副词条'}]" /></label><label>词条值<input :aria-label="'装备'+(i+1)+'词条值'+(j+1)" type="text" inputmode="decimal" :value="stat.value" @input="setStat(i,j,'value',$event.target.value)" placeholder="未提供" /></label><label>单位<MenuSelect :label="'装备'+(i+1)+'词条单位'+(j+1)" :model-value="stat.unit||''" @change="setStat(i,j,'unit',$event)" :options="[{value:'',label:'未提供'},{value:'flat',label:'平值'},{value:'ratio',label:'比例（10%=0.1）'},{value:'percent_points',label:'百分数（10%=10）'}]" /></label><button type="button" @click="removeStat(i,j)">移除装备词条</button></div>
   <div v-if="item.nte?.kind==='cartridge'" class="field-row"><h5>卡带主词条</h5><MenuSelect label="卡带主词条" :model-value="item.nte.mainstat?.canonical_id||''" @change="setMain(i,'canonical_id',$event)" :options="[{value:'',label:'未提供'},...statOptions.map(o=>({value:o.id,label:o.label}))]" /><input aria-label="卡带主词条值" type="number" min="0" step="any" :value="item.nte.mainstat?.value" @input="setMain(i,'value',$event.target.value)" placeholder="主词条值" /><MenuSelect label="卡带主词条单位" :model-value="item.nte.mainstat?.unit||''" @change="setMain(i,'unit',$event)" :options="[{value:'',label:'未提供'},{value:'flat',label:'平值'},{value:'ratio',label:'比例'},{value:'percent_points',label:'百分数'}]" /><input aria-label="卡带参考上下文" :value="item.nte.mainstat?.context?.scope" @input="setMain(i,'scope',$event.target.value)" placeholder="与模型参考上下文一致" /></div></section>
   <details><summary>高级 JSON 导入与导出</summary><label>权重及公式配置 JSON<textarea aria-label="权重及公式配置 JSON" :value="modelJson" @input="modelJson=$event.target.value;edited()" spellcheck="false" rows="6" /></label><label>装备输入 JSON<textarea aria-label="装备输入 JSON" :value="itemsJson" @input="itemsJson=$event.target.value;edited()" spellcheck="false" rows="6" /></label></details>
   <button type="button" :disabled="busy" @click="score">评价当前输入</button><button type="button" :disabled="busy" @click="saveConfig">保存配置</button>
   <ul><li v-for="row in saved" :key="row.id"><button type="button" @click="load(row)">{{ row.data.name }}</button> · 修订 {{ row.revision }} <button type="button" :disabled="busy" @click="remove(row.id)">删除配置</button></li></ul>
   <label>A<MenuSelect label="配置 A" :model-value="a" :disabled="busy" @change="a=$event" :options="[{value:'',label:'请选择'},...saved.map(row=>({value:String(row.id),label:row.data.name}))]" /></label><label>B<MenuSelect label="配置 B" :model-value="b" :disabled="busy" @change="b=$event" :options="[{value:'',label:'请选择'},...saved.map(row=>({value:String(row.id),label:row.data.name}))]" /></label><button type="button" :disabled="busy||!a||!b" @click="compareSaved">同模型重新计算并对比</button>
   <div v-if="comparison"><p>同一模型 {{ comparison.model_version }} · A {{ status(comparison.a.status) }} {{ comparison.a.value ?? '—' }} · B {{ status(comparison.b.status) }} {{ comparison.b.value ?? '—' }} · 差值 {{ comparison.delta ?? '—' }} · 变化 {{ comparison.percent_delta==null?'无法计算':comparison.percent_delta+'%' }}</p><p v-if="comparison.reason">{{ reason(comparison.reason) }}</p><details><summary>A/B 逐项贡献与模型证据</summary><pre>{{ json(comparison) }}</pre></details></div>
  </div>
  <div v-if="visibleScore" class="assessment-result">
   <p v-if="noDefault">暂无默认权重 <span>可配置个人权重后评分</span></p>
   <p v-else-if="visibleScore.status==='scored' && visibleScore.max_value!=null">总分 {{ visibleScore.value }} / {{ visibleScore.max_value }}<template v-if="gradeLabel(visibleScore.grade)"> · 等级 {{ gradeLabel(visibleScore.grade) }}</template></p>
   <p v-else>{{ status(visibleScore.status) }}：{{ visibleScore.value ?? '—' }} <span v-if="visibleScore.reason">{{ reason(visibleScore.reason) }}</span></p>
   <p v-if="attributionLabel(visibleScore)" class="assessment-source">{{ attributionLabel(visibleScore) }}</p>
   <ul v-if="visibleScore.item_results?.length"><li v-for="(item,index) in visibleScore.item_results" :key="item.item_id">装备 {{ index+1 }}：{{ status(item.status) }} {{ reason(item.reason) }} · {{ item.value ?? '—' }}<template v-if="item.max_value!=null"> / {{ item.max_value }}</template><template v-if="gradeLabel(item.grade)"> · {{ gradeLabel(item.grade) }}</template></li></ul>
   <p v-if="visibleScore.partial">仅部分装备可评分，已知小计 {{ visibleScore.partial_known_total }}；套装总分仍不可评分。</p>
   <details v-if="!imageMode" data-render-collapsed><summary>评分详情</summary>
    <p>模型 {{ visibleScore.model_version }} · 权重 {{ visibleScore.weight_version }} · 来源 {{ sources[visibleScore.origin||visibleScore.source]||visibleScore.source }} · 公式 {{ visibleScore.formula }}</p><p>{{ visibleScore.formula_text }}</p><table v-if="contributionRows.length"><thead><tr><th>装备 / 词条</th><th>规范值</th><th>单位</th><th>权重</th><th>因子</th><th>参考值</th><th>贡献</th></tr></thead><tbody><tr v-for="(entry,i) in contributionRows" :key="i"><td>{{ entry.item_id }} / {{ entry.contribution_id }}</td><td>{{ entry.current_value ?? '存在性' }}</td><td>{{ entry.unit }}</td><td>{{ entry.weight }}</td><td>{{ entry.factor ?? '—' }}</td><td>{{ entry.reference_value ?? '—' }}</td><td>{{ entry.value }}</td></tr></tbody></table><table v-if="visibleScore.item_results?.length"><thead><tr><th>装备</th><th>状态</th><th>单件小计</th></tr></thead><tbody><tr v-for="item in visibleScore.item_results" :key="item.item_id"><td>{{ item.item_id }}</td><td>{{ status(item.status) }} {{ reason(item.reason) }}</td><td>{{ item.value ?? '—' }}</td></tr></tbody></table><p v-if="visibleScore.rounding_adjustment">最终舍入调整 {{ visibleScore.rounding_adjustment }}</p>
   </details>
  </div>
 </section>
</template>
<style scoped>
/* A soft tile with a hairline: the score first, the editor and its inputs as white controls. */
.personal-assessment{padding:16px 18px;border-radius:var(--radius-tile);background:var(--surface-soft);box-shadow:inset 0 0 0 1px var(--overlay-2);font-size:13px;line-height:1.6;overflow-wrap:anywhere}
.personal-assessment h4{margin:0;color:var(--text);font-size:15px;font-weight:600;letter-spacing:-.01em}
.personal-assessment h5{margin:12px 0 4px;color:var(--text);font-size:13px;font-weight:500}
.personal-assessment strong{font-weight:500}
.personal-assessment p{margin:6px 0}
.assessment-editor label{display:block;margin:8px 0}
.assessment-editor textarea{display:block;width:100%;min-width:0;box-sizing:border-box;font:12px/1.6 var(--font-mono);background:var(--card-bg);color:var(--text);border:1px solid var(--border);border-radius:var(--radius-control);padding:8px 10px}
.personal-assessment button,.personal-assessment input:not([type=checkbox]){margin:3px;padding:4px 12px;min-height:32px;color:var(--text);background:var(--card-bg);border:1px solid var(--border);border-radius:var(--radius-control);font-size:13px}
.assessment-editor :deep(.menu-select){margin:3px;max-width:100%;min-width:100px;vertical-align:middle}
.assessment-editor :deep(.menu-select-trigger){min-height:32px;padding:4px 12px;font-size:13px}
@media(pointer:coarse){.assessment-editor :deep(.menu-select-trigger){min-height:44px}}
/* Buttons follow the shared small button: white, a hairline, a 14px corner, one pixel down when pressed. */
.personal-assessment button{color:var(--text);font-weight:500;line-height:20px}
.personal-assessment button:not(:disabled):active{transform:translateY(1px)}
.personal-assessment input[type=checkbox]{margin:3px 6px 3px 3px;accent-color:var(--accent)}
@media(hover:hover) and (pointer:fine){.personal-assessment button:not(:disabled):hover{background:var(--button-hover-bg);border-color:var(--border-strong)}}
@media(pointer:coarse){.personal-assessment button,.personal-assessment input:not([type=checkbox]){min-height:44px}}
.personal-assessment table{border-collapse:collapse;font-size:13px;width:100%;text-align:left}
.personal-assessment th{color:var(--text-muted);font-size:12px;font-weight:500}
.personal-assessment pre{margin:6px 0;padding:8px 10px;border-radius:var(--radius-control);background:var(--card-bg);font:12px/1.6 var(--font-mono);white-space:pre-wrap;overflow-wrap:anywhere}
.field-row,.stat-row{display:flex;flex-wrap:wrap;align-items:center;gap:5px}
.equipment-input{border-radius:var(--radius-well);background:var(--card-bg);box-shadow:inset 0 0 0 1px var(--overlay-2);padding:12px;margin:8px 0}
.stat-row input{width:100px}
/* The score line leads the result: big, with the reason in the normal size beside it. */
.assessment-result{margin-top:10px;padding:12px 14px;overflow-x:auto;border-radius:var(--radius-well);background:var(--card-bg);box-shadow:inset 0 0 0 1px var(--overlay-2)}
.assessment-result>p:first-child{margin-top:0;color:var(--text);font-size:20px;line-height:28px;font-weight:550;letter-spacing:-.03em;font-variant-numeric:tabular-nums}
.assessment-result>p:first-child span{color:var(--text-muted);font-size:13px;font-weight:400;letter-spacing:0}
.assessment-result td,.assessment-result th{padding:4px 8px 4px 0;border-bottom:1px solid var(--border)}
</style>
