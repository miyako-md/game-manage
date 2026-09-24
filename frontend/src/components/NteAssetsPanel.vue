<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { fetchedLabel } from '../time.js'
import { safeUrl } from '../calendar.js'
import { displayRoleValue } from '../nte-roles.js'

const props = defineProps({
  capability: { type: String, required: true },
  snap: { type: Object, default: null },
  roles: { type: Array, default: () => [] },
})
const search = ref('')
const ownership = ref('all')
const failedImages = reactive(new Set())
const titles = { realestate: '房产详情', vehicles: '载具详情', teams: '官方配队推荐' }
const list = value => Array.isArray(value) ? value : []
const display = (value) => displayRoleValue(value, '未知', { numbers: false })
const state = value => value === true ? '已拥有' : value === false ? '未拥有' : '拥有状态未知'
const payload = computed(() => props.snap?.payload ?? null)
const legacy = computed(() => payload.value !== null && payload.value.schema_version !== 1)
const data = computed(() => legacy.value ? {} : payload.value ?? {})
const entries = computed(() => list(data.value.entries))
const roleMap = computed(() => new Map(props.roles.map(role => [String(role.id), role])))
const roleName = id => roleMap.value.get(String(id))?.name || `角色 ${id}`
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))
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
  <section class="nte-assets">
    <header class="panel-header">
      <h3>{{ titles[capability] }}</h3>
      <span v-if="snap?.stale" class="stale">缓存已过期</span>
    </header>
    <p class="source">{{ capability === 'teams' ? '来源：塔吉多官方配队推荐 · 公共内容' : '来源：塔吉多已登录角色资产' }}</p>
    <p v-if="!payload" class="empty">尚未采集，请刷新获取数据</p>
    <p v-else-if="legacy" class="empty">数据版本已更新，请刷新获取资产详情</p>
    <template v-else>
      <p v-if="capability !== 'teams'" class="count">拥有 {{ display(data.owned_count) }} / {{ display(data.total) }}</p>
      <p v-if="capability === 'vehicles' && (data.show_name || data.show_id)" class="source">展示载具：{{ data.show_name || data.show_id }}</p>
      <div v-if="entries.length" class="filters">
        <label class="search">搜索
          <input type="search" :value="search" :placeholder="capability === 'teams' ? '名称、描述' : '名称、角色、家具'" @input="search = $event.target.value" />
        </label>
        <label v-if="capability !== 'teams'">拥有状态
          <select :value="ownership" @change="ownership = $event.target.value">
            <option value="all">全部状态</option>
            <option value="owned">已拥有</option>
            <option value="unowned">未拥有</option>
            <option value="unknown">未知</option>
          </select>
        </label>
      </div>
      <p v-if="!entries.length" class="empty">{{ capability === 'teams' ? '暂无官方配队推荐' : '暂无资产明细' }}</p>
      <p v-else-if="!filtered.length" class="empty" role="status">没有符合筛选条件的条目</p>
      <p v-else class="result-count" role="status">显示 {{ filtered.length }} / {{ entries.length }} 条</p>
      <div class="asset-list">
        <details v-for="(entry, index) in filtered" :key="`${entry.id}-${index}`" class="asset t-item" :style="{ '--i': Math.min(index, 11) }">
          <summary>
            <img v-if="capability === 'teams' && imageUrl(entry.icon_url)" :src="imageUrl(entry.icon_url)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" />
            <strong>{{ entry.name || `${capability === 'teams' ? '推荐' : '资产'} ${entry.id}` }} · 详情</strong>
            <span v-if="capability !== 'teams'" class="ownership" :class="{ owned: entry.owned === true }">{{ state(entry.owned) }}</span>
          </summary>
          <div class="detail-body">
            <template v-if="capability === 'realestate'">
              <h4>入住角色</h4>
              <ul v-if="list(entry.resident_ids).length" class="residents">
                <li v-for="(id, residentIndex) in entry.resident_ids" :key="residentIndex">
                  <img v-if="imageUrl(roleMap.get(String(id))?.icon_url)" :src="imageUrl(roleMap.get(String(id))?.icon_url)" alt="" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed" />
                  <span>{{ roleName(id) }}</span>
                </li>
              </ul>
              <p v-else class="muted">未提供入住角色</p>
              <h4>家具</h4>
              <ul v-if="list(entry.furniture).length" class="rows">
                <li v-for="(item, i) in entry.furniture" :key="i"><span>{{ item.name || `家具 ${item.id}` }}</span><span class="muted">{{ state(item.owned) }}</span></li>
              </ul>
              <p v-else class="muted">暂无家具明细</p>
            </template>
            <template v-else-if="capability === 'vehicles'">
              <h4>基础属性</h4>
              <dl v-if="list(entry.base).length" class="rows">
                <div v-for="(stat, i) in entry.base" :key="i"><dt>{{ stat.name || '未命名属性' }}</dt><dd>{{ display(stat.value) }}</dd></div>
              </dl>
              <p v-else class="muted">未提供基础属性</p>
              <h4>进阶属性</h4>
              <dl v-if="list(entry.advanced).length" class="rows">
                <div v-for="(stat, i) in entry.advanced" :key="i"><dt>{{ stat.name || '未命名属性' }}</dt><dd>{{ display(stat.value) }} / {{ display(stat.maximum) }}</dd></div>
              </dl>
              <p v-else class="muted">未提供进阶属性</p>
              <h4>装饰 / 涂装</h4>
              <ul v-if="list(entry.models).length" class="rows">
                <li v-for="(model, i) in entry.models" :key="i"><span>{{ display(model.type) }}</span><span class="muted">ID {{ display(model.id) }}</span></li>
              </ul>
              <p v-else class="muted">暂无装饰 / 涂装明细</p>
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
    <p v-if="fetchedAt" class="source fetched-at">采集时间（北京时间） {{ fetchedAt }}</p>
  </section>
</template>

<style scoped>
.nte-assets { min-width: 0; color: var(--text); }
.panel-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { margin: 0; color: var(--accent); font-size: 15px; }
.source, .muted, .result-count { color: var(--text-muted); font-size: 12px; line-height: 1.7; }
.source { margin: 6px 0 12px; }
.stale { color: var(--accent); font-size: 12px; }
.count { font-size: 18px; margin: 12px 0; font-variant-numeric: tabular-nums; }
.filters { display: flex; gap: 10px; flex-wrap: wrap; margin: 12px 0; }
.filters label { display: grid; gap: 5px; color: var(--text-muted); font-size: 12px; }
.search { flex: 1; min-width: 130px; }
input, select { box-sizing: border-box; width: 100%; min-width: 0; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 6px; font: inherit; font-size: 13px; padding: 8px; }
.empty { padding: 16px 0; color: var(--text-muted); font-size: 13px; }
.asset-list { display: grid; gap: 10px; }
.asset { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; min-width: 0; }
summary { cursor: pointer; padding: 12px; color: var(--text); font-size: 13px; overflow-wrap: anywhere; }
summary::marker { color: var(--accent); }
summary img { width: 36px; height: 36px; object-fit: cover; vertical-align: middle; border-radius: 5px; margin-right: 8px; }
.ownership { display: inline-block; margin: 5px 0 0 10px; color: var(--text-muted); font-size: 12px; }
.ownership.owned { color: var(--accent); }
.detail-body { border-top: 1px solid var(--border); padding: 0 12px 12px; overflow-wrap: anywhere; }
h4 { margin: 14px 0 8px; font-size: 13px; }
.rows { list-style: none; margin: 0; padding: 0; font-size: 13px; }
.rows > li, .rows > div { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; padding: 5px 0; }
.rows dd { margin: 0; text-align: right; }
.residents { list-style: none; display: flex; flex-wrap: wrap; gap: 10px; padding: 0; font-size: 13px; }
.residents li { display: flex; align-items: center; gap: 6px; }
.residents img { width: 36px; height: 36px; object-fit: contain; border-radius: 5px; }
.description { white-space: pre-wrap; line-height: 1.8; font-size: 13px; }
.recommendation-images { display: grid; gap: 12px; }
.recommendation-images img { display: block; width: 100%; height: auto; border-radius: 6px; }
a { color: var(--accent); font-size: 12px; }
input:focus-visible, select:focus-visible, summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.fetched-at { margin: 12px 0 0; }
@media (max-width: 420px) { .filters { flex-direction: column; } .ownership { margin-left: 6px; } }
</style>
