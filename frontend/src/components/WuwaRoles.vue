<script setup>
import { computed, ref } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { list, starCount, value } from '../wuwa-display.js'
import WuwaRoleDetail from './WuwaRoleDetail.vue'
import WuwaStatus from './WuwaStatus.vue'
import { vGlide, vReveal } from '../motion.js'
import { attributeSplit, levelBands, rosterSummary } from '../wuwa-charts.js'
import BarChart from './BarChart.vue'
import DonutChart from './DonutChart.vue'
import MenuSelect from './MenuSelect.vue'
import WuwaGuide from './WuwaGuide.vue'
import WuwaRoleDialog from './WuwaRoleDialog.vue'
import { normalizeSearch, searchCharacters } from '../character-search.js'
import WuwaGuideBrowser from './WuwaGuideBrowser.vue'
import { characterIcon } from '../wuwa-icons.js'
import { roleArtwork } from '../game-visuals.js'
import { skinOf } from '../game-themes.js'
const props = defineProps({
  snap: { default: null },
  accountKey: { type: String, default: '' },
  imageMode: { type: Boolean, default: false },
})
const search = ref(''),
  attribute = ref(''),
  weapon = ref(''),
  rarity = ref(''),
  sort = ref('level'),
  selected = ref(null),
  detail = ref(null),
  error = ref(''),
  loading = ref(false)
const detailTab = ref('panel')
const browseGuides = ref(false)
function reset() {
  selected.value = null
  detailTab.value = 'panel'
  detail.value = null
  error.value = ''
  loading.value = false
}
const request = useWuwaRequest(() => props.accountKey, reset)
const roles = computed(() => list(props.snap?.payload))
const brokenPictures = ref(new Set())
const roleImage = role => [...roleArtwork(role), characterIcon(role.role_id)].find(url => url && !brokenPictures.value.has(url))
function imageFailed(role) { brokenPictures.value = new Set([...brokenPictures.value, roleImage(role)]) }
const options = (key) => [
  ...new Set(
    roles.value.map((r) => r[key]).filter((v) => v != null && v !== ''),
  ),
]
const filtered = computed(() =>
  roles.value
    .filter(
      (r) =>
        (!normalizeSearch(search.value) || searchMatches.value.has(r)) &&
        (!attribute.value || r.attribute === attribute.value) &&
        (!weapon.value || r.weapon === weapon.value) &&
        (!rarity.value || String(r.star_level) === rarity.value),
    )
    .sort((a, b) => {
      if (normalizeSearch(search.value) && searchMatches.value.get(a) !== searchMatches.value.get(b)) return searchMatches.value.get(a) - searchMatches.value.get(b)
      const read = (r) =>
        sort.value === 'total_skill_level'
          ? r.extra?.total_skill_level
          : r[sort.value]
      return (read(b) ?? -1) - (read(a) ?? -1)
    }),
)
const searchMatches = computed(() => new Map(searchCharacters('wuthering_waves', search.value, roles.value).map(item => [item.entry, item.score])))
// The strip above the roster counts every recorded role, not only the filtered ones.
const summary = computed(() => rosterSummary(roles.value))
const attributes = computed(() => attributeSplit(roles.value).map((part, i) => ({ ...part, color: `var(--chart-${i + 1})` })))
const bands = computed(() => levelBands(roles.value))
// Rarity as stars: on the website one tag on the picture (5★ filled with the game ink); bot images keep
// 5★ in the game gold and 4★ in the purple series beside the name (same as the gacha split).
async function open(role) {
  if (props.imageMode) return
  selected.value = role
  detail.value = null
  error.value = ''
  loading.value = true
  try {
    const result = await request.run(
      `roles/${encodeURIComponent(role.role_id)}`,
    )
    if (!result) return
    if (String(result.payload?.character_id) !== String(role.role_id))
      throw new Error('角色数据不匹配，请重试')
    detail.value = result
    loading.value = false
  } catch (e) {
    error.value = e.message
    loading.value = false
  }
}
function close() {
  request.cancel()
  reset()
}
</script>
<template>
  <section class="wuwa-board" :data-skin="imageMode ? undefined : skinOf('wuthering_waves')">
    <header class="wuwa-board-head">
      <h2>角色档案</h2>
      <WuwaStatus :snap="snap" />
      <button v-if="!imageMode" type="button" class="ui-button small-button" :aria-expanded="browseGuides" @click="browseGuides=!browseGuides">公开角色攻略</button>
    </header>
    <div v-if="browseGuides" class="wuwa-panel"><WuwaGuideBrowser :roles="roles" @role="open" /></div>
    <div v-if="!imageMode && roles.length" v-reveal class="wuwa-bento roster-summary">
      <section class="wuwa-panel span-3 is-hero roster-total">
        <header class="cap-title"><h3>已记录角色</h3></header>
        <p class="roster-count"><b>{{ summary.total }}</b><small>位</small></p>
        <div class="stack-bar" aria-hidden="true">
          <i v-show="summary.five" :style="{ flex: summary.five, '--series': 'var(--wuwa-vivid)' }"></i>
          <i v-show="summary.four" :style="{ flex: summary.four, '--series': 'var(--chart-7)' }"></i>
        </div>
        <ul class="legend">
          <li :style="{ '--series': 'var(--wuwa-vivid)' }">5 星 <b>{{ summary.five }}</b></li>
          <li :style="{ '--series': 'var(--chart-7)' }">4 星 <b>{{ summary.four }}</b></li>
        </ul>
        <ul class="chip-list">
          <li class="chip">满级 <b>{{ summary.maxLevel }}</b></li>
          <li class="chip">满链 <b>{{ summary.fullChain }}</b></li>
        </ul>
      </section>
      <section class="wuwa-panel span-6">
        <header class="cap-title"><h3>属性分布</h3></header>
        <DonutChart :segments="attributes" label="角色属性分布" unit=" 位" :size="116" :stroke="14">
          <b class="donut-total">{{ summary.total }}</b><small class="ring-cap">位</small>
        </DonutChart>
      </section>
      <section class="wuwa-panel span-3">
        <header class="cap-title"><h3>等级分布</h3></header>
        <BarChart :items="bands" label="角色等级分布" unit=" 位" :height="112" />
      </section>
    </div>
    <div v-if="!imageMode" class="toolbar">
      <input
        class="grow"
        type="search"
        aria-label="搜索角色"
        placeholder="名称、别名、拼音或首字母"
        :value="search"
        @input="$event.isComposing || (search = $event.target.value)"
        @compositionend="search = $event.target.value"
      /><MenuSelect
        v-model="attribute"
        label="属性"
        :options="[{ value: '', label: '全部属性' }, ...options('attribute')]"
      /><MenuSelect
        v-model="weapon"
        label="武器类型"
        :options="[{ value: '', label: '全部武器类型' }, ...options('weapon')]"
      /><MenuSelect
        v-model="rarity"
        label="稀有度"
        :options="[
          { value: '', label: '全部稀有度' },
          ...options('star_level').map((v) => ({ value: String(v), label: `${v} 星` })),
        ]"
      /><MenuSelect
        v-model="sort"
        label="排序"
        align="end"
        :options="[
          { value: 'level', label: '等级优先' },
          { value: 'chain', label: '共鸣链优先' },
          { value: 'total_skill_level', label: '技能总等级优先' },
        ]"
      /><span class="count"
        ><template v-if="filtered.length !== roles.length"
          >筛选 {{ filtered.length }} 位 · </template
        >已记录 {{ roles.length }} 位</span
      >
    </div>
    <div class="wuwa-role-grid">
      <component :is="imageMode ? 'article' : 'button'"
        v-for="(r, index) in filtered"
        :key="r.role_id"
        :type="imageMode ? undefined : 'button'"
        class="wuwa-role t-item"
        :data-render-block="imageMode ? '' : undefined"
        :style="{ '--i': Math.min(index, 11) }"
        :aria-pressed="imageMode ? undefined : selected?.role_id === r.role_id"
        @click="open(r)"
      >
        <!-- Mockup .role-card: the picture on the tone with the level as a white tag, then name, rarity and one muted line. -->
        <span class="wuwa-role-art"
          ><img
            v-if="roleImage(r)"
            :src="roleImage(r)"
            :alt="r.name"
            loading="lazy"
            decoding="async"
            referrerpolicy="no-referrer"
            @error="imageFailed(r)"
          /><span v-else class="wuwa-avatar-placeholder" aria-hidden="true">{{
            (r.name || '?').slice(0, 1)
          }}</span
          ><span
            v-if="!imageMode"
            class="role-rarity"
            :data-tier="starCount(r.star_level) >= 5 ? 'top' : undefined"
            role="img"
            :aria-label="`${value(r.star_level)} 星`"
            >{{ starCount(r.star_level) ? '★'.repeat(starCount(r.star_level)) : `${value(r.star_level)} 星` }}</span
          ><span class="wuwa-role-level">Lv.{{ value(r.level) }}</span></span
        ><span class="wuwa-role-body"
          ><strong>{{ r.name || r.role_id }}</strong
          ><template v-if="imageMode"
            ><span
              v-if="starCount(r.star_level)"
              class="stars"
              :class="{ 'is-four': starCount(r.star_level) === 4 }"
              role="img"
              :aria-label="`${r.star_level} 星`"
              >{{ '★'.repeat(starCount(r.star_level)) }}</span
            ><span v-else class="wuwa-meta">{{ value(r.star_level) }} 星</span></template
          ><span class="wuwa-role-sub" title="属性 · 武器类型 · 共鸣链 · 技能总等级"
            ><template v-if="r.attribute">{{ r.attribute }} · </template
            >{{ value(r.weapon) }} · {{ value(r.chain) }} 链 · 技能
            {{ value(r.extra?.total_skill_level) }}</span
          ></span
        >
      </component>
    </div>
    <p v-if="!filtered.length" class="wuwa-panel wuwa-empty">{{ roles.length ? '暂无符合条件的角色，请调整筛选。' : '暂无角色记录，请刷新数据。' }}</p>
    <WuwaRoleDialog
      v-if="selected"
      :title="`${selected.name} · 角色详情`"
      :width="760"
      @close="close"
    >
      <div v-glide class="segmented wuwa-dialog-tabs" role="group" aria-label="角色详情视图">
        <button type="button" :aria-pressed="detailTab === 'panel'" @click="detailTab = 'panel'">角色面板</button>
        <button type="button" :aria-pressed="detailTab === 'guide'" @click="detailTab = 'guide'">培养攻略</button>
      </div>
      <WuwaGuide v-if="detailTab === 'guide'" :character-id="selected.role_id" :character-name="selected.name" :attribute="selected.attribute || ''" />
      <template v-else>
      <p v-if="loading" role="status">正在读取角色详情…</p>
      <p v-if="error" class="wuwa-error" role="alert">
        {{ error }} <button type="button" class="ui-button small-button" @click="open(selected)">重试</button>
      </p>
      <template v-if="detail"
        ><WuwaRoleDetail :data="detail.payload.data" /><WuwaStatus
          :snap="detail"
      /></template>
      </template>
    </WuwaRoleDialog>
  </section>
</template>
