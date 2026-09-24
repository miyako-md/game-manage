<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { formatTime } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
const props = defineProps({ gameId: { type: String, default: '' } })
const emit = defineEmits(['collected'])
const sources = ref([]), rows = ref([]), error = ref(''), login = ref(false), showLogin = ref(false)
const sessdata = ref(''), csrf = ref(''), buvid = ref(''), selected = ref(''), decision = ref('accepted'), busy = ref(false)
const visible = computed(() => sources.value.filter(s => !props.gameId || s.game_id === props.gameId))
const filtered = computed(() => rows.value.filter(r => !decision.value || r.decision === decision.value))
const STATUS_ERROR = '无法读取B站来源状态'
let timer, stopped = false, wasRunning = false, latestLoad = 0
async function request(path, options = {}) {
  const r = await fetch(path, { ...options, headers: { 'Content-Type': 'application/json', 'X-Game-Assistant': '1' } })
  let data = null
  try { data = await r.json() } catch { /* Never show a non-JSON error page, such as a proxy's. */ }
  if (!r.ok) throw new Error(typeof data?.detail === 'string' && data.detail ? data.detail : '操作失败，请稍后重试')
  return data
}
async function load() {
  // Only the newest read may update the panel and schedule the next poll, so
  // a refresh during a timer read cannot leave two polling loops running.
  const run = ++latestLoad
  clearTimeout(timer)
  try {
    const data = await request('/api/sources/bilibili')
    if (stopped || run !== latestLoad) return
    if (error.value === STATUS_ERROR) error.value = ''
    sources.value = data.sources; login.value = data.login.configured
    const running = data.sources.some(s => s.running), finished = wasRunning && !running
    wasRunning = running
    if (finished) { emit('collected'); if (selected.value) await audit(selected.value) }
  } catch { if (!stopped && run === latestLoad) error.value = STATUS_ERROR }
  finally { if (!stopped && run === latestLoad) timer = setTimeout(load, wasRunning ? 2500 : 30000) }
}
async function refresh(game, backfill) {
  busy.value = true; error.value = ''
  try {
    await request(`/api/sources/bilibili/${game}/refresh?backfill=${backfill}`, { method: 'POST' })
    wasRunning = true; await load()
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
async function audit(game) {
  try { const data = await request(`/api/sources/bilibili/${game}/audit`); selected.value = game; rows.value = data.rows }
  catch { error.value = '无法读取筛选记录' }
}
async function saveLogin() {
  busy.value = true; error.value = ''
  try {
    await request('/api/auth/bilibili-source/credentials', { method: 'POST', body: JSON.stringify({ sessdata: sessdata.value, bili_jct: csrf.value, buvid3: buvid.value }) })
    sessdata.value = csrf.value = buvid.value = ''; login.value = true; showLogin.value = false
  } catch (e) { error.value = e.message }
  finally { busy.value = false }
}
onMounted(load)
onUnmounted(() => { stopped = true; clearTimeout(timer) })
</script>

<template>
  <section v-if="visible.length" class="bili-panel">
    <details>
      <summary>B站官方动态来源 <span>60 天回补 · 仅图文通知</span><i class="t-disclosure" aria-hidden="true">⌄</i></summary>
      <p class="muted">只收录正文有明确日期的游戏内版本、活动、卡池等通知。视频、抽奖、PV/EP、实机与时装展示自动过滤。</p>
      <p v-if="error" role="alert">{{ error }}</p>
      <div v-for="s in visible" :key="s.uid" class="bili-status">
        <strong>{{ ({ nte: '异环', wuthering_waves: '鸣潮' })[s.game_id] || s.game_id }} · UID {{ s.uid }}</strong>
        <p :class="{ warning: s.status === 'error' }" role="status">{{ s.message || '等待首次采集' }} · 已读取 {{ s.pages || 0 }} 页</p>
        <p>已保存 {{ s.total }} 条 · 收入资讯 {{ s.accepted }} 条 · {{ s.history_complete ? '60天历史已回补' : '60天历史尚未完整回补' }}</p>
        <small v-if="s.last_success">最近成功 {{ formatTime(s.last_success) }}</small>
        <small v-if="s.next_retry && s.next_retry * 1000 > Date.now()">下次可请求 {{ formatTime(s.next_retry * 1000) }}</small>
        <div class="bili-actions"><button :disabled="busy || s.running" @click="refresh(s.game_id, false)">采集新动态</button><button :disabled="busy || s.running" @click="refresh(s.game_id, true)">回补60天</button><button @click="audit(s.game_id)">查看筛选记录</button></div>
      </div>
      <button class="login-toggle" @click="showLogin = !showLogin">{{ login ? '更新B站登录信息' : '配置B站登录信息（匿名受限时）' }}</button>
      <form v-if="showLogin" @submit.prevent="saveLogin" class="bili-login">
        <p>从已登录的 bilibili.com 浏览器 Cookie 中复制。仅在本机加密保存，用于查询官方动态，不执行点赞或发送消息。</p>
        <label>SESSDATA<input v-model="sessdata" type="password" required autocomplete="off" /></label>
        <label>bili_jct（可选）<input v-model="csrf" type="password" autocomplete="off" /></label>
        <label>buvid3（可选）<input v-model="buvid" type="password" autocomplete="off" /></label>
        <button :disabled="busy" type="submit">加密保存</button>
      </form>
      <div v-if="selected" class="bili-audit">
        <label>筛选记录 <select v-model="decision"><option value="accepted">已收入资讯</option><option value="excluded">已过滤</option><option value="">全部</option></select></label>
        <p v-if="!filtered.length" class="muted">暂无符合条件的已采集记录；不代表官方没有发布。</p>
        <article v-for="r in filtered" :key="r.id"><a v-if="safeUrl(r.url)" :href="safeUrl(r.url)" target="_blank" rel="noopener noreferrer">{{ r.title || '无文字动态' }} ↗</a><small>{{ formatTime(r.published_at) }} · {{ r.reason_text }}</small><p v-if="r.time_evidence?.length">日期依据：{{ r.time_evidence.map(t => t.text).join('；') }}</p><details><summary>查看原文</summary><p class="original">{{ r.body || '无文字内容' }}</p></details></article>
      </div>
    </details>
  </section>
</template>

<style scoped>
.bili-panel { margin-top:24px; padding:20px; background:var(--card-bg); border:1px solid var(--border); border-radius:12px; font-size:12px; color:var(--text); }
summary { cursor:pointer; font-weight:550; } summary span { margin-left:12px; font-size:11px; color:var(--text-muted); } summary .t-disclosure { margin-left:10px; font-style:normal; color:var(--accent); }
p { margin-top:10px; line-height:1.7; }.muted,small { color:var(--text-muted); }.warning,[role=alert] { color:#e3ba9a; }
.bili-status { padding:16px 0; border-bottom:1px solid var(--border); }.bili-status small { display:block; margin-top:5px; }
.bili-actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:12px; }
button,select { background:var(--bg); border:1px solid var(--border); border-radius:7px; color:var(--accent); padding:7px 12px; cursor:pointer; box-shadow:var(--btn-shadow); transition:color var(--duration-quick) var(--ease-smooth-out),border-color var(--duration-quick) var(--ease-smooth-out),background-color var(--duration-quick) var(--ease-smooth-out),transform var(--duration-quick) var(--ease-smooth-out); }button:disabled { opacity:.5; cursor:wait; box-shadow:none; }button:not(:disabled):hover { border-color:#627081; background:var(--surface-soft); }button:not(:disabled):active { transform:scale(var(--scale-small)); }
.login-toggle { margin-top:16px; }.bili-login { max-width:520px; }.bili-login label { display:block; margin:12px 0; }.bili-login input { display:block; width:100%; margin-top:5px; padding:8px; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:5px; }
.bili-audit { margin-top:20px; max-height:650px; overflow:auto; }.bili-audit article { padding:14px 0; border-bottom:1px solid var(--border); }.bili-audit small { display:block; margin-top:6px; }.bili-audit a { color:var(--accent); }.bili-audit details { margin-top:8px; }.original { white-space:pre-wrap; overflow-wrap:anywhere; }
</style>
