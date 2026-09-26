<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { fetchedLabel } from '../time.js'
import { safeUrl } from '../calendar.js'
import { filterRoles, comparisonGroups, favoritesKey, loadFavorites, saveFavorites, roleId, displayRoleValue as display } from '../nte-roles.js'
import AppIcon from './AppIcon.vue'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'

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
const qualityCount = value => roles.value.filter(role => role.quality === value).length
const isFavorite = role => favorites.value.includes(roleId(role))
const isCompared = role => selected.value.includes(keyOf(role))
function favoriteTitle(role) {
  if (!roleId(role)) return '角色标识未提供，暂不可收藏'
  if (!canPersist.value) return '当前账号身份未提供，暂不可收藏'
  return isFavorite(role) ? '取消收藏' : '收藏'
}
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
function imageFailed(event) { const url = safeUrl(event.currentTarget?.src); if (url) failedImages.add(url) }
</script>

<template>
  <section class="cap-card nte-roles-panel">
    <div class="cap-title">
      角色练度
      <InfoHint v-if="roles.length" text="未提供的排序值排在最后。收藏仅保存在当前浏览器，按异环账号区分。" />
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="roles.length" class="chip-list summary">
        <span class="chip">角色总数 <b>{{ roles.length }}</b></span>
        <span class="chip">S级 <b>{{ qualityCount('S') }}</b></span>
        <span class="chip">A级 <b>{{ qualityCount('A') }}</b></span>
      </span>
      <span v-if="fetchedLabel(snap?.fetched_at)" class="cap-meta">更新于 {{ fetchedLabel(snap?.fetched_at) }}</span>
    </div>
    <p v-if="payload === null" class="empty">暂无数据，请登录后刷新</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>
    <p v-else-if="!roles.length" class="empty">暂无数据</p>
    <template v-else>
      <div class="toolbar">
        <input class="grow" type="search" aria-label="搜索角色" placeholder="搜索角色名称" :value="search" @input="search = $event.target.value" />
        <MenuSelect v-model="quality" label="品质筛选" :options="[{ value: '', label: '全部品质' }, ...qualities]" />
        <MenuSelect v-model="element" label="元素筛选" :options="[{ value: '', label: '全部元素' }, ...elements]" />
        <MenuSelect v-model="sort" label="角色排序" :options="[{ value: 'level', label: '按等级' }, { value: 'awaken_level', label: '按觉醒' }, { value: 'mix_level', label: '按混频' }, { value: 'name', label: '按名称' }]" />
        <MenuSelect v-model="direction" label="排序方向" align="end" :options="[{ value: 'desc', label: '降序' }, { value: 'asc', label: '升序' }]" />
        <label class="favorite-filter"><input type="checkbox" aria-label="仅收藏" :checked="favoritesOnly" @change="favoritesOnly = $event.target.checked" /><span>仅收藏</span></label>
        <span class="count">显示 {{ visible.length }} / {{ roles.length }}</span>
      </div>
      <p v-if="!canPersist" class="notice">当前账号身份未提供，暂不可收藏。</p>
      <p v-if="storageError" class="notice" role="status">{{ storageError }}</p>
      <div class="compare-tray" role="group" aria-label="角色对比选择">
        <div class="compare-heading">
          <strong>角色对比</strong>
          <span class="compare-count">已选 {{ selected.length }} / 4</span>
          <InfoHint v-if="selected.length < 2" text="至少选择 2 名角色，最多 4 名。切换筛选后保留对比选择。" />
          <InfoHint v-else text="按字段名称对齐；战技与城区技能数值为等级，属性保留来源值与单位。未提供不等于零。" />
          <span v-if="compared.length" class="compare-chips">
            <button v-for="role in compared" :key="keyOf(role)" type="button" class="compare-chip" :aria-label="`移除对比${role.name || '角色'}`" @click="toggleCompare(role)">{{ display(role.name) }}<AppIcon name="close" :size="11" /></button>
          </span>
          <button v-if="selected.length" type="button" class="ui-button ghost small-button clear-compare" @click="selected = []">清空对比</button>
        </div>
        <div v-if="selected.length >= 2" class="comparison-scroll" tabindex="0" role="region" aria-label="角色对比表，可横向滚动">
          <table class="data-table"><caption class="sr-only">已选角色的基础、弧盘、属性、战技和城区技能</caption><thead><tr><th scope="col">字段</th><th v-for="role in compared" :key="keyOf(role)" scope="col">{{ display(role.name) }}</th></tr></thead>
            <tbody v-for="group in groups" :key="group.name"><tr class="group-row"><th :colspan="compared.length + 1" scope="colgroup">{{ group.name }}</th></tr>
              <tr v-for="(row, i) in group.rows" :key="i"><th scope="row">{{ row.name }}</th><td v-for="(value, index) in row.values" :key="index">{{ value }}</td></tr>
              <tr v-if="!group.rows.length"><th scope="row">数据</th><td v-for="role in compared" :key="keyOf(role)">未提供</td></tr>
            </tbody>
          </table>
        </div>
      </div>
      <p v-if="!visible.length" class="empty">没有符合筛选条件的角色</p>
      <ul v-else class="role-grid">
        <li v-for="(role, index) in visible" :key="keyOf(role)" class="role-card t-item" :class="{ compared: isCompared(role) }" :style="{ '--i': Math.min(index, 11) }">
          <div class="role-top">
            <img v-if="safeUrl(role.icon_url) && !failedImages.has(safeUrl(role.icon_url))" :key="safeUrl(role.icon_url)" :src="safeUrl(role.icon_url)" :alt="role.name || '角色'" loading="lazy" class="avatar" @error="imageFailed" />
            <span v-else class="avatar avatar-empty" aria-hidden="true">{{ (role.name || '?').slice(0, 1) }}</span>
            <div class="role-heading">
              <strong :title="role.name">{{ display(role.name) }}</strong>
              <span class="role-sub"><span class="rank" :class="`rank-${role.quality}`">{{ display(role.quality) }}</span><span>{{ display(role.element) }}</span><span class="level">Lv{{ display(role.level) }}</span></span>
            </div>
            <div class="role-actions">
              <button type="button" class="icon-button favorite" :aria-label="`${isFavorite(role) ? '取消收藏' : '收藏'}${role.name || '角色'}`" :aria-pressed="isFavorite(role)" :disabled="!canPersist || !roleId(role)" :title="favoriteTitle(role)" @click="toggleFavorite(role)"><AppIcon name="star" :size="15" /></button>
              <button type="button" class="icon-button" :aria-label="`对比${role.name || '角色'}`" :aria-pressed="isCompared(role)" :disabled="selected.length >= 4 && !isCompared(role)" :title="isCompared(role) ? '移出对比' : '加入对比'" @click="toggleCompare(role)"><AppIcon :name="isCompared(role) ? 'close' : 'plus'" :size="15" /></button>
            </div>
          </div>
          <details class="role-more">
            <summary>
              <span class="chip">觉醒 <b>{{ display(role.awaken_level) }}</b></span>
              <span class="chip">混频 <b>{{ display(role.mix_level) }}</b></span>
              <span class="chip">羁遇累计经验 <b>{{ display(role.affinity_exp) }}</b></span>
              <span class="sr-only">{{ role.name || '角色' }}详情</span>
              <AppIcon name="chevron" :size="14" class="t-disclosure" />
            </summary>
            <div class="detail-body">
              <section class="detail-group">
                <h4>弧盘</h4>
                <p v-if="role.weapon" class="weapon"><strong>{{ display(role.weapon.name) }}</strong><span class="chip">{{ display(role.weapon.quality) }}</span><span class="chip">Lv{{ display(role.weapon.level) }}</span><span class="chip">混频 <b>{{ display(role.weapon.mix_level) }}</b></span></p>
                <p v-else class="muted">暂无数据</p>
              </section>
              <section v-for="group in [{ name: '属性', rows: role.properties, value: 'value' }, { name: '战技', rows: role.skills, value: 'level' }, { name: '城区技能', rows: role.city_skills, value: 'level' }]" :key="group.name" class="detail-group">
                <h4>{{ group.name }}</h4>
                <dl v-if="list(group.rows).length" class="detail-rows"><div v-for="(entry, index) in list(group.rows)" :key="index"><dt>{{ display(entry.name) }}</dt><dd>{{ group.value === 'level' && display(entry[group.value]) !== '未提供' ? 'Lv' : '' }}{{ display(entry[group.value]) }}</dd></div></dl>
                <p v-else class="muted">暂无数据</p>
              </section>
            </div>
          </details>
        </li>
      </ul>
    </template>
  </section>
</template>

<style scoped>
.nte-roles-panel { min-width: 0; overflow-wrap: anywhere; }
.cap-title { position: relative; }
.summary { gap: 4px; }
.muted { color: var(--text-muted); font-size: 12px; line-height: 1.6; }
input[type=checkbox] { margin: 0; accent-color: var(--accent); }
.toolbar input[type=search] { min-width: 150px; }
.favorite-filter { display: inline-flex; align-items: center; gap: 6px; min-height: 30px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 7px; color: var(--text-body); font-size: 12px; cursor: pointer; }
.favorite-filter:has(input:checked) { border-color: color-mix(in srgb, var(--accent) 35%, transparent); background: var(--accent-soft); color: var(--accent-strong); }
.favorite-filter:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.notice { margin: 0 0 8px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 7px; background: var(--panel-bg); color: var(--text-muted); font-size: 12px; }

/* Comparison: a one-line strip until two roles are picked, then the table. */
.compare-tray { margin: 0 0 12px; padding: 6px 10px; border-radius: 8px; background: var(--overlay-2); }
.compare-heading { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; min-height: 28px; font-size: 12px; }
.compare-heading > strong { color: var(--text); font-size: 13px; font-weight: 600; }
.compare-count { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.compare-chips { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.compare-chip { display: inline-flex; align-items: center; gap: 4px; min-height: 22px; padding: 0 6px 0 8px; border: 0; border-radius: 5px; background: var(--accent-soft); color: var(--accent-strong); font-size: 12px; font-weight: 500; }
.compare-chip:not(:disabled):active { transform: scale(var(--scale-medium)); }
.clear-compare { margin-left: auto; min-height: 24px; padding: 2px 8px; }
.comparison-scroll { overflow-x: auto; margin: 6px -10px -6px; padding: 0 10px 6px; }
.comparison-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 8px; }
.comparison-scroll table { min-width: 460px; table-layout: fixed; font-variant-numeric: tabular-nums; }
.comparison-scroll :is(th, td) { padding-top: 4px; padding-bottom: 4px; line-height: 18px; }
.comparison-scroll thead th:first-child { width: 112px; }
.comparison-scroll tbody tr:last-child th { border-bottom: 0; }
.comparison-scroll tbody th { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.comparison-scroll .group-row th { padding-top: 10px; color: var(--text); font-size: 11px; font-weight: 600; letter-spacing: .03em; }

/* Role cards: portrait, name and rank on one line; actions top-right; the
   level chips double as the disclosure for the full sheet. */
.role-grid { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr)); gap: 8px; align-items: start; }
.role-card { min-width: 0; padding: 8px 10px; border: 1px solid var(--border); border-radius: 10px; background: var(--card-bg); }
.role-card.compared { border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.role-top { display: flex; align-items: center; gap: 8px; }
.avatar { width: 36px; height: 36px; flex-shrink: 0; border-radius: 8px; object-fit: cover; background: var(--surface-soft); }
.avatar-empty { display: grid; place-items: center; color: var(--text-muted); font-size: 15px; }
.role-heading { display: grid; gap: 1px; min-width: 0; flex: 1; }
.role-heading > strong { overflow: hidden; color: var(--text); font-size: 13px; line-height: 18px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.role-sub { display: flex; align-items: center; gap: 6px; color: var(--text-muted); font-size: 11px; line-height: 16px; white-space: nowrap; }
.rank { padding: 0 4px; border-radius: 3px; background: var(--overlay-3); color: var(--text-body); font-size: 10px; font-weight: 700; line-height: 14px; }
/* Letters mix toward the text colour: lighter at night, darker by day, so the
   10px glyph keeps its contrast on the tint in both themes. */
.rank-S { background: color-mix(in srgb, var(--chart-4) 18%, transparent); color: color-mix(in srgb, var(--chart-4) 60%, var(--text)); }
.rank-A { background: color-mix(in srgb, var(--chart-5) 16%, transparent); color: color-mix(in srgb, var(--chart-5) 75%, var(--text)); }
.level { color: var(--text-body); font-variant-numeric: tabular-nums; }
.role-actions { display: flex; gap: 4px; margin-left: auto; align-self: flex-start; }
/* Quiet until used: 24 bordered buttons would outweigh the data. */
.role-actions .icon-button { width: 28px; height: 28px; border-color: transparent; border-radius: 6px; background: transparent; box-shadow: none; color: var(--text-faint); }
@media (hover: hover) and (pointer: fine) { .role-actions .icon-button:not(:disabled):not([aria-pressed=true]):hover { background: var(--hover-bg); color: var(--text); } }
.role-actions .icon-button:disabled { opacity: .4; cursor: not-allowed; }
.role-actions .icon-button[aria-pressed=true] { border-color: transparent; background: var(--accent-soft); color: var(--accent-strong); }
.role-actions .favorite[aria-pressed=true] { background: color-mix(in srgb, var(--chart-4) 16%, transparent); color: var(--chart-4); }
.role-actions .favorite[aria-pressed=true] svg { fill: currentColor; }
.role-actions .icon-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.role-more { margin-top: 6px; }
.role-more > summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin: 0 -4px; padding: 2px 4px; border-radius: 6px; list-style: none; cursor: pointer; }
.role-more > summary::-webkit-details-marker { display: none; }
.role-more > summary > svg { margin-left: auto; color: var(--text-faint); }
.role-more > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; }
@media (hover: hover) and (pointer: fine) { .role-more > summary:hover { background: var(--hover-bg); } .role-more > summary:hover > svg { color: var(--text-body); } }
.detail-body { display: grid; gap: 8px; margin-top: 6px; padding-top: 8px; border-top: 1px solid var(--border); }
.detail-group h4 { margin: 0 0 3px; color: var(--text-faint); font-size: 11px; font-weight: 500; letter-spacing: .03em; }
.weapon { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; font-size: 12px; }
.weapon > strong { margin-right: 2px; color: var(--text); font-weight: 600; }
.detail-rows { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 12px; margin: 0; }
.detail-rows > div { display: flex; justify-content: space-between; gap: 6px; min-width: 0; padding: 1px 0; font-size: 12px; line-height: 18px; }
.detail-rows dt { overflow: hidden; color: var(--text-muted); text-overflow: ellipsis; white-space: nowrap; }
.detail-rows dd { margin: 0; color: var(--text); font-variant-numeric: tabular-nums; white-space: nowrap; }
@media (max-width: 560px) {
  .toolbar .menu-select { flex: 1 1 calc(25% - 8px); min-width: 0; }
  .toolbar .count { margin-left: auto; }
}
</style>
