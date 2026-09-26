<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { formatTime } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'
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
      <summary>
        B站官方动态来源
        <span>60 天回补 · 仅图文通知</span>
        <i class="t-disclosure" aria-hidden="true">⌄</i>
      </summary>
      <div class="bili-body">
        <div class="bili-intro">
          <span class="eyebrow">采集范围</span>
          <InfoHint text="只收录正文有明确日期的游戏内版本、活动、卡池等通知。视频、抽奖、PV/EP、实机与时装展示自动过滤。" />
        </div>
        <p v-if="error" role="alert" class="bili-alert">{{ error }}</p>
        <div v-for="s in visible" :key="s.uid" class="bili-status">
          <div class="bili-status-head">
            <strong>{{ ({ nte: '异环', wuthering_waves: '鸣潮' })[s.game_id] || s.game_id }} · UID {{ s.uid }}</strong>
            <span v-if="s.running" class="chip">采集中</span>
          </div>
          <p :class="{ warning: s.status === 'error' }" role="status" class="status-line">{{ s.message || '等待首次采集' }} · 已读取 {{ s.pages || 0 }} 页</p>
          <dl class="kv-list cols-2 bili-kv">
            <div><dt>已保存</dt><dd>{{ s.total }} 条</dd></div>
            <div><dt>收入资讯</dt><dd>{{ s.accepted }} 条</dd></div>
            <div><dt>历史回补</dt><dd>{{ s.history_complete ? '60天历史已回补' : '60天历史尚未完整回补' }}</dd></div>
            <div v-if="s.last_success"><dt>最近成功</dt><dd>{{ formatTime(s.last_success) }}</dd></div>
            <div v-if="s.next_retry && s.next_retry * 1000 > Date.now()"><dt>下次可请求</dt><dd>{{ formatTime(s.next_retry * 1000) }}</dd></div>
          </dl>
          <div class="bili-actions">
            <button :disabled="busy || s.running" class="ui-button small-button" @click="refresh(s.game_id, false)">采集新动态</button>
            <button :disabled="busy || s.running" class="ui-button small-button" @click="refresh(s.game_id, true)">回补60天</button>
            <button class="ui-button ghost small-button" @click="audit(s.game_id)">查看筛选记录</button>
          </div>
        </div>
        <div class="login-row">
          <button type="button" class="text-link" @click="showLogin = !showLogin">{{ login ? '更新B站登录信息' : '配置B站登录信息（匿名受限时）' }}</button>
          <InfoHint v-if="showLogin" text="从已登录的 bilibili.com 浏览器 Cookie 中复制。仅在本机加密保存，用于查询官方动态，不执行点赞或发送消息。" />
        </div>
        <form v-if="showLogin" @submit.prevent="saveLogin" class="bili-login">
          <label>SESSDATA<input v-model="sessdata" type="password" required autocomplete="off" /></label>
          <label>bili_jct（可选）<input v-model="csrf" type="password" autocomplete="off" /></label>
          <label>buvid3（可选）<input v-model="buvid" type="password" autocomplete="off" /></label>
          <button :disabled="busy" type="submit" class="ui-button primary small-button">加密保存</button>
        </form>
        <div v-if="selected" class="bili-audit">
          <div class="toolbar">
            <span class="audit-filter-label">
              筛选记录
              <MenuSelect v-model="decision" label="筛选记录" :options="[{ value: 'accepted', label: '已收入资讯' }, { value: 'excluded', label: '已过滤' }, { value: '', label: '全部' }]" />
            </span>
          </div>
          <p v-if="!filtered.length" class="muted bili-empty">暂无符合条件的已采集记录；不代表官方没有发布。</p>
          <article v-for="r in filtered" :key="r.id">
            <a v-if="safeUrl(r.url)" :href="safeUrl(r.url)" target="_blank" rel="noopener noreferrer" class="audit-title">{{ r.title || '无文字动态' }} ↗</a>
            <div class="audit-meta">
              <span class="chip">{{ r.reason_text }}</span>
              <span class="audit-date">{{ formatTime(r.published_at) }}</span>
            </div>
            <p v-if="r.time_evidence?.length" class="audit-evidence">日期依据：{{ r.time_evidence.map(t => t.text).join('；') }}</p>
            <details>
              <summary>查看原文</summary>
              <p class="original">{{ r.body || '无文字内容' }}</p>
            </details>
          </article>
        </div>
      </div>
    </details>
  </section>
</template>

<style scoped>
.bili-panel { margin-top:24px; padding:0 16px; background:var(--card-bg); border:1px solid var(--border); border-radius:12px; font-size:12px; color:var(--text); }
.bili-panel > details > summary { cursor:pointer; font-weight:600; font-size:13px; display:flex; align-items:center; gap:10px; min-height:40px; list-style:none; }
.bili-panel > details > summary::-webkit-details-marker { display:none; }
.bili-panel > details > summary span { font-size:11px; font-weight:400; color:var(--text-muted); }
.bili-panel > details > summary .t-disclosure { margin-left:auto; font-style:normal; color:var(--accent); font-size:15px; }
.bili-body { padding-bottom:14px; }
.bili-intro { display:flex; align-items:center; gap:2px; margin-bottom:8px; }
.bili-alert { margin:0 0 8px; color:var(--warning-text); }
.muted { color:var(--text-muted); }
.bili-status { padding:9px 0; border-bottom:1px solid var(--border); }
.bili-status-head { display:flex; align-items:center; gap:8px; }
.status-line { margin:4px 0 0; color:var(--text-muted); }
.status-line.warning { color:var(--warning-text); }
.bili-kv { margin:6px 0 0; }
.bili-actions { display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }
.login-row { display:flex; align-items:center; gap:6px; margin-top:12px; }
.bili-login { max-width:480px; margin-top:10px; }
.bili-login label { display:block; margin:10px 0; color:var(--text-muted); }
.bili-login input { display:block; width:100%; margin-top:4px; padding:7px 8px; background:var(--bg); color:var(--text); border:1px solid var(--border); border-radius:6px; font-size:12px; }
.bili-audit { margin-top:14px; max-height:650px; overflow:auto; }
.bili-audit .toolbar { margin:0 0 6px; }
.audit-filter-label { display:flex; align-items:center; gap:8px; color:var(--text-muted); }
.bili-empty { padding:6px 0; }
.bili-audit article { padding:9px 0; border-bottom:1px solid var(--border); }
.audit-title { color:var(--accent); font-weight:500; text-decoration:none; }
@media(hover:hover) and (pointer:fine) { .audit-title:hover { text-decoration:underline; } }
.audit-meta { display:flex; align-items:center; gap:8px; margin-top:4px; }
.audit-date { margin-left:auto; color:var(--text-faint); font-size:11px; }
.audit-evidence { margin:4px 0 0; color:var(--text-muted); font-size:11px; }
.bili-audit details { margin-top:6px; }
.original { margin:4px 0 0; white-space:pre-wrap; overflow-wrap:anywhere; line-height:1.6; color:var(--text-muted); font-size:11px; }
</style>
