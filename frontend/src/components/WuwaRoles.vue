<script setup>
import { computed, ref } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { safeUrl } from '../calendar.js'
import { list, value } from '../wuwa-display.js'
import WuwaRoleDetail from './WuwaRoleDetail.vue'
import WuwaStatus from './WuwaStatus.vue'
import InfoHint from './InfoHint.vue'
import AppIcon from './AppIcon.vue'
import MenuSelect from './MenuSelect.vue'
const props = defineProps({
  snap: { default: null },
  accountKey: { type: String, default: '' },
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
function reset() {
  selected.value = null
  detail.value = null
  error.value = ''
  loading.value = false
}
const request = useWuwaRequest(() => props.accountKey, reset)
const roles = computed(() => list(props.snap?.payload))
const options = (key) => [
  ...new Set(
    roles.value.map((r) => r[key]).filter((v) => v != null && v !== ''),
  ),
]
const filtered = computed(() =>
  roles.value
    .filter(
      (r) =>
        (r.name || '').includes(search.value) &&
        (!attribute.value || r.attribute === attribute.value) &&
        (!weapon.value || r.weapon === weapon.value) &&
        (!rarity.value || String(r.star_level) === rarity.value),
    )
    .sort((a, b) => {
      const read = (r) =>
        sort.value === 'total_skill_level'
          ? r.extra?.total_skill_level
          : r[sort.value]
      return (read(b) ?? -1) - (read(a) ?? -1)
    }),
)
// Rarity as stars: 5★ in the game gold, 4★ in the purple series (same as the gacha split).
const starCount = (r) => {
  const n = Number(r.star_level)
  return Number.isInteger(n) && n > 0 && n <= 6 ? n : 0
}
async function open(role) {
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
  <section class="wuwa-panel">
    <header class="cap-title">
      <h2>角色档案</h2>
      <InfoHint text="点击角色按需读取完整面板。武器类型不代表实际装备。" />
      <WuwaStatus :snap="snap" />
    </header>
    <div class="toolbar">
      <input
        class="grow"
        type="search"
        aria-label="搜索角色"
        placeholder="搜索角色"
        :value="search"
        @input="search = $event.target.value"
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
      <button
        v-for="(r, index) in filtered"
        :key="r.role_id"
        type="button"
        class="wuwa-role t-item"
        :style="{ '--i': Math.min(index, 11) }"
        :aria-pressed="selected?.role_id === r.role_id"
        @click="open(r)"
      >
        <img
          v-if="safeUrl(r.icon_url)"
          :src="safeUrl(r.icon_url)"
          :alt="r.name"
          loading="lazy"
        /><span v-else class="wuwa-avatar-placeholder" aria-hidden="true">{{
          (r.name || '?').slice(0, 1)
        }}</span
        ><span class="wuwa-role-body"
          ><span class="wuwa-role-head"
            ><strong>{{ r.name || r.role_id }}</strong
            ><span
              v-if="starCount(r)"
              class="stars"
              :class="{ 'is-four': starCount(r) === 4 }"
              role="img"
              :aria-label="`${r.star_level} 星`"
              >{{ '★'.repeat(starCount(r)) }}</span
            ><span v-else class="wuwa-meta">{{ value(r.star_level) }} 星</span></span
          ><span class="wuwa-role-meta"
            ><span class="wuwa-role-stats"
              >Lv.{{ value(r.level) }} · {{ value(r.chain) }} 链 · 技能
              {{ value(r.extra?.total_skill_level) }}</span
            ><span class="wuwa-role-tags"
              ><span v-if="r.attribute" class="chip">{{ r.attribute }}</span
              ><span class="wuwa-role-weapon" title="武器类型">{{
                value(r.weapon)
              }}</span></span
            ></span
          ></span
        >
      </button>
    </div>
    <p v-if="!filtered.length" class="wuwa-muted">暂无符合条件的角色</p>
    <section
      v-if="selected"
      class="wuwa-detail"
      role="region"
      aria-label="角色完整面板"
      aria-live="polite"
    >
      <header class="cap-title">
        <h2>{{ selected.name }} · 完整面板</h2>
        <WuwaStatus v-if="detail" :snap="detail" />
        <button
          type="button"
          class="ui-button small-button ghost wuwa-close"
          @click="close"
        >
          <AppIcon name="close" :size="14" />关闭详情
        </button>
      </header>
      <p v-if="loading" role="status" class="wuwa-meta">
        正在读取角色详情…
      </p>
      <p v-if="error" class="wuwa-error" role="alert">
        {{ error }}
        <button
          type="button"
          class="ui-button small-button"
          @click="open(selected)"
        >
          重试
        </button>
      </p>
      <WuwaRoleDetail v-if="detail" :data="detail.payload.data" />
    </section>
  </section>
</template>
