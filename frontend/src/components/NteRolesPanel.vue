<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { displayBeijing } from '../time.js'
import { filterRoles, comparisonGroups, favoritesKey, loadFavorites, saveFavorites, roleId, displayRoleValue as display } from '../nte-roles.js'

const props = defineProps({ snap: { type: Object, default: null }, accountId: { type: String, default: '' } })
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const list = value => Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : []
const roles = computed(() => legacy.value ? [] : list(payload.value?.entries))
const search = ref(''), quality = ref(''), element = ref(''), favoritesOnly = ref(false), sort = ref('level'), direction = ref('desc')
const favorites = ref([]), storageError = ref(''), selected = ref([]), failedImages = reactive(new Set())
const canPersist = computed(() => Boolean(favoritesKey(props.accountId)))
const keyOf = role => roleId(role) ? `id:${roleId(role)}` : `row:${roles.value.indexOf(role)}`
watch(() => props.accountId, () => {
  const loaded = loadFavorites(props.accountId)
  favorites.value = loaded.ids; storageError.value = loaded.error ?? ''; selected.value = []; favoritesOnly.value = false
}, { immediate: true })
watch(roles, () => { selected.value = selected.value.filter(key => roles.value.some(role => keyOf(role) === key)) })
const options = field => [...new Set(roles.value.map(role => role[field]).filter(value => typeof value === 'string' && value))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
const qualities = computed(() => options('quality')), elements = computed(() => options('element'))
const visible = computed(() => filterRoles(roles.value, { search: search.value, quality: quality.value, element: element.value, favoritesOnly: favoritesOnly.value, favorites: favorites.value, sort: sort.value, direction: direction.value }))
const compared = computed(() => selected.value.map(key => roles.value.find(role => keyOf(role) === key)).filter(Boolean))
const groups = computed(() => comparisonGroups(compared.value))
const isFavorite = role => favorites.value.includes(roleId(role))
function toggleFavorite(role) {
  const id = roleId(role)
  if (!canPersist.value || !id) return
  favorites.value = isFavorite(role) ? favorites.value.filter(value => value !== id) : [...favorites.value, id]
  storageError.value = saveFavorites(props.accountId, favorites.value).error ?? ''
}
function toggleCompare(role) {
  const key = keyOf(role)
  if (selected.value.includes(key)) selected.value = selected.value.filter(value => value !== key)
  else if (selected.value.length < 4) selected.value = [...selected.value, key]
}
function safeUrl(value) {
  if (typeof value !== 'string' || !/^https?:\/\//i.test(value)) return null
  try { const url = new URL(value); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null } catch { return null }
}
function imageFailed(event) { const url = safeUrl(event.currentTarget?.src); if (url) failedImages.add(url) }
</script>

<template>
  <section class="cap-card nte-roles-panel">
    <div class="cap-title">角色练度 <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span></div>
    <p v-if="payload === null" class="empty">暂无数据，请登录后刷新</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>
    <p v-else-if="!roles.length" class="empty">暂无数据</p>
    <template v-else>
      <p class="muted">角色总数 {{ roles.length }} · S级 {{ roles.filter(role => role.quality === 'S').length }} · A级 {{ roles.filter(role => role.quality === 'A').length }}</p>
      <div class="role-toolbar">
        <label class="search-label">名称<input aria-label="搜索角色" type="search" placeholder="搜索角色名称" :value="search" @input="search = $event.target.value" /></label>
        <label>品质<select aria-label="品质筛选" :value="quality" @change="quality = $event.target.value"><option value="">全部品质</option><option v-for="item in qualities" :key="item" :value="item">{{ item }}</option></select></label>
        <label>元素<select aria-label="元素筛选" :value="element" @change="element = $event.target.value"><option value="">全部元素</option><option v-for="item in elements" :key="item" :value="item">{{ item }}</option></select></label>
        <label>排序<select aria-label="角色排序" :value="sort" @change="sort = $event.target.value"><option value="level">等级</option><option value="awaken_level">觉醒</option><option value="mix_level">混频</option><option value="name">名称</option></select></label>
        <label>顺序<select aria-label="排序方向" :value="direction" @change="direction = $event.target.value"><option value="desc">降序</option><option value="asc">升序</option></select></label>
        <label class="favorite-filter"><input type="checkbox" aria-label="仅收藏" :checked="favoritesOnly" @change="favoritesOnly = $event.target.checked" />仅收藏</label>
      </div>
      <p class="muted">显示 {{ visible.length }} / {{ roles.length }} · 未提供的排序值排在最后。收藏仅保存在当前浏览器，按异环账号区分。</p>
      <p v-if="!canPersist" class="notice">当前账号身份未提供，暂不可收藏。</p>
      <p v-if="storageError" class="notice" role="status">{{ storageError }}</p>
      <div class="compare-tray" aria-label="角色对比选择">
        <div class="compare-heading"><strong>角色对比</strong><span class="muted">已选 {{ selected.length }} / 4</span><button v-if="selected.length" type="button" @click="selected = []">清空对比</button></div>
        <div v-if="compared.length" class="compare-chips"><button v-for="role in compared" :key="keyOf(role)" type="button" :aria-label="`移除对比${role.name || '角色'}`" @click="toggleCompare(role)">{{ display(role.name) }} ×</button></div>
        <p v-if="selected.length < 2" class="muted">至少选择 2 名角色，最多 4 名。切换筛选后保留对比选择。</p>
        <template v-else>
          <p class="muted">按字段名称对齐；战技与城区技能数值为等级，属性保留来源值与单位。未提供不等于零。</p>
          <div class="comparison-scroll" tabindex="0" role="region" aria-label="角色对比表，可横向滚动">
            <table><caption class="sr-only">已选角色的基础、弧盘、属性、战技和城区技能</caption><thead><tr><th scope="col">字段</th><th v-for="role in compared" :key="keyOf(role)" scope="col">{{ display(role.name) }}</th></tr></thead>
              <tbody v-for="group in groups" :key="group.name"><tr class="group-row"><th :colspan="compared.length + 1" scope="colgroup">{{ group.name }}</th></tr>
                <tr v-for="(row, i) in group.rows" :key="i"><th scope="row">{{ row.name }}</th><td v-for="(value, index) in row.values" :key="index">{{ value }}</td></tr>
                <tr v-if="!group.rows.length"><th scope="row">数据</th><td v-for="role in compared" :key="keyOf(role)">未提供</td></tr>
              </tbody>
            </table>
          </div>
        </template>
      </div>
      <p v-if="!visible.length" class="empty">没有符合筛选条件的角色</p>
      <ul v-else class="role-grid">
        <li v-for="role in visible" :key="keyOf(role)" class="role-card">
          <div class="role-overview">
            <img v-if="safeUrl(role.icon_url) && !failedImages.has(safeUrl(role.icon_url))" :key="safeUrl(role.icon_url)" :src="safeUrl(role.icon_url)" :alt="role.name || '角色'" loading="lazy" class="avatar" @error="imageFailed" />
            <span v-else class="avatar avatar-empty" aria-hidden="true">{{ (role.name || '?').slice(0, 1) }}</span>
            <div class="role-heading"><strong>{{ display(role.name) }}</strong><span>{{ display(role.quality) }} · {{ display(role.element) }} · Lv{{ display(role.level) }}</span></div>
          </div>
          <p class="role-meta">觉醒 {{ display(role.awaken_level) }} · 混频 {{ display(role.mix_level) }}</p>
          <p class="muted">羁遇累计经验 {{ display(role.affinity_exp) }}</p>
          <div class="role-actions">
            <button type="button" :aria-label="`${isFavorite(role) ? '取消收藏' : '收藏'}${role.name || '角色'}`" :aria-pressed="isFavorite(role)" :disabled="!canPersist || !roleId(role)" :title="!roleId(role) ? '角色标识未提供，暂不可收藏' : ''" @click="toggleFavorite(role)">{{ isFavorite(role) ? '★ 已收藏' : '☆ 收藏' }}</button>
            <button type="button" :aria-label="`对比${role.name || '角色'}`" :aria-pressed="selected.includes(keyOf(role))" :disabled="selected.length >= 4 && !selected.includes(keyOf(role))" @click="toggleCompare(role)">{{ selected.includes(keyOf(role)) ? '移出对比' : '加入对比' }}</button>
          </div>
          <details><summary>{{ role.name || '角色' }}详情</summary><div class="detail-body">
            <h4>弧盘</h4><template v-if="role.weapon"><strong>{{ display(role.weapon.name) }}</strong><p class="muted">{{ display(role.weapon.quality) }} · Lv{{ display(role.weapon.level) }} · 混频 {{ display(role.weapon.mix_level) }}</p></template><p v-else class="muted">暂无数据</p>
            <template v-for="group in [{ name: '属性', rows: role.properties, value: 'value' }, { name: '战技', rows: role.skills, value: 'level' }, { name: '城区技能', rows: role.city_skills, value: 'level' }]" :key="group.name">
              <h4>{{ group.name }}</h4><dl v-if="list(group.rows).length" class="detail-rows"><div v-for="(entry, index) in list(group.rows)" :key="index"><dt>{{ display(entry.name) }}</dt><dd>{{ group.value === 'level' && display(entry[group.value]) !== '未提供' ? 'Lv' : '' }}{{ display(entry[group.value]) }}</dd></div></dl><p v-else class="muted">暂无数据</p>
            </template>
          </div></details>
        </li>
      </ul>
    </template>
    <p v-if="snap?.fetched_at" class="fetched-at">更新于 {{ displayBeijing(snap.fetched_at) }}</p>
  </section>
</template>

<style scoped>
.nte-roles-panel { min-width: 0; overflow-wrap: anywhere; }
.muted { color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.role-toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: end; margin: 16px 0 10px; }
.role-toolbar label { display: grid; gap: 6px; color: var(--text-muted); font-size: 12px; }
.role-toolbar .search-label { flex: 1 1 180px; }
input, select, button { color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 7px; padding: 8px 10px; font: inherit; }
input[type=search] { min-width: 0; width: 100%; box-sizing: border-box; }
input[type=checkbox] { accent-color: var(--accent); }
.role-toolbar .favorite-filter { display: flex; align-items: center; min-height: 36px; }
button { cursor: pointer; font-size: 12px; }
button[aria-pressed=true] { color: var(--accent); border-color: var(--accent); }
button:disabled { cursor: default; opacity: .45; }
button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible, .comparison-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.notice { color: var(--accent); padding: 10px 12px; background: var(--bg); border-radius: 6px; font-size: 12px; margin-top: 10px; }
.compare-tray { margin-top: 16px; padding: 14px; background: var(--bg); border: 1px solid var(--border); border-radius: 10px; }
.compare-heading, .compare-chips, .role-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.compare-heading { margin-bottom: 8px; }.compare-heading strong { color: var(--accent); font-size: 14px; }.compare-heading > button { margin-left: auto; }
.compare-chips { margin-bottom: 8px; }.compare-chips button { color: var(--accent); }
.comparison-scroll { overflow-x: auto; margin-top: 12px; }
table { width: 100%; min-width: 500px; border-collapse: collapse; font-size: 12px; table-layout: fixed; }
th, td { padding: 10px; border: 1px solid var(--border); text-align: left; font-variant-numeric: tabular-nums; }
thead th { color: var(--accent); } tbody th { color: var(--text-muted); font-weight: 500; }.group-row th { color: var(--accent); background: var(--bg-card, var(--bg)); font-weight: 600; }
.role-grid { margin: 16px 0 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); gap: 12px; align-items: start; }
.role-card { border: 1px solid var(--border); border-radius: 10px; padding: 14px; min-width: 0; }
.role-overview { display: flex; align-items: center; gap: 10px; }.avatar { width: 52px; height: 52px; border-radius: 8px; object-fit: cover; background: var(--bg); flex-shrink: 0; }.avatar-empty { display: grid; place-items: center; color: var(--text-muted); font-size: 20px; }
.role-heading { display: grid; gap: 5px; }.role-heading > span { color: var(--text-muted); font-size: 12px; }.role-meta { font-size: 13px; margin: 10px 0 4px; }.role-actions { margin-top: 12px; }
details { margin-top: 12px; border-top: 1px solid var(--border); } summary { color: var(--accent); cursor: pointer; padding: 10px 0 2px; font-size: 13px; }.detail-body h4 { margin: 12px 0 6px; font-size: 13px; }.detail-rows { margin: 0; }.detail-rows > div { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; }.detail-rows dt { color: var(--text-muted); font-size: 12px; }.detail-rows dd { margin: 0; font-size: 12px; font-variant-numeric: tabular-nums; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 560px) { .role-toolbar label:not(.search-label):not(.favorite-filter) { flex: 1 1 40%; }.role-toolbar .search-label { flex-basis: 100%; }.compare-tray { padding: 10px; } }
</style>
