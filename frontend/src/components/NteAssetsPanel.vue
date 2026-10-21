<script setup>
import { nteAssetImage } from '../nte-artwork.js'
import { displayVehicleStat, imageTeams, vehicleDecorationType } from '../nte-display.js'
import { computed, reactive, ref, watch,inject } from 'vue'
import { fetchedLabel } from '../time.js'
import { percentOf } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
import { displayRoleValue } from '../nte-roles.js'
import { GLYPHS } from '../nte-charts.js'
import AppIcon from './AppIcon.vue'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'
import RingGauge from './RingGauge.vue'

const props = defineProps({
  capability: { type: String, required: true },
  snap: { type: Object, default: null },
  roles: { type: Array, default: () => [] },
  imageMode: Boolean,
})
const search = ref('')
const ownership = ref('all')
const ownershipOptions = [{ value: 'all', label: '全部状态' }, { value: 'owned', label: '已拥有' }, { value: 'unowned', label: '未拥有' }, { value: 'unknown', label: '未知' }]
const failedImages = reactive(new Set())
// Cards start open; one the reader folds stays folded while the list is searched or filtered.
const folded = reactive(new Set())
const foldKey = entry => entry.id != null ? `id:${entry.id}` : entry.name ? `name:${entry.name}` : `#${entries.value.indexOf(entry)}`
function onFold(event, key) {
  if (event.currentTarget.open) folded.delete(key)
  else folded.add(key)
}
const titles = { realestate: '房产详情', vehicles: '载具详情', teams: '官方配队推荐' }
const searchLabels = { realestate: '搜索房产', vehicles: '搜索载具', teams: '搜索配队推荐' }
const placeholders = { realestate: '搜索名称、入住角色、家具', vehicles: '搜索载具名称', teams: '搜索名称、描述' }
// Official team cards carry other guide images too. The QQ team command keeps
// one entry per team name and its complete team diagram; skill/weapon guide images remain
// in the original cached payload rather than repeating unrelated guide pages.
const recommendationImages=entry=>props.imageMode
  ? list(entry.image_urls).filter(url=>/peidui|2team_rec/i.test(url))
  : list(entry.image_urls)
const list = value => Array.isArray(value) ? value : []
const display = (value) => displayRoleValue(value, '未知')
const state = value => value === true ? '已拥有' : value === false ? '未拥有' : '拥有状态未知'
const stateClass = value => value === true ? 'owned' : value === false ? 'unowned' : 'unknown'
// Counts arrive as numbers, vehicle stats as strings; only a known value over
// a positive maximum draws a bar (percentOf).
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => legacy.value ? {} : payload.value ?? {})
const renderRoleCatalog=inject('renderRoleCatalog',{})
// The image keeps one entry per team name and, when an owned roster is supplied, only teams naming an owned role.
const entries = computed(() => props.imageMode && props.capability === 'teams'
  ? imageTeams(list(data.value.entries), list(data.value.owned_role_names).length ? list(data.value.owned_role_names) : props.roles.map(role => role.name), list(renderRoleCatalog.nte).map(role => role.name))
  : list(data.value.entries))
const roleMap = computed(() => new Map([...(renderRoleCatalog.nte||[]),...props.roles].map(role => [String(role.id), role])))
const roleName = id => roleMap.value.get(String(id))?.name || (props.imageMode?'名称未提供':`角色 ${id}`)
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
const ownedShare = computed(() => percentOf(data.value.owned_count, data.value.total))
const filtered = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('zh-CN')
  return entries.value.filter(entry => {
    if (props.capability !== 'teams' && ownership.value !== 'all') {
      const expected = { owned: true, unowned: false, unknown: null }[ownership.value]
      if (expected === null ? entry.owned != null : entry.owned !== expected) return false
    }
    const words = [entry.name, entry.id, entry.description,
      ...list(entry.resident_ids).map(roleName), ...list(entry.furniture).map(item => item.name)]
    return !query || words.filter(Boolean).join(' ').toLocaleLowerCase('zh-CN').includes(query)
  })
})

function imageUrl(value) {
  const url = safeUrl(value)
  return url && !failedImages.has(url) ? url : null
}
function imageFailed(event) {
  const url = safeUrl(event.currentTarget?.src)
  if (url) failedImages.add(url)
}
watch(() => props.capability, () => { search.value = ''; ownership.value = 'all' })
</script>

<template>
  <section class="nte-assets cap-card" :class="{ 'is-image': imageMode }">
    <header class="cap-title">
      <h3>{{ titles[capability] }}</h3>
      <InfoHint :text="capability === 'teams' ? '来源：塔吉多官方配队推荐 · 公共内容' : '来源：塔吉多已登录角色资产'" />
      <span v-if="snap?.stale && !imageMode" class="badge badge-stale">缓存已过期</span>
      <span v-if="payload && !legacy && capability !== 'teams'" class="owned-count">
        <span class="owned-label">拥有</span><b>{{ display(data.owned_count) }}</b><small>/ {{ display(data.total) }}</small>
        <span v-if="ownedShare !== null" class="owned-ring" aria-hidden="true"><RingGauge :value="ownedShare" :max="100" label="拥有" :size="36" :stroke="5" color="var(--game-vivid)" /></span>
      </span>
      <span v-if="payload && !legacy && capability === 'vehicles' && (data.show_name || data.show_id)" class="chip">展示载具：{{ data.show_name || data.show_id }}</span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </header>
    <p v-if="!payload" class="empty">暂无数据，请刷新后查看</p>
    <p v-else-if="legacy" class="empty">数据版本已更新，请刷新获取资产详情</p>
    <template v-else>
      <div v-if="entries.length && !imageMode" class="toolbar">
        <input class="grow" type="search" :aria-label="searchLabels[capability]" :placeholder="placeholders[capability]" :value="search" @input="$event.isComposing || (search = $event.target.value)" @compositionend="search = $event.target.value" />
        <MenuSelect v-if="capability !== 'teams'" v-model="ownership" label="拥有状态" align="end" :options="ownershipOptions" />
        <span class="count" role="status">显示 {{ filtered.length }} / {{ entries.length }} 条</span>
      </div>
      <p v-if="!entries.length" class="empty">{{ capability === 'teams' ? '暂无官方配队推荐' : '暂无资产明细' }}</p>
      <p v-else-if="!filtered.length" class="empty" role="status">没有符合筛选条件的条目</p>
      <div v-else class="asset-list" :class="capability === 'teams' ? 'team-list' : capability === 'vehicles' ? 'vehicle-grid' : 'asset-grid'">
        <details v-for="(entry, index) in filtered" :key="`${entry.id}-${index}`" class="asset t-item" :style="{ '--i': Math.min(index, 11) }" :open="!folded.has(foldKey(entry))" @toggle="onFold($event, foldKey(entry))">
          <summary>
            <span v-if="capability !== 'teams'" class="asset-cover" aria-hidden="true"><img v-if="imageUrl(nteAssetImage(capability,entry.id))" :src="imageUrl(nteAssetImage(capability,entry.id))" alt="" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" /><svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"><path :d="capability === 'vehicles' ? GLYPHS.car : GLYPHS.house" /></svg></span>
            <img v-if="capability === 'teams' && imageUrl(entry.icon_url)" class="team-icon" :src="imageUrl(entry.icon_url)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" />
            <strong class="asset-name" :title="entry.name">{{ entry.name || `${capability === 'teams' ? '推荐' : '资产'} ${entry.id}` }}</strong>
            <template v-if="capability === 'realestate'">
              <span v-if="list(entry.resident_ids).length" class="chip">入住 <b>{{ list(entry.resident_ids).length }}</b></span>
              <span v-if="list(entry.furniture).length" class="chip">家具 <b>{{ list(entry.furniture).length }}</b></span>
            </template>
            <span v-if="capability === 'teams' && entry.description" class="preview" aria-hidden="true">{{ entry.description }}</span>
            <span v-if="capability !== 'teams'" class="ownership" :class="stateClass(entry.owned)">{{ state(entry.owned) }}</span>
            <span class="sr-only">详情</span>
            <AppIcon name="chevron" :size="14" class="t-disclosure" />
          </summary>
          <div class="detail-body">
            <template v-if="capability === 'realestate'">
              <section class="detail-group">
                <h4>入住角色</h4>
                <ul v-if="list(entry.resident_ids).length" class="residents">
                  <li v-for="(id, residentIndex) in entry.resident_ids" :key="residentIndex">
                    <img v-if="imageUrl(roleMap.get(String(id))?.icon_url)" :src="imageUrl(roleMap.get(String(id))?.icon_url)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" />
                    <span>{{ roleName(id) }}</span>
                  </li>
                </ul>
                <p v-else class="muted">未提供入住角色</p>
              </section>
              <section class="detail-group">
                <h4>家具</h4>
                <ul v-if="list(entry.furniture).length" class="rows">
                  <li v-for="(item, i) in entry.furniture" :key="i"><span>{{ item.name || `家具 ${item.id}` }}</span><span class="state" :class="stateClass(item.owned)">{{ state(item.owned) }}</span></li>
                </ul>
                <p v-else class="muted">暂无家具明细</p>
              </section>
            </template>
            <template v-else-if="capability === 'vehicles'">
              <section class="detail-group">
                <h4>基础属性</h4>
                <dl v-if="list(entry.base).length" class="kv-grid base-stats">
                  <div v-for="(stat, i) in entry.base" :key="i"><dt :title="String(stat.value ?? '')">{{ stat.name || '未命名属性' }}</dt><dd>{{ displayVehicleStat(stat) }}</dd></div>
                </dl>
                <p v-else class="muted">未提供基础属性</p>
              </section>
              <section class="detail-group">
                <h4>进阶属性</h4>
                <dl v-if="list(entry.advanced).length" class="rows">
                  <div v-for="(stat, i) in entry.advanced" :key="i">
                    <dt :title="String(stat.value ?? '')">{{ stat.name || '未命名属性' }}</dt>
                    <dd class="gauge"><span v-if="percentOf(stat.value, stat.maximum) !== null" class="meter" aria-hidden="true"><i :style="{ '--pct': `${percentOf(stat.value, stat.maximum)}%` }" /></span>{{ displayVehicleStat(stat) }} / {{ display(stat.maximum) }}</dd>
                  </div>
                </dl>
                <p v-else class="muted">未提供进阶属性</p>
              </section>
              <section class="detail-group">
                <h4>装饰 / 涂装</h4>
                <ul v-if="list(entry.models).length" class="chip-list">
                  <li v-for="(model, i) in entry.models" :key="i" class="chip">{{ vehicleDecorationType(model.type) }}</li>
                </ul>
                <p v-else class="muted">暂无装饰 / 涂装明细</p>
              </section>
            </template>
            <template v-else-if="capability === 'teams'">
              <p class="description">{{ entry.description || '未提供推荐说明' }}</p>
              <div class="recommendation-images">
                <template v-for="(url, i) in recommendationImages(entry)" :key="i">
                  <a v-if="safeUrl(url)" :href="safeUrl(url)" target="_blank" rel="noopener noreferrer" :aria-label="`${entry.name || '配队推荐'}图片 ${i + 1}，打开原图`">
                    <img v-if="imageUrl(url)" :src="imageUrl(url)" :alt="`${entry.name || '配队推荐'}图片 ${i + 1}`" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" />
                    <span v-else>图片暂时无法加载，打开原图 ↗</span>
                  </a>
                </template>
              </div>
            </template>
          </div>
        </details>
      </div>
    </template>
  </section>
</template>

<style scoped>
.nte-assets { min-width: 0; color: var(--text); }
.cap-title { position: relative; }
.cap-title h3 { margin: 0; color: var(--text); font-size: 16px; line-height: 24px; font-weight: 600; letter-spacing: -.01em; }
.muted { color: var(--text-muted); font-size: 12px; line-height: 1.6; }

/* Header count: 拥有 3 / 8 with a small ring in the game's line colour. */
.owned-count { display: inline-flex; align-items: center; gap: 4px; margin-left: 4px; font-variant-numeric: tabular-nums; }
.owned-label { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.owned-count b { color: var(--text); font-size: 20px; line-height: 24px; font-weight: 550; letter-spacing: -.03em; }
.owned-count small { color: var(--text-muted); font-size: 13px; font-weight: 500; }
.owned-ring { display: inline-flex; margin-left: 6px; }

.toolbar input[type=search] { min-width: 150px; }

/* Cards open by default (the details are short); columns pack their uneven
   heights without leaving holes, and each card can still be folded away. */
.asset-list { display: grid; gap: 12px; align-items: start; }
.asset-grid { display: block; columns: 320px auto; column-gap: 12px; }
.asset-grid > .asset { break-inside: avoid; margin-bottom: 12px; }
/* Vehicle cards are all the same shape, so a plain grid keeps rows aligned. */
.vehicle-grid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); }
.base-stats { --kv-min: 84px; gap: 8px; }
/* On the page a stat with its unit (267 km/h) needs a wider tile than the bot image's ellipsis allows. */
.nte-assets:not(.is-image) .base-stats { --kv-min: 112px; }
.base-stats > div { padding: 10px 12px; border-radius: var(--radius-well); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.base-stats dd { font-size: 15px; line-height: 20px; }
/* Entries are soft tiles with a hairline. */
.asset { min-width: 0; border-radius: var(--radius-tile); background: var(--surface-soft); box-shadow: inset 0 0 0 1px var(--overlay-2); }
summary { display: flex; align-items: center; gap: 10px; min-height: 56px; padding: 8px 12px 8px 10px; border-radius: var(--radius-tile); list-style: none; cursor: pointer; color: var(--text); font-size: 13px; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: var(--radius-tile); }
@media (hover: hover) and (pointer: fine) { summary:hover { background: var(--hover-bg); } summary:hover > svg { color: var(--text-body); } }
summary > svg { flex-shrink: 0; margin-left: auto; color: var(--text-faint); }
.asset-name { min-width: 0; overflow: hidden; font-size: 15px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.asset-cover { display: grid; place-items: center; flex-shrink: 0; width: 104px; height: 70px; border-radius: 30%; color: var(--game-accent); background: var(--game-tone); }
.asset-cover{border-radius:10px}.asset-cover img{width:100%;height:100%;object-fit:contain}
.asset-cover svg { width: 22px; height: 22px; }
.team-icon { width: 48px; height: 48px; flex-shrink: 0; border-radius: 30%; object-fit: cover; }
.preview { flex: 1 1 0; min-width: 0; overflow: hidden; color: var(--text-muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
/* Open rows show the full description below, so the preview steps aside. */
.asset[open] .preview { visibility: hidden; }
/* Ownership sits at the right edge so the states line up down each column. */
.ownership { flex-shrink: 0; margin-left: auto; padding: 0 10px; border-radius: var(--radius-chip); font-size: 12px; font-weight: 500; line-height: 22px; white-space: nowrap; }
.ownership + .sr-only + svg { margin-left: 0; }
.ownership.owned { background: var(--game-tone); color: var(--game-accent); }
.ownership.unowned { background: var(--overlay-3); color: var(--text-muted); }
.ownership.unknown { color: var(--text-faint); }
.state { font-size: 12px; color: var(--text-muted); }
.state.owned { color: var(--game-accent); }

.detail-body { display: grid; gap: 10px; padding: 2px 12px 14px; overflow-wrap: anywhere; }
.detail-group { padding: 12px 14px; border-radius: var(--radius-well); background: var(--card-bg); box-shadow: inset 0 0 0 1px var(--overlay-2); }
.detail-group h4 { margin: 0 0 4px; color: var(--text-muted); font-size: 12px; font-weight: 500; }
.rows { margin: 0; padding: 0; list-style: none; font-size: 13px; }
.rows > li, .rows > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 4px 0; border-bottom: 1px solid var(--border); }
.rows > :last-child { border-bottom: 0; }
.rows dt { color: var(--text-muted); }
.rows dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.rows dd.gauge { display: inline-flex; align-items: center; gap: 8px; }
.gauge > .meter { --series: var(--game-vivid); width: 64px; height: 5px; }
.residents { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; font-size: 13px; }
.residents li { display: inline-flex; align-items: center; gap: 6px; padding: 3px 12px 3px 3px; border-radius: var(--radius-chip); background: var(--surface-soft); }
.residents li:not(:has(img)) { padding-left: 12px; }
.residents img { width: 28px; height: 28px; object-fit: cover; border-radius: 30%; }

/* Official teams: the first picture leads at full width, the rest sit beneath it. */
.team-list { grid-template-columns: 1fr; }
.team-list .detail-body { gap: 12px; }
.description { white-space: pre-wrap; color: var(--text-body); font-size: 13px; line-height: 1.7; }
.recommendation-images { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr)); gap: 10px; align-items: start; }
.recommendation-images a { display: block; color: var(--accent); font-size: 12px; }
@media (min-width: 900px) { .recommendation-images a:first-child { grid-column: span 2; } }
.recommendation-images img { display: block; width: 100%; height: auto; max-height: 320px; object-fit: contain; border-radius: var(--radius-tile); }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 600px) { .recommendation-images { grid-template-columns: repeat(auto-fill, minmax(min(100%, 132px), 1fr)); } }
@media (max-width: 480px) { .preview { display: none; } }
</style>
