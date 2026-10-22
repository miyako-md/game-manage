<script setup>
import { computed,ref,onMounted,onUnmounted } from 'vue'
import { subscribeSessionInvalidation } from '../http-client.js'
import { getCloudGuideStatus,checkCloudGuides } from '../cloud-guides-api.js'
import { formatTime } from '../dashboard.js'
const status=ref(null),error=ref(''),message=ref(''),busy=ref(false),paused=ref(false),cooldownUntil=ref(0),now=ref(Date.now())
const states={idle:'空闲',queued:'已排队',running:'正在检查'}
const outcomes={ok:'完成',partial:'部分完成',stopped:'已停止',failed:'失败'}
let stopped=false,invalidated=false,generation=0,readId=0,timer,reads=0,deadline=0,controller=new AbortController()
const job=computed(()=>status.value?.job||{})
const wuwa=computed(()=>status.value?.wuthering_waves||{})
const active=computed(()=>['queued','running'].includes(job.value.state))
const cooling=computed(()=>cooldownUntil.value>now.value)
const time=value=>value?formatTime(value):'未知'
const count=value=>Number.isInteger(value)?value:'未知'
function resetBudget(){reads=0;deadline=Date.now()+10*60*1000;paused.value=false}
function clear(){generation++;controller.abort();controller=new AbortController();clearTimeout(timer);status.value=null;busy.value=false;error.value=message.value=''}
const unsubscribe=subscribeSessionInvalidation(()=>{invalidated=true;clear()})
function cooldown(seconds){if(seconds>0)cooldownUntil.value=Date.now()+seconds*1000}
async function load(){
  if(stopped||invalidated)return
  const run=generation,id=++readId;clearTimeout(timer);reads++
  try{
    const result=await getCloudGuideStatus(controller.signal)
    if(stopped||invalidated||run!==generation||id!==readId)return
    if(status.value&&['queued','running'].includes(status.value.job?.state)&&!['queued','running'].includes(result.job.state))
      message.value=result.job.last_run?.outcome==='ok'?'后台检查已完成。':'后台检查已结束，请查看结果与失败项。'
    status.value=result;error.value='';now.value=Date.now();cooldown(result.job.retry_after)
  }catch(e){
    if(!stopped&&!invalidated&&run===generation&&id===readId&&e.name!=='AbortError'){error.value='无法读取攻略更新状态，请手动检查';paused.value=true;return}
  }finally{
    if(!stopped&&!invalidated&&run===generation&&id===readId&&!paused.value){
      if(reads>=120||Date.now()>=deadline)paused.value=true
      else timer=setTimeout(load,active.value?2500:30000)
    }
  }
}
async function checkNow(){
  if(stopped||invalidated||busy.value||active.value||cooling.value)return
  const run=generation;busy.value=true;error.value=message.value='';resetBudget()
  try{
    const result=await checkCloudGuides(controller.signal)
    if(stopped||invalidated||run!==generation)return
    message.value=result.state==='merged'?'已有后台检查在进行，本次请求已合并。':'已排入后台检查。'
    cooldown(result.retry_after);now.value=Date.now();await load()
  }catch(e){
    if(stopped||invalidated||run!==generation||e.name==='AbortError')return
    error.value=e.message||'无法提交检查，请稍后重试'
    if(e.status===429){cooldown(e.retryAfter);now.value=Date.now()}
  }finally{if(run===generation)busy.value=false}
}
function check(){resetBudget();now.value=Date.now();void load()}
onMounted(check)
onUnmounted(()=>{stopped=true;unsubscribe();clear()})
</script>
<template>
  <section class="cap-card cloud-guide-admin" aria-label="管理员攻略更新">
    <h2>管理员 · 攻略更新</h2>
    <p>每天北京时间清晨后台检查鸣潮角色攻略、逆境深塔与异环原帖；自动提炼的内容一律标注待校对。</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message" role="status">{{ message }}</p>
    <template v-if="status">
      <article>
        <strong>后台任务 · {{ states[job.state] || '状态未知' }}</strong>
        <p v-if="job.last_run">最近运行：{{ time(job.last_run.started_at) }}<span v-if="job.last_run.finished_at"> 至 {{ time(job.last_run.finished_at) }}</span> · {{ outcomes[job.last_run.outcome] || '结果未知' }}<span v-if="job.last_run.stop_code"> · 停止原因 {{ job.last_run.stop_code }}</span></p>
        <p v-else>尚无运行记录。</p>
        <p>下次运行：{{ time(job.next_run_at) }}</p>
      </article>
      <article>
        <strong>鸣潮角色攻略 · 已检查 {{ count(wuwa.roles_checked) }} / {{ count(wuwa.roles_total) }} 名</strong>
        <p>最早一次检查：{{ time(wuwa.checked_at_oldest) }}</p>
        <details v-if="wuwa.pending?.length" open><summary>有新帖待提炼 · {{ wuwa.pending.length }} 名</summary><p v-for="item in wuwa.pending" :key="item.character_id">{{ item.name }} · {{ item.title }} · {{ item.author }} · 发布 {{ time(item.published_at) }}</p></details>
        <p v-else-if="Array.isArray(wuwa.pending)">没有待提炼的新帖。</p>
        <details v-if="wuwa.extraction_failed?.length"><summary>提炼失败 · {{ wuwa.extraction_failed.length }} 名</summary><p>{{ wuwa.extraction_failed.map(item=>item.name).join('、') }}</p></details>
        <details v-if="wuwa.failed?.length"><summary>检查失败 · {{ wuwa.failed.length }} 名</summary><p v-for="item in wuwa.failed" :key="item.character_id">{{ item.name }} · {{ item.error_code || '原因未知' }}</p></details>
      </article>
      <article>
        <strong>逆境深塔</strong>
        <p>最近检查：{{ time(status.tower?.checked_at) }} · {{ status.tower?.current_period_covered===true?'当期已收录':status.tower?.current_period_covered===false?'当期尚未收录':'当期收录情况未知' }}<span v-if="status.tower?.error_code"> · 失败 {{ status.tower.error_code }}</span></p>
      </article>
      <article>
        <strong>异环原帖</strong>
        <p v-for="post in status.nte.posts || []" :key="post.post_id">{{ post.title }} · 读取于 {{ time(post.fetched_at) }}<span v-if="post.summary_changed"> · 原帖有更新，摘要待复核</span><span v-if="post.error"> · 最近读取失败</span><span v-else-if="post.stale"> · 待更新</span></p>
        <p v-if="!status.nte.posts?.length">尚未读取收录的原帖。</p>
      </article>
    </template>
    <p v-else-if="!error">正在读取攻略更新状态…</p>
    <p v-if="paused">自动刷新已暂停，可手动检查。</p>
    <p v-if="cooling && !active">立即检查冷却中，可于 {{ formatTime(cooldownUntil) }} 后再试。</p>
    <div class="actions"><button class="ui-button" :disabled="busy || active || cooling || !status" @click="checkNow">{{ active ? '后台检查进行中' : '立即检查' }}</button><button class="ui-button" :disabled="busy" @click="check">刷新状态</button></div>
  </section>
</template>
<style scoped>
.cloud-guide-admin{display:grid;gap:12px}.cloud-guide-admin article{display:grid;gap:6px;padding:10px 0;border-top:1px solid var(--border)}.cloud-guide-admin article strong{font-weight:500}h2,p{margin:0}h2{font-size:16px;font-weight:500;line-height:24px}p{line-height:1.65;overflow-wrap:anywhere}p[role=alert]{color:var(--danger)}summary{cursor:pointer}.actions{display:flex;flex-wrap:wrap;gap:10px}
</style>
