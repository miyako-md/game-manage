<script setup>
import { ref,onMounted,onUnmounted } from 'vue'
import { subscribeSessionInvalidation } from '../http-client.js'
import { getCloudBilibiliSources,refreshCloudBilibiliSource } from '../cloud-bilibili-api.js'
import { formatTime } from '../dashboard.js'
const sources=ref([]),error=ref(''),message=ref(''),busy=ref(false),paused=ref(false)
const names={wuthering_waves:'鸣潮',nte:'异环',endfield:'终末地'}
const labels={queued:'已排队',running:'正在更新',backoff:'稍后再试',cooldown:'等待下次更新',idle:'待更新'}
let stopped=false,invalidated=false,generation=0,readId=0,timer,reads=0,deadline=0,controller=new AbortController()
const observed=new Map()
function active(s){return ['queued','running'].includes(s.queue_state)}
function disabled(s){return busy.value||active(s)||['backoff','cooldown'].includes(s.queue_state)}
function resetBudget(){reads=0;deadline=Date.now()+10*60*1000;paused.value=false}
function clear(){generation++;controller.abort();controller=new AbortController();clearTimeout(timer);sources.value=[];observed.clear();busy.value=false;error.value=message.value=''}
const unsubscribe=subscribeSessionInvalidation(()=>{invalidated=true;clear()})
async function load(){
  if(stopped||invalidated)return
  const run=generation,id=++readId;clearTimeout(timer);reads++
  try{
    const result=await getCloudBilibiliSources(controller.signal)
    if(stopped||invalidated||run!==generation||id!==readId)return
    if(!Array.isArray(result.sources))throw new Error('无法读取B站采集状态')
    for(const s of result.sources){
      const before=observed.get(s.game_id)
      if(before&&!active(s)){
        message.value=s.last_success&&s.last_success!==before.lastSuccess?'采集完成，请刷新游戏资讯或日历查看。':s.status==='error'?'采集失败，已保留已有记录。':'本次任务已结束，请检查最近成功时间。'
        observed.delete(s.game_id)
      }
      if(active(s)&&!observed.has(s.game_id))observed.set(s.game_id,{lastSuccess:s.last_success})
    }
    sources.value=result.sources;error.value=''
  }catch(e){
    if(!stopped&&!invalidated&&run===generation&&id===readId&&e.name!=='AbortError'){error.value='无法读取B站采集状态，请手动检查';paused.value=true;return}
  }finally{
    if(!stopped&&!invalidated&&run===generation&&id===readId&&!paused.value){
      if(reads>=120||Date.now()>=deadline)paused.value=true
      else timer=setTimeout(load,sources.value.some(active)?2500:30000)
    }
  }
}
async function refresh(s,backfill){
  if(stopped||invalidated||disabled(s))return
  const run=generation;busy.value=true;error.value=message.value='';resetBudget()
  try{
    await refreshCloudBilibiliSource(s.game_id,backfill,controller.signal)
    if(stopped||invalidated||run!==generation)return
    observed.set(s.game_id,{lastSuccess:s.last_success});await load()
  }catch(e){if(!stopped&&!invalidated&&run===generation&&e.name!=='AbortError')error.value=({source_busy:'该游戏正在同步或排队中，请稍候。',source_backoff:'来源暂不可用，请到可重试时间后再试。'})[e.detail]||'无法提交任务，请稍后重试'}
  finally{if(run===generation)busy.value=false}
}
function check(){resetBudget();void load()}
onMounted(check)
onUnmounted(()=>{stopped=true;unsubscribe();clear()})
</script>
<template>
  <section class="cloud-bili-collection" aria-label="B站公共动态采集">
    <h3>公共动态采集</h3>
    <details><summary>查看采集说明</summary><p>历史不完整或规则更新时会自动回补历史；手动回补覆盖近 60 天。</p></details>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <article v-for="s in sources" :key="s.game_id">
      <strong>{{ names[s.game_id] || s.game_id }} · {{ labels[s.queue_state] || '状态未知' }}</strong>
      <p>{{ s.status==='ok'?'最近更新成功':s.status==='error'?'最近更新未成功，可稍后重试':s.status==='running'?'正在读取动态':'等待首次更新' }} · 已收录资讯 {{ s.article_count || 0 }} 条</p>
      <details><summary>查看采集详情</summary><p>来源 UID {{ s.uid }} · 已读取 {{ s.pages || 0 }} 页 · 连续失败 {{ s.failures || 0 }} 次<span v-if="s.http_status"> · HTTP {{ s.http_status }}</span><span v-if="s.business_code !== undefined"> · 业务码 {{ s.business_code }}</span></p><p>{{ s.history_complete?'历史已完整回补':'历史尚未完整回补' }} · 已保存 {{ s.total || 0 }} 条 · 收入资讯 {{ s.article_count || 0 }} 条</p><p v-if="s.last_attempt">最近尝试：{{ formatTime(s.last_attempt) }}</p></details>
      <p v-if="s.last_success">最近成功：{{ formatTime(s.last_success) }}</p>
      <p v-if="s.queue_state==='backoff'">可重试时间：{{ formatTime(s.next_retry*1000) }}</p>
      <p v-else-if="s.queue_state==='cooldown'">下次可更新：{{ formatTime(s.next_retry*1000) }}</p>
      <p v-else-if="active(s)">任务排队或执行中，请稍候。</p>
      <div class="actions"><button class="ui-button" :disabled="disabled(s)" @click="refresh(s,false)">采集新动态</button><button class="ui-button" :disabled="disabled(s)" @click="refresh(s,true)">回补60天</button></div>
    </article>
    <p v-if="paused">自动刷新已暂停，可手动检查。</p>
    <button class="ui-button" :disabled="busy" @click="check">检查采集状态</button>
  </section>
</template>
<style scoped>
.cloud-bili-collection{display:grid;gap:10px;border-top:1px solid var(--border);padding-top:14px}.cloud-bili-collection article{display:grid;gap:6px;padding:10px 0;border-bottom:1px solid var(--border)}.cloud-bili-collection article strong{font-weight:500}.cloud-bili-collection>button{justify-self:start}h3,p{margin:0}h3{font-size:14px;font-weight:500}p{line-height:1.65}p[role=alert]{color:var(--danger)}.actions{display:flex;flex-wrap:wrap;gap:10px}
</style>
