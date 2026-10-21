<script setup>
import MenuSelect from './MenuSelect.vue'
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  getPublic, refreshPublic, getMap, getMapMark, getSklandStatus, connectSkland, connectSklandWithPassport, chooseSklandRole,
  disconnectSkland, getSklandCard, refreshSklandCard, getAttendance, signAttendance,
  getChallenges, getSklandTools, getSklandOperator, getBlueprints, exportBlueprints, saveBlueprint, updateBlueprint, deleteBlueprint, safeExternalUrl,
} from '../endfield-tools-api.js'
import AppIcon from './AppIcon.vue'
import { friendlyDataError } from '../cloud-display.js'
import EndfieldGachaPanel from './EndfieldGachaPanel.vue'
import EndfieldGachaSummary from './EndfieldGachaSummary.vue'
import { gachaView } from '../endfield-gacha-summary.js'
import EndfieldReports from './EndfieldReports.vue'
import EndfieldChallenges from './EndfieldChallenges.vue'
import { challengeReport, retainedChallenge } from '../endfield-challenges.js'
import AnnouncementList from './AnnouncementList.vue'
import EndfieldAttendance from './EndfieldAttendance.vue'
import EndfieldNewsSummary from './EndfieldNewsSummary.vue'
import { attendanceEnvelope } from '../endfield-attendance.js'
import { vGlide } from '../motion.js'
import EndfieldLocked from './EndfieldLocked.vue'
import EndfieldAuthGuide from './EndfieldAuthGuide.vue'
import { endfieldProviderLabel, endfieldSourceLabel } from '../endfield-accounts.js'

const props = defineProps({ cloudAccount:Object, cloudRole:String, cloudSources:Object, sourceSnapshots:Object, isAdmin:Boolean, configured:{type:Boolean,default:undefined}, authAccount:Object, refreshing:Boolean, snaps: { type: Object, default: () => ({}) }, initialSection: { type: String, default: 'overview' } })
const emit = defineEmits(['calendar','refresh'])
const cloud = computed(()=>!!props.cloudAccount)
const passportSource = computed(() => props.cloudSources ? props.cloudSources.hypergryph || null : props.cloudAccount?.provider === 'hypergryph' ? { account: props.cloudAccount, role: props.cloudRole } : null)
const profileSource = computed(() => props.cloudSources ? props.cloudSources.skland || null : props.cloudAccount?.provider === 'skland' ? { account: props.cloudAccount, role: props.cloudRole } : null)
const passport = computed(() => !cloud.value || !!passportSource.value)
// A fallback lends one provider's pages from an entry that is not paired with the selected one.
const fallbackSource = computed(() => Object.values(props.cloudSources || {}).find(source => source?.fallback) || null)
const merged = computed(() => cloud.value && !!passportSource.value && !!profileSource.value && !fallbackSource.value)
const candidates = inject('endfieldCandidates', null)
const guideCandidates = provider => candidates?.value?.[provider] || []
const profileSnapshot = computed(() => {
  if (!props.cloudSources?.skland) return props.cloudAccount?.provider === 'skland' ? props.snaps.account || null : null
  const snapshot = props.sourceSnapshots?.skland?.account, source = profileSource.value
  return snapshot?.account_id === source.account.account_id && snapshot?.role_id === source.role ? snapshot : null
})
const passportSnapshots = computed(() => props.cloudSources?.hypergryph ? props.sourceSnapshots?.hypergryph || {} : props.snaps)
const canMaintain = computed(()=>!cloud.value || props.isAdmin)
const connectionHint = computed(() => {
  const source = profileSource.value?.fallback ? profileSource.value : { account: props.cloudAccount, role: props.cloudRole }
  return `${merged.value ? '鹰角资料与寻访 · 森空岛档案' : profileSource.value ? '森空岛档案' : '鹰角资料与寻访'} · ${source.account?.roles?.find(r => r.role_id === source.role)?.display_name || source.role}`
})
const tabs = [
  ['overview', '概览'], ['operators', '全员练度'], ['regions', '地区建设'], ['ship', '帝江号'], ['gacha', '抽卡统计'],
  ['honor', '光荣之路'], ['challenges', '挑战记录'], ['news', '公告与资讯'], ['map', '地图与图鉴'], ['blueprints', '蓝图收藏'],
]
const primaryTabs = tabs.slice(0, 5)
const additionalTabs = tabs.slice(5)
const moreOpen = ref(false)
const profileSections = ['overview', 'operators', 'regions', 'ship', 'honor', 'challenges']
const section = ref(tabs.some(([id]) => id === props.initialSection) ? props.initialSection : 'overview')
// The overview shows the profile and the gacha summary; the map's catalog query is a Skland route.
const sectionUses = provider => provider === 'hypergryph' ? ['overview', 'gacha'].includes(section.value) : [...profileSections, 'map', 'blueprints'].includes(section.value)
const fallbackNote = computed(() => {
  const source = fallbackSource.value
  return source && sectionUses(source.account.provider) ? `本页使用${endfieldProviderLabel(source.account.provider)}「${endfieldSourceLabel(source)}」，与当前${endfieldProviderLabel(props.cloudAccount.provider)}未配对为同一角色` : ''
})
const status = ref(null), statusBusy = ref(false), statusError = ref('')
const card = ref(null), cardBusy = ref(false), cardError = ref('')
const operatorDetail = ref(null), operatorDetailId = ref(''), operatorBusy = ref(false), operatorError = ref(''), operatorStale = ref(false)
const operatorFetchedAt = ref(null)
const attendance = ref(null), attendanceBusy = ref(false), attendanceError = ref('')
const challengeKind = ref('war'), challenge = ref(null), challengeBusy = ref(false), challengeError = ref('')
const publicData = ref(null), publicBusy = ref(false), publicError = ref('')
const map = ref(null), mapBusy = ref(false), mapError = ref('')
const markDetail = ref(null), markBusy = ref(false), markError = ref('')
const mapId = ref(''), levelId = ref(''), typeId = ref(''), mapQuery = ref(''), submittedQuery = ref(''), mapOffset = ref(0)
const toolKind = ref('characters'), toolQuery = ref(''), toolPage = ref(0), toolData = ref(null), toolBusy = ref(false), toolError = ref('')
const blueprints = ref([]), blueprintBusy = ref(false), blueprintError = ref(''), blueprintMessage = ref(''), editingId = ref(null)
const blueprintName = ref(''), blueprintCode = ref(''), blueprintNotes = ref('')
const cred = ref(''), deviceId = ref(''), actionBusy = ref(false), actionError = ref(''), actionMessage = ref(''), manualOpen = ref(false)
let statusSeq = 0, privateSeq = 0, attendanceSeq = 0, operatorSeq = 0, challengeSeq = 0, mapSeq = 0, markSeq = 0, toolSeq = 0, publicSeq = 0, blueprintsSeq = 0
let mapController = null
let destroyed = false
let cloudSnapshotInvalidated = false

const connected = computed(() => !!status.value?.connected)
const passportAvailable = computed(() => !!status.value?.passport_available)
const connectionSource = computed(() => ({ passport: '鹰角通行证', manual: '手动连接' })[status.value?.source] || '')
const selectedRole = computed(() => status.value?.roles?.find(role => String(role.role_id) === String(status.value.selected_role_id) && String(role.server_id) === String(status.value.selected_server_id)))
const roleKey = computed(() => selectedRole.value ? `${selectedRole.value.role_id}:${selectedRole.value.server_id}` : '')
const passportView = computed(() => gachaView({snaps:passportSnapshots.value,cloudAccount:passportSource.value?.account || props.cloudAccount,cloudRole:passportSource.value?.role || props.cloudRole,configured:props.configured,authAccount:props.authAccount}))
const cardPayload = computed(() => card.value?.payload || null)
const display = value => value === null || value === undefined || value === '' ? '未知' : String(value)
const list = value => Array.isArray(value) ? value : []
const humanError = value => value === '暂时无法连接服务，请稍后重试。' ? value : value ? friendlyDataError(value) : ''
const roleLabel = role => cloud.value ? `${role.nickname || '未命名角色'} · ${role.role_id}` : `${role.nickname || '未命名角色'} · ${role.role_id} / ${role.server_id}`
const roleValue = computed(() => roleKey.value)
const publicNewsSnap = computed(() => publicData.value?.news ? { ...publicData.value.news, payload: publicData.value.news.items, error: publicError.value } : null)
const newsSnapshots = computed(() => [publicNewsSnap.value, props.snaps.news, props.snaps.announcement].filter(Boolean))
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
  if (cloud.value) {
    const source = profileSource.value, selected = source?.account.roles?.find(row => row.role_id === source.role)
    status.value = source && selected ? {connected:true,roles:[{role_id:source.role,server_id:source.account.server || '',nickname:selected.display_name}],selected_role_id:source.role,selected_server_id:source.account.server || ''} : {connected:false,roles:[]}
    return
  }
  const seq = ++statusSeq
  statusBusy.value = true; statusError.value = ''
  try {
    const data = await getSklandStatus()
    if (destroyed || seq !== statusSeq) return
    status.value = data
    statusError.value = humanError(data.error)
  } catch (error) { if (seq === statusSeq) statusError.value = humanError(error.message) }
  finally { if (seq === statusSeq) statusBusy.value = false }
}
function clearPrivate() {
  ++privateSeq; ++operatorSeq; ++challengeSeq
  ++attendanceSeq; attendanceBusy.value = false
  cardBusy.value = false; operatorBusy.value = false; challengeBusy.value = false; toolBusy.value = false
  ++toolSeq; toolData.value = null; toolError.value = ''
  card.value = null; cardError.value = ''; attendance.value = null; attendanceError.value = ''
  operatorDetail.value = null; operatorDetailId.value = ''; operatorError.value = ''; operatorStale.value = false; operatorFetchedAt.value = null
  challenge.value = null; challengeError.value = ''
}
async function loadOperator(id) {
  if (!id || !roleKey.value) return
  const seq = ++operatorSeq, owner = roleKey.value
  operatorDetailId.value = String(id); operatorDetail.value = null; operatorError.value = ''; operatorStale.value = false; operatorFetchedAt.value = null; operatorBusy.value = true
  try {
    const data = await getSklandOperator(id)
    if (destroyed || seq !== operatorSeq || owner !== roleKey.value) return
    operatorDetail.value = data.operator || data.payload || null; operatorStale.value = !!data.stale; operatorFetchedAt.value = data.fetched_at || null; operatorError.value = humanError(data.error)
    if (!operatorDetail.value && !operatorError.value) operatorError.value = '暂时无法读取这名干员的配装。'
  } catch (error) { if (seq === operatorSeq) operatorError.value = humanError(error.message) }
  finally { if (seq === operatorSeq) operatorBusy.value = false }
}
function closeOperator() {
  ++operatorSeq
  operatorDetailId.value = ''; operatorDetail.value = null; operatorBusy.value = false
  operatorError.value = ''; operatorStale.value = false; operatorFetchedAt.value = null
}
function selectSection(id) { section.value = id; moreOpen.value = false }
async function loadTool() {
  if (!roleKey.value) { toolError.value = '请先连接并选择森空岛角色。'; return }
  const seq = ++toolSeq, owner = roleKey.value, kind = toolKind.value
  toolBusy.value = true; toolError.value = ''; toolData.value = null
  try {
    const data = await getSklandTools(kind)
    if (destroyed || seq !== toolSeq || owner !== roleKey.value || kind !== toolKind.value) return
    toolData.value = data; toolError.value = humanError(data.error)
  } catch (error) { if (seq === toolSeq) toolError.value = humanError(error.message) }
  finally { if (seq === toolSeq) toolBusy.value = false }
}
async function loadCard(refresh = false) {
  if (cloud.value) {
    if (refresh) emit('refresh')
    else if (!cloudSnapshotInvalidated || props.cloudSources?.skland) { card.value = profileSnapshot.value; cardError.value = humanError(card.value?.error || card.value?.poll_status?.error) }
    return
  }
  if (!roleKey.value) return
  const seq = ++privateSeq, owner = roleKey.value
  cardBusy.value = true; cardError.value = ''
  try {
    const data = refresh ? await refreshSklandCard() : await getSklandCard()
    if (destroyed || seq !== privateSeq || owner !== roleKey.value) return
    card.value = data; cardError.value = humanError(data.error)
  } catch (error) { if (!destroyed && seq === privateSeq && owner === roleKey.value && error.name !== 'AbortError') {
    cardError.value = humanError(error.message)
    if (card.value?.payload) card.value = { ...card.value, stale: true, error: humanError(error.message) }
  } }
  finally { if (seq === privateSeq) cardBusy.value = false }
}
async function loadAttendance(sign = false) {
  if (cloud.value && sign) return
  if (!roleKey.value) return
  const seq = ++attendanceSeq, owner = roleKey.value
  attendanceBusy.value = true; attendanceError.value = ''
  try {
    const data = sign ? await signAttendance() : await getAttendance()
    if (destroyed || seq !== attendanceSeq || owner !== roleKey.value) return
    attendance.value = attendanceEnvelope(data); attendanceError.value = humanError(attendance.value?.error)
  } catch (error) { if (!destroyed && seq === attendanceSeq && owner === roleKey.value && error.name !== 'AbortError') {
    attendanceError.value = humanError(error.message)
    if (attendance.value) attendance.value = { ...attendance.value, stale: true, error: humanError(error.message) }
  } }
  finally { if (seq === attendanceSeq) attendanceBusy.value = false }
}
async function loadChallenge() {
  if (!roleKey.value) return
  const seq = ++challengeSeq, kind = challengeKind.value, owner = roleKey.value
  const previous = challengeReport(challenge.value, kind).available ? challenge.value : null
  const current = () => !destroyed && seq === challengeSeq && owner === roleKey.value && kind === challengeKind.value
  challengeBusy.value = true; challengeError.value = ''
  try {
    const data = await getChallenges(kind)
    if (!current()) return
    const next = challengeReport(data, kind), error = humanError(data.error)
    challenge.value = error && previous && !next.available && next.supported !== false ? retainedChallenge(previous, error) : data
    challengeError.value = error
  } catch (error) { if (current()) { challengeError.value = humanError(error.message); challenge.value = retainedChallenge(previous, humanError(error.message)) } }
  finally { if (seq === challengeSeq) challengeBusy.value = false }
}
async function loadPublic(refresh = false) {
  const seq = ++publicSeq
  publicBusy.value = true; publicError.value = ''
  try {
    const data = refresh ? await refreshPublic() : await getPublic()
    if (destroyed || seq !== publicSeq) return
    publicData.value = data; publicError.value = humanError(data.news?.error)
  } catch (error) { if (seq === publicSeq) publicError.value = humanError(error.message) }
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
  } catch (error) { if (seq === mapSeq && error.name !== 'AbortError') mapError.value = humanError(error.message) }
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
  } catch (error) { if (seq === markSeq) markError.value = humanError(error.message) }
  finally { if (seq === markSeq) markBusy.value = false }
}
async function loadBlueprints() {
  if (cloud.value && !profileSource.value) return
  const seq = ++blueprintsSeq
  blueprintBusy.value = true; blueprintError.value = ''; blueprintMessage.value = ''
  try {
    const data = await getBlueprints()
    if (destroyed || seq !== blueprintsSeq) return
    blueprints.value = list(data.items)
  } catch (error) { if (seq === blueprintsSeq) blueprintError.value = humanError(error.message) }
  finally { if (seq === blueprintsSeq) blueprintBusy.value = false }
}
async function connect() {
  if (!cred.value.trim()) return
  actionBusy.value = true; actionError.value = ''; actionMessage.value = ''
  try {
    const data = await connectSkland(cred.value.trim(), deviceId.value.trim())
    cred.value = ''; deviceId.value = ''; clearPrivate(); status.value = data
    actionMessage.value = '森空岛账号已连接。'
  } catch (error) { actionError.value = humanError(error.message) }
  finally { actionBusy.value = false }
}
async function connectWithPassport() {
  actionBusy.value = true; actionError.value = ''; actionMessage.value = ''
  try {
    const data = await connectSklandWithPassport()
    clearPrivate(); status.value = data
    actionMessage.value = data.selected_role_id ? '已用鹰角通行证连接森空岛。' : '已连接森空岛，请确认角色。'
  } catch (error) { actionError.value = humanError(error.message); manualOpen.value = true }
  finally { actionBusy.value = false }
}
async function selectRole(value) {
  const role = status.value?.roles?.find(item => `${item.role_id}:${item.server_id}` === value)
  if (!role || value === roleKey.value) return
  clearPrivate(); actionBusy.value = true; actionError.value = ''; actionMessage.value = ''
  try { status.value = await chooseSklandRole(role.role_id, role.server_id) }
  catch (error) { actionError.value = humanError(error.message); await loadStatus(); if (roleKey.value) reloadPrivate() }
  finally { actionBusy.value = false }
}
async function disconnect() {
  actionBusy.value = true; actionError.value = ''; actionMessage.value = ''; clearPrivate()
  try { status.value = await disconnectSkland(); actionMessage.value = '已断开森空岛连接。' }
  catch (error) { actionError.value = humanError(error.message); await loadStatus(); if (roleKey.value) reloadPrivate() }
  finally { actionBusy.value = false }
}
function editBlueprint(item) {
  editingId.value = item.id; blueprintName.value = item.name || ''; blueprintCode.value = item.code || ''; blueprintNotes.value = item.notes || ''
}
function resetBlueprint() { editingId.value = null; blueprintName.value = ''; blueprintCode.value = ''; blueprintNotes.value = '' }
async function submitBlueprint() {
  const item = { name: blueprintName.value.trim(), code: blueprintCode.value.trim(), notes: blueprintNotes.value.trim() }
  if (!item.name || !item.code) { blueprintError.value = '请填写名称和分享码。'; return }
  blueprintBusy.value = true; blueprintError.value = ''; blueprintMessage.value = ''
  try {
    if (editingId.value === null) await saveBlueprint(item)
    else await updateBlueprint(editingId.value, item)
    resetBlueprint(); await loadBlueprints()
  } catch (error) { blueprintError.value = humanError(error.message) }
  finally { blueprintBusy.value = false }
}
async function removeBlueprint(id) {
  blueprintBusy.value = true; blueprintError.value = ''; blueprintMessage.value = ''
  try { await deleteBlueprint(id); if (editingId.value === id) resetBlueprint(); await loadBlueprints() }
  catch (error) { blueprintError.value = humanError(error.message) }
  finally { blueprintBusy.value = false }
}
async function copyCode(code) {
  blueprintError.value = ''; blueprintMessage.value = ''
  try { await navigator.clipboard.writeText(code); blueprintMessage.value = '分享码已复制。' }
  catch { blueprintError.value = '复制失败，请手动选取分享码。' }
}
async function downloadBlueprints() {
  try {
    const data = await exportBlueprints()
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = 'endfield-blueprints.json'; link.click(); URL.revokeObjectURL(url)
  } catch (error) { blueprintError.value = humanError(error.message) }
}
function submitMapSearch() { submittedQuery.value = mapQuery.value.trim(); if (mapOffset.value) mapOffset.value = 0; else loadMap() }

// Without a passport login the manual form is the only way in, so show it expanded.
watch(() => status.value?.passport_available, available => { manualOpen.value = available !== true }, { immediate: true })
// Re-read the role data the current section shows.
function reloadPrivate() {
  if (['overview', 'operators', 'regions', 'ship', 'honor'].includes(section.value)) { loadCard(); if (section.value === 'overview') loadAttendance() }
  if (section.value === 'challenges') loadChallenge()
}
watch(roleValue, (next, previous) => {
  if (next === previous) return
  clearPrivate()
  if (next) reloadPrivate()
})
watch(section, current => {
  if (['overview', 'operators', 'regions', 'ship', 'honor'].includes(current)) { if (roleKey.value && !card.value) loadCard(); if (current === 'overview' && roleKey.value && !attendance.value) loadAttendance() }
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
watch(challengeKind, () => { ++challengeSeq; challenge.value = null; challengeError.value = ''; challengeBusy.value = false; if (section.value === 'challenges') loadChallenge() }, { flush: 'sync' })
watch(toolKind, () => { ++toolSeq; toolBusy.value = false; toolData.value = null; toolError.value = ''; toolQuery.value = ''; toolPage.value = 0 })
watch(toolQuery, () => { toolPage.value = 0 })
watch(() => [props.cloudAccount?.account_id, props.cloudRole, props.cloudAccount?.provider, profileSource.value?.account.account_id, profileSource.value?.role, profileSource.value?.account.version], () => { if (cloud.value) { cloudSnapshotInvalidated = true; clearPrivate(); loadStatus() } }, { flush: 'sync' })
watch(profileSnapshot, snap => { if (cloud.value && profileSource.value) { cloudSnapshotInvalidated = false; card.value = snap || null; cardError.value = humanError(snap?.error || snap?.poll_status?.error) } })
onMounted(() => { loadStatus(); if (section.value === 'map') { loadPublic(); loadMap() } if (section.value === 'blueprints') loadBlueprints(); if (section.value === 'news') loadPublic() })
onUnmounted(() => { destroyed = true; mapController?.abort(); ++statusSeq; ++privateSeq; ++operatorSeq; ++challengeSeq; ++mapSeq; ++markSeq; ++toolSeq; ++publicSeq; ++blueprintsSeq })
</script>

<template>
  <div class="endfield-dashboard">
    <div class="endfield-nav">
      <nav v-glide class="ef-main-nav segmented" aria-label="终末地数据分区">
        <button v-for="[id, label] in primaryTabs" :key="id" type="button" :aria-pressed="section === id" @click="selectSection(id)">{{ label }}</button>
        <button type="button" :aria-expanded="moreOpen" aria-controls="endfield-more-nav" :class="{ active: additionalTabs.some(([id]) => id === section) }" @click="moreOpen = !moreOpen">{{ additionalTabs.find(([id]) => id === section)?.[1] || '更多' }}<AppIcon name="chevron" :size="13" /></button>
      </nav>
      <button type="button" class="text-link ef-calendar-link" @click="emit('calendar')"><AppIcon name="calendar" :size="15" />活动日历<AppIcon name="arrow" :size="15" /></button>
      <nav v-show="moreOpen" id="endfield-more-nav" class="ef-more-nav segmented" aria-label="其他终末地入口"><button v-for="[id,label] in additionalTabs" :key="id" type="button" :aria-pressed="section === id" @click="selectSection(id)">{{ label }}</button></nav>
    </div>
    <p v-if="fallbackNote" class="cap-card hint ef-fallback-note" role="note">{{ fallbackNote }}</p>

    <div v-if="profileSections.includes(section)" class="endfield-stack">
      <section class="cap-card ef-connection" :class="{ 'is-connected': connected }"><div class="cap-title"><span class="ef-connection-dot" :class="{ connected }"></span>{{ merged ? '终末地游戏档案' : cloud && passport && !profileSource ? '鹰角通行证寻访' : '森空岛游戏档案' }}<span v-if="connected && connectionSource" class="badge">{{ connectionSource }}</span><span v-if="card?.stale" class="badge badge-stale">待更新</span></div>
        <p v-if="statusBusy" class="hint" role="status">正在读取连接状态…</p>
        <p v-if="statusError" class="error" role="alert">{{ statusError }}</p>
        <template v-if="!cloud && !statusBusy && !connected">
          <div v-if="passportAvailable" class="passport-connect">
            <button type="button" class="ui-button primary" :disabled="actionBusy" @click="connectWithPassport">{{ actionBusy ? '连接中…' : '用鹰角通行证连接' }}</button>
          </div>
          <p v-else class="hint">在「社区账号」登录终末地后，可一键连接森空岛；也可以手动连接。</p>
          <details class="manual-connect" :open="manualOpen" @toggle="manualOpen = $event.target.open"><summary>手动连接（备用）</summary>
            <form class="field-grid" @submit.prevent="connect">
              <p class="hint">凭据只在本机加密保存。</p>
              <label>森空岛凭据<input v-model="cred" type="password" required autocomplete="off" /></label>
              <label>官方设备标识（可选）<input v-model="deviceId" type="password" autocomplete="off" placeholder="已有设备标识时填写" /></label>
              <button type="submit" class="ui-button" :disabled="actionBusy">{{ actionBusy ? '连接中…' : '连接森空岛' }}</button>
            </form>
          </details>
        </template>
        <div v-else-if="connected && !cloud" class="role-bar"><label><span class="ef-role-label">当前角色</span><MenuSelect label="森空岛角色" :model-value="roleKey" :disabled="actionBusy" @change="selectRole" :options="[{value:'',label:'请选择角色'},...list(status.roles).map(role=>({value:`${role.role_id}:${role.server_id}`,label:roleLabel(role)}))]" /></label><button type="button" class="ui-button" :disabled="actionBusy || !roleKey || cardBusy" @click="loadCard(true)"><AppIcon name="refresh" :size="14" />{{ cardBusy ? '读取中…' : '刷新档案' }}</button><details class="ef-connection-settings"><summary>连接设置</summary><button type="button" class="ui-button" :disabled="actionBusy" @click="disconnect">断开森空岛</button></details></div>
        <p v-if="connected && !roleKey" class="hint">{{ status.source === 'passport' ? '森空岛绑定的角色与通行证登录的角色不同，请确认后手动选择。' : '请选择一个森空岛角色。' }}</p>

        <p v-if="cloud" class="hint">{{ connectionHint }}</p>
        <p v-if="actionError" class="error" role="alert">{{ actionError }}</p><p v-if="actionMessage" class="hint" role="status">{{ actionMessage }}</p>
      </section>
      <EndfieldAuthGuide v-if="cloud && !connected" need="skland" :passport="!!passportSource" :candidates="guideCandidates('skland')" />
      <EndfieldLocked v-if="!roleKey && section !== 'overview'" :section="section" :note="!cloud" />

      <template v-if="section === 'overview'">
        <template v-if="roleKey"><p v-if="cardBusy" class="hint" role="status">正在读取档案…</p><p v-if="cardError" class="error" role="alert">{{ cardError }}</p>
          <EndfieldReports v-if="cardPayload" :payload="cardPayload" :fetched-at="card?.fetched_at" :stale="card?.stale" view="overview" @navigate="section = $event" /><p v-else-if="!cardBusy && !cardError" class="empty cap-card">暂无档案数据，请手动刷新。</p>
          <EndfieldAttendance :value="attendance" :busy="attendanceBusy" :error="attendanceError" :allow-sign="!cloud" @reload="loadAttendance(false)" @sign="loadAttendance(true)" />
        </template>
        <EndfieldGachaSummary v-if="passport" :view="passportView" :refreshing="refreshing" @details="selectSection('gacha')" @refresh="emit('refresh')" />
        <EndfieldNewsSummary :snapshots="newsSnapshots" @all="selectSection('news')" />
      </template>

      <template v-if="['operators','regions','ship','honor'].includes(section) && roleKey">
        <p v-if="cardBusy" class="hint" role="status">正在读取档案…</p><p v-if="cardError" class="error" role="alert">{{ cardError }}</p>
        <EndfieldReports v-if="cardPayload" :key="roleKey" :payload="cardPayload" :view="section" :fetched-at="card?.fetched_at" :stale="card?.stale" :operator-detail="operatorDetail" :operator-detail-id="operatorDetailId" :operator-busy="operatorBusy" :operator-error="operatorError" :operator-stale="operatorStale" :operator-fetched-at="operatorFetchedAt" @inspect="loadOperator" @close-detail="closeOperator" />
        <p v-else-if="!cardBusy && !cardError" class="empty cap-card">暂无档案数据，请手动刷新。</p>
      </template>

      <EndfieldChallenges v-if="section === 'challenges' && roleKey" :value="challenge" :kind="challengeKind" :busy="challengeBusy" :error="challengeError" @select-kind="challengeKind = $event" @reload="loadChallenge" />
    </div>

    <div v-else-if="section === 'gacha'" class="endfield-stack"><section v-if="passport" class="cap-card ef-identity-card"><div class="cap-title">鹰角通行证寻访账号<span v-if="passportView.snapshot?.stale" class="badge badge-stale">寻访待更新</span></div><p v-if="passportView.account" class="identity">{{ passportView.account.nickname || '未知昵称' }} · 角色编号 {{ passportView.account.role_id }}</p><p v-if="passportView.message" class="hint">{{ passportView.message }}</p><button type="button" class="ui-button" :disabled="refreshing" @click="emit('refresh')">{{ refreshing ? '同步中…' : '刷新寻访数据' }}</button></section><EndfieldGachaPanel v-if="passport && passportView.accountId" :snap="passportView.snapshot" :account-id="passportView.accountId" /><EndfieldAuthGuide v-if="!passport" need="hypergryph" :candidates="guideCandidates('hypergryph')" /></div>

    <div v-else-if="section === 'map'" class="endfield-stack"><section class="cap-card"><div class="cap-title">官方地图</div><form class="map-filters" @submit.prevent="submitMapSearch"><label>地图<MenuSelect v-model="mapId" label="地图" :options="[{value:'',label:'请选择地图'},...list(map?.maps).map(item=>({value:item.id,label:item.name}))]" /></label><label>区域<MenuSelect v-model="levelId" label="区域" :options="[{value:'',label:'默认区域'},...list(selectedMap?.levels).map(item=>({value:item.id,label:item.name}))]" /></label><label>点位类型<MenuSelect v-model="typeId" label="点位类型" :options="[{value:'',label:'全部类型'},...list(map?.categories).map(item=>({value:item.id,label:item.name}))]" /></label><label>搜索点位<input v-model="mapQuery" type="search" placeholder="输入名称" /></label><button type="submit" class="ui-button primary" :disabled="mapBusy">搜索</button></form><p v-if="mapBusy" class="hint" role="status">正在读取地图点位…</p><p v-if="mapError" class="error" role="alert">{{ mapError }}</p><p v-if="map?.stale" class="badge badge-stale">地图待更新</p><p v-if="!mapBusy && !list(map?.marks).length" class="empty">暂无匹配点位</p><ul v-else class="mark-list"><li v-for="(mark, i) in list(map?.marks)" :key="mark.id || i"><div><strong>{{ display(mark.name) }}</strong><p class="hint">坐标 {{ display(mark.x) }}，{{ display(mark.y) }}，{{ display(mark.z) }}<span v-if="mark.description"> · {{ mark.description }}</span></p></div><div class="actions"><button type="button" class="ui-button" :disabled="markBusy" @click="loadMark(mark)">查看详情</button><a v-if="safeExternalUrl(mark.url)" :href="safeExternalUrl(mark.url)" target="_blank" rel="noopener noreferrer">官方地图<AppIcon name="arrow" :size="14" /></a></div></li></ul><section v-if="markDetail || markBusy || markError" class="inner-card mark-detail"><p v-if="markBusy" class="hint" role="status">正在读取点位详情…</p><p v-if="markError" class="error" role="alert">{{ markError }}</p><template v-if="markDetail"><h3>{{ markDetail.typeSub?.name || markDetail.typeMain?.name || "地图点位" }}</h3><p v-if="markDetail.desc">{{ markDetail.desc }}</p><p>坐标：{{ display(markDetail.pos?.x) }}，{{ display(markDetail.pos?.y) }}，{{ display(markDetail.pos?.z) }}</p><a v-if="safeExternalUrl(markDetail.link)" :href="safeExternalUrl(markDetail.link)" target="_blank" rel="noopener noreferrer">{{ markDetail.linkText || "查看官方说明" }}<AppIcon name="arrow" :size="14" /></a></template></section><div v-if="map?.total > map?.limit" class="actions"><button type="button" class="ui-button" :disabled="mapBusy || mapOffset === 0" @click="mapOffset = Math.max(0, mapOffset - map.limit)">上一页</button><span class="hint">{{ mapOffset + 1 }}–{{ Math.min(mapOffset + map.limit, map.total) }} / {{ map.total }}</span><button type="button" class="ui-button" :disabled="mapBusy || mapOffset + map.limit >= map.total" @click="mapOffset += map.limit">下一页</button></div></section><section class="cap-card"><div class="cap-title">官方百科与养成</div><p v-if="publicBusy" class="hint" role="status">正在读取官方入口…</p><p v-if="publicError" class="error" role="alert">{{ publicError }}</p><p v-if="!officialTools.length" class="empty">暂未取得官方入口</p><ul v-else class="tool-grid"><li v-for="tool in officialTools" :key="tool.id"><a :href="safeExternalUrl(tool.url)" target="_blank" rel="noopener noreferrer"><strong>{{ tool.name }}</strong><AppIcon name="arrow" :size="14" /></a><p class="hint">{{ tool.description }}</p><p v-if="tool.status === 'unavailable'" class="hint">请前往官网查看。</p></li></ul></section>
      <section class="cap-card"><div class="cap-title">森空岛资料查询<span v-if="toolData?.stale" class="badge badge-stale">待更新</span></div>
        <form class="map-filters" @submit.prevent="loadTool">
          <label>资料类别<MenuSelect v-model="toolKind" label="资料类别" :options="toolKinds.map(([value,label])=>({value,label}))" /></label>
          <button type="submit" class="ui-button primary" :disabled="toolBusy || !roleKey">查询资料</button>
        </form>
        <p v-if="!roleKey" class="hint">请先在概览中连接并选择森空岛角色。</p>
        <p v-if="toolBusy" class="hint" role="status">正在读取官方资料…</p>
        <p v-if="toolError" class="error" role="alert">{{ toolError }}</p>
        <p v-if="toolData?.supported === false" class="hint">这类资料暂时无法读取。</p>
        <template v-else-if="toolData?.payload">
          <label class="tool-search">筛选结果<input v-model="toolQuery" type="search" placeholder="按名称或编号筛选" /></label>
          <p v-if="!toolRows.length" class="empty">暂无匹配资料</p>
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

    <div v-else-if="section === 'blueprints'" class="endfield-stack"><EndfieldAuthGuide v-if="cloud && !profileSource" need="skland" :passport="!!passportSource" :candidates="guideCandidates('skland')" /><section v-else class="cap-card"><div class="cap-title">蓝图收藏<button type="button" class="ui-button" :disabled="blueprintBusy" @click="downloadBlueprints">导出备份</button></div><form class="field-grid" @submit.prevent="submitBlueprint"><label>名称<input v-model="blueprintName" type="text" maxlength="100" required /></label><label>分享码<input v-model="blueprintCode" type="text" maxlength="2000" required /></label><label>备注<textarea v-model="blueprintNotes" maxlength="2000" rows="2" /></label><div class="actions"><button type="submit" class="ui-button primary" :disabled="blueprintBusy">{{ editingId === null ? '保存蓝图' : '保存修改' }}</button><button v-if="editingId !== null" type="button" class="ui-button" @click="resetBlueprint">取消编辑</button></div></form><p v-if="blueprintError" class="error" role="alert">{{ blueprintError }}</p><p v-if="blueprintMessage" class="hint" role="status">{{ blueprintMessage }}</p><p v-if="blueprintBusy" class="hint" role="status">正在处理蓝图…</p><p v-if="!blueprintBusy && !blueprints.length" class="empty">还没有收藏蓝图</p><ul v-else class="blueprint-list"><li v-for="item in blueprints" :key="item.id"><strong>{{ item.name }}</strong><code>{{ item.code }}</code><p v-if="item.notes" class="hint">{{ item.notes }}</p><div class="actions"><button type="button" class="ui-button" @click="copyCode(item.code)">复制分享码</button><button type="button" class="ui-button" :disabled="blueprintBusy" @click="editBlueprint(item)">编辑</button><button type="button" class="ui-button" :disabled="blueprintBusy" @click="removeBlueprint(item.id)">删除</button></div></li></ul></section></div>

    <div v-else-if="section === 'news'" class="endfield-stack"><AnnouncementList game-id="endfield" :snap="newsSnapshots[0]" :extra-snaps="newsSnapshots.slice(1)"><template #actions><button v-if="canMaintain" type="button" class="ui-button" :disabled="publicBusy" @click="loadPublic(true)"><AppIcon name="refresh" :size="14" />{{ publicBusy ? '正在读取…' : '刷新资讯' }}</button></template></AnnouncementList><p v-if="publicBusy" class="hint" role="status">正在读取公开资讯…</p><p v-if="publicError && !publicNewsSnap" class="error" role="alert">{{ publicError }}</p></div>
  </div>
</template>

<style scoped>
.endfield-dashboard { min-width:0; }
/* Tabs: the shared segmented control with a sliding slip (v-glide); 更多 opens a second row. */
.endfield-nav { display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:center; gap:10px 16px; margin-bottom:16px; }
.ef-main-nav { justify-self:start; }
.ef-more-nav { grid-column:1 / -1; justify-self:start; }
.ef-main-nav > button { display:inline-flex; align-items:center; gap:4px; }
.ef-main-nav > button[aria-expanded] > svg { transition:transform var(--duration-fast) var(--ease-smooth-out); }
.ef-main-nav > button[aria-expanded="true"] > svg { transform:rotate(180deg); }
.ef-calendar-link { white-space:nowrap; }

/* One 12-column bento per tab. Cards span the row unless a rule below gives them a share. */
.endfield-stack { display:grid; grid-template-columns:repeat(12,minmax(0,1fr)); gap:16px; min-width:0; }
.endfield-stack > * { grid-column:1 / -1; min-width:0; }
.ef-attendance { grid-column:span 5; }
.ef-connection ~ .ef-gacha-summary { grid-column:span 7; }
.ef-connection ~ .ef-news-summary { grid-column:span 5; }
.ef-attendance ~ .ef-news-summary { grid-column:1 / -1; }
p.empty.cap-card { padding:24px; }
.endfield-stack > p.error { padding:10px 16px; border-radius:var(--radius-tile); background:var(--danger-bg); }
.endfield-stack > p.hint { padding:0 4px; }

.hint { color:var(--text-muted); font-size:13px; line-height:1.6; overflow-wrap:anywhere; }
.error { color:var(--danger); font-size:13px; overflow-wrap:anywhere; }
.identity { font-weight:500; font-size:14px; color:var(--text); }
.cap-title { justify-content:space-between; }
.ui-button { display:inline-flex; align-items:center; gap:5px; }

/* Forms: white fields on a hairline, like the shared toolbar inputs. */
.field-grid { display:grid; gap:10px; max-width:600px; }
.field-grid label, .role-bar label, .map-filters label { display:grid; gap:5px; color:var(--text-muted); font-size:12px; }
.field-grid input, .field-grid textarea, .map-filters input, .tool-search input { box-sizing:border-box; width:100%; min-height:38px; border:1px solid var(--border); border-radius:var(--radius-control); padding:7px 14px; background:var(--card-bg); color:var(--text); font-size:13px; }
.role-bar :deep(.menu-select), .map-filters :deep(.menu-select) { width:100%; min-width:0; }
.role-bar :deep(.menu-select-trigger), .map-filters :deep(.menu-select-trigger) { min-height:38px; }
.field-grid :is(input,textarea):focus-visible, .map-filters input:focus-visible, .tool-search input:focus-visible { border-color:var(--game-accent,var(--game-endfield)); outline:0; box-shadow:var(--ring); }
.field-grid textarea { resize:vertical; }
.field-grid .ui-button { justify-self:start; }
.role-bar, .map-filters, .actions { display:flex; gap:8px; align-items:end; flex-wrap:wrap; }
.role-bar label { min-width:min(100%,240px); flex:1; }
.map-filters label { min-width:min(100%,150px); flex:1; }
.map-filters label:last-of-type { flex:2; }

/* Connection: a roomy invitation until a role is connected, then a slim strip with the role switcher. */
.ef-connection { display:grid; gap:12px; align-content:start; padding:22px 26px; }
.ef-connection > .cap-title { justify-content:flex-start; gap:8px 10px; margin:0; }
.ef-connection-dot { width:8px; height:8px; border-radius:50%; background:var(--text-faint); }
.ef-connection-dot.connected { background:var(--game-vivid); }
.ef-connection:not(.is-connected) { padding:28px 30px; }
.ef-connection:not(.is-connected) > * { max-width:min(540px,100%); }
.ef-connection:not(.is-connected) > .cap-title { font-size:20px; line-height:28px; }
.ef-connection.is-connected { display:flex; align-items:center; flex-wrap:wrap; gap:10px 18px; padding:12px 18px; }
.ef-connection.is-connected > .cap-title { font-size:14px; }
.ef-connection.is-connected > p { flex-basis:100%; margin:0; }
.ef-connection .role-bar { flex:1; align-items:center; justify-content:flex-end; gap:10px; }
.ef-connection .role-bar label { display:flex; gap:8px; align-items:center; min-width:180px; max-width:380px; }
.ef-role-label { font-size:12px; white-space:nowrap; }
.ef-connection .role-bar :deep(.menu-select) { min-width:0; width:100%; }
.ef-connection:has(.ef-connection-settings[open]) { position:relative; z-index:20; }
.ef-connection-settings { position:relative; font-size:12px; color:var(--text-muted); }
.ef-connection-settings > summary { cursor:pointer; padding:10px 0; white-space:nowrap; }
.ef-connection-settings .ui-button { position:absolute; z-index:5; right:0; top:100%; min-width:120px; background:var(--card-bg); box-shadow:var(--popover-shadow); }
.passport-connect { display:flex; align-items:center; justify-content:space-between; gap:8px 16px; flex-wrap:wrap; }
.passport-connect .hint { margin:0; }
.passport-connect .ui-button { min-height:40px; padding-inline:20px; }
.manual-connect > summary { cursor:pointer; color:var(--text-muted); font-size:13px; margin-bottom:8px; }

/* 抽卡统计: the passport account is a slim strip above the bento. */
.ef-identity-card { display:flex; flex-wrap:wrap; align-items:center; gap:6px 16px; padding:12px 18px; }
.ef-identity-card > .cap-title { flex:0 0 auto; margin:0; font-size:14px; }
.ef-identity-card .identity { margin:0; }
.ef-identity-card .hint { flex-basis:100%; margin:0; }
.ef-identity-card > .ui-button { margin-left:auto; }

/* 地图与图鉴 · 蓝图收藏: lists keep their rows; boxes inside a card take a tone step. */
.inner-card, .tool-grid li { border-radius:var(--radius-tile); background:var(--surface-soft); padding:14px; min-width:0; }
.inner-card h3 { font-size:14px; font-weight:600; color:var(--text); margin:0 0 6px; }
.inner-card p { font-size:13px; color:var(--text-muted); line-height:1.6; overflow-wrap:anywhere; }
.cap-card > p.badge { margin:10px 0 4px; }
.mark-list li { display:flex; justify-content:space-between; gap:12px; align-items:start; padding:12px 0; border-bottom:1px solid var(--border); }
.mark-list strong, .blueprint-list strong { font-size:13px; font-weight:500; }
.mark-list a, .tool-grid a, .inner-card a { display:inline-flex; align-items:center; gap:4px; font-size:13px; color:var(--accent); text-decoration:none; }
.tool-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.tool-grid a { justify-content:space-between; width:100%; }
.tool-grid a strong { font-weight:500; }
.blueprint-list { margin-top:14px; }
.blueprint-list li { padding:12px 0; border-top:1px solid var(--border); }
.blueprint-list code { display:block; white-space:pre-wrap; overflow-wrap:anywhere; color:var(--text-muted); font-size:12px; margin:6px 0; }
.blueprint-list .actions { margin-top:9px; }
.tool-search { display:grid; gap:5px; color:var(--text-muted); font-size:12px; margin:12px 0; }
.catalog-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.catalog-item { display:grid; gap:5px; align-content:start; }
.catalog-item h3 { margin:0; }
.catalog-description { display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2; overflow:hidden; }
.catalog-item details { margin-top:4px; border-top:1px solid var(--border-strong); padding-top:6px; color:var(--text-muted); font-size:13px; overflow-wrap:anywhere; }
.catalog-item summary { cursor:pointer; color:var(--accent); }
.catalog-item details li { padding:4px 0; border-bottom:1px solid var(--border-strong); }
.catalog-item details a { display:inline-flex; align-items:center; gap:4px; margin-top:7px; }

@media(max-width:900px) {
  .ef-attendance, .ef-connection ~ .ef-gacha-summary, .ef-connection ~ .ef-news-summary { grid-column:1 / -1; }
  .ef-connection .role-bar { justify-content:flex-start; }
}
@media(max-width:720px) {
  .tool-grid, .catalog-grid { grid-template-columns:1fr; }
  .role-bar > * { width:100%; }
  .map-filters label, .map-filters label:last-of-type { min-width:100%; }
  .mark-list li { flex-direction:column; }
}
@media(max-width:600px) {
  .endfield-nav { grid-template-columns:minmax(0,1fr); }
  .ef-calendar-link { justify-self:end; }
  .ef-connection:not(.is-connected) { padding:24px 20px; }
  .ef-connection.is-connected { padding:12px; gap:12px; }
  .ef-connection .role-bar { width:100%; gap:8px; }
  .ef-connection .role-bar > label { flex-basis:100%; max-width:none; }
  .ef-connection .role-bar > button, .ef-connection .role-bar > details { width:auto; }
  .ef-connection .role-bar > details { margin-left:auto; }
  .ef-connection-settings .ui-button { width:auto; }
  .ef-identity-card { padding:12px 16px; }
}
</style>
