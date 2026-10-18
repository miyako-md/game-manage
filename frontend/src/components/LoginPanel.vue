<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createAuthSession, getAuthStatus, loginAuth, logoutAuth, sendAuthSms } from '../auth-api.js'
import { isCloudMode } from '../http-client.js'

const emit = defineEmits(['account-changed'])
const GAMES = [{ id: 'wuthering_waves', name: '鸣潮' }, { id: 'nte', name: '异环' }, { id: 'endfield', name: '终末地' }]
const LOGIN_HINTS = { endfield: '官服与 B 服均使用鹰角通行证手机号接收短信登录。' }
const ENDFIELD_CHANNELS = [{ id: 'official', name: '官服' }, { id: 'bilibili', name: 'B 服' }]
const endfieldChannel = ref('official')
const channelName = channel => ENDFIELD_CHANNELS.find(item => item.id === channel)?.name || '渠道未提供'
const boundChannels = account => (account?.channels || (account?.channel ? [account.channel] : [])).map(channelName).join('、')
const endfieldConnectionHint = computed(() => isCloudMode() ? '登录后可在下方一键连接森空岛。' : '登录后可在终末地页面一键连接森空岛。')
const STATE_LABELS = { connected: '已登录', active: '已授权', configured: '已登录', expired: '登录已失效', revoked: '授权已撤销', unconfigured: '未登录' }
const accounts = ref({})
const statusError = ref('')
const statusLoading = ref(false)
const selectedGame = ref('wuthering_waves')
const expanded = ref(false)
const mobile = ref('')
const code = ref('')
const session = ref(null)
const busy = ref('')
const error = ref('')
const notice = ref('')
const now = ref(Date.now())
const retryUntil = ref(0)
const shaking = ref(false)
let shakeTimer = null
const captchaReady = ref(false)
const captchaValidated = ref(false)
let captcha = null
let generation = 0
let widgetGeneration = 0
let statusGeneration = 0
let disposed = false
let clockTimer = null
let statusTimer = null
let captchaTimer = null
let cancelScriptLoad = null

const selectedName = computed(() => GAMES.find((g) => g.id === selectedGame.value)?.name)
const needsCaptcha = computed(() => selectedGame.value === 'wuthering_waves')
const validMobile = computed(() => /^1[3-9]\d{9}$/.test(mobile.value))
const validCode = computed(() => /^\d{4,8}$/.test(code.value))
const remaining = computed(() => session.value ? Math.max(0, Math.ceil((session.value.expiresAt - now.value) / 1000)) : 0)
const expired = computed(() => !!session.value && remaining.value === 0)
const cooldown = computed(() => Math.max(0, Math.ceil((retryUntil.value - now.value) / 1000)))
const timeLabel = computed(() => `${Math.floor(remaining.value / 60)}:${String(remaining.value % 60).padStart(2, '0')}`)
const canSend = computed(() => !busy.value && validMobile.value && !!session.value && !expired.value && !cooldown.value && (!needsCaptcha.value || captchaValidated.value))

function destroyCaptcha() {
  widgetGeneration += 1
  if (captchaTimer) clearTimeout(captchaTimer)
  captchaTimer = null
  if (cancelScriptLoad) cancelScriptLoad()
  cancelScriptLoad = null
  if (captcha) {
    try { captcha.destroy() } catch { /* A failed external widget must not block cleanup. */ }
  }
  captcha = null
  captchaReady.value = false
  captchaValidated.value = false
}

function resetSession() {
  generation += 1
  destroyCaptcha()
  session.value = null
  code.value = ''
  error.value = ''
  notice.value = ''
  busy.value = ''
}

function selectGame(game) {
  if (busy.value) return
  resetSession()
  selectedGame.value = game
  mobile.value = ''
  expanded.value = true
  refreshStatus()
}

function selectEndfieldChannel(channel) {
  if (busy.value || endfieldChannel.value === channel) return
  resetSession()
  endfieldChannel.value = channel
}

function closeForm() {
  if (busy.value) return
  resetSession()
  mobile.value = ''
  expanded.value = false
}

watch(mobile, resetSession, { flush: 'sync' })
watch(error, (value) => {
  // A new error message shakes once; the class is cleared after the animation so it can replay.
  if (!value) return
  if (shakeTimer) clearTimeout(shakeTimer)
  shaking.value = false
  shakeTimer = setTimeout(() => { shaking.value = true; shakeTimer = setTimeout(() => { shaking.value = false }, 450) }, 0)
})
watch(expired, (value) => {
  if (value) {
    destroyCaptcha()
    error.value = '登录会话已过期，请重新登录。'
  }
})

async function refreshStatus() {
  const requestId = ++statusGeneration
  statusLoading.value = true
  try {
    const data = await getAuthStatus()
    if (disposed || requestId !== statusGeneration) return
    accounts.value = data.accounts || {}
    statusError.value = ''
  } catch (e) {
    if (!disposed && requestId === statusGeneration && e.name !== 'AbortError') statusError.value = e.message
  } finally {
    if (!disposed && requestId === statusGeneration) statusLoading.value = false
  }
}

function loadGeetest() {
  if (typeof window.initGeetest4 === 'function') return Promise.resolve()
  return new Promise((resolve, reject) => {
    let script = document.querySelector('script[data-game-assistant-geetest]')
    const created = !script
    if (created) {
      script = document.createElement('script')
      script.src = 'https://static.geetest.com/v4/gt4.js'
      script.async = true
      script.dataset.gameAssistantGeetest = 'true'
    }
    const finish = (failure) => {
      clearTimeout(timeout)
      script.removeEventListener('load', loaded)
      script.removeEventListener('error', failed)
      cancelScriptLoad = null
      if (failure) {
        script.remove()
        reject(new Error('安全验证加载失败，请检查网络后重新登录。'))
      } else resolve()
    }
    const loaded = () => finish(typeof window.initGeetest4 !== 'function')
    const failed = () => finish(true)
    const timeout = setTimeout(failed, 15000)
    cancelScriptLoad = failed
    script.addEventListener('load', loaded, { once: true })
    script.addEventListener('error', failed, { once: true })
    if (created) document.head.appendChild(script)
  })
}

async function mountCaptcha(requestId, currentSession) {
  const widgetId = widgetGeneration
  await loadGeetest()
  if (disposed || requestId !== generation || widgetId !== widgetGeneration || expired.value) return
  captchaTimer = setTimeout(() => {
    if (disposed || requestId !== generation || widgetId !== widgetGeneration) return
    destroyCaptcha()
    error.value = '安全验证加载超时，请重新登录。'
  }, 20000)
  window.initGeetest4({ captchaId: currentSession.captcha_id, product: 'float', language: 'zho' }, (instance) => {
    if (disposed || requestId !== generation || widgetId !== widgetGeneration || expired.value) {
      instance.destroy()
      return
    }
    captcha = instance
    instance.onReady(() => {
      if (disposed || requestId !== generation || captcha !== instance) return
      clearTimeout(captchaTimer)
      captchaTimer = null
      captchaReady.value = true
    })
    instance.onSuccess(() => {
      if (disposed || requestId !== generation || expired.value || captcha !== instance) return
      const proof = instance.getValidate()
      captchaValidated.value = !!(proof?.lot_number && proof?.captcha_output && proof?.pass_token && proof?.gen_time)
      error.value = captchaValidated.value ? '' : '安全验证未完成，请重试。'
    })
    instance.onError(() => {
      if (disposed || requestId !== generation || captcha !== instance) return
      captchaValidated.value = false
      error.value = '安全验证暂时不可用，请重新登录。'
    })
    instance.onFail(() => {
      if (disposed || requestId !== generation || captcha !== instance) return
      captchaValidated.value = false
    })
    instance.appendTo('#community-login-captcha')
  })
}

function handleError(e) {
  error.value = e.message || '登录失败，请稍后重试。'
  notice.value = ''
  if (e.status === 429) retryUntil.value = Date.now() + (e.retryAfter || 60) * 1000
  if (e.status === 410 && session.value) {
    session.value = { ...session.value, expiresAt: 0 }
    code.value = ''
    destroyCaptcha()
  }
}

async function startSession() {
  if (busy.value || !validMobile.value) return
  resetSession()
  const requestId = generation
  const game = selectedGame.value
  busy.value = 'session'
  try {
    const data = await createAuthSession(game, game === 'endfield' ? { channel: endfieldChannel.value } : undefined)
    if (disposed || requestId !== generation) return
    if (!data.session_id || !(Number(data.expires_in) > 0) || (needsCaptcha.value && !data.captcha_id)) {
      throw new Error('登录服务响应异常，请重新登录。')
    }
    now.value = Date.now()
    session.value = { ...data, expiresAt: now.value + Number(data.expires_in) * 1000 }
    if (needsCaptcha.value) await mountCaptcha(requestId, data)
  } catch (e) {
    if (!disposed && requestId === generation) handleError(e)
  } finally {
    if (!disposed && requestId === generation) busy.value = ''
  }
}

async function sendSms() {
  if (!canSend.value) return
  const requestId = generation
  const body = { session_id: session.value.session_id, mobile: mobile.value }
  if (needsCaptcha.value) {
    const proof = captcha?.getValidate()
    if (!captchaValidated.value || !proof?.lot_number || !proof?.captcha_output || !proof?.pass_token || !proof?.gen_time) {
      captchaValidated.value = false
      error.value = '请先完成安全验证。'
      return
    }
    body.captcha = { ...proof, captcha_id: session.value.captcha_id }
  }
  busy.value = 'sms'
  error.value = ''
  notice.value = ''
  try {
    const data = await sendAuthSms(selectedGame.value, body)
    if (disposed || requestId !== generation) return
    if (data.ok !== true) throw new Error('短信发送未成功，请重试。')
    const retry = Number(data.retry_after)
    retryUntil.value = Date.now() + (Number.isFinite(retry) && retry > 0 ? retry : 60) * 1000
    notice.value = '短信已发送，请输入验证码。'
  } catch (e) {
    if (!disposed && requestId === generation) handleError(e)
  } finally {
    if (!disposed && requestId === generation) {
      busy.value = ''
      // A proof is single-use; retry SMS on this same session/device with a new human challenge.
      if (needsCaptcha.value && captcha) {
        captchaValidated.value = false
        try { captcha.reset() } catch { destroyCaptcha() }
      }
    }
  }
}

async function submitLogin() {
  if (busy.value || !validMobile.value || !validCode.value || !session.value || expired.value) return
  const requestId = generation
  const game = selectedGame.value
  busy.value = 'login'
  error.value = ''
  notice.value = ''
  try {
    const data = await loginAuth(game, { session_id: session.value.session_id, mobile: mobile.value, code: code.value })
    if (disposed || requestId !== generation) return
    if (data.ok !== true) throw new Error('登录未成功，请重试。')
    statusGeneration += 1
    if (data.account) accounts.value = { ...accounts.value, [game]: data.account }
    resetSession()
    mobile.value = ''
    expanded.value = false
    notice.value = game === 'endfield' ? `终末地${channelName(endfieldChannel.value)}登录成功。` : `${selectedName.value}登录成功。`
    emit('account-changed', { game, loggedIn: true })
    await refreshStatus()
  } catch (e) {
    if (!disposed && requestId === generation) handleError(e)
  } finally {
    if (!disposed && requestId === generation) busy.value = ''
  }
}

async function logout(game) {
  if (busy.value) return
  resetSession()
  mobile.value = ''
  expanded.value = false
  const requestId = generation
  busy.value = 'logout'
  try {
    const data = await logoutAuth(game)
    if (disposed || requestId !== generation) return
    if (data.ok !== true) throw new Error('退出未成功，请重试。')
    statusGeneration += 1
    accounts.value = { ...accounts.value, [game]: data.account || { configured: false, state: 'unconfigured', source: 'none' } }
    notice.value = '已退出登录'
    emit('account-changed', { game, loggedIn: false })
    await refreshStatus()
  } catch (e) {
    if (!disposed && requestId === generation) handleError(e)
  } finally {
    if (!disposed && requestId === generation) busy.value = ''
  }
}

onMounted(() => {
  refreshStatus()
  clockTimer = setInterval(() => { now.value = Date.now() }, 1000)
  statusTimer = setInterval(() => {
    if (!busy.value && !statusLoading.value) refreshStatus()
  }, 60000)
})
onBeforeUnmount(() => {
  disposed = true
  generation += 1
  statusGeneration += 1
  clearInterval(clockTimer)
  clearInterval(statusTimer)
  if (shakeTimer) clearTimeout(shakeTimer)
  destroyCaptcha()
  mobile.value = ''; code.value = ''; session.value = null; accounts.value = {}
})
</script>

<template>
  <section class="login-panel" aria-labelledby="accounts-title">
    <header class="panel-header">
      <div><h2 id="accounts-title">社区账号</h2></div>
      <button class="text-button" :disabled="statusLoading || !!busy" @click="refreshStatus">{{ statusLoading ? '读取中…' : '刷新状态' }}</button>
    </header>
    <div class="accounts">
      <div v-for="game in GAMES" :key="game.id" class="account-row" :data-game="game.id">
        <div class="account-info">
          <strong>{{ game.name }}</strong>
          <span class="account-mark" aria-hidden="true">{{ game.name.slice(0, 1) }}</span>
          <span class="state" :class="accounts[game.id]?.state">{{ accounts[game.id] ? (STATE_LABELS[accounts[game.id].state] || '状态未知') : (statusLoading ? '读取中' : '状态未知') }}</span>
          <span v-if="accounts[game.id]?.nickname" class="nickname">{{ accounts[game.id].nickname }}</span>
          <small v-if="game.id === 'endfield' && accounts[game.id]?.configured && boundChannels(accounts[game.id])" class="muted">已登录：{{ boundChannels(accounts[game.id]) }}</small>
          <small v-if="game.id === 'endfield' && accounts[game.id]?.account_count > 1" class="muted">在下方按账号管理授权</small>
          <small v-if="accounts[game.id]?.source === 'config'" class="muted">来自原有配置</small>
          <p v-if="accounts[game.id]?.message" class="account-message muted">{{ accounts[game.id].message }}</p>
        </div>
        <div class="account-actions">
          <button class="text-button" :disabled="!!busy" @click="selectGame(game.id)">{{ accounts[game.id]?.configured ? '重新登录' : '登录' }}</button>
          <button v-if="(accounts[game.id]?.configured || accounts[game.id]?.state === 'expired') && !(game.id === 'endfield' && accounts[game.id]?.account_count > 1)" class="text-button logout" :disabled="!!busy" @click="logout(game.id)">退出</button>
        </div>
      </div>
    </div>
    <p v-if="statusError" class="error" role="alert">{{ statusError }}</p>
    <form v-if="expanded" class="login-form" @submit.prevent="submitLogin">
      <div class="form-header"><h3>登录{{ selectedName }}</h3><button type="button" class="text-button" :disabled="!!busy" @click="closeForm">收起</button></div>
      <p v-if="LOGIN_HINTS[selectedGame] || selectedGame === 'endfield'" class="muted">{{ LOGIN_HINTS[selectedGame] || '' }}{{ selectedGame === 'endfield' ? endfieldConnectionHint : '' }}</p>
      <fieldset v-if="selectedGame === 'endfield'" class="channel-selector" :disabled="!!busy">
        <legend>游戏渠道</legend>
        <div class="channel-options"><button v-for="channel in ENDFIELD_CHANNELS" :key="channel.id" type="button" :aria-pressed="endfieldChannel === channel.id" :disabled="!!busy" @click="selectEndfieldChannel(channel.id)">{{ channel.name }}</button></div>
      </fieldset>
      <div v-if="selectedGame === 'endfield' && endfieldChannel === 'bilibili'" class="binding-guide">
        <p>首次登录 B 服前，请先在鹰角官网绑定游戏角色：</p>
        <ol><li>打开<a href="https://user.hypergryph.com/bindCharacters?game=endfield" target="_blank" rel="noopener noreferrer">鹰角角色绑定页面</a>，登录鹰角通行证。</li><li>选择 bilibili 服，填写游戏 UID 并通过游戏内邮件验证码完成绑定。</li><li>回到本页，使用该鹰角通行证的手机号登录。</li></ol>
        <p class="muted">此处使用鹰角短信登录，无需填写 B 站 SESSDATA。</p>
      </div>
      <label for="community-mobile">手机号</label>
      <input id="community-mobile" v-model.trim="mobile" type="tel" inputmode="numeric" autocomplete="tel-national" maxlength="11" placeholder="11 位中国大陆手机号" :readonly="!!busy" />
      <p v-if="mobile && !validMobile" class="field-hint">请输入有效的 11 位中国大陆手机号。</p>
      <div class="session-row">
        <button type="button" class="primary" :disabled="!!busy || !validMobile || cooldown > 0" @click="startSession">{{ busy === 'session' ? '准备中…' : (session ? '重新登录' : '开始登录') }}</button>
        <span v-if="session" class="muted">{{ expired ? '会话已过期' : `剩余 ${timeLabel}` }}</span>
        <span v-else-if="cooldown" class="muted">请 {{ cooldown }} 秒后重试</span>
      </div>
      <template v-if="session && !expired">
        <div v-if="needsCaptcha" class="captcha-area">
          <p class="muted">{{ captchaValidated ? '验证通过' : (captchaReady ? '请完成安全验证' : '正在加载安全验证…') }}</p>
          <div id="community-login-captcha"></div>
        </div>
        <label for="community-code">短信验证码</label>
        <div class="sms-row">
          <input id="community-code" v-model.trim="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="4–8 位数字验证码" :readonly="!!busy" />
          <button type="button" :disabled="!canSend" @click="sendSms">{{ busy === 'sms' ? '发送中…' : (cooldown ? `${cooldown} 秒后重发` : '发送验证码') }}</button>
        </div>
        <button type="submit" class="primary submit-button" :disabled="!!busy || !validMobile || !validCode">{{ busy === 'login' ? '登录中…' : '登录' }}</button>
      </template>
    </form>
    <p v-if="error" class="error" :class="{ 'is-shaking': shaking }" role="alert">{{ error }}</p>
    <p v-if="notice" class="success" role="status"><svg class="t-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="t-check-path" d="M5 13l4 4L19 7" /></svg>{{ notice }}</p>
  </section>
</template>

<style scoped>
.login-panel { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: var(--radius-card); box-shadow: var(--card-shadow); padding: 20px; }
.panel-header, .form-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h2 { font-size: 17px; font-weight: 600; letter-spacing: -.01em; margin-bottom: 4px; }
h3 { font-size: 15px; font-weight: 600; }
.muted, .field-hint { color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.accounts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: 12px; margin-top: 14px; }
/* Each game is a white row with a hairline and its mark on the game's pale tone. */
.account-row { --mark-tone: var(--control-track); --mark-ink: var(--text); position: relative; display: flex; align-items: center; justify-content: space-between; gap: 10px; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius-tile); background: var(--card-bg); padding: 14px; }
.account-row[data-game="wuthering_waves"] { --mark-tone: var(--game-wuwa-tone); --mark-ink: var(--game-wuwa); }
.account-row[data-game="nte"] { --mark-tone: var(--game-nte-tone); --mark-ink: var(--game-nte); }
.account-row[data-game="endfield"] { --mark-tone: var(--game-endfield-tone); --mark-ink: var(--game-endfield); }
.account-info { position: relative; display: flex; align-items: center; gap: 8px 10px; flex-wrap: wrap; min-width: 0; }
/* Placed after the name in the markup (the name leads the row's text); drawn first. */
.account-mark { order: -1; display: grid; place-items: center; width: 38px; height: 38px; flex-shrink: 0; border: 3px solid var(--card-bg); border-radius: 13px; background: var(--mark-tone); box-shadow: 0 0 0 1px var(--card-border); color: var(--mark-ink); font-size: 15px; font-weight: 600; }
.account-info > strong { font-size: 15px; font-weight: 600; }
.account-message { flex-basis: 100%; overflow-wrap: anywhere; }
.nickname { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: var(--text-muted); }
.account-actions { position: relative; display: flex; flex-shrink: 0; gap: 6px; }
.state { font-size: 12px; font-weight: 500; line-height: 22px; border-radius: var(--radius-chip); padding: 0 10px; color: var(--text-muted); background: var(--card-bg); }
.connected, .active { color: var(--success); background: var(--success-bg); }
.expired, .revoked { color: var(--danger); background: var(--danger-bg); }
.configured { color: var(--stale-text); background: var(--stale-bg); }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 36px; border: 1px solid var(--border); border-radius: var(--radius-control); background: var(--card-bg); box-shadow: var(--btn-shadow); color: var(--text); padding: 6px 14px; font-size: 13px; font-weight: 500; line-height: 20px; cursor: pointer; transition: color var(--duration-quick) var(--ease-smooth-out), border-color var(--duration-quick) var(--ease-smooth-out), background-color var(--duration-quick) var(--ease-smooth-out), transform var(--duration-quick) var(--ease-smooth-out); }
@media (hover: hover) and (pointer: fine) { button:not(:disabled):hover { background: var(--button-hover-bg); color: var(--text); } }
button:not(:disabled):active { transform: translateY(1px); }
.text-button, .text-button:not(:disabled):hover { background: transparent; border-color: transparent; box-shadow: none; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.text-button { border: 0; color: var(--accent); min-height: 0; padding: 4px 6px; white-space: nowrap; }
@media (hover: hover) and (pointer: fine) { .text-button:not(:disabled):hover { color: var(--accent-strong); } }
.account-actions .text-button { min-height: 36px; padding: 6px 13px; border: 1px solid var(--border); border-radius: 10px; background: var(--card-bg); box-shadow: none; }
@media (hover: hover) and (pointer: fine) { .account-actions .text-button:not(:disabled):hover { background: var(--panel-bg); border-color: var(--border-strong); } }
.logout { color: var(--text-muted); }
.primary { color: var(--accent-ink); background: var(--accent-fill); border-color: var(--accent-fill); box-shadow: none; }
@media (hover: hover) and (pointer: fine) { .primary:not(:disabled):hover { color: var(--accent-ink); background: var(--accent-hover); } }
.primary:not(:disabled):active { transform: translateY(1px); }
.login-form { margin-top: 18px; padding: 18px; display: flex; flex-direction: column; align-items: stretch; gap: 10px; max-width: 600px; border: 1px solid var(--border); border-radius: var(--radius-tile); background: var(--panel-bg); }
.channel-selector { margin: 0; padding: 0; border: 0; min-width: 0; }
.channel-selector legend { font-size: 13px; font-weight: 500; margin-bottom: 8px; }
.channel-options { display: flex; gap: 8px; }
.channel-options button { flex: 1; }
.channel-options button[aria-pressed="true"] { border-color: var(--accent); color: var(--accent); background: var(--card-bg); }
.binding-guide { font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
.binding-guide ol { margin: 8px 0; padding-left: 20px; }
.binding-guide a { color: var(--accent); text-decoration: underline; }
label { font-size: 13px; font-weight: 500; margin-top: 4px; }
input { width: 100%; min-width: 0; min-height: 44px; border: 1px solid var(--border); border-radius: var(--radius-control); padding: 10px 13px; font: inherit; color: var(--text); background: var(--card-bg); box-shadow: none; }
input::placeholder { color: var(--text-faint); }
input:focus-visible { border-color: var(--accent); outline: none; box-shadow: var(--ring); }
input[readonly] { background: var(--panel-bg); }
.session-row, .sms-row { display: flex; align-items: center; gap: 12px; }
.session-row { flex-wrap: wrap; }
.sms-row button { flex-shrink: 0; min-height: 44px; }
.captcha-area { min-height: 64px; display: flex; flex-direction: column; gap: 8px; }
.submit-button { align-self: flex-start; min-width: 132px; min-height: 40px; }
.error, .success { font-size: 13px; line-height: 1.6; margin-top: 12px; overflow-wrap: anywhere; animation: t-rise var(--duration-medium) var(--ease-smooth-out) backwards; }
.success { display: flex; align-items: flex-start; gap: 8px; }
.error.is-shaking { animation: t-shake var(--duration-slow) var(--ease-smooth-out) both; }
.error { color: var(--danger); }
.success { color: var(--success); }
@media (pointer: coarse) { button:not(.text-button) { min-height: 44px; } }
@media (max-width: 640px) { .login-panel { padding: 16px; } .login-form { padding: 14px; } }
</style>
