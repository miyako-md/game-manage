<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { createBilibiliSession, getBilibiliSession, cancelBilibiliSession, createBilibiliCaptcha,
  submitBilibiliPassword, sendBilibiliSms, submitBilibiliSms, pollBilibiliQr, importBilibiliCookie, commitBilibiliSession } from '../bilibili-auth-api.js'
import { loadBilibiliGeetest } from '../bilibili-geetest.js'
const props=defineProps({account:{type:Object,default:()=>({})}})
const emit=defineEmits(['account-changed','close'])
const modes=[['qr','扫码登录'],['password','账号密码'],['sms','手机号验证码'],['cookie','Cookie 导入']]
const mode=ref('qr'),session=ref(null),state=ref('ready'),busy=ref(false),error=ref(''),message=ref('')
const username=ref(''),password=ref(''),mobile=ref(''),code=ref(''),sessdata=ref(''),csrf=ref(''),buvid=ref(''),proof=ref(null)
const cooldown=ref(0),qrExpires=ref(0)
const validMobile=computed(()=>/^1[3-9][0-9]{9}$/.test(mobile.value))
const stateText=computed(()=>({waiting_scan:'等待使用哔哩哔哩 App 扫码',waiting_confirm:'已扫码，请在 App 确认',verifying:'正在验证账号',pending_save:'账号已验证，等待保存',complete:'登录账号已保存',expired:'登录已过期，请重新开始',blocked:'本次登录已停止',failed:'登录未完成，请重新验证或重试'})[state.value]||'')
let generation=0,widgetGeneration=0,proofDeadline=0,controller=new AbortController(),timer,widget,stopped=false,qrDeadline=0,cooldownDeadline=0
function destroyWidget() {widgetGeneration++;try{widget?.destroy?.()}catch{} widget=null;proof.value=null;proofDeadline=0}
function validProof() {if(!proof.value||Date.now()>=proofDeadline){destroyWidget();error.value='人工验证已过期，请重新验证';return false}return true}
function clearSecrets() {password.value=code.value=sessdata.value=csrf.value=buvid.value='';destroyWidget()}
function cancel(sid) { if(sid) void cancelBilibiliSession(sid).catch(()=>{}) }
function invalidate() {
  generation++;controller.abort();controller=new AbortController();clearTimeout(timer);cancel(session.value?.session_id)
  session.value=null;busy.value=false;clearSecrets();qrExpires.value=0
}
function schedulePoll() {
  clearTimeout(timer)
  if(stopped||mode.value!=='qr'||!session.value||!['waiting_scan','waiting_confirm'].includes(state.value))return
  timer=setTimeout(()=>void pollQr(),3000)
}
function countdown() {
  clearTimeout(timer);cooldown.value=Math.max(0,Math.ceil((cooldownDeadline-Date.now())/1000))
  if(!stopped&&cooldown.value&&mode.value==='sms')timer=setTimeout(countdown,1000)
}
function update(result) {
  state.value=result.state||state.value
  if(state.value==='complete') {
    const account=result.account;const warning=result.warning;invalidate();state.value='complete'
    message.value=warning||'账号已验证并加密保存，可手动采集动态';emit('account-changed',account)
  }
}
async function handleError(e,run) {
  if(stopped||run!==generation||e.name==='AbortError')return
  error.value=e.message||'登录失败，请稍后重试'
  if(e.retryAfter){cooldownDeadline=Date.now()+e.retryAfter*1000;cooldown.value=e.retryAfter;if(mode.value==='sms')countdown()}
  if(e.timedOut&&session.value) {
    try {const result=await getBilibiliSession(session.value.session_id,controller.signal);if(run===generation&&!stopped)update(result)}catch{}
  }
  if(e.state)state.value=e.state
  if(e.status===410) {invalidate();state.value='expired'}
  if(['UPSTREAM_RESTRICTED','SECURITY_VERIFICATION_REQUIRED','UNSUPPORTED_RESPONSE'].includes(e.errorCode)){invalidate();state.value='blocked'}
}
async function startSession() {
  if(stopped||busy.value)return
  const run=generation,selected=mode.value;busy.value=true;error.value='';message.value=''
  try {
    const result=await createBilibiliSession(selected,controller.signal)
    if(stopped||run!==generation){cancel(result.session_id);return}
    session.value=result;state.value=result.state||'ready'
    qrExpires.value=result.qr_expires_in||0;qrDeadline=Date.now()+qrExpires.value*1000
    schedulePoll()
  }catch(e){await handleError(e,run)}finally{if(run===generation)busy.value=false}
}
async function ensureSession() {if(!session.value)await startSession();return session.value?.session_id}
async function selectMode(selected) {
  if(mode.value===selected)return
  invalidate();mode.value=selected;state.value='ready';error.value=message.value='';await startSession()
  if(selected==='sms')countdown()
}
async function restart() {invalidate();state.value='ready';await startSession()}
async function operation(action) {
  if(busy.value||stopped)return
  const run=generation;const sid=await ensureSession();if(!sid||run!==generation||stopped)return
  busy.value=true;error.value=''
  try {const result=await action(sid,controller.signal);if(run===generation&&!stopped)update(result)}
  catch(e){await handleError(e,run)}finally{if(run===generation)busy.value=false}
}
async function pollQr() {
  clearTimeout(timer);qrExpires.value=Math.max(0,Math.ceil((qrDeadline-Date.now())/1000))
  if(!qrExpires.value){invalidate();state.value='expired';return}
  await operation((sid,signal)=>pollBilibiliQr(sid,signal));schedulePoll()
}
async function prepareCaptcha() {
  if(busy.value||!['password','sms'].includes(mode.value))return
  const sid=await ensureSession();if(!sid)return
  const run=generation;busy.value=true;error.value='';destroyWidget();const widgetRun=widgetGeneration
  try {
    const challenge=await createBilibiliCaptcha(sid,controller.signal)
    const initialize=await loadBilibiliGeetest()
    if(run!==generation||widgetRun!==widgetGeneration||stopped)return
    proofDeadline=Date.now()+120000
    initialize({gt:challenge.gt,challenge:challenge.challenge,offline:false,new_captcha:true,product:'bind',https:true},object=> {
      if(run!==generation||widgetRun!==widgetGeneration||stopped){object.destroy?.();return}
      widget=object
      object.onSuccess(()=>{
        if(run!==generation||widgetRun!==widgetGeneration||Date.now()>=proofDeadline||stopped)return
        const result=object.getValidate()
        // The server binds its own original challenge/token to this generation;
        // the installed SDK only consumes validate/seccode from the widget.
        if(result?.geetest_validate&&result.geetest_seccode)proof.value={validate:result.geetest_validate,seccode:result.geetest_seccode}
      })
      const failed=()=>{if(run===generation&&widgetRun===widgetGeneration&&!stopped){proof.value=null;error.value='人工验证未完成，请重新验证'}}
      object.onError(failed);object.onClose?.(()=>{if(!proof.value)failed()})
      object.onReady(()=>{if(run===generation&&widgetRun===widgetGeneration&&!stopped)object.verify()})
    })
  }catch(e){await handleError(e,run)}finally{if(run===generation)busy.value=false}
}
async function submitPassword() {
  if(!proof.value||!username.value.trim()||!password.value||busy.value)return
  if(!validProof())return
  const body={username:username.value,password:password.value,proof:proof.value};password.value='';destroyWidget()
  await operation((sid,signal)=>submitBilibiliPassword(sid,body,signal))
}
async function sendSms() {
  if(!proof.value||!validMobile.value||cooldown.value||busy.value)return
  if(!validProof())return
  const body={mobile:mobile.value,proof:proof.value};destroyWidget()
  // Reserve the local cooldown even when the network fails; the server is authoritative.
  cooldownDeadline=Date.now()+60000;countdown()
  await operation(async(sid,signal)=>{const result=await sendBilibiliSms(sid,body,signal);cooldownDeadline=Date.now()+(result.retry_after||60)*1000;countdown();return result})
}
async function submitSms() {
  if(!/^[0-9]{4,8}$/.test(code.value)||busy.value||state.value!=='sms_sent')return
  const value=code.value;code.value='';await operation((sid,signal)=>submitBilibiliSms(sid,value,signal))
}
async function importCookie() {
  if(!sessdata.value||busy.value)return
  const body={sessdata:sessdata.value,bili_jct:csrf.value,buvid3:buvid.value};clearSecrets()
  await operation((sid,signal)=>importBilibiliCookie(sid,body,signal))
}
async function retrySave() {await operation((sid,signal)=>commitBilibiliSession(sid,signal))}
function close() {invalidate();emit('close')}
watch([username,mobile],()=>{if(session.value){invalidate();state.value='ready';error.value='输入账号已变化，请重新验证';if(mode.value==='sms')countdown()}},{flush:'sync'})
onMounted(()=>void startSession())
onUnmounted(()=>{stopped=true;invalidate()})
</script>

<template>
  <section class="bili-login" aria-label="B站登录">
    <p class="login-note">用于读取B站官方动态。登录凭据仅在本机加密保存，密码和短信验证码不保存。接口可能因B站风控暂时不可用。</p>
    <p v-if="props.account.configured" class="login-note">当前账号：{{ props.account.nickname || props.account.uid || '已配置' }} · {{ props.account.state === 'validated' ? '本次运行已验证' : '已配置，尚未重新验证' }}</p>
    <nav class="login-tabs" aria-label="B站登录方式">
      <button v-for="[value,label] in modes" :key="value" type="button" :aria-pressed="mode===value" @click="selectMode(value)">{{ label }}</button>
    </nav>
    <p v-if="error" role="alert" class="login-error">{{ error }}</p>
    <p v-if="stateText || message" role="status">{{ message || stateText }}</p>
    <div v-if="state==='pending_save'">
      <p>原账号仍保留。采集结束后，在有效期内重试保存。</p>
      <button :disabled="busy" type="button" class="ui-button" @click="retrySave">重试保存</button>
    </div>
    <template v-else-if="state!=='complete'">
      <div v-if="mode==='qr'" class="qr-login">
        <img v-if="session?.qr_image?.startsWith('data:image/png;base64,')" :src="session.qr_image" alt="B站登录二维码" width="200" height="200" />
        <p v-if="qrExpires">二维码约 {{ qrExpires }} 秒内有效</p>
        <button :disabled="busy" type="button" class="ui-button" @click="restart">刷新二维码</button>
      </div>
      <form v-else-if="mode==='password'" @submit.prevent="submitPassword">
        <label>手机号 / 邮箱 / 账号<input v-model="username" maxlength="254" autocomplete="username" /></label>
        <label>密码<input v-model="password" type="password" maxlength="512" autocomplete="current-password" /></label>
        <button type="button" class="ui-button" :disabled="busy || !username.trim()" @click="prepareCaptcha">{{ proof ? '重新人工验证' : '完成人工验证' }}</button>
        <button type="submit" class="ui-button primary" :disabled="busy || !proof || !password">登录并保存</button>
      </form>
      <form v-else-if="mode==='sms'" @submit.prevent="submitSms">
        <label>中国大陆手机号 +86<input v-model="mobile" inputmode="tel" maxlength="11" autocomplete="tel-national" /></label>
        <button type="button" class="ui-button" :disabled="busy || !validMobile || cooldown>0" @click="prepareCaptcha">{{ proof ? '重新人工验证' : '完成人工验证' }}</button>
        <button type="button" class="ui-button" :disabled="busy || !validMobile || !proof || cooldown>0" @click="sendSms">{{ cooldown ? `${cooldown} 秒后重发` : '发送短信验证码' }}</button>
        <label>短信验证码<input v-model="code" inputmode="numeric" maxlength="8" autocomplete="one-time-code" /></label>
        <button type="submit" class="ui-button primary" :disabled="busy || state!=='sms_sent' || !/^[0-9]{4,8}$/.test(code)">登录并保存</button>
      </form>
      <form v-else @submit.prevent="importCookie">
        <p class="login-note">备用入口：从已登录的 bilibili.com 浏览器 Cookie 复制，验证有效后保存。</p>
        <label>SESSDATA<input v-model="sessdata" type="password" maxlength="4096" autocomplete="off" /></label>
        <label>bili_jct（可选）<input v-model="csrf" type="password" maxlength="128" autocomplete="off" /></label>
        <label>buvid3（可选）<input v-model="buvid" type="password" maxlength="256" autocomplete="off" /></label>
        <button type="submit" class="ui-button primary" :disabled="busy || !sessdata">验证并加密保存</button>
      </form>
    </template>
    <p v-if="state==='blocked'"><a href="https://passport.bilibili.com/login" target="_blank" rel="noopener noreferrer">前往B站官方登录页完成安全验证</a>，然后重新开始。</p>
    <button type="button" class="text-link close-login" @click="close">关闭登录</button>
  </section>
</template>

<style scoped>
.bili-login{max-width:480px;margin-top:10px;padding:12px;border:1px solid var(--border);border-radius:8px;}
.login-note{color:var(--text-muted);font-size:12px;line-height:1.7;}
.login-tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;}
.login-tabs button{background:var(--bg);color:var(--text);border:1px solid var(--border);padding:7px 9px;border-radius:6px;cursor:pointer;}
.login-tabs button[aria-pressed=true]{border-color:var(--accent);color:var(--accent);}
.login-error{color:var(--warning-text);}
label{display:block;margin:10px 0;color:var(--text-muted);}
input{box-sizing:border-box;display:block;width:100%;margin-top:4px;padding:7px 8px;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;}
form button{margin:4px 8px 4px 0;}.qr-login img{background:white;border-radius:8px;padding:8px;}.close-login{margin-top:12px;}
</style>
