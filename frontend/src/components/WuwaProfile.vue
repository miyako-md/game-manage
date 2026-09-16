<script setup>
import { computed } from 'vue'
import { stamp, value, list } from '../wuwa-display.js'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
const props = defineProps({ snap: { default: null } })
const profile = computed(() => props.snap?.payload?.extra?.profile || {})
const metrics = {
  world_level: '世界等级',
  active_days: '活跃天数',
  achievement_count: '成就数',
  achievement_star: '成就星数',
  big_count: '大型信标',
  small_count: '小型信标',
}
const collections = {
  box_list: '奇藏箱（基础统计）',
  treasure_box_list: '奇藏箱（分类统计）',
  phantom_box_list: '潮汐之遗',
}
</script>
<template>
  <section class="wuwa-panel">
    <header class="wuwa-heading">
      <div>
        <p class="wuwa-kicker">RESONATOR ARCHIVE</p>
        <h2>{{ snap?.payload?.nickname || '漂泊者档案' }}</h2>
      </div>
      <strong>联觉等级 {{ value(snap?.payload?.level) }}</strong>
    </header>
    <p class="wuwa-meta">
      UID {{ value(snap?.payload?.extra?.role_id) }} · 区服
      {{ value(snap?.payload?.extra?.server_id) }} · 注册日期
      {{ stamp(profile.creat_time) }}
    </p>
    <div class="wuwa-metrics">
      <div v-for="(text, key) in metrics" :key="key">
        <span>{{ text }}</span
        ><strong>{{ value(profile[key]) }}</strong>
      </div>
    </div>
    <p class="wuwa-muted">以下为来源记录数量；分类可能重叠，未合计为完成率。</p>
    <div class="wuwa-grid">
      <section v-for="(text, key) in collections" :key="key" class="wuwa-inset">
        <h3>{{ text }}</h3>
        <p v-if="!list(profile[key]).length" class="wuwa-muted">未提供</p>
        <dl v-else>
          <div v-for="(row, i) in profile[key]" :key="i">
            <dt>
              {{ row?.box_name || row?.name || `分类 ${row?.id ?? i + 1}` }}
            </dt>
            <dd>{{ value(row?.num) }}</dd>
          </div>
        </dl>
      </section>
    </div>
    <WuwaFields
      :data="profile"
      :exclude="[
        ...Object.keys(metrics),
        ...Object.keys(collections),
        'creat_time',
      ]"
    /><WuwaStatus :snap="snap" />
  </section>
</template>
