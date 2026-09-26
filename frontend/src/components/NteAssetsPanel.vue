<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { fetchedLabel } from '../time.js'
import { percentOf } from '../dashboard.js'
import { safeUrl } from '../calendar.js'
import { displayRoleValue } from '../nte-roles.js'
import AppIcon from './AppIcon.vue'
import InfoHint from './InfoHint.vue'
import MenuSelect from './MenuSelect.vue'

const props = defineProps({
  capability: { type: String, required: true },
  snap: { type: Object, default: null },
  roles: { type: Array, default: () => [] },
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
const list = value => Array.isArray(value) ? value : []
const display = (value) => displayRoleValue(value, '未知')
const state = value => value === true ? '已拥有' : value === false ? '未拥有' : '拥有状态未知'
const stateClass = value => value === true ? 'owned' : value === false ? 'unowned' : 'unknown'
// Counts arrive as numbers, vehicle stats as strings; only a known value over
// a positive maximum draws a bar (percentOf).
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => legacy.value ? {} : payload.value ?? {})
const entries = computed(() => list(data.value.entries))
const roleMap = computed(() => new Map(props.roles.map(role => [String(role.id), role])))
const roleName = id => roleMap.value.get(String(id))?.name || `角色 ${id}`
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
  <section class="nte-assets cap-card">
    <header class="cap-title">
      <h3>{{ titles[capability] }}</h3>
      <InfoHint :text="capability === 'teams' ? '来源：塔吉多官方配队推荐 · 公共内容' : '来源：塔吉多已登录角色资产'" />
      <span v-if="snap?.stale" class="badge badge-stale">缓存已过期</span>
      <span v-if="payload && !legacy && capability !== 'teams'" class="owned-count">
        <span class="owned-label">拥有</span><b>{{ display(data.owned_count) }}</b><small>/ {{ display(data.total) }}</small>
        <span v-if="ownedShare !== null" class="meter"><i :style="{ '--pct': `${ownedShare}%` }" /></span>
      </span>
      <span v-if="payload && !legacy && capability === 'vehicles' && (data.show_name || data.show_id)" class="chip">展示载具：{{ data.show_name || data.show_id }}</span>
      <span v-if="fetchedAt" class="cap-meta">采集时间（北京时间） {{ fetchedAt }}</span>
    </header>
    <p v-if="!payload" class="empty">尚未采集，请刷新获取数据</p>
    <p v-else-if="legacy" class="empty">数据版本已更新，请刷新获取资产详情</p>
    <template v-else>
      <div v-if="entries.length" class="toolbar">
        <input class="grow" type="search" :aria-label="searchLabels[capability]" :placeholder="placeholders[capability]" :value="search" @input="search = $event.target.value" />
        <MenuSelect v-if="capability !== 'teams'" v-model="ownership" label="拥有状态" align="end" :options="ownershipOptions" />
        <span class="count" role="status">显示 {{ filtered.length }} / {{ entries.length }} 条</span>
      </div>
      <p v-if="!entries.length" class="empty">{{ capability === 'teams' ? '暂无官方配队推荐' : '暂无资产明细' }}</p>
      <p v-else-if="!filtered.length" class="empty" role="status">没有符合筛选条件的条目</p>
      <div v-else class="asset-list" :class="capability === 'teams' ? 'team-list' : capability === 'vehicles' ? 'vehicle-grid' : 'asset-grid'">
        <details v-for="(entry, index) in filtered" :key="`${entry.id}-${index}`" class="asset t-item" :style="{ '--i': Math.min(index, 11) }" :open="!folded.has(foldKey(entry))" @toggle="onFold($event, foldKey(entry))">
          <summary>
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
                  <div v-for="(stat, i) in entry.base" :key="i"><dt>{{ stat.name || '未命名属性' }}</dt><dd>{{ display(stat.value) }}</dd></div>
                </dl>
                <p v-else class="muted">未提供基础属性</p>
              </section>
              <section class="detail-group">
                <h4>进阶属性</h4>
                <dl v-if="list(entry.advanced).length" class="rows">
                  <div v-for="(stat, i) in entry.advanced" :key="i">
                    <dt>{{ stat.name || '未命名属性' }}</dt>
                    <dd class="gauge"><span v-if="percentOf(stat.value, stat.maximum) !== null" class="meter" aria-hidden="true"><i :style="{ '--pct': `${percentOf(stat.value, stat.maximum)}%` }" /></span>{{ display(stat.value) }} / {{ display(stat.maximum) }}</dd>
                  </div>
                </dl>
                <p v-else class="muted">未提供进阶属性</p>
              </section>
              <section class="detail-group">
                <h4>装饰 / 涂装</h4>
                <ul v-if="list(entry.models).length" class="chip-list">
                  <li v-for="(model, i) in entry.models" :key="i" class="chip">{{ display(model.type) }} <span class="mono">ID {{ display(model.id) }}</span></li>
                </ul>
                <p v-else class="muted">暂无装饰 / 涂装明细</p>
              </section>
            </template>
            <template v-else-if="capability === 'teams'">
              <p class="description">{{ entry.description || '未提供推荐说明' }}</p>
              <div class="recommendation-images">
                <template v-for="(url, i) in list(entry.image_urls)" :key="i">
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
.cap-title h3 { margin: 0; color: var(--text); font-size: 14px; line-height: 20px; font-weight: 600; }
.muted { color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.mono { font-family: var(--font-mono); font-size: 11px; }

/* Header count: 拥有 3 / 8 with a short bar in the NTE identity colour. */
.owned-count { display: inline-flex; align-items: baseline; gap: 4px; margin-left: 4px; font-variant-numeric: tabular-nums; }
.owned-label { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.owned-count b { color: var(--text); font-size: 15px; font-weight: 600; }
.owned-count small { color: var(--text-muted); font-size: 12px; font-weight: 400; }
.owned-count .meter { --series: var(--game-nte); align-self: center; width: 64px; height: 5px; margin-left: 4px; }

.toolbar input[type=search] { min-width: 150px; }

/* Cards open by default (the details are short); columns pack their uneven
   heights without leaving holes, and each card can still be folded away. */
.asset-list { display: grid; gap: 6px 8px; align-items: start; }
.asset-grid { display: block; columns: 300px auto; column-gap: 8px; }
.asset-grid > .asset { break-inside: avoid; margin-bottom: 8px; }
/* Vehicle cards are all the same shape, so a plain grid keeps rows aligned. */
.vehicle-grid { grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr)); gap: 8px; }
.base-stats { --kv-min: 72px; gap: 4px 12px; }
.base-stats dd { font-size: 14px; line-height: 20px; }
.asset { min-width: 0; border: 1px solid var(--border); border-radius: 8px; background: var(--card-bg); }
summary { display: flex; align-items: center; gap: 6px; min-height: 36px; padding: 5px 8px 5px 10px; border-radius: 7px; list-style: none; cursor: pointer; color: var(--text); font-size: 13px; }
summary::-webkit-details-marker { display: none; }
summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
@media (hover: hover) and (pointer: fine) { summary:hover { background: var(--overlay-2); } summary:hover > svg { color: var(--text-body); } }
summary > svg { flex-shrink: 0; margin-left: auto; color: var(--text-faint); }
.asset-name { min-width: 0; overflow: hidden; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.team-icon { width: 28px; height: 28px; flex-shrink: 0; border-radius: 6px; object-fit: cover; }
.preview { flex: 1 1 0; min-width: 0; overflow: hidden; color: var(--text-muted); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
/* Open rows show the full description below, so the preview steps aside. */
.asset[open] .preview { visibility: hidden; }
/* Ownership sits at the right edge so the states line up down each column. */
.ownership { flex-shrink: 0; margin-left: auto; padding: 0 6px; border-radius: 4px; font-size: 11px; line-height: 18px; white-space: nowrap; }
.ownership + .sr-only + svg { margin-left: 0; }
.ownership.owned { background: color-mix(in srgb, var(--game-nte) 14%, transparent); color: var(--game-nte); }
.ownership.unowned { background: var(--overlay-3); color: var(--text-muted); }
.ownership.unknown { box-shadow: inset 0 0 0 1px var(--border-strong); color: var(--text-faint); }
.state { font-size: 12px; color: var(--text-muted); }
.state.owned { color: var(--game-nte); }

.detail-body { display: grid; gap: 8px; padding: 8px 10px 10px; border-top: 1px solid var(--border); overflow-wrap: anywhere; }
.detail-group h4 { margin: 0 0 2px; color: var(--text-faint); font-size: 11px; font-weight: 500; letter-spacing: .03em; }
.rows { margin: 0; padding: 0; list-style: none; font-size: 12px; }
.rows > li, .rows > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 3px 0; border-bottom: 1px solid var(--border); }
.rows > :last-child { border-bottom: 0; }
.rows dt { color: var(--text-muted); }
.rows dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
.rows dd.gauge { display: inline-flex; align-items: center; gap: 8px; }
.gauge > .meter { --series: var(--game-nte); width: 56px; height: 4px; }
.residents { display: flex; flex-wrap: wrap; gap: 4px; margin: 0; padding: 0; list-style: none; font-size: 12px; }
.residents li { display: inline-flex; align-items: center; gap: 5px; padding: 2px 8px 2px 2px; border-radius: 6px; background: var(--overlay-3); }
.residents li:not(:has(img)) { padding-left: 8px; }
.residents img { width: 22px; height: 22px; object-fit: cover; border-radius: 5px; }

/* Official teams: one row each with a description preview; images open in a grid. */
.team-list { grid-template-columns: 1fr; }
.team-list .detail-body { gap: 10px; }
.description { white-space: pre-wrap; color: var(--text-body); font-size: 13px; line-height: 1.7; }
.recommendation-images { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr)); gap: 8px; }
.recommendation-images a { display: block; color: var(--accent); font-size: 12px; }
.recommendation-images img { display: block; width: 100%; height: auto; border-radius: 6px; }
a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (max-width: 600px) { .recommendation-images { grid-template-columns: repeat(auto-fill, minmax(min(100%, 132px), 1fr)); } }
@media (max-width: 480px) { .preview { display: none; } }
</style>
