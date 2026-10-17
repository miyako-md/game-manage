<script setup>
import { computed, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useDialog } from '../use-dialog.js'
import { canApplySystemUpdate, createSystemUpdateController, systemUpdateReason, systemUpdateStatus, updateIsRunning, updateIsVerified } from '../system-update-controller.js'
import AppIcon from './AppIcon.vue'
const emit = defineEmits(['close'])
const headingId = `system-update-${useId()}`
const confirmId = `${headingId}-confirm`
const controller = createSystemUpdateController()
const { state } = controller
const { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded } = useDialog(() => emit('close'))
const confirmTarget = ref('')
const shortSha = sha => sha ? sha.slice(0, 7) : '未知'
const status = computed(() => systemUpdateStatus(state))
const canApply = computed(() => canApplySystemUpdate(state))
const running = computed(() => updateIsRunning(state.snapshot))
const verified = computed(() => updateIsVerified(state))
const reason = computed(() => systemUpdateReason(state.snapshot?.unavailable_reason))
const latestUrl = computed(() => state.snapshot?.latest?.sha ? `https://github.com/miyako-md/game-manage/commit/${state.snapshot.latest.sha}` : '')
const canCheck = computed(() => !state.operation && !state.uncertain && !running.value && !state.sessionEnded)
const showsApply = computed(() => state.snapshot?.relation === 'ahead' && state.snapshot?.can_apply === true)
function date(value) {
  if (!value) return '时间未提供'
  const stamp = new Date(value)
  return Number.isNaN(stamp.getTime()) ? '时间未提供' : new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(stamp)
}
function close() { controller.destroy(); requestClose() }
function clickBackdrop(event) { backdropClick(event); if (closing.value) controller.destroy() }
function askUpdate() { if (canApply.value) confirmTarget.value = state.snapshot.latest.sha }
async function confirmUpdate() {
  const target = confirmTarget.value
  if (!target || !canApply.value) return
  confirmTarget.value = ''
  await controller.apply(target)
}
function refreshPage() { if (verified.value) globalThis.window?.location?.reload() }
watch(() => state.snapshot?.latest?.sha, () => { confirmTarget.value = '' })
watch(() => state.sessionEnded, ended => { if (ended) confirmTarget.value = '' })
onMounted(controller.start)
onBeforeUnmount(controller.destroy)
</script>
<template>
  <dialog ref="dialog" class="system-update-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" :aria-labelledby="headingId" @cancel.prevent="close" @pointerdown="backdropDown" @click="clickBackdrop" @animationend="animationEnded">
    <header class="update-heading"><h2 :id="headingId">系统更新</h2><button class="icon-button" type="button" aria-label="关闭系统更新" autofocus @click="close"><AppIcon name="close" :size="18" /></button></header>
    <div class="update-body">
      <p class="update-intro">检查主分支（main）的最新版本。</p>
      <dl class="update-versions">
        <div><dt>当前版本</dt><dd><code>{{ shortSha(state.snapshot?.current?.sha) }}</code><span v-if="state.snapshot?.current?.dirty" class="update-note">安装目录有本地修改</span></dd></div>
        <div><dt>主分支最新提交</dt><dd><a v-if="latestUrl" :href="latestUrl" target="_blank" rel="noopener noreferrer"><code>{{ shortSha(state.snapshot.latest.sha) }}</code><AppIcon name="arrow" :size="13" /></a><span v-else>尚未检查</span><p v-if="state.snapshot?.latest?.message" class="update-commit-title">{{ state.snapshot.latest.message }}</p><time v-if="state.snapshot?.latest" class="update-note" :datetime="state.snapshot.latest.committed_at">{{ date(state.snapshot.latest.committed_at) }}</time></dd></div>
      </dl>
      <div class="update-status" :class="{ 'is-verified': verified && !showsApply }"><AppIcon :name="verified && !showsApply ? 'check' : running || state.operation ? 'refresh' : 'info'" :class="{ spinning: running || !!state.operation }" :size="18" /><p role="status" aria-live="polite" aria-atomic="true">{{ status }}</p></div>
      <p v-if="state.error && !state.connectionLost" role="alert" class="update-error">{{ state.error }}</p>
      <p v-if="reason && !running && !verified && !state.uncertain" class="update-note">{{ reason }}</p>
      <p v-if="state.snapshot?.job" class="update-note">目标版本 <code>{{ shortSha(state.snapshot.job.target_sha) }}</code><template v-if="state.snapshot.job.error_code"> · {{ systemUpdateReason(state.snapshot.job.error_code) }}</template></p>
      <p class="update-note">更新时服务会短暂重启；完成后可手动刷新页面。</p>
      <section v-if="confirmTarget" class="update-confirm" role="group" :aria-labelledby="confirmId"><h3 :id="confirmId">更新到 <code>{{ shortSha(confirmTarget) }}</code>？</h3><p>请先保存正在编辑的内容。</p><div class="update-actions"><button class="ui-button" type="button" @click="confirmTarget = ''">暂不更新</button><button class="ui-button primary" type="button" :disabled="!canApply" @click="confirmUpdate">确认更新</button></div></section>
      <footer class="update-actions">
        <button v-if="state.timedOut || state.readFailed" class="ui-button" type="button" :disabled="!!state.operation || state.sessionEnded" @click="controller.retryStatus">重新读取状态</button>
        <button class="ui-button" type="button" :disabled="!canCheck" @click="controller.check">{{ state.operation === 'checking' ? '正在检查…' : '检查更新' }}</button>
        <button v-if="showsApply && !confirmTarget" class="ui-button primary" type="button" :disabled="!canApply" @click="askUpdate">更新到此版本</button>
        <button v-if="verified && !showsApply" class="ui-button primary" type="button" @click="refreshPage">刷新页面</button>
      </footer>
    </div>
  </dialog>
</template>
<style scoped>
.system-update-dialog { position:fixed; inset:0; width:min(560px,calc(100vw - 24px)); max-width:none; max-height:calc(100dvh - 24px); height:fit-content; margin:auto; padding:0; overflow:auto; overscroll-behavior:contain; border:1px solid var(--card-border); border-radius:var(--radius-card); background:var(--card-bg); color:var(--text); box-shadow:var(--popover-shadow); }
.system-update-dialog::backdrop { background:var(--scrim); }
.update-heading { position:sticky; top:0; z-index:1; display:flex; align-items:center; justify-content:space-between; gap:16px; padding:14px 20px; border-bottom:1px solid var(--border); background:var(--card-bg); }
.update-heading h2 { margin:0; font-size:20px; line-height:28px; font-weight:600; letter-spacing:-.03em; }
.update-body { padding:20px; }
.update-intro { margin:0 0 20px; color:var(--text-muted); font-size:13px; }
.update-versions { margin:0; display:grid; gap:18px; }
.update-versions>div { display:grid; grid-template-columns:116px minmax(0,1fr); gap:12px; }
.update-versions dt { color:var(--text-muted); font-size:13px; line-height:22px; }
.update-versions dd { min-width:0; margin:0; font-size:14px; line-height:22px; }
.update-versions a { display:inline-flex; align-items:center; gap:6px; color:var(--accent); text-decoration:none; }
.update-commit-title { margin:4px 0; overflow-wrap:anywhere; white-space:pre-wrap; font-size:14px; }
.update-note { display:block; margin:8px 0 0; color:var(--text-muted); font-size:12px; line-height:1.7; overflow-wrap:anywhere; }
.update-status { display:flex; align-items:flex-start; gap:10px; margin:24px 0 12px; padding:14px; border:1px solid var(--border); border-radius:var(--radius-control); background:var(--panel-bg); }
.update-status>svg { margin-top:2px; flex-shrink:0; }
.update-status p { margin:0; font-size:14px; line-height:22px; }
.is-verified { color:var(--text); }
.update-error { margin:10px 0; color:var(--danger); font-size:13px; line-height:1.7; }
.update-actions { display:flex; flex-wrap:wrap; justify-content:flex-end; gap:10px; margin-top:22px; }
.update-actions button,.update-heading button { min-width:44px; min-height:44px; }
.update-confirm { margin-top:20px; padding:16px; border:1px solid var(--border-strong); border-radius:var(--radius-control); background:var(--panel-bg); }
.update-confirm h3 { margin:0; font-size:15px; font-weight:600; }
.update-confirm p { margin:8px 0 0; color:var(--text-muted); font-size:13px; line-height:1.7; }
code { font-size:13px; font-variant-numeric:tabular-nums; }
@media(max-width:480px) { .update-heading { padding:12px 16px; }.update-body { padding:16px; }.update-versions>div { grid-template-columns:minmax(0,1fr); gap:4px; }.update-actions button { flex:1 1 auto; } }
</style>
