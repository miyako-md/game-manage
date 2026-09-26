<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { createAuthSession, getAuthStatus, loginAuth, logoutAuth, sendAuthSms } from '../auth-api.js'

const emit = defineEmits(['account-changed'])
const GAMES = [{ id: 'wuthering_waves', name: '鸣潮' }, { id: 'nte', name: '异环' }]
const STATE_LABELS = { connected: '已连接', configured: '已配置', expired: '登录已失效', unconfigured: '未登录' }
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
    error.value = '登录会话已过期，请重新开始。'
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
    if (!disposed && requestId === statusGeneration) statusError.value = e.message
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
        reject(new Error('人工验证加载失败，请检查网络后重新开始。'))
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
    error.value = '人工验证加载超时，请重新开始。'
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
      error.value = captchaValidated.value ? '' : '人工验证未完成，请重试。'
    })
    instance.onError(() => {
      if (disposed || requestId !== generation || captcha !== instance) return
      captchaValidated.value = false
      error.value = '人工验证暂时不可用，请重新开始。'
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
    const data = await createAuthSession(game)
    if (disposed || requestId !== generation) return
    if (!data.session_id || !(Number(data.expires_in) > 0) || (needsCaptcha.value && !data.captcha_id)) {
      throw new Error('登录服务响应异常，请重新开始。')
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
      error.value = '请先完成人工验证。'
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
    notice.value = `${selectedName.value}登录成功，切换到手游并点击对应游戏的「刷新」加载数据。`
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
    notice.value = '已清除此游戏在本工具中的授权。'
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
})
</script>

<template>
  <section class="login-panel" aria-labelledby="accounts-title">
    <header class="panel-header">
      <div><h2 id="accounts-title">社区账号</h2><p class="muted">手机号登录，连接你的游戏数据</p></div>
      <button class="text-button" :disabled="statusLoading || !!busy" @click="refreshStatus">{{ statusLoading ? '读取中…' : '刷新状态' }}</button>
    </header>
    <div class="accounts">
      <div v-for="game in GAMES" :key="game.id" class="account-row">
        <div class="account-info">
          <strong>{{ game.name }}</strong>
          <span class="state" :class="accounts[game.id]?.state">{{ accounts[game.id] ? (STATE_LABELS[accounts[game.id].state] || '状态未知') : (statusLoading ? '读取中' : '状态未知') }}</span>
          <span v-if="accounts[game.id]?.nickname" class="nickname">{{ accounts[game.id].nickname }}</span>
          <small v-if="accounts[game.id]?.source === 'config'" class="muted">来自原有配置</small>
          <p v-if="accounts[game.id]?.message" class="account-message muted">{{ accounts[game.id].message }}</p>
        </div>
        <div class="account-actions">
          <button class="text-button" :disabled="!!busy" @click="selectGame(game.id)">{{ accounts[game.id]?.configured ? '重新登录' : '登录' }}</button>
          <button v-if="accounts[game.id]?.configured || accounts[game.id]?.state === 'expired'" class="text-button logout" :disabled="!!busy" @click="logout(game.id)">退出</button>
        </div>
      </div>
    </div>
    <p v-if="statusError" class="error" role="alert">{{ statusError }}</p>
    <form v-if="expanded" class="login-form" @submit.prevent="submitLogin">
      <div class="form-header"><h3>登录{{ selectedName }}</h3><button type="button" class="text-button" :disabled="!!busy" @click="closeForm">收起</button></div>
      <p class="muted">请使用游戏社区绑定的中国大陆手机号。退出仅清除本工具授权。</p>
      <label for="community-mobile">手机号</label>
      <input id="community-mobile" v-model.trim="mobile" type="tel" inputmode="numeric" autocomplete="tel-national" maxlength="11" placeholder="11 位中国大陆手机号" :readonly="!!busy" />
      <p v-if="mobile && !validMobile" class="field-hint">请输入有效的 11 位中国大陆手机号。</p>
      <div class="session-row">
        <button type="button" class="primary" :disabled="!!busy || !validMobile || cooldown > 0" @click="startSession">{{ busy === 'session' ? '准备中…' : (session ? '重新开始' : '开始登录') }}</button>
        <span v-if="session" class="muted">{{ expired ? '会话已过期' : `本次登录剩余 ${timeLabel}` }}</span>
        <span v-else-if="cooldown" class="muted">请 {{ cooldown }} 秒后重试</span>
      </div>
      <template v-if="session && !expired">
        <div v-if="needsCaptcha" class="captcha-area">
          <p class="muted">{{ captchaValidated ? '人工验证已完成，可以发送短信。' : (captchaReady ? '请点击下方极验组件完成人工验证。' : '正在加载人工验证…') }}</p>
          <div id="community-login-captcha"></div>
        </div>
        <label for="community-code">短信验证码</label>
        <div class="sms-row">
          <input id="community-code" v-model.trim="code" type="text" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="4–8 位数字验证码" :readonly="!!busy" />
          <button type="button" :disabled="!canSend" @click="sendSms">{{ busy === 'sms' ? '发送中…' : (cooldown ? `${cooldown} 秒后重发` : '发送验证码') }}</button>
        </div>
        <button type="submit" class="primary submit-button" :disabled="!!busy || !validMobile || !validCode">{{ busy === 'login' ? '登录中…' : '登录并保存' }}</button>
      </template>
    </form>
    <p v-if="error" class="error" :class="{ 'is-shaking': shaking }" role="alert">{{ error }}</p>
    <p v-if="notice" class="success" role="status"><svg class="t-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path class="t-check-path" d="M5 13l4 4L19 7" /></svg>{{ notice }}</p>
  </section>
</template>

<style scoped>
.login-panel { background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px; padding: 16px; box-shadow: var(--card-shadow); }
.panel-header, .form-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h2 { font-size: 16px; font-weight: 600; margin-bottom: 4px; }
h3 { font-size: 15px; font-weight: 600; }
.muted, .field-hint { color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.accounts { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.account-row { display: flex; align-items: center; justify-content: space-between; gap: 10px; border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.account-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; min-width: 0; }
.account-message { flex-basis: 100%; overflow-wrap: anywhere; }
.nickname { max-width: 180px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.account-actions { display: flex; flex-shrink: 0; gap: 6px; }
.state { font-size: 11px; font-weight: 500; line-height: 18px; border-radius: 5px; padding: 1px 7px; color: var(--text-muted); background: var(--overlay-3); }
.connected { color: var(--success); background: var(--success-bg); }
.expired { color: var(--danger); background: var(--danger-bg); }
.configured { color: var(--stale-text); background: var(--stale-bg); }
button { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-height: 32px; border: 1px solid var(--border-strong); border-radius: 7px; background: var(--card-bg); color: var(--text-body); padding: 5px 12px; font-size: 12px; font-weight: 500; line-height: 18px; cursor: pointer; box-shadow: var(--btn-shadow); transition: color var(--duration-quick) var(--ease-smooth-out), border-color var(--duration-quick) var(--ease-smooth-out), background-color var(--duration-quick) var(--ease-smooth-out), box-shadow var(--duration-quick) var(--ease-smooth-out), transform var(--duration-quick) var(--ease-smooth-out); }
@media (hover: hover) and (pointer: fine) { button:not(:disabled):hover { background: var(--button-hover-bg); color: var(--text); } }
button:not(:disabled):active { transform: scale(var(--scale-medium)); box-shadow: var(--btn-shadow-pressed); }
.text-button, .text-button:not(:disabled):hover { box-shadow: none; background: transparent; border-color: transparent; }
button:disabled { opacity: .5; cursor: not-allowed; }
button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.text-button { border: 0; color: var(--accent); min-height: 0; padding: 4px; white-space: nowrap; background: transparent; }
@media (hover: hover) and (pointer: fine) { .text-button:not(:disabled):hover { color: var(--accent-strong); } }
.logout { color: var(--text-muted); }
.primary { color: var(--accent-ink); background: var(--accent-fill); border-color: transparent; box-shadow: var(--btn-primary-shadow); }
@media (hover: hover) and (pointer: fine) { .primary:not(:disabled):hover { color: var(--accent-ink); background: var(--accent-hover); } }
.primary:not(:disabled):active { transform: scale(var(--scale-small)); box-shadow: var(--btn-primary-pressed); }
.login-form { border-top: 1px solid var(--border); margin-top: 16px; padding-top: 16px; display: flex; flex-direction: column; align-items: stretch; gap: 10px; max-width: 560px; }
label { font-size: 13px; font-weight: 600; margin-top: 4px; }
input { width: 100%; min-width: 0; border: 1px solid var(--border-strong); border-radius: 7px; padding: 9px 12px; font: inherit; color: var(--text); background: var(--card-bg); box-shadow: inset 0 1px 2px rgba(16, 24, 40, .04); }
input::placeholder { color: var(--text-faint); }
input:focus-visible { border-color: var(--accent); outline: none; box-shadow: var(--ring); }
input[readonly] { background: var(--panel-bg); }
.session-row, .sms-row { display: flex; align-items: center; gap: 12px; }
.session-row { flex-wrap: wrap; }
.sms-row button { flex-shrink: 0; }
.captcha-area { min-height: 64px; display: flex; flex-direction: column; gap: 8px; }
.submit-button { align-self: flex-start; min-width: 132px; }
.error, .success { font-size: 13px; line-height: 1.6; margin-top: 12px; overflow-wrap: anywhere; animation: t-rise var(--duration-medium) var(--ease-smooth-out) backwards; }
.success { display: flex; align-items: flex-start; gap: 8px; }
.error.is-shaking { animation: t-shake var(--duration-slow) var(--ease-smooth-out) both; }
.error { color: var(--danger); }
.success { color: var(--success); }
@media (pointer: coarse) { button:not(.text-button) { min-height: 44px; } }
@media (max-width: 640px) { .accounts { grid-template-columns: 1fr; } .login-panel { padding: 12px; } }
</style>
