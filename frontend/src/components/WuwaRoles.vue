<script setup>
import { computed, ref } from 'vue'
import { useWuwaRequest } from '../wuwa-api.js'
import { safeUrl } from '../calendar.js'
import { list, value } from '../wuwa-display.js'
import WuwaRoleDetail from './WuwaRoleDetail.vue'
import WuwaStatus from './WuwaStatus.vue'
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
    <header class="wuwa-heading">
      <div>
        <p class="wuwa-kicker">RESONATORS</p>
        <h2>角色档案</h2>
      </div>
      <span class="wuwa-meta">已记录 {{ roles.length }} 位</span>
    </header>
    <div class="wuwa-toolbar">
      <label
        >搜索角色<input
          :value="search"
          @input="search = $event.target.value"
          placeholder="输入名字" /></label
      ><label
        >属性<select
          :value="attribute"
          @change="attribute = $event.target.value"
        >
          <option value="">全部</option>
          <option v-for="v in options('attribute')" :key="v" :value="v">
            {{ v }}
          </option>
        </select></label
      ><label
        >武器类型<select :value="weapon" @change="weapon = $event.target.value">
          <option value="">全部</option>
          <option v-for="v in options('weapon')" :key="v" :value="v">
            {{ v }}
          </option>
        </select></label
      ><label
        >稀有度<select :value="rarity" @change="rarity = $event.target.value">
          <option value="">全部</option>
          <option v-for="v in options('star_level')" :key="v" :value="v">
            {{ v }} 星
          </option>
        </select></label
      ><label
        >排序<select :value="sort" @change="sort = $event.target.value">
          <option value="level">等级优先</option>
          <option value="chain">共鸣链优先</option>
          <option value="total_skill_level">技能总等级优先</option>
        </select></label
      >
    </div>
    <p class="wuwa-muted">点击角色按需读取完整面板。武器类型不代表实际装备。</p>
    <div class="wuwa-role-grid">
      <button
        v-for="(r, index) in filtered"
        :key="r.role_id"
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
        /><span v-else class="wuwa-avatar-placeholder">{{
          (r.name || '?').slice(0, 1)
        }}</span
        ><strong>{{ r.name || r.role_id }}</strong
        ><span>{{ value(r.attribute) }} · {{ value(r.star_level) }} 星</span
        ><span>Lv.{{ value(r.level) }} · {{ value(r.chain) }} 链</span
        ><span class="wuwa-meta">武器类型 {{ value(r.weapon) }}</span
        ><span class="wuwa-meta"
          >技能总等级 {{ value(r.extra?.total_skill_level) }}</span
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
      <header class="wuwa-heading">
        <h2>{{ selected.name }} · 完整面板</h2>
        <button @click="close">关闭详情</button>
      </header>
      <p v-if="loading" role="status">正在读取角色详情…</p>
      <p v-if="error" class="wuwa-error" role="alert">
        {{ error }} <button @click="open(selected)">重试</button>
      </p>
      <template v-if="detail"
        ><WuwaRoleDetail :data="detail.payload.data" /><WuwaStatus
          :snap="detail"
      /></template>
    </section>
    <WuwaStatus :snap="snap" />
  </section>
</template>
