<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { fetchedLabel } from '../time.js'
import { safeUrl } from '../calendar.js'
import { filterRoles, comparisonGroups, favoritesKey, loadFavorites, saveFavorites, roleId, displayRoleValue as display } from '../nte-roles.js'
import AppIcon from './AppIcon.vue'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'
import NteIcon from './NteIcon.vue'
import NteRoleDetail from './NteRoleDetail.vue'
import NteRoleDialog from './NteRoleDialog.vue'
import NteRoleSheet from './NteRoleSheet.vue'
import { roleBreakdown } from '../nte-charts.js'
import { levelBands } from '../wuwa-charts.js'
import BarChart from './BarChart.vue'
import DonutChart from './DonutChart.vue'

import { nteRoleIcon } from '../nte-icons.js'
import { skinOf } from '../game-themes.js'

const props = defineProps({ snap: { type: Object, default: null }, accountId: { type: [String,Object], default: '' }, focusCharacterId:{type:String,default:''}, imageMode:{type:Boolean,default:false}, detailMode:{type:Boolean,default:false}, guideCharacterId:{type:String,default:''}, initialGuideBrowser:Boolean, canMaintain:{type:Boolean,default:true} })
const openedKey=ref(null),detailTab=ref('panel'),browseGuides=ref(props.initialGuideBrowser)
function openRole(role,tab='panel'){openedKey.value=keyOf(role);detailTab.value=tab;browseGuides.value=false}
function openOwned(id){const role=roles.value.find(row=>roleId(row)===String(id));if(role)openRole(role)}

const payload = computed(() => props.snap?.payload ?? null)
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const list = value => Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : []
const roles = computed(() => legacy.value ? [] : list(payload.value?.entries))
const breakdown=computed(()=>roleBreakdown(roles.value))
const qualitySegments=computed(()=>breakdown.value.quality.map((row,i)=>({...row,color:['var(--chart-1)','var(--chart-2)','var(--chart-3)'][i%3]})))

const search = ref(''), quality = ref(''), element = ref(''), favoritesOnly = ref(false), sort = ref('newest'), direction = ref('desc')
const favorites = ref([]), storageError = ref(''), selected = ref([]), failedImages = reactive(new Set())
const canPersist = computed(() => Boolean(favoritesKey(props.accountId)))
const openedRole=computed(()=>roles.value.find(role=>keyOf(role)===openedKey.value)||null)
const keyOf = role => roleId(role) ? `id:${roleId(role)}` : `row:${roles.value.indexOf(role)}`
watch(()=>props.guideCharacterId,id=>{if(id){const role=roles.value.find(row=>roleId(row)===id);openedKey.value=role?keyOf(role):null;detailTab.value='guide';browseGuides.value=!role}},{immediate:true})
watch(() => props.accountId, () => {
  if (props.imageMode) return
  const loaded = loadFavorites(props.accountId)
  favorites.value = loaded.ids; storageError.value = loaded.error ?? ''; selected.value = []; favoritesOnly.value = false
}, { immediate: true })
watch(()=>props.accountId,()=>{openedKey.value=null;browseGuides.value=false})
watch(roles, () => { if(openedKey.value && !openedRole.value)openedKey.value=null; selected.value = selected.value.filter(key => roles.value.some(role => keyOf(role) === key)) })
const options = field => [...new Set(roles.value.map(role => role[field]).filter(value => typeof value === 'string' && value))].sort((a, b) => a.localeCompare(b, 'zh-CN'))
const qualities = computed(() => options('quality')), elements = computed(() => options('element'))
const visible = computed(() => filterRoles(roles.value, { search: search.value, quality: quality.value, element: element.value, favoritesOnly: favoritesOnly.value, favorites: favorites.value, sort: sort.value, direction: direction.value }))
watch(()=>[props.focusCharacterId,roles.value],([id])=>{if(id&&!props.detailMode&&!props.imageMode)openOwned(id)},{immediate:true})
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
  <section class="cap-card nte-roles-panel" :class="{ 'role-detail-view': detailMode, 'is-image': imageMode }" :data-skin="imageMode ? undefined : skinOf('nte')">
    <div class="cap-title">
      角色练度
      <button v-if="!imageMode && !detailMode" type="button" class="ui-button small-button" @click="browseGuides=true">浏览全部攻略</button>
      <InfoHint v-if="roles.length" text="收藏保存在当前浏览器，按账号与角色分别保存。" />
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="roles.length && !(imageMode && detailMode)" class="chip-list summary">
        <span class="chip">角色总数 <b>{{ roles.length }}</b></span>
        <span class="chip">S级 <b>{{ qualityCount('S') }}</b></span>
        <span class="chip">A级 <b>{{ qualityCount('A') }}</b></span>
      </span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>
    <p v-if="snap?.reading && payload === null" class="empty" role="status">正在读取角色…</p>
    <p v-else-if="snap?.readError && payload === null" class="empty" role="alert">{{ snap.readError }}</p>
    <p v-else-if="payload === null" class="empty">暂无数据，请刷新后查看</p>
    <p v-else-if="legacy" class="empty">数据格式已更新，请刷新</p>
    <p v-else-if="!roles.length" class="empty">暂无数据</p>
    <template v-else>
      <p v-if="imageMode && !detailMode" class="notice">完整角色概览。查看装备、属性与技能详情：异环 角色 名称</p>
      <div v-if="!imageMode && !detailMode" class="roster-charts"><DonutChart :segments="qualitySegments" label="角色品质分布" unit="位" :size="120"><b>{{ roles.length }}</b></DonutChart><BarChart :items="breakdown.element" label="角色元素分布" /><BarChart :items="levelBands(roles)" label="角色等级分布" unit=" 位" /></div>
      <div v-if="!imageMode && !detailMode" class="toolbar">
        <input class="grow" type="search" aria-label="搜索角色" placeholder="名称、别名、拼音或首字母" :value="search" @input="$event.isComposing || (search = $event.target.value)" @compositionend="search = $event.target.value" />
        <MenuSelect v-model="quality" label="品质筛选" :options="[{ value: '', label: '全部品质' }, ...qualities]" />
        <MenuSelect v-model="element" label="元素筛选" :options="[{ value: '', label: '全部元素' }, ...elements]" />
        <MenuSelect v-model="sort" label="角色排序" :options="[{ value: 'newest', label: '从新到旧' }, { value: 'level', label: '按等级' }, { value: 'awaken_level', label: '按觉醒' }, { value: 'mix_level', label: '按混频' }, { value: 'name', label: '按名称' }]" />
        <MenuSelect v-model="direction" label="排序方向" align="end" :options="[{ value: 'desc', label: '降序' }, { value: 'asc', label: '升序' }]" />
        <label class="favorite-filter"><input type="checkbox" aria-label="仅收藏" :checked="favoritesOnly" @change="favoritesOnly = $event.target.checked" /><span>仅收藏</span></label>
        <span class="count">显示 {{ visible.length }} / {{ roles.length }}</span>
      </div>
      <p v-if="!canPersist && !imageMode" class="notice">登录账号后可收藏角色。</p>
      <p v-if="storageError" class="notice" role="status">{{ storageError }}</p>
      <div v-if="!imageMode && !detailMode" class="compare-tray" role="group" aria-label="角色对比选择">
        <div class="compare-heading">
          <strong>角色对比</strong>
          <span class="compare-count">已选 {{ selected.length }} / 4</span>
          <InfoHint v-if="selected.length < 2" text="至少选择 2 名角色，最多 4 名。切换筛选后保留对比选择。" />
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
      <!-- A selected role's image is the role sheet; the website and the roster keep the cards. -->
      <template v-else-if="imageMode && detailMode"><NteRoleSheet v-for="role in visible" :key="keyOf(role)" :role="role" /></template>
      <ul v-else class="role-grid">
        <li v-for="(role, index) in visible" :key="keyOf(role)" class="role-card t-item" :data-render-block="imageMode && !detailMode ? '' : undefined" :class="{ compared: isCompared(role) }" :style="{ '--i': Math.min(index, 11) }">
          <div class="role-top" :data-render-block="imageMode && detailMode ? '' : undefined">
            <div class="role-art">
              <img v-if="safeUrl(role.icon_url) && !failedImages.has(safeUrl(role.icon_url))" :key="safeUrl(role.icon_url)" :src="safeUrl(role.icon_url)" :alt="role.name || '角色'" :loading="imageMode ? 'eager' : 'lazy'" class="avatar" @error="imageFailed" />
              <NteIcon v-else :src="nteRoleIcon(role.id) || nteRoleIcon(role.name)" :name="role.name || '角色'" size="xl" />
              <span v-if="!imageMode" class="role-rarity" :data-tier="role.quality === 'S' ? 'top' : undefined" :aria-label="`品质 ${display(role.quality)}`">{{ display(role.quality) }}</span>
              <div v-if="!imageMode" class="role-actions">
                <button type="button" class="icon-button favorite" :aria-label="`${isFavorite(role) ? '取消收藏' : '收藏'}${role.name || '角色'}`" :aria-pressed="isFavorite(role)" :disabled="!canPersist || !roleId(role)" :title="favoriteTitle(role)" @click="toggleFavorite(role)"><AppIcon name="star" :size="15" /></button>
                <button type="button" class="icon-button" :aria-label="`对比${role.name || '角色'}`" :aria-pressed="isCompared(role)" :disabled="selected.length >= 4 && !isCompared(role)" :title="isCompared(role) ? '移出对比' : '加入对比'" @click="toggleCompare(role)"><AppIcon :name="isCompared(role) ? 'close' : 'plus'" :size="15" /></button>
              </div>
            </div>
            <div class="role-heading">
              <button v-if="!imageMode && !detailMode" type="button" class="role-open" :aria-label="`查看${role.name || '角色'}面板`" @click="openRole(role)">{{ display(role.name) }}</button><strong v-else :title="role.name">{{ display(role.name) }}</strong>
              <span class="role-sub"><span v-if="imageMode" class="rank" :class="`rank-${role.quality}`">{{ display(role.quality) }}</span><span>{{ display(role.element) }}</span></span>
            </div>
            <span class="level">Lv{{ display(role.level) }}</span>
            <button v-if="!imageMode" type="button" class="ui-button small-button guide-link" :aria-label="`查看${role.name || '角色'}攻略`" :disabled="!roleId(role)" @click="openRole(role,'guide')">攻略</button>
          </div>
          <p v-if="!detailMode" class="chip-list"><span class="chip">觉醒 <b>{{ display(role.awaken_level) }}</b></span><span class="chip">混频 <b>{{ display(role.mix_level) }}</b></span><span v-if="imageMode" class="chip">羁遇累计经验 <b>{{ display(role.affinity_exp) }}</b></span></p>
          <details v-if="detailMode" class="role-more" :open="imageMode || detailMode || (focusCharacterId===roleId(role) && !!focusCharacterId)">
            <summary :data-render-block="imageMode ? '' : undefined">
              <span class="chip">觉醒 <b>{{ display(role.awaken_level) }}</b></span>
              <span class="chip">混频 <b>{{ display(role.mix_level) }}</b></span>
              <span v-if="imageMode" class="chip">羁遇累计经验 <b>{{ display(role.affinity_exp) }}</b></span>
              <span class="sr-only">{{ role.name || '角色' }}详情</span>
              <AppIcon name="chevron" :size="14" class="t-disclosure" />
            </summary>
            <NteRoleDetail :role="role" :account-id="accountId" :image-mode="imageMode" />
          </details>
        </li>
      </ul>
    </template>
    <NteRoleDialog v-if="!imageMode && !detailMode && (openedRole || browseGuides)" :role="openedRole" :roles="roles" :account-id="accountId" :initial-tab="detailTab" :character-id="guideCharacterId" :can-maintain="canMaintain" @close="openedKey=null;browseGuides=false" @role="openOwned" />
  </section>
</template>

<style scoped>
.roster-charts{display:grid;grid-template-columns:minmax(180px,auto) minmax(0,1fr) minmax(0,1fr);gap:24px;align-items:center;margin:12px 0 24px}.role-open{padding:0;border:0;background:none;text-align:left;color:var(--text);font:inherit;font-weight:600;cursor:pointer}.role-open:hover{color:var(--accent)}.role-open:focus-visible{outline:2px solid var(--accent)}@media(max-width:720px){.roster-charts{grid-template-columns:1fr}}
.nte-roles-panel { grid-column: 1 / -1; min-width: 0; overflow-wrap: anywhere; }
.cap-title { position: relative; font-size: 16px; line-height: 24px; }
.summary { gap: 4px; }
input[type=checkbox] { margin: 0; accent-color: var(--accent); }
.toolbar input[type=search] { min-width: 150px; }
.favorite-filter { display: inline-flex; align-items: center; gap: 6px; min-height: 36px; padding: 4px 13px; border: 1px solid var(--border); border-radius: var(--radius-control); background: var(--card-bg); color: var(--text-body); font-size: 13px; cursor: pointer; }
.favorite-filter:has(input:checked) { border-color: color-mix(in srgb, var(--accent) 35%, transparent); background: var(--accent-soft); color: var(--accent-strong); }
.favorite-filter:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (hover: hover) and (pointer: fine) { .favorite-filter:not(:has(input:checked)):hover { background: var(--button-hover-bg); color: var(--text); } }
.notice { margin: 0 0 8px; padding: 8px 14px; border-radius: var(--radius-well); background: var(--surface-soft); color: var(--text-muted); font-size: 13px; }

/* Comparison: a one-line strip until two roles are picked, then the table. */
.compare-tray { margin: 0 0 14px; padding: 10px 14px; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.compare-heading { position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; min-height: 28px; font-size: 12px; }
.compare-heading > strong { color: var(--text); font-size: 14px; font-weight: 600; }
.compare-count { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.compare-chips { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.compare-chip { display: inline-flex; align-items: center; gap: 4px; min-height: 24px; padding: 0 6px 0 10px; border: 0; border-radius: var(--radius-chip); background: var(--accent-soft); color: var(--accent-strong); font-size: 12px; font-weight: 500; }
.compare-chip:not(:disabled):active { transform: translateY(1px); }
.clear-compare { margin-left: auto; min-height: 24px; padding: 2px 10px; }
.comparison-scroll { overflow-x: auto; margin: 6px -14px -6px; padding: 0 14px 6px; }
.comparison-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: var(--radius-control); }
.comparison-scroll table { min-width: 460px; table-layout: fixed; font-variant-numeric: tabular-nums; }
.comparison-scroll :is(th, td) { padding-top: 4px; padding-bottom: 4px; line-height: 18px; }
.comparison-scroll thead th:first-child { width: 112px; }
.comparison-scroll tbody tr:last-child th { border-bottom: 0; }
.comparison-scroll tbody th { color: var(--text-muted); font-size: 13px; font-weight: 400; }
.comparison-scroll .group-row th { padding-top: 10px; color: var(--text); font-size: 12px; font-weight: 500; }

/* Role cards (mockup .role-card): a white card with its frame, a tone panel with the
   portrait at its bottom right, the quality as the shared rarity tag top left and the level
   as a white tag bottom left, then the name and one muted line. Grid, frame and panel read
   the shared role-card tokens. Favourite and compare sit on the panel; 攻略 and the details are below. */
.role-grid { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, var(--role-card-min)), 1fr)); gap: var(--role-card-gap); align-items: start; }
.role-detail-view .role-grid { grid-template-columns: 1fr; }
.role-card { min-width: 0; padding: var(--role-card-frame); border: 1px solid var(--card-border); border-radius: var(--role-card-radius); background: var(--card-bg); box-shadow: var(--card-shadow); }
.role-card.compared { border-color: var(--role-accent, var(--game-vivid)); box-shadow: 0 0 0 1px var(--role-accent, var(--game-vivid)); }
.role-top { display: grid; grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "art art" "heading action"; align-items: center; }
.role-art { grid-area: art; position: relative; height: var(--role-art-h); overflow: hidden; border-radius: var(--role-art-radius); background: var(--game-tone); isolation: isolate; }
.avatar { position: absolute; right: 0; bottom: 0; width: 100%; height: 100%; object-fit: contain; object-position: right bottom; }
.role-art > .nte-icon[data-size] { --size: 100%; position: absolute; right: 0; bottom: 0; place-items: end end; padding: 0 22px 10px 0; border-radius: 0; background: none; }
.role-art :deep(.icon-fallback) { font-size: 72px; }
/* In a bot image a picture that could not be fetched is swapped for its name. */
.role-art :deep(.render-missing-image) { display: block; padding: 8px 10px; color: var(--game-accent); line-height: 1.4; }
.level { grid-area: art; position: relative; z-index: 1; align-self: end; justify-self: start; margin: 0 0 11px 11px; padding: 3px 8px; border-radius: var(--radius-chip); background: var(--card-bg); color: var(--game-accent); font-size: 12px; font-weight: 500; line-height: 18px; font-variant-numeric: tabular-nums; }
.role-heading { grid-area: heading; display: grid; gap: 3px; min-width: 0; padding: 13px 10px 10px; }
.role-heading > strong { overflow: hidden; color: var(--text); font-size: 14px; line-height: 20px; font-weight: 600; letter-spacing: -.01em; text-overflow: ellipsis; white-space: nowrap; }
.role-sub { display: flex; align-items: center; gap: 8px; color: var(--text-muted); font-size: 12px; line-height: 18px; white-space: nowrap; }
/* Quality is a tag, not a colour of its own: S takes the tone, the rest stay neutral. */
.rank { padding: 0 8px; border-radius: var(--radius-chip); background: var(--control-track); color: var(--text-body); font-size: 12px; font-weight: 600; line-height: 18px; }
.rank-S { background: var(--game-tone); color: var(--game-accent); }
.guide-link { grid-area: action; margin-right: 6px; }
.role-actions { position: absolute; top: 8px; right: 8px; z-index: 2; display: flex; gap: 6px; }
.role-actions .icon-button { width: 34px; height: 34px; border-color: var(--card-border); background: var(--card-bg); color: var(--text-muted); }
@media (pointer: coarse) { .role-actions .icon-button { width: 44px; height: 44px; } }
@media (hover: hover) and (pointer: fine) { .role-actions .icon-button:not(:disabled):not([aria-pressed=true]):hover { background: var(--button-hover-bg); color: var(--text); } }
.role-actions .icon-button:disabled { opacity: .4; cursor: not-allowed; }
.role-actions .icon-button[aria-pressed=true] { border-color: transparent; background: var(--accent-fill); color: var(--accent-ink); }
.role-actions .favorite[aria-pressed=true] { background: color-mix(in srgb, var(--chart-4) 22%, var(--card-bg)); color: color-mix(in srgb, var(--chart-4) 62%, var(--text)); }
.role-actions .favorite[aria-pressed=true] svg { fill: currentColor; }
.role-actions .icon-button:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: var(--radius-control); }
.role-card > .chip-list { margin-top: 10px; }
.role-more { margin: 2px 4px 4px; border-top: 1px solid var(--border); }
.role-more > summary { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin: 0 -6px; padding: 10px 6px; border-radius: var(--radius-control); list-style: none; cursor: pointer; }
.role-more > summary::-webkit-details-marker { display: none; }
.role-more > summary > svg { margin-left: auto; color: var(--text-faint); }
.role-more > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-radius: var(--radius-control); }
@media (hover: hover) and (pointer: fine) { .role-more > summary:hover { background: var(--hover-bg); } .role-more > summary:hover > svg { color: var(--text-body); } }

/* One role on its own (the guide's 查看本人面板) lies sideways: the panel on the left, the name beside it. */
.role-detail-view .role-top { grid-template-columns: 200px minmax(0, 1fr) auto; grid-template-areas: "art heading action"; column-gap: 16px; }
.role-detail-view .role-art { height: 150px; }
.role-detail-view .role-heading { padding: 0; }
.role-detail-view .role-heading > strong { font-size: 20px; line-height: 28px; letter-spacing: -.02em; }
.role-detail-view .guide-link { margin-right: 10px; }

/* Bot images keep the height they had: the card lies sideways with the panel on the left. */
.is-image .role-grid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 290px), 1fr)); }
.is-image.role-detail-view .role-grid { grid-template-columns: 1fr; }
.is-image .role-art { height: 108px; }
.is-image .role-art :deep(.icon-fallback) { font-size: 44px; }
.is-image .role-art > .nte-icon[data-size] { padding: 0 12px 8px 0; }
.is-image:not(.role-detail-view) .role-card { display: grid; grid-template-columns: 108px minmax(0, 1fr); grid-template-rows: auto 1fr; column-gap: 12px; }
.is-image:not(.role-detail-view) .role-top { display: contents; }
.is-image:not(.role-detail-view) .role-art, .is-image:not(.role-detail-view) .level { grid-area: 1 / 1 / 3 / 2; }
.is-image:not(.role-detail-view) .role-heading { grid-area: 1 / 2; padding: 6px 0 0; }
.is-image:not(.role-detail-view) .role-card > .chip-list { grid-area: 2 / 2; align-self: start; margin: 4px 0 0; }
.is-image.role-detail-view .role-top { grid-template-columns: 92px minmax(0, 1fr); grid-template-areas: "art heading"; }
.is-image.role-detail-view .role-art { height: 92px; }
/* Phones: two cards a row, like the other games' role grids. */
@media (max-width: 767px) { .nte-roles-panel:not(.is-image):not(.role-detail-view) .role-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; } }
@media (max-width: 560px) {
  .toolbar input[type=search] { flex-basis: 100%; }
  .toolbar .menu-select { flex: 1 1 calc(50% - 8px); min-width: 0; }
  .toolbar .count { margin-left: auto; }
  .role-detail-view .role-top { grid-template-columns: minmax(0, 1fr) auto; grid-template-areas: "art art" "heading action"; column-gap: 0; }
  .role-detail-view .role-art { height: 176px; }
  .role-detail-view .role-heading { padding: 13px 10px 10px; }
  .is-image.role-detail-view .role-top { grid-template-columns: 92px minmax(0, 1fr); grid-template-areas: "art heading"; }
}
</style>
