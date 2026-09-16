<script setup>
import { computed, ref } from 'vue'
import { list, value, stamp } from '../wuwa-display.js'
const props = defineProps({
  roleNames: { type: Object, default: () => ({}) },
  data: { default: null },
})
const difficulty = ref('3')
const zones = computed(() => list(props.data?.difficulty_list))
const current = computed(() =>
  zones.value.find((z) => String(z.difficulty) === difficulty.value),
)
const roster = (entry) => list(entry?.role_list || entry?.roles)
const hasMissingFloorCaps = computed(() =>
  list(current.value?.tower_area_list).some((area) =>
    list(area.floor_list).some((floor) => floor.max_star == null),
  ),
)
</script>
<template>
  <div>
    <p class="wuwa-meta">
      周期结束 {{ stamp(data?.season_end_at) }}（北京时间）
    </p>
    <p v-if="data?.is_unlock === false" class="wuwa-muted">尚未解锁</p>
    <template v-else
      ><div class="wuwa-tabs" aria-label="深塔分区">
        <button
          v-for="zone in zones"
          :key="zone.difficulty"
          :aria-pressed="String(zone.difficulty) === difficulty"
          @click="difficulty = String(zone.difficulty)"
        >
          {{ zone.difficulty_name || `分区 ${zone.difficulty}` }}
        </button>
      </div>
      <p v-if="!current" class="wuwa-muted">未提供所选分区记录</p>
      <p v-if="hasMissingFloorCaps" class="wuwa-meta">
        来源未提供部分楼层的星数上限；这些楼层仅显示已得星数。
      </p>
      <div v-if="current" class="wuwa-grid">
        <article
          v-for="(area, i) in list(current.tower_area_list)"
          :key="i"
          class="wuwa-inset"
        >
          <h4>
            {{ area.area_name || `区域 ${i + 1}` }}
            <span class="wuwa-gold"
              >{{ value(area.star) }} / {{ value(area.max_star) }} 星</span
            >
          </h4>
          <div
            v-for="(floor, j) in list(area.floor_list)"
            :key="j"
            class="wuwa-floor"
          >
            <strong>第 {{ value(floor.floor ?? floor.floor_index) }} 层</strong
            ><span v-if="floor.max_star != null"
              >{{ value(floor.star) }} / {{ value(floor.max_star) }} 星</span
            >
            <span v-else>已得 {{ value(floor.star) }} 星</span>
            <p>
              队伍：<span
                v-for="(role, k) in roster(floor)"
                :key="k"
                class="wuwa-tag"
                >{{
                  role.role_name ||
                  role.name ||
                  roleNames[role.role_id] ||
                  `角色 ${role.role_id ?? '未知'}`
                }}<template v-if="role.role_level != null">
                  Lv.{{ role.role_level }}</template
                ></span
              ><span v-if="!roster(floor).length" class="wuwa-muted"
                >未提供</span
              >
            </p>
          </div>
          <p v-if="!list(area.floor_list).length" class="wuwa-muted">
            未提供分层数据
          </p>
        </article>
      </div></template
    >
  </div>
</template>
