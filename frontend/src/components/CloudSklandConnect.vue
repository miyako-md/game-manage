<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { connectCloudSkland, connectCloudSklandPassport } from '../accounts-api.js'
import { isCloudMode, subscribeSessionInvalidation } from '../http-client.js'
const props = defineProps({ accounts: { type: Array, default: () => [] }, userId: { type: String, required: true } })
const emit = defineEmits(['changed'])
const accountId = ref(''), roleId = ref(''), cred = ref(''), deviceId = ref('')
const busy = ref(''), error = ref(''), success = ref('')
// The accounts endpoint returns only the website user's verified roles. An
// explicit owner, when supplied, must still match the current website session.
const sources = computed(() => props.accounts.filter(account => account.provider === 'hypergryph' && account.game === 'endfield' && account.state === 'active' && (!account.user_id || account.user_id === props.userId)))
const source = computed(() => sources.value.find(account => account.account_id === accountId.value))
const roles = computed(() => source.value?.roles || [])
const role = computed(() => roles.value.find(item => item.role_id === roleId.value))
const canConnect = computed(() => isCloudMode() && !!props.userId && !!source.value && !!role.value && !busy.value)
const sourceStamp = computed(() => JSON.stringify([props.userId, source.value?.account_id, source.value?.grant_id, source.value?.version, source.value?.state, roles.value, roleId.value]))
let operation = 0, controller = null
function clear() { operation++; controller?.abort(); controller = null; busy.value = ''; error.value = ''; success.value = ''; cred.value = ''; deviceId.value = '' }
watch(sourceStamp, clear, { flush: 'sync' })
watch(() => props.userId, () => { accountId.value = ''; roleId.value = ''; clear() }, { flush: 'sync' })
function chooseAccount(value) { accountId.value = value; roleId.value = ''; clear() }
function chooseRole(value) { roleId.value = value; clear() }
async function run(kind, request) {
  if (busy.value || !isCloudMode() || !props.userId) return
  const id = ++operation, owner = props.userId, stamp = sourceStamp.value
  controller = new AbortController(); const signal = controller.signal
  busy.value = kind; error.value = ''; success.value = ''
  const current = () => id === operation && owner === props.userId && stamp === sourceStamp.value
  try {
    await request(signal)
    if (!current()) return
    success.value = '森空岛档案已连接。'
    emit('changed')
  } catch (failure) {
    if (!current() || failure.name === 'AbortError') return
    error.value = failure.status === 409 && failure.code === 'skland_role_mismatch'
      ? '所选鹰角角色与森空岛角色不匹配，请核对后重试，或使用下方手动授权。'
      : failure.status === 409 && failure.code === 'authorization_changed'
        ? '来源授权已变化，请刷新后重新选择；已有授权已保留。'
        : (failure.name === 'HttpError' ? failure.message : '连接失败，请稍后重试') + '；已有授权已保留，可使用下方手动授权。'
  } finally { if (current()) { busy.value = ''; controller = null } }
}
function connectPassport() {
  if (!canConnect.value) return
  const id = accountId.value, selectedRole = roleId.value
  return run('passport', signal => connectCloudSklandPassport(id, selectedRole, { signal }))
}
function connectManual() {
  if (busy.value || !cred.value.trim()) return
  const bodyCred = cred.value.trim(), bodyDevice = deviceId.value.trim()
  cred.value = ''; deviceId.value = ''
  return run('manual', signal => connectCloudSkland(bodyCred, bodyDevice, { signal }))
}
const stop = subscribeSessionInvalidation(clear)
// The Endfield authorization guide links here with #/accounts?focus=skland.
const panel = ref(null)
onMounted(() => { if (/[?&]focus=skland(?:&|$)/.test(globalThis.location?.hash || '')) panel.value?.scrollIntoView?.({ block: 'start' }) })
onBeforeUnmount(() => { stop(); clear() })
</script>
<template>
  <section v-if="isCloudMode()" ref="panel" class="cap-card cloud-skland" aria-label="森空岛档案授权">
    <h2>终末地 · 森空岛档案授权</h2>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="success" role="status">{{ success }}</p>
    <form aria-label="通过鹰角授权连接森空岛" @submit.prevent="connectPassport">
      <label>来源鹰角授权<MenuSelect class="skland-source-menu" label="用于连接森空岛的鹰角授权" :model-value="accountId" :disabled="!!busy" :options="[{value:'',label:'请选择鹰角授权'},...sources.map((account,index) => ({value:account.account_id,label:`鹰角授权 ${index + 1} · ${account.roles?.find(item => item.is_default)?.display_name || account.roles?.[0]?.display_name || '未命名角色'}`}))]" @change="chooseAccount" /></label>
      <label>来源角色<MenuSelect class="skland-source-menu" label="用于连接森空岛的鹰角角色" :model-value="roleId" :disabled="!!busy || !source" :options="[{value:'',label:'请选择角色'},...roles.map((item,index) => ({value:item.role_id,label:`${item.display_name || `角色 ${index + 1}`}${item.is_default ? '（鹰角默认）' : ''}`}))]" @change="chooseRole" /></label>
      <p v-if="!sources.length">暂无可用的鹰角授权，请先在上方登录，或使用手动授权。</p><p v-else-if="source && !roles.length">此鹰角授权暂无可用角色，请重新授权或使用手动授权。</p>
      <button class="ui-button primary" :disabled="!canConnect">{{ busy === 'passport' ? '连接中…' : '一键连接森空岛档案' }}</button>
    </form>
    <details><summary>手动授权（备用）</summary>
      <form aria-label="手动连接森空岛" @submit.prevent="connectManual"><label>森空岛 cred<input v-model="cred" type="password" autocomplete="off" required maxlength="4096" :disabled="!!busy" /></label><label>设备标识（可选）<input v-model="deviceId" autocomplete="off" maxlength="512" :disabled="!!busy" /></label><button class="ui-button" :disabled="!!busy || !cred.trim()">{{ busy === 'manual' ? '连接中…' : '手动连接森空岛档案' }}</button></form>
    </details>
  </section>
</template>
<style scoped>
.cloud-skland,.cloud-skland form,.cloud-skland details{display:grid;gap:14px}.cloud-skland label{display:grid;gap:7px;font-size:13px;font-weight:500}.cloud-skland form>button{justify-self:start}.cloud-skland input{width:100%;box-sizing:border-box;min-width:0;padding:9px 12px;border:1px solid var(--border);border-radius:var(--radius-control);background:var(--card-bg);color:var(--text);font-weight:400}.skland-source-menu{width:100%;min-width:0}.skland-source-menu :deep(.menu-select-trigger){width:100%;min-width:0;min-height:40px;font-weight:400}h2,p{margin:0}h2{font-size:16px;font-weight:500;line-height:24px}summary{cursor:pointer}p[role=alert]{color:var(--danger);overflow-wrap:anywhere}
</style>
