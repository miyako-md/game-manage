<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { vGlide } from '../motion.js'
import { formatTime } from '../dashboard.js'
import {
  getPublic, refreshPublic, getMap, getMapMark, getSklandStatus, connectSkland, chooseSklandRole,
  disconnectSkland, getSklandCard, refreshSklandCard, getAttendance, signAttendance,
  getChallenges, getSklandTools, getSklandOperator, getBlueprints, exportBlueprints, saveBlueprint, updateBlueprint, deleteBlueprint, safeExternalUrl,
} from '../endfield-tools-api.js'
import AppIcon from './AppIcon.vue'
import EndfieldGachaPanel from './EndfieldGachaPanel.vue'
import AnnouncementList from './AnnouncementList.vue'

const props = defineProps({ snaps: { type: Object, default: () => ({}) }, initialSection: { type: String, default: 'overview' } })
const emit = defineEmits(['calendar'])
const tabs = [
  ['overview', '概览'], ['operators', '干员与探索'], ['challenges', '挑战记录'],
  ['gacha', '抽卡统计'], ['map', '地图与图鉴'], ['blueprints', '蓝图收藏'], ['news', '公告与资讯'],
]
const section = ref(tabs.some(([id]) => id === props.initialSection) ? props.initialSection : 'overview')
const status = ref(null), statusBusy = ref(false), statusError = ref('')
const card = ref(null), cardBusy = ref(false), cardError = ref('')
const operatorDetail = ref(null), operatorDetailId = ref(''), operatorBusy = ref(false), operatorError = ref(''), operatorStale = ref(false)
const attendance = ref(null), attendanceBusy = ref(false), attendanceError = ref('')
const challengeKind = ref('war'), challenge = ref(null), challengeBusy = ref(false), challengeError = ref('')
const publicData = ref(null), publicBusy = ref(false), publicError = ref('')
const map = ref(null), mapBusy = ref(false), mapError = ref('')
const markDetail = ref(null), markBusy = ref(false), markError = ref('')
const mapId = ref(''), levelId = ref(''), typeId = ref(''), mapQuery = ref(''), submittedQuery = ref(''), mapOffset = ref(0)
const toolKind = ref('characters'), toolQuery = ref(''), toolPage = ref(0), toolData = ref(null), toolBusy = ref(false), toolError = ref('')
const blueprints = ref([]), blueprintBusy = ref(false), blueprintError = ref(''), editingId = ref(null)
const blueprintName = ref(''), blueprintCode = ref(''), blueprintNotes = ref('')
const cred = ref(''), deviceId = ref(''), actionBusy = ref(false), actionError = ref(''), actionMessage = ref('')
let statusSeq = 0, privateSeq = 0, attendanceSeq = 0, operatorSeq = 0, challengeSeq = 0, mapSeq = 0, markSeq = 0, toolSeq = 0, publicSeq = 0, blueprintsSeq = 0
let mapController = null
let destroyed = false

const connected = computed(() => !!status.value?.connected)
const selectedRole = computed(() => status.value?.roles?.find(role => String(role.role_id) === String(status.value.selected_role_id) && String(role.server_id) === String(status.value.selected_server_id)))
const roleKey = computed(() => selectedRole.value ? `${selectedRole.value.role_id}:${selectedRole.value.server_id}` : '')
const originalAccount = computed(() => props.snaps.account?.payload || null)
const gachaAccountId = computed(() => originalAccount.value?.role_id == null ? '' : String(originalAccount.value.role_id))
const cardPayload = computed(() => card.value?.payload || null)
const display = value => value === null || value === undefined || value === '' ? '未知' : String(value)
const dateText = value => value ? formatTime(value) : '未知'
const list = value => Array.isArray(value) ? value : []
const humanError = value => typeof value === 'string' ? value : value ? '暂时无法读取，请稍后重试。' : ''
const roleLabel = role => `${role.nickname || '未命名角色'} · ${role.role_id} / ${role.server_id}`
const named = value => typeof value === 'string' ? value : (value?.name || value?.title || '未知')
const regionSummary = item => `等级 ${display(item.level)} · ${list(item.levels).length} 个区域 · ${list(item.settlements).length} 处据点`
const shipSummary = item => `${item.name || '舱室'} · 等级 ${display(item.level)} · ${list(item.operators).length} 名干员`
const countPair = item => `${display(item?.count)} / ${display(item?.total)}`
const passText = item => item?.isPass === true ? '已通关' : item?.isPass === false ? '未通关' : '状态未知'
const stageList = group => ['normalDungeon', 'hardDungeon', 'cruelDungeon'].flatMap(key => group?.[key] ? [{ ...group[key], difficulty: {normalDungeon:'普通', hardDungeon:'困难', cruelDungeon:'险境'}[key] }] : [])
const challengeResult = (item, kind) => kind === 'war' ? `${display(item.stars)} 星` : kind === 'monument' ? `${list(item.groups).length} 组` : display(item.score ?? item.grade ?? item.result)
const roleValue = computed(() => roleKey.value)
const publicNews = computed(() => list(publicData.value?.news?.items))
const signedDays = computed(() => list(attendance.value?.calendar).filter(item => item.done).length)
const officialTools = computed(() => list(publicData.value?.tools).filter(item => safeExternalUrl(item.url)))
const selectedMap = computed(() => list(map.value?.maps).find(item => String(item.id) === String(mapId.value)))
const toolKinds = [
  ['characters', '干员'], ['weapons', '武器'], ['equipment', '装备'],
  ['tactical', '战术物品'], ['materials', '养成材料'],
]
function materialRows(payload) {
  const seen = new Set(), result = []
  for (const key of ['materials', 'charExpMaterials', 'weaponExpMaterials']) {
    const entries = payload?.[key]
    if (!entries || typeof entries !== 'object' || Array.isArray(entries)) continue
    for (const item of Object.values(entries)) {
      if (!item || typeof item !== 'object') continue
      const id = String(item.id ?? '')
      if (id && seen.has(id)) continue
      if (id) seen.add(id)
      result.push(item)
    }
  }
  return result
}
const rawToolRows = computed(() => {
  const payload = toolData.value?.payload
  if (toolKind.value === 'materials') return materialRows(payload)
  const key = { characters: 'chars', weapons: 'weapons', equipment: 'equips', tactical: 'tacticalItems' }[toolKind.value]
  return list(payload?.[key])
})
const toolRows = computed(() => rawToolRows.value.filter(item => {
  if (!toolQuery.value.trim()) return true
  return [item.name, item.id].some(value => String(value ?? '').toLowerCase().includes(toolQuery.value.trim().toLowerCase()))
}))
const toolPageRows = computed(() => toolRows.value.slice(toolPage.value * 20, (toolPage.value + 1) * 20))
const sourceLabel = value => value && typeof value === 'object' ? display(value.value ?? value.name ?? value.key) : display(value)
const toolSummary = item => {
  if (toolKind.value === 'characters') return [sourceLabel(item.rarity), sourceLabel(item.property), sourceLabel(item.profession)].filter(value => value !== '未知').join(' · ')
  if (toolKind.value === 'weapons') return [sourceLabel(item.rarity), sourceLabel(item.type)].filter(value => value !== '未知').join(' · ')
  if (toolKind.value === 'equipment') return [sourceLabel(item.rarity), sourceLabel(item.type), sourceLabel(item.level)].filter(value => value !== '未知').join(' · ')
  if (toolKind.value === 'tactical') return sourceLabel(item.rarity)
  return sourceLabel(item.rarity)
}
const toolDescription = item => {
  if (toolKind.value === 'weapons') return item.description || item.function || ''
  if (toolKind.value === 'equipment') return item.function || ''
  if (toolKind.value === 'tactical') return item.activeEffect || item.passiveEffect || ''
  return ''
}

async function loadStatus() {
  const seq = ++statusSeq
  statusBusy.value = true; statusError.value = ''
  try {
    const data = await getSklandStatus()
    if (destroyed || seq !== statusSeq) return
    status.value = data
    statusError.value = humanError(data.error)
  } catch (error) { if (seq === statusSeq) statusError.value = error.message }
  finally { if (seq === statusSeq) statusBusy.value = false }
}
function clearPrivate() {
  ++privateSeq; ++operatorSeq; ++challengeSeq
  ++attendanceSeq; attendanceBusy.value = false
  cardBusy.value = false; operatorBusy.value = false; challengeBusy.value = false; toolBusy.value = false
  ++toolSeq; toolData.value = null; toolError.value = ''
  card.value = null; cardError.value = ''; attendance.value = null; attendanceError.value = ''
  operatorDetail.value = null; operatorDetailId.value = ''; operatorError.value = ''; operatorStale.value = false
  challenge.value = null; challengeError.value = ''
}
async function loadOperator(id) {
  if (!id || !roleKey.value) return
  const seq = ++operatorSeq, owner = roleKey.value
  operatorDetailId.value = String(id); operatorDetail.value = null; operatorError.value = ''; operatorStale.value = false; operatorBusy.value = true
  try {
    const data = await getSklandOperator(id)
    if (destroyed || seq !== operatorSeq || owner !== roleKey.value) return
    operatorDetail.value = data.operator || null; operatorStale.value = !!data.stale; operatorError.value = humanError(data.error)
    if (!operatorDetail.value && !operatorError.value) operatorError.value = '暂时无法读取这名干员的配装。'
  } catch (error) { if (seq === operatorSeq) operatorError.value = error.message }
  finally { if (seq === operatorSeq) operatorBusy.value = false }
}
async function loadTool() {
  if (!roleKey.value) { toolError.value = '请先连接并选择森空岛角色。'; return }
  const seq = ++toolSeq, owner = roleKey.value, kind = toolKind.value
  toolBusy.value = true; toolError.value = ''; toolData.value = null
  try {
    const data = await getSklandTools(kind)
    if (destroyed || seq !== toolSeq || owner !== roleKey.value || kind !== toolKind.value) return
    toolData.value = data; toolError.value = humanError(data.error)
  } catch (error) { if (seq === toolSeq) toolError.value = error.message }
  finally { if (seq === toolSeq) toolBusy.value = false }
}
async function loadCard(refresh = false) {
  if (!roleKey.value) return
  const seq = ++privateSeq, owner = roleKey.value
  cardBusy.value = true; cardError.value = ''
  try {
    const data = refresh ? await refreshSklandCard() : await getSklandCard()
    if (destroyed || seq !== privateSeq || owner !== roleKey.value) return
    card.value = data; cardError.value = humanError(data.error)
  } catch (error) { if (seq === privateSeq && owner === roleKey.value) cardError.value = error.message }
  finally { if (seq === privateSeq) cardBusy.value = false }
}
async function loadAttendance(sign = false) {
  if (!roleKey.value) return
  const seq = ++attendanceSeq, owner = roleKey.value
  attendanceBusy.value = true; attendanceError.value = ''
  try {
    const data = sign ? await signAttendance() : await getAttendance()
    if (destroyed || seq !== attendanceSeq || owner !== roleKey.value) return
    attendance.value = data; attendanceError.value = humanError(data.error)
  } catch (error) { if (seq === attendanceSeq && owner === roleKey.value) attendanceError.value = error.message }
  finally { if (seq === attendanceSeq) attendanceBusy.value = false }
}
async function loadChallenge() {
  if (!roleKey.value) return
  const seq = ++challengeSeq, kind = challengeKind.value, owner = roleKey.value
  challengeBusy.value = true; challengeError.value = ''; challenge.value = null
  try {
    const data = await getChallenges(kind)
    if (destroyed || seq !== challengeSeq || owner !== roleKey.value || kind !== challengeKind.value) return
    challenge.value = data; challengeError.value = humanError(data.error)
  } catch (error) { if (seq === challengeSeq) challengeError.value = error.message }
  finally { if (seq === challengeSeq) challengeBusy.value = false }
}
async function loadPublic(refresh = false) {
  const seq = ++publicSeq
  publicBusy.value = true; publicError.value = ''
  try {
    const data = refresh ? await refreshPublic() : await getPublic()
    if (destroyed || seq !== publicSeq) return
    publicData.value = data; publicError.value = humanError(data.news?.error)
  } catch (error) { if (seq === publicSeq) publicError.value = error.message }
  finally { if (seq === publicSeq) publicBusy.value = false }
}
async function loadMap() {
  mapController?.abort()
  ++markSeq; markDetail.value = null; markError.value = ''; markBusy.value = false
  mapController = new AbortController()
  const seq = ++mapSeq
  mapBusy.value = true; mapError.value = ''
  if (map.value) map.value = { ...map.value, marks: [], total: 0 }
  try {
    const data = await getMap({ map_id: mapId.value, level_id: levelId.value, type_id: typeId.value, q: submittedQuery.value, offset: mapOffset.value, limit: 100 }, mapController.signal)
    if (destroyed || seq !== mapSeq) return
    map.value = data; mapError.value = humanError(data.error)
    if (!mapId.value && list(data.maps).length) mapId.value = data.maps[0].id
  } catch (error) { if (seq === mapSeq && error.name !== 'AbortError') mapError.value = error.message }
  finally { if (seq === mapSeq) mapBusy.value = false }
}
async function loadMark(mark) {
  if (!mapId.value || !mark.id) return
  const seq = ++markSeq, owner = mapId.value
  markBusy.value = true; markError.value = ''; markDetail.value = null
  try {
    const data = await getMapMark(owner, mark.id)
    if (destroyed || seq !== markSeq || owner !== mapId.value) return
    markDetail.value = data.info; markError.value = humanError(data.error)
  } catch (error) { if (seq === markSeq) markError.value = error.message }
  finally { if (seq === markSeq) markBusy.value = false }
}
async function loadBlueprints() {
  const seq = ++blueprintsSeq
  blueprintBusy.value = true; blueprintError.value = ''
  try {
    const data = await getBlueprints()
    if (destroyed || seq !== blueprintsSeq) return
    blueprints.value = list(data.items)
  } catch (error) { if (seq === blueprintsSeq) blueprintError.value = error.message }
  finally { if (seq === blueprintsSeq) blueprintBusy.value = false }
}
async function connect() {
  if (!cred.value.trim()) return
  actionBusy.value = true; actionError.value = ''; actionMessage.value = ''
  try {
    const data = await connectSkland(cred.value.trim(), deviceId.value.trim())
    cred.value = ''; deviceId.value = ''; clearPrivate(); status.value = data
    actionMessage.value = '森空岛账号已连接。'
  } catch (error) { actionError.value = error.message }
  finally { actionBusy.value = false }
}
async function selectRole(event) {
  const role = status.value?.roles?.find(item => `${item.role_id}:${item.server_id}` === event.target.value)
  if (!role || event.target.value === roleKey.value) return
  clearPrivate(); actionBusy.value = true; actionError.value = ''; actionMessage.value = ''
  try { status.value = await chooseSklandRole(role.role_id, role.server_id) }
  catch (error) { actionError.value = error.message; await loadStatus(); if (roleKey.value) { loadCard(); if (section.value === 'overview') loadAttendance() } }
  finally { actionBusy.value = false }
}
async function disconnect() {
  actionBusy.value = true; actionError.value = ''; actionMessage.value = ''; clearPrivate()
  try { status.value = await disconnectSkland(); actionMessage.value = '已断开森空岛连接。' }
  catch (error) { actionError.value = error.message; await loadStatus(); if (roleKey.value) { loadCard(); if (section.value === 'overview') loadAttendance() } }
  finally { actionBusy.value = false }
}
function editBlueprint(item) {
  editingId.value = item.id; blueprintName.value = item.name || ''; blueprintCode.value = item.code || ''; blueprintNotes.value = item.notes || ''
}
function resetBlueprint() { editingId.value = null; blueprintName.value = ''; blueprintCode.value = ''; blueprintNotes.value = '' }
async function submitBlueprint() {
  const item = { name: blueprintName.value.trim(), code: blueprintCode.value.trim(), notes: blueprintNotes.value.trim() }
  if (!item.name || !item.code) { blueprintError.value = '请填写名称和分享码。'; return }
  blueprintBusy.value = true; blueprintError.value = ''
  try {
    if (editingId.value === null) await saveBlueprint(item)
    else await updateBlueprint(editingId.value, item)
    resetBlueprint(); await loadBlueprints()
  } catch (error) { blueprintError.value = error.message }
  finally { blueprintBusy.value = false }
}
async function removeBlueprint(id) {
  blueprintBusy.value = true; blueprintError.value = ''
  try { await deleteBlueprint(id); if (editingId.value === id) resetBlueprint(); await loadBlueprints() }
  catch (error) { blueprintError.value = error.message }
  finally { blueprintBusy.value = false }
}
async function copyCode(code) {
  try { await navigator.clipboard.writeText(code); actionMessage.value = '分享码已复制。' }
  catch { blueprintError.value = '复制失败，请手动选取分享码。' }
}
async function downloadBlueprints() {
  try {
    const data = await exportBlueprints()
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = 'endfield-blueprints.json'; link.click(); URL.revokeObjectURL(url)
  } catch (error) { blueprintError.value = error.message }
}
function submitMapSearch() { submittedQuery.value = mapQuery.value.trim(); if (mapOffset.value) mapOffset.value = 0; else loadMap() }

watch(roleValue, (next, previous) => {
  if (next === previous) return
  clearPrivate()
  if (next && ['overview', 'operators'].includes(section.value)) { loadCard(); if (section.value === 'overview') loadAttendance() }
  if (next && section.value === 'challenges') loadChallenge()
})
watch(section, current => {
  if (current === 'overview' || current === 'operators') { if (roleKey.value && !card.value) loadCard(); if (current === 'overview' && roleKey.value && !attendance.value) loadAttendance() }
  if (current === 'challenges' && roleKey.value) loadChallenge()
  if (current === 'map') { if (!publicData.value) loadPublic(); if (!map.value) loadMap() }
  if (current === 'blueprints') loadBlueprints()
  if (current === 'news' && !publicData.value) loadPublic()
})
watch([mapId, levelId, typeId], (current, previous) => {
  if (current[0] !== previous[0] && (levelId.value || typeId.value)) { levelId.value = ''; typeId.value = ''; return }
  if (mapOffset.value) { mapOffset.value = 0; return }
  if (section.value === 'map') loadMap()
})
watch(mapOffset, () => { if (section.value === 'map') loadMap() })
watch(challengeKind, () => { if (section.value === 'challenges') loadChallenge() })
watch(toolKind, () => { ++toolSeq; toolBusy.value = false; toolData.value = null; toolError.value = ''; toolQuery.value = ''; toolPage.value = 0 })
watch(toolQuery, () => { toolPage.value = 0 })
onMounted(() => { loadStatus(); if (section.value === 'map') { loadPublic(); loadMap() } if (section.value === 'blueprints') loadBlueprints(); if (section.value === 'news') loadPublic() })
onUnmounted(() => { destroyed = true; mapController?.abort(); ++statusSeq; ++privateSeq; ++operatorSeq; ++challengeSeq; ++mapSeq; ++markSeq; ++toolSeq; ++publicSeq; ++blueprintsSeq })
</script>

<template>
  <div class="endfield-dashboard">
    <div class="endfield-nav"><nav v-glide class="segmented" aria-label="终末地数据分区"><button v-for="[id, label] in tabs" :key="id" type="button" :aria-pressed="section === id" @click="section = id">{{ label }}</button></nav><button type="button" class="text-link" @click="emit('calendar')"><AppIcon name="calendar" :size="15" />活动日历<AppIcon name="arrow" :size="15" /></button></div>

    <div v-if="['overview','operators','challenges'].includes(section)" class="endfield-stack">
      <section class="cap-card"><div class="cap-title">森空岛档案<span v-if="card?.stale" class="badge badge-stale">数据可能过期</span></div>
        <p v-if="statusBusy" class="hint" role="status">正在读取连接状态…</p>
        <p v-if="statusError" class="error" role="alert">{{ statusError }}</p>
        <form v-if="!statusBusy && !connected" class="field-grid" @submit.prevent="connect">
          <p class="hint">连接森空岛后，可查看理智、干员、探索和挑战记录。凭据只在本机加密保存。</p>
          <label>森空岛凭据<input v-model="cred" type="password" required autocomplete="off" placeholder="填写 cred" /></label>
          <label>官方设备标识（可选）<input v-model="deviceId" type="password" autocomplete="off" placeholder="已有设备标识时填写" /></label>
          <button type="submit" class="ui-button" :disabled="actionBusy">{{ actionBusy ? '连接中…' : '连接森空岛' }}</button>
        </form>
        <div v-else-if="connected" class="role-bar"><label>森空岛角色<select :value="roleKey" :disabled="actionBusy" @change="selectRole"><option value="">请选择角色</option><option v-for="role in list(status.roles)" :key="`${role.role_id}:${role.server_id}`" :value="`${role.role_id}:${role.server_id}`">{{ roleLabel(role) }}</option></select></label><button type="button" class="ui-button" :disabled="actionBusy || !roleKey || cardBusy" @click="loadCard(true)"><AppIcon name="refresh" :size="14" />手动刷新档案</button><button type="button" class="ui-button" :disabled="actionBusy" @click="disconnect">断开</button></div>
        <p v-if="connected && !roleKey" class="hint">请选择一个森空岛角色。</p>
        <p v-if="roleKey" class="hint">当前森空岛档案：{{ roleLabel(selectedRole) }}。寻访统计使用下方单独标明的通行证账号。</p>
        <p v-if="actionError" class="error" role="alert">{{ actionError }}</p><p v-if="actionMessage" class="hint" role="status">{{ actionMessage }}</p>
      </section>

      <template v-if="section === 'overview'">
        <section class="cap-card"><div class="cap-title">寻访账号<span v-if="snaps.account?.stale" class="badge badge-stale">数据可能过期</span></div><p class="hint">寻访记录所属账号，与上方森空岛角色分别管理。</p><p class="identity">{{ originalAccount?.nickname || '未知昵称' }} · 角色编号 {{ display(originalAccount?.role_id) }}</p></section>
        <template v-if="roleKey"><p v-if="cardBusy" class="hint" role="status">正在读取档案…</p><p v-if="cardError" class="error" role="alert">{{ cardError }}</p>
          <div v-if="cardPayload" class="endfield-grid">
            <section class="cap-card"><div class="cap-title">账号与理智<span v-if="card?.fetched_at" class="cap-meta">更新于 {{ dateText(card.fetched_at) }}</span></div><p class="identity">{{ cardPayload.base?.name || selectedRole?.nickname || '未知昵称' }} · 等级 {{ display(cardPayload.base?.level) }}</p><dl class="fact-list"><div><dt>理智</dt><dd>{{ display(cardPayload.stamina?.current) }} / {{ display(cardPayload.stamina?.maximum) }}</dd></div><div><dt>预计回满</dt><dd>{{ dateText(cardPayload.stamina?.expected_full_at) }}</dd></div><div><dt>数据时间</dt><dd>{{ dateText(cardPayload.stamina?.updated_at) }}</dd></div></dl></section>
            <section class="cap-card"><div class="cap-title">每日与通行证进度</div><p v-if="!list(cardPayload.progress).length" class="empty">暂无进度数据</p><ul v-else class="plain-list"><li v-for="(item, i) in list(cardPayload.progress)" :key="i"><span>{{ named(item) }}</span><strong>{{ display(item.cur) }} / {{ display(item.total) }}</strong></li></ul></section>
          </div><p v-else-if="!cardBusy && !cardError" class="empty cap-card">暂无档案数据，请手动刷新。</p>
          <section class="cap-card"><div class="cap-title">每日签到<span v-if="attendance?.stale" class="badge badge-stale">数据可能过期</span></div>
            <p v-if="attendanceBusy" class="hint" role="status">正在读取签到状态…</p>
            <p v-if="attendanceError" class="error" role="alert">{{ attendanceError }}</p>
            <p v-if="attendance?.supported === false" class="hint">当前账号暂不支持签到。</p>
            <template v-else>
              <div class="attendance-summary"><strong>{{ { signed: '今日已签', unsigned: '今日待签', unknown: '状态未知' }[attendance?.status] || '尚未读取' }}</strong><span v-if="list(attendance?.calendar).length">本期已签 {{ signedDays }} 天</span></div>
              <p v-if="attendance?.today_award" class="hint">今日奖励：{{ named(attendance.today_award) }}<template v-if="attendance.today_award.count != null"> × {{ attendance.today_award.count }}</template></p>
              <p v-if="attendance?.updated_at" class="hint">更新于 {{ dateText(attendance.updated_at) }}</p>
              <button type="button" class="ui-button" :disabled="attendanceBusy || attendance?.status === 'signed'" @click="loadAttendance(true)">手动签到</button>
            </template>
          </section>
        </template>
      </template>

      <template v-if="section === 'operators' && roleKey"><p v-if="cardBusy" class="hint" role="status">正在读取干员与探索…</p><p v-if="cardError" class="error" role="alert">{{ cardError }}</p><template v-if="cardPayload"><section class="cap-card"><div class="cap-title">干员</div><p v-if="!list(cardPayload.operators).length" class="empty">暂无干员数据</p><div v-else class="operator-grid"><article v-for="(operator, i) in list(cardPayload.operators)" :key="operator.id || i" class="inner-card operator-item">
          <h3>{{ display(operator.name) }}<span class="muted">{{ display(operator.rarity) }}★</span></h3>
          <p>等级 {{ display(operator.level) }} · 潜能 {{ display(operator.potential) }}</p>
          <p v-if="operator.profession || operator.property">{{ display(operator.profession) }} · {{ display(operator.property) }}</p>
          <button type="button" class="ui-button" :disabled="operatorBusy || !operator.id" @click="loadOperator(operator.id)">查看配装</button>
          <template v-if="operatorDetailId === String(operator.id)">
            <p v-if="operatorBusy" class="hint" role="status">正在读取干员配装…</p>
            <p v-if="operatorError" class="error" role="alert">{{ operatorError }}</p>
            <span v-if="operatorStale" class="badge badge-stale">配装数据可能过期</span>
            <div v-if="operatorDetail" class="operator-detail">
              <p>武器：{{ named(operatorDetail.weapon) }} · 等级 {{ display(operatorDetail.weapon?.level) }} · 精炼 {{ display(operatorDetail.weapon?.refine_level) }}</p>
              <p v-if="operatorDetail.weapon?.gem">镶嵌：{{ named(operatorDetail.weapon.gem) }}<span v-if="list(operatorDetail.weapon.gem.terms).length"> · {{ list(operatorDetail.weapon.gem.terms).map(term => `${display(term.name)} ${display(term.cost)}`).join('、') }}</span></p>
              <p>装备：{{ list(operatorDetail.equipment).length ? list(operatorDetail.equipment).map(item => `${named(item)}（等级 ${display(item.level)}）`).join('、') : '未知' }}</p>
              <p>技能：{{ list(operatorDetail.skills).length ? list(operatorDetail.skills).map(skill => `${named(skill)}（等级 ${display(skill.level)}）`).join('、') : '未知' }}</p>
            </div>
          </template>
        </article></div></section>
        <div class="endfield-grid">
          <section class="cap-card"><div class="cap-title">地区探索与建设</div><p v-if="!list(cardPayload.regions).length" class="empty">暂无地区数据</p>
            <details v-for="(item, i) in list(cardPayload.regions)" :key="i" class="record-detail" open>
              <summary>{{ named(item) }}<span class="hint">{{ regionSummary(item) }}</span></summary>
              <p v-if="item.money?.count != null || item.money?.total != null" class="hint">调度券：{{ countPair(item.money) }}</p>
              <ul class="plain-list"><li v-for="settlement in list(item.settlements)" :key="settlement.id"><span>{{ settlement.name || settlement.id || '据点' }}</span><span>等级 {{ display(settlement.level) }} · 资金 {{ display(settlement.money) }} / {{ display(settlement.money_max) }}</span></li></ul>
              <div v-for="level in list(item.levels)" :key="level.id" class="inner-card"><h3>{{ level.name || level.id || '区域' }}</h3><p>谜质 {{ countPair(level.puzzles) }} · 储藏箱 {{ countPair(level.chests) }}</p><p>装备箱 {{ countPair(level.equipment_chests) }} · 维修点 {{ countPair(level.pieces) }} · 黑匣子 {{ countPair(level.blackboxes) }}</p></div>
              <p v-for="entry in list(item.collections)" :key="entry.level_id" class="hint">{{ entry.level_id || '区域收集' }}：谜质 {{ display(entry.puzzle_count) }} · 储藏箱 {{ display(entry.chest_count) }} · 维修点 {{ display(entry.piece_count) }} · 黑匣子 {{ display(entry.blackbox_count) }}</p>
            </details>
          </section>
          <section class="cap-card"><div class="cap-title">帝江号</div><p v-if="!list(cardPayload.ship).length" class="empty">暂无帝江号数据</p>
            <details v-for="(item, i) in list(cardPayload.ship)" :key="i" class="record-detail"><summary>{{ shipSummary(item) }}</summary><ul class="plain-list"><li v-for="(operator, index) in list(item.operators)" :key="index"><span>{{ operator.name || operator.charId || '驻守干员' }}</span><span>体力 {{ display(operator.physicalStrength) }} · 好感度 {{ display(operator.favorability) }}</span></li></ul><p v-if="!list(item.operators).length" class="hint">暂无驻守干员</p></details>
          </section>
        </div>
        <section class="cap-card"><div class="cap-title">成就</div><p v-if="cardPayload.achievements?.count == null && !list(cardPayload.achievements?.medals).length" class="empty">暂无成就数据</p><ul v-else class="plain-list"><li><span>成就总数</span><strong>{{ display(cardPayload.achievements?.count) }}</strong></li><li><span>勋章</span><strong>{{ list(cardPayload.achievements?.medals).length }}</strong></li></ul></section></template></template>

      <template v-if="section === 'challenges' && roleKey"><section class="cap-card"><div class="cap-title">挑战记录<span v-if="challenge?.stale" class="badge badge-stale">数据可能过期</span></div><div class="segmented" aria-label="挑战类型"><button v-for="[key,label] in [['war','战争'],['monument','丰碑'],['crisis','危机']]" :key="key" type="button" :aria-pressed="challengeKind === key" @click="challengeKind = key">{{ label }}</button></div><p v-if="challengeBusy" class="hint" role="status">正在读取挑战记录…</p><p v-if="challengeError" class="error" role="alert">{{ challengeError }}</p><p v-if="challenge?.supported === false" class="empty">当前账号暂不支持这项挑战。</p><p v-if="challengeKind === 'crisis' && challenge?.summary?.highest != null" class="hint">历史最高：{{ challenge.summary.highest }} · 挑战次数：{{ display(challenge.summary.challenge_count) }}</p><p v-if="challengeKind === 'war' && list(challenge?.summary?.honors).length" class="hint">已获得 {{ list(challenge.summary.honors).length }} 项荣誉。</p><p v-if="!challengeBusy && !list(challenge?.records).length && challenge?.supported !== false" class="empty">暂无挑战记录</p><div v-else><details v-for="(item, i) in list(challenge?.records)" :key="i" class="record-detail" open><summary>{{ item.name || (item.id ? '记录 ' + item.id : '挑战记录') }}<strong>{{ challengeResult(item, challengeKind) }}</strong></summary><p v-if="item.start_at || item.end_at" class="hint">{{ dateText(item.start_at) }} — {{ dateText(item.end_at) }}</p><div v-for="week in list(item.weeks)" :key="week.id" class="inner-card"><h3>{{ week.name || week.id || '轮换' }} · {{ display(week.stars) }} 星</h3><div v-for="(group, j) in list(week.groups)" :key="j"><p>{{ group.name || '关卡' }} · {{ display(group.star) }} 星</p><p v-for="stage in stageList(group)" :key="stage.id || stage.difficulty" class="hint">{{ stage.difficulty }}：{{ stage.name || '关卡' }} · {{ passText(stage) }}</p></div></div><div v-for="(group, j) in list(item.groups)" :key="j" class="inner-card"><p>{{ group.name || '关卡组' }}</p><p v-for="stage in stageList(group)" :key="stage.id || stage.difficulty" class="hint">{{ stage.difficulty }}：{{ stage.name || '关卡' }} · {{ passText(stage) }}</p></div><p v-if="challengeKind === 'crisis'" class="hint">{{ passText(item) }}</p></details></div></section></template>
    </div>

    <div v-else-if="section === 'gacha'" class="endfield-stack"><section class="cap-card"><div class="cap-title">寻访账号<span v-if="snaps.gacha?.stale" class="badge badge-stale">寻访数据可能过期</span></div><p class="identity">{{ originalAccount?.nickname || '未知昵称' }} · 角色编号 {{ display(originalAccount?.role_id) }}</p></section><EndfieldGachaPanel :snap="snaps.gacha" :account-id="gachaAccountId" /></div>

    <div v-else-if="section === 'map'" class="endfield-stack"><section class="cap-card"><div class="cap-title">官方地图</div><form class="map-filters" @submit.prevent="submitMapSearch"><label>地图<select v-model="mapId"><option value="">请选择地图</option><option v-for="item in list(map?.maps)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>区域<select v-model="levelId"><option value="">默认区域</option><option v-for="item in list(selectedMap?.levels)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>点位类型<select v-model="typeId"><option value="">全部类型</option><option v-for="item in list(map?.categories)" :key="item.id" :value="item.id">{{ item.name }}</option></select></label><label>搜索点位<input v-model="mapQuery" type="search" placeholder="输入名称" /></label><button type="submit" class="ui-button" :disabled="mapBusy">搜索</button></form><p v-if="mapBusy" class="hint" role="status">正在读取地图点位…</p><p v-if="mapError" class="error" role="alert">{{ mapError }}</p><p v-if="map?.stale" class="badge badge-stale">地图数据可能过期</p><p v-if="!mapBusy && !list(map?.marks).length" class="empty">暂无匹配点位</p><ul v-else class="mark-list"><li v-for="(mark, i) in list(map?.marks)" :key="mark.id || i"><div><strong>{{ display(mark.name) }}</strong><p class="hint">坐标 {{ display(mark.x) }}，{{ display(mark.y) }}，{{ display(mark.z) }}<span v-if="mark.description"> · {{ mark.description }}</span></p></div><div class="actions"><button type="button" class="ui-button" :disabled="markBusy" @click="loadMark(mark)">查看详情</button><a v-if="safeExternalUrl(mark.url)" :href="safeExternalUrl(mark.url)" target="_blank" rel="noopener noreferrer">官方地图<AppIcon name="arrow" :size="14" /></a></div></li></ul><section v-if="markDetail || markBusy || markError" class="inner-card mark-detail"><p v-if="markBusy" class="hint" role="status">正在读取点位详情…</p><p v-if="markError" class="error" role="alert">{{ markError }}</p><template v-if="markDetail"><h3>{{ markDetail.typeSub?.name || markDetail.typeMain?.name || "地图点位" }}</h3><p v-if="markDetail.desc">{{ markDetail.desc }}</p><p>坐标：{{ display(markDetail.pos?.x) }}，{{ display(markDetail.pos?.y) }}，{{ display(markDetail.pos?.z) }}</p><a v-if="safeExternalUrl(markDetail.link)" :href="safeExternalUrl(markDetail.link)" target="_blank" rel="noopener noreferrer">{{ markDetail.linkText || "查看官方说明" }}<AppIcon name="arrow" :size="14" /></a></template></section><div v-if="map?.total > map?.limit" class="actions"><button type="button" class="ui-button" :disabled="mapBusy || mapOffset === 0" @click="mapOffset = Math.max(0, mapOffset - map.limit)">上一页</button><span class="hint">{{ mapOffset + 1 }}–{{ Math.min(mapOffset + map.limit, map.total) }} / {{ map.total }}</span><button type="button" class="ui-button" :disabled="mapBusy || mapOffset + map.limit >= map.total" @click="mapOffset += map.limit">下一页</button></div></section><section class="cap-card"><div class="cap-title">官方百科与养成</div><p v-if="publicBusy" class="hint" role="status">正在读取官方入口…</p><p v-if="publicError" class="error" role="alert">{{ publicError }}</p><p v-if="!officialTools.length" class="empty">暂未取得官方入口</p><ul v-else class="tool-grid"><li v-for="tool in officialTools" :key="tool.id"><a :href="safeExternalUrl(tool.url)" target="_blank" rel="noopener noreferrer"><strong>{{ tool.name }}</strong><AppIcon name="arrow" :size="14" /></a><p class="hint">{{ tool.description }}</p><p v-if="tool.status === 'unavailable'" class="hint">请前往官网查询；本页暂不能读取百科目录。</p></li></ul></section>
      <section class="cap-card"><div class="cap-title">森空岛资料查询<span v-if="toolData?.stale" class="badge badge-stale">数据可能过期</span></div>
        <p class="hint">连接森空岛角色后，可尝试读取官方资料目录。配队与养成方案请使用上方官网入口。</p>
        <form class="map-filters" @submit.prevent="loadTool">
          <label>资料类别<select v-model="toolKind"><option v-for="[kind,label] in toolKinds" :key="kind" :value="kind">{{ label }}</option></select></label>
          <button type="submit" class="ui-button" :disabled="toolBusy || !roleKey">查询资料</button>
        </form>
        <p v-if="!roleKey" class="hint">请先在概览中连接并选择森空岛角色。</p>
        <p v-if="toolBusy" class="hint" role="status">正在读取官方资料…</p>
        <p v-if="toolError" class="error" role="alert">{{ toolError }}</p>
        <p v-if="toolData?.supported === false" class="hint">这类资料暂时无法读取。</p>
        <template v-else-if="toolData?.payload">
          <label class="tool-search">筛选结果<input v-model="toolQuery" type="search" placeholder="按名称或编号筛选" /></label>
          <p v-if="!toolRows.length" class="empty">暂无匹配资料；若目录格式变化，请前往官网查看。</p>
          <div v-else class="catalog-grid"><article v-for="(item,i) in toolPageRows" :key="item.id || i" class="inner-card catalog-item">
            <h3>{{ display(item.name) }}</h3><p class="hint">{{ toolSummary(item) || '资料待补充' }}</p>
            <p v-if="toolDescription(item)" class="catalog-description">{{ toolDescription(item) }}</p>
            <details><summary>查看详情</summary>
              <p>编号：{{ display(item.id) }}</p>
              <template v-if="toolKind === 'characters'"><p v-if="item.weaponType">武器类别：{{ sourceLabel(item.weaponType) }}</p><ul v-if="list(item.skills).length"><li v-for="(skill,j) in list(item.skills)" :key="skill.id || j">{{ display(skill.name) }}<span v-if="skill.desc"> · {{ skill.desc }}</span></li></ul></template>
              <template v-if="toolKind === 'weapons'"><p v-if="item.function">用途：{{ item.function }}</p><ul v-if="list(item.skills).length"><li v-for="(skill,j) in list(item.skills)" :key="j">{{ sourceLabel(skill) }}</li></ul></template>
              <template v-if="toolKind === 'equipment'"><p v-if="item.function">装备效果：{{ item.function }}</p><ul v-if="list(item.properties).length"><li v-for="(property,j) in list(item.properties)" :key="j">{{ sourceLabel(property) }}</li></ul></template>
              <template v-if="toolKind === 'tactical'"><p v-if="item.activeEffect">主动效果：{{ item.activeEffect }}</p><p v-if="item.passiveEffect">被动效果：{{ item.passiveEffect }}</p></template>
              <template v-if="toolKind === 'materials'"><p v-if="item.exp != null">经验：{{ item.exp }}</p><p v-if="item.startLevel != null || item.maxLevel != null">适用等级：{{ display(item.startLevel) }}–{{ display(item.maxLevel) }}</p></template>
              <a href="https://wiki.skland.com/endfield" target="_blank" rel="noopener noreferrer">前往官方百科<AppIcon name="arrow" :size="14" /></a>
            </details>
          </article></div>
          <div v-if="toolRows.length > 20" class="actions"><button type="button" class="ui-button" :disabled="toolPage === 0" @click="toolPage--">上一页</button><span class="hint">{{ toolPage * 20 + 1 }}–{{ Math.min((toolPage + 1) * 20, toolRows.length) }} / {{ toolRows.length }}</span><button type="button" class="ui-button" :disabled="(toolPage + 1) * 20 >= toolRows.length" @click="toolPage++">下一页</button></div>
        </template>
      </section></div>

    <div v-else-if="section === 'blueprints'" class="endfield-stack"><section class="cap-card"><div class="cap-title">蓝图收藏<button type="button" class="ui-button" :disabled="blueprintBusy" @click="downloadBlueprints">导出备份</button></div><p class="hint">分享码和备注保存在本机。</p><form class="field-grid" @submit.prevent="submitBlueprint"><label>名称<input v-model="blueprintName" type="text" maxlength="100" required /></label><label>分享码<input v-model="blueprintCode" type="text" maxlength="2000" required /></label><label>备注<textarea v-model="blueprintNotes" maxlength="2000" rows="2" /></label><div class="actions"><button type="submit" class="ui-button" :disabled="blueprintBusy">{{ editingId === null ? '保存蓝图' : '保存修改' }}</button><button v-if="editingId !== null" type="button" class="ui-button" @click="resetBlueprint">取消编辑</button></div></form><p v-if="blueprintError" class="error" role="alert">{{ blueprintError }}</p><p v-if="blueprintBusy" class="hint" role="status">正在处理蓝图…</p><p v-if="!blueprintBusy && !blueprints.length" class="empty">还没有收藏蓝图</p><ul v-else class="blueprint-list"><li v-for="item in blueprints" :key="item.id"><strong>{{ item.name }}</strong><code>{{ item.code }}</code><p v-if="item.notes" class="hint">{{ item.notes }}</p><div class="actions"><button type="button" class="ui-button" @click="copyCode(item.code)">复制分享码</button><button type="button" class="ui-button" :disabled="blueprintBusy" @click="editBlueprint(item)">编辑</button><button type="button" class="ui-button" :disabled="blueprintBusy" @click="removeBlueprint(item.id)">删除</button></div></li></ul></section></div>

    <div v-else-if="section === 'news'" class="endfield-stack"><section class="cap-card"><div class="cap-title">官网资讯<button type="button" class="ui-button" :disabled="publicBusy" @click="loadPublic(true)"><AppIcon name="refresh" :size="14" />刷新官网资讯</button><span v-if="publicData?.news?.stale" class="badge badge-stale">数据可能过期</span></div><p v-if="publicBusy" class="hint" role="status">正在读取官网资讯…</p><p v-if="publicError" class="error" role="alert">{{ publicError }}</p><p v-if="!publicBusy && !publicNews.length" class="empty">暂无官网资讯</p><ul v-else class="news-list"><li v-for="(item, i) in publicNews" :key="item.url || i"><a v-if="safeExternalUrl(item.url)" :href="safeExternalUrl(item.url)" target="_blank" rel="noopener noreferrer">{{ display(item.title) }}</a><strong v-else>{{ display(item.title) }}</strong><p class="hint">{{ dateText(item.published_at) }}</p></li></ul></section><AnnouncementList :snap="snaps.news?.payload ? snaps.news : snaps.announcement" capability="news" /></div>
  </div>
</template>

<style scoped>
.record-detail { margin-top:10px; border-top:1px solid var(--border); padding-top:10px; }.record-detail summary { cursor:pointer; display:flex; flex-wrap:wrap; align-items:center; gap:8px; }.record-detail summary strong,.record-detail summary .hint { margin-left:auto; }.record-detail .inner-card { margin-top:8px; }.record-detail summary:focus-visible { outline:2px solid var(--game-accent); outline-offset:3px; }
.endfield-dashboard{min-width:0}.endfield-nav{display:flex;align-items:center;justify-content:space-between;gap:10px 16px;flex-wrap:wrap;margin-bottom:16px}.endfield-stack{display:grid;gap:12px}.endfield-grid,.operator-grid,.tool-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.cap-title{justify-content:space-between}.cap-title .ui-button{font-size:12px}.hint{color:var(--text-muted);font-size:12px;line-height:1.55;overflow-wrap:anywhere}.error{color:var(--danger);font-size:12px;overflow-wrap:anywhere}.identity{font-weight:600;font-size:14px;color:var(--text);margin-top:8px}.muted{color:var(--text-muted);font-size:11px;font-weight:400;margin-left:8px}.field-grid{display:grid;gap:10px;max-width:600px}.field-grid label,.role-bar label,.map-filters label{display:grid;gap:5px;color:var(--text-muted);font-size:12px}.field-grid input,.field-grid textarea,.role-bar select,.map-filters :is(select,input){box-sizing:border-box;width:100%;min-height:36px;border:1px solid var(--border);border-radius:7px;padding:7px 9px;background:var(--card-bg);color:var(--text)}.field-grid textarea{resize:vertical}.field-grid .ui-button{justify-self:start}.role-bar,.map-filters,.actions{display:flex;gap:8px;align-items:end;flex-wrap:wrap}.role-bar label{min-width:min(100%,240px);flex:1}.map-filters label{min-width:min(100%,150px);flex:1}.map-filters label:last-of-type{flex:2}.ui-button{display:inline-flex;align-items:center;gap:5px}.fact-list{display:grid;gap:8px;margin-top:12px}.fact-list div,.plain-list li,.mark-list li{display:flex;justify-content:space-between;gap:12px;align-items:start;padding:9px 0;border-bottom:1px solid var(--border)}.fact-list dt,.plain-list span{color:var(--text-muted);font-size:12px}.fact-list dd{margin:0;color:var(--text);font-weight:600;font-size:13px}.plain-list strong{font-size:13px;font-weight:600;color:var(--text);text-align:right}.plain-list small{display:block;margin-top:3px;color:var(--text-faint)}.inner-card,.tool-grid li{border:1px solid var(--border);border-radius:9px;background:var(--panel-bg);padding:12px;min-width:0}.inner-card h3{font-size:13px;color:var(--text);margin:0 0 6px}.inner-card p{font-size:12px;color:var(--text-muted);line-height:1.5;overflow-wrap:anywhere}.mark-list strong,.blueprint-list strong{font-size:13px}.mark-list a,.tool-grid a{display:inline-flex;align-items:center;gap:4px;font-size:12px;color:var(--accent);text-decoration:none}.tool-grid a{justify-content:space-between;width:100%}.blueprint-list li,.news-list li{padding:12px 0;border-top:1px solid var(--border)}.blueprint-list code{display:block;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--text-muted);font-size:12px;margin:6px 0}.blueprint-list .actions{margin-top:9px}.news-list a{color:var(--accent);font-size:13px}.news-list strong{font-size:13px}@media(max-width:720px){.endfield-grid,.operator-grid,.tool-grid{grid-template-columns:1fr}.role-bar>*{width:100%}.map-filters label,.map-filters label:last-of-type{min-width:100%}.endfield-nav .segmented{width:100%}.mark-list li{flex-direction:column}}
.attendance-summary{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;margin-bottom:8px}.attendance-summary strong{color:var(--text);font-size:14px}.attendance-summary span{color:var(--text-muted);font-size:12px}
.tool-search{display:grid;gap:5px;color:var(--text-muted);font-size:12px;margin:12px 0}.tool-search input{box-sizing:border-box;min-height:36px;border:1px solid var(--border);border-radius:7px;padding:7px 9px;background:var(--card-bg);color:var(--text)}
.catalog-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.catalog-item{display:grid;gap:5px;align-content:start}.catalog-item h3{margin:0}.catalog-description{display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:2;overflow:hidden}.catalog-item details{margin-top:4px;border-top:1px solid var(--border);padding-top:6px;color:var(--text-muted);font-size:12px;overflow-wrap:anywhere}.catalog-item summary{cursor:pointer;color:var(--accent)}.catalog-item details li{padding:4px 0;border-bottom:1px solid var(--border)}.catalog-item details a{display:inline-flex;align-items:center;gap:4px;margin-top:7px}@media(max-width:720px){.catalog-grid{grid-template-columns:1fr}}
.operator-item .ui-button{margin-top:8px;font-size:12px}.operator-detail{margin-top:8px;border-top:1px solid var(--border);padding-top:8px;display:grid;gap:5px}
</style>
