<script setup>
import { ref,onMounted,onUnmounted } from 'vue'
import { subscribeSessionInvalidation } from '../http-client.js'
import CloudBilibiliCollectionControls from './CloudBilibiliCollectionControls.vue'
import { getCloudBilibiliStatus,startCloudBilibiliQr,startCloudBilibiliCookie,submitCloudBilibiliSessdata,pollCloudBilibiliQr,getCloudBilibiliSession,commitCloudBilibiliQr,cancelCloudBilibiliQr } from '../cloud-bilibili-api.js'
const account=ref(null),session=ref(null),state=ref('ready'),busy=ref(false),error=ref(''),message=ref('')
const mode=ref('cookie'),sessdata=ref(''),loadingAccount=ref(false)
let generation=0,stopped=false,timer,deadline=0,controller=new AbortController()
const labels={waiting_scan:'请使用哔哩哔哩 App 扫码',waiting_confirm:'请在哔哩哔哩 App 确认授权',verifying:'正在验证 B 站授权',pending_save:'账号已验证，等待保存',expired:'授权会话已过期，请重新开始',blocked:'本次授权已停止',cancelled:'已取消授权'}
function cancel(sid) {if(sid) void cancelCloudBilibiliQr(sid).catch(()=>{})}
function clear() {
  generation++;controller.abort();controller=new AbortController();clearTimeout(timer)
  cancel(session.value?.session_id);session.value=null;busy.value=false;sessdata.value='';loadingAccount.value=false
}
const unsubscribe=subscribeSessionInvalidation(()=>{clear();account.value=null;state.value='ready';message.value='';error.value=''})
function update(result) {
  state.value=result.state||state.value
  if(state.value==='complete') {
    account.value=result.account;clear();state.value='complete'
    message.value=result.warning||'B站授权已在云端加密保存。'
  }
}
function schedule() {
  clearTimeout(timer)
  if(!stopped && mode.value==='qr' && session.value && ['waiting_scan','waiting_confirm'].includes(state.value)) timer=setTimeout(()=>void poll(),3000)
}
async function operation(action) {
  if(stopped||busy.value)return
  const run=generation;busy.value=true;error.value=''
  try {const result=await action(controller.signal);if(!stopped&&run===generation)update(result)}
  catch(e) {if(!stopped&&run===generation&&e.name!=='AbortError') {
    error.value=e.message||'B站授权暂不可用，请稍后重试'
    state.value=e.state||'failed'
    if(e.status===410){clear();state.value='expired'}
    if(['UPSTREAM_RESTRICTED','SECURITY_VERIFICATION_REQUIRED','UNSUPPORTED_RESPONSE'].includes(e.errorCode)){clear();state.value='blocked'}
  }} finally {if(run===generation)busy.value=false}
}
async function start() {
  if(busy.value||stopped)return
  clear();mode.value='qr';error.value=message.value='';state.value='ready'
  const run=generation;busy.value=true
  try {
    const result=await startCloudBilibiliQr(controller.signal)
    if(stopped||run!==generation){cancel(result.session_id);return}
    session.value=result;state.value=result.state;deadline=Date.now()+(result.qr_expires_in||0)*1000;schedule()
  }catch(e){if(run===generation&&e.name!=='AbortError')error.value=e.message||'无法开始B站授权'}
  finally{if(run===generation)busy.value=false}
}
async function submitSessdata() {
  if(stopped||busy.value||!sessdata.value.trim())return
  let value=sessdata.value
  clear();mode.value='cookie';error.value=message.value='';state.value='verifying'
  const run=generation;busy.value=true
  try {
    const created=await startCloudBilibiliCookie(controller.signal)
    if(stopped||run!==generation){cancel(created.session_id);return}
    session.value=created
    const pending=submitCloudBilibiliSessdata(created.session_id,value,controller.signal)
    value=''
    const result=await pending
    if(!stopped&&run===generation)update(result)
  }catch(e){if(!stopped&&run===generation&&e.name!=='AbortError') {
    error.value=e.message||'B站授权验证失败，原授权已保留';state.value=e.state||'failed'
    if(e.status===410){clear();state.value='expired'}
    if(['UPSTREAM_RESTRICTED','SECURITY_VERIFICATION_REQUIRED','UNSUPPORTED_RESPONSE'].includes(e.errorCode)){clear();state.value='blocked'}
  }}finally{value='';if(run===generation)busy.value=false}
}
function useSessdata() {clear();mode.value='cookie';state.value='ready';error.value=message.value=''}
async function poll() {
  if(Date.now()>=deadline){clear();state.value='expired';return}
  const sid=session.value?.session_id;if(!sid)return
  await operation(signal=>pollCloudBilibiliQr(sid,signal));schedule()
}
async function commit() {const sid=session.value?.session_id;if(sid)await operation(signal=>commitCloudBilibiliQr(sid,signal))}
async function checkStatus() {const sid=session.value?.session_id;if(sid){await operation(signal=>getCloudBilibiliSession(sid,signal));schedule()}}
async function loadAccount() {
  const run=generation;loadingAccount.value=true
  try {
    const value=await getCloudBilibiliStatus(controller.signal)
    if(!stopped&&run===generation)account.value=value
  }catch(e){if(!stopped&&run===generation&&e.name!=='AbortError'){account.value=null;if(!error.value)error.value=e.message}}
  finally{if(run===generation)loadingAccount.value=false}
}
function close() {clear();state.value='cancelled';message.value=error.value=''}
onMounted(loadAccount)
onUnmounted(()=>{stopped=true;unsubscribe();clear()})
</script>
<template>
  <section class="cap-card cloud-bili-source" aria-label="管理员 B 站公共源授权">
    <h2>管理员 · B 站公共源授权</h2>
    <p>填写 B 站 SESSDATA（无需完整 Cookie），在云端加密保存。</p>
    <p v-if="account?.configured">当前来源账号：{{ account.nickname || account.uid || '已配置' }} · {{ account.state==='validated'?'已验证':'已配置' }}</p>
    <p v-else-if="account?.state==='storage_error'" role="alert">云端授权读取失败，无法确认是否已配置。请检查服务端密钥与存储后刷新状态。</p>
    <p v-else-if="account">尚未配置 B 站公共源授权。</p>
    <p v-else>{{ loadingAccount ? '正在读取云端授权状态…' : '云端授权状态尚未确认，请刷新状态。' }}</p>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="message || labels[state]" role="status">{{ message || labels[state] }}</p>
    <form v-if="mode==='cookie'" @submit.prevent="submitSessdata"><label>SESSDATA<input v-model="sessdata" type="password" name="sessdata" autocomplete="off" maxlength="4096" required :disabled="busy" /></label><button class="ui-button primary" :disabled="busy || !sessdata.trim()">验证并加密保存</button></form>
    <img v-if="session?.qr_image?.startsWith('data:image/png;base64,') && ['waiting_scan','waiting_confirm'].includes(state)" :src="session.qr_image" alt="B站登录二维码" width="200" height="200" />
    <div class="cloud-bili-actions"><button class="ui-button" :disabled="busy || loadingAccount" @click="loadAccount">刷新授权状态</button><button v-if="mode==='qr'" class="ui-button" @click="useSessdata">使用 SESSDATA</button><button class="ui-button" :class="{ primary: mode === 'qr' }" :disabled="busy" @click="start">{{ session && mode==='qr'?'重新生成二维码':'扫码授权 B 站' }}</button><button v-if="session" class="ui-button" @click="close">{{ mode==='qr'?'取消扫码':'取消授权' }}</button><button v-if="session && ['failed','verifying','ready'].includes(state)" class="ui-button" :disabled="busy" @click="checkStatus">检查授权状态</button><button v-if="state==='pending_save'" class="ui-button" :disabled="busy" @click="commit">重试保存</button></div>
    <CloudBilibiliCollectionControls />
  </section>
</template>
<style scoped>
.cloud-bili-source{display:grid;gap:12px}.cloud-bili-source img{background:white;padding:8px;border-radius:var(--radius-control);max-width:100%;box-sizing:border-box}.cloud-bili-actions{display:flex;gap:10px;flex-wrap:wrap}h2,p{margin:0}h2{font-size:16px;font-weight:500;line-height:24px}p{line-height:1.65}p[role=alert]{color:var(--danger)}
form,label{display:grid;gap:10px}label{font-size:13px;font-weight:500}input{box-sizing:border-box;width:100%;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--card-bg);color:var(--text);font-weight:400}form>button{justify-self:start}
</style>
