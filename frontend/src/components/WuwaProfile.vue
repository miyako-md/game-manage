<script setup>
import { computed } from 'vue'
import { fieldLabels, stamp, value, list } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
import InfoHint from './InfoHint.vue'
const props = defineProps({ snap: { default: null } })
const profile = computed(() => props.snap?.payload?.extra?.profile || {})
const server = computed(() => props.snap?.payload?.extra?.server_id)
const metrics = Object.fromEntries(['world_level', 'active_days', 'achievement_count', 'achievement_star', 'big_count', 'small_count'].map((key) => [key, fieldLabels[key]]))
const collections = {
  box_list: '奇藏箱（基础统计）',
  treasure_box_list: '奇藏箱（分类统计）',
  phantom_box_list: '潮汐之遗',
}
// 等级名称、下一级经验、经验上限与解锁标记合成等级一格：等级数值 + 经验条。
const levelKeys = ['unlock', 'level_name', 'next_exp', 'exp_limit']
const exp = computed(() => {
  const { next_exp: cur, exp_limit: max } = profile.value
  if (cur == null && max == null) return null
  const pct =
    typeof cur === 'number' && typeof max === 'number' && max > 0
      ? Math.max(0, Math.min(100, Math.round((cur / max) * 100)))
      : 0
  return { cur, max, pct }
})
const excluded = [
  ...Object.keys(metrics),
  ...Object.keys(collections),
  ...levelKeys,
  'creat_time',
]
const hasRest = computed(() =>
  Object.keys(profile.value).some(
    (k) =>
      !excluded.includes(k) &&
      !/(?:icon|pic|image|_url|^sort$|^provenance$)/.test(k),
  ),
)
</script>
<template>
  <section class="wuwa-panel">
    <header class="cap-title">
      <h2 class="wuwa-name">{{ snap?.payload?.nickname || '漂泊者档案' }}</h2>
      <span v-if="profile.unlock === false" class="badge badge-stale">未解锁</span>
      <WuwaStatus :snap="snap" />
    </header>
    <dl class="kv-grid wuwa-idgrid">
      <div>
        <dt>UID</dt>
        <dd class="mono">{{ value(snap?.payload?.extra?.role_id) }}</dd>
      </div>
      <div>
        <dt>区服</dt>
        <dd class="mono" :title="server == null ? undefined : String(server)">
          {{ value(server) }}
        </dd>
      </div>
      <div>
        <dt>注册日期</dt>
        <dd>{{ stamp(profile.creat_time) }}</dd>
      </div>
      <div class="wuwa-level">
        <dt>{{ profile.level_name || '联觉等级' }}</dt>
        <dd>
          <b>{{ value(snap?.payload?.level) }}</b>
          <template v-if="exp"
            ><span
              class="wuwa-exp"
              :title="`下一级经验 ${value(exp.cur)} / 经验上限 ${value(exp.max)}`"
              >经验 {{ value(exp.cur) }} / {{ value(exp.max) }}</span
            ><span class="meter"
              ><i :style="{ '--pct': exp.pct + '%' }"></i></span
          ></template>
        </dd>
      </div>
    </dl>
    <dl class="kv-grid tiles wuwa-metrics">
      <div v-for="(text, key) in metrics" :key="key">
        <dt>{{ text }}</dt>
        <dd>{{ value(profile[key]) }}</dd>
      </div>
    </dl>
    <section class="wuwa-section">
      <h3 class="wuwa-subhead">
        收集记录<InfoHint
          text="以下为来源记录数量；分类可能重叠，未合计为完成率。"
        />
      </h3>
      <div class="wuwa-columns">
        <div v-for="(text, key) in collections" :key="key">
          <h4 class="wuwa-colhead">{{ text }}</h4>
          <p v-if="!list(profile[key]).length" class="wuwa-muted">未提供</p>
          <dl v-else class="kv-list">
            <div v-for="(row, i) in profile[key]" :key="i">
              <dt>
                {{ row?.box_name || row?.name || `分类 ${row?.id ?? i + 1}` }}
              </dt>
              <dd>{{ value(row?.num) }}</dd>
            </div>
          </dl>
        </div>
      </div>
    </section>
    <section v-if="hasRest" class="wuwa-section">
      <WuwaFields :data="profile" :exclude="excluded" />
    </section>
  </section>
</template>
