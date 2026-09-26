<script setup>
import { computed, ref } from 'vue'
import { list, value, stamp } from '../wuwa-display.js'
import { vGlide } from '../motion.js'
import InfoHint from './InfoHint.vue'
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
// Star glyphs only when both counts are small whole numbers; otherwise text.
const glyphs = (floor) => {
  const got = Number(floor.star),
    cap = Number(floor.max_star)
  return floor.star != null &&
    Number.isInteger(got) &&
    Number.isInteger(cap) &&
    cap > 0 &&
    cap <= 6 &&
    got >= 0 &&
    got <= cap
    ? { got, cap }
    : null
}
</script>
<template>
  <div class="wuwa-tower">
    <div class="wuwa-tower-bar">
      <div
        v-if="data?.is_unlock !== false"
        v-glide
        class="segmented"
        role="group"
        aria-label="深塔分区"
      >
        <button
          v-for="zone in zones"
          :key="zone.difficulty"
          type="button"
          :aria-pressed="String(zone.difficulty) === difficulty"
          @click="difficulty = String(zone.difficulty)"
        >
          {{ zone.difficulty_name || `分区 ${zone.difficulty}` }}
        </button>
      </div>
      <span class="wuwa-meta wuwa-bar-end"
        >周期结束 {{ stamp(data?.season_end_at) }}（北京时间）<InfoHint
          v-if="data?.is_unlock !== false && hasMissingFloorCaps"
          text="来源未提供部分楼层的星数上限；这些楼层仅显示已得星数。"
          align="end"
      /></span>
    </div>
    <p v-if="data?.is_unlock === false" class="wuwa-muted">尚未解锁</p>
    <template v-else>
      <p v-if="!current" class="wuwa-muted">未提供所选分区记录</p>
      <div v-else class="wuwa-tiles wuwa-towers">
        <section
          v-for="(area, i) in list(current.tower_area_list)"
          :key="i"
          class="wuwa-tile"
        >
          <header class="wuwa-tile-head">
            <h3>{{ area.area_name || `区域 ${i + 1}` }}</h3>
            <span v-if="area.max_star != null" class="wuwa-tile-end wuwa-gold"
              >{{ value(area.star) }} / {{ value(area.max_star) }} 星</span
            ><span v-else-if="area.star != null" class="wuwa-tile-end wuwa-gold"
              >已得 {{ value(area.star) }} 星</span
            >
          </header>
          <table v-if="list(area.floor_list).length" class="data-table wuwa-floors">
            <tbody>
              <tr v-for="(floor, j) in list(area.floor_list)" :key="j">
                <th scope="row">
                  第 {{ value(floor.floor ?? floor.floor_index) }} 层
                </th>
                <td class="wuwa-floor-stars">
                  <template v-if="glyphs(floor)"
                    ><span class="stars" aria-hidden="true"
                      ><span
                        v-for="n in glyphs(floor).cap"
                        :key="n"
                        :class="{ off: n > glyphs(floor).got }"
                        >★</span
                      ></span
                    ><span class="sr-only"
                      >{{ value(floor.star) }} / {{ value(floor.max_star) }} 星</span
                    ></template
                  ><span v-else-if="floor.max_star != null"
                    >{{ value(floor.star) }} / {{ value(floor.max_star) }} 星</span
                  ><span v-else class="wuwa-meta"
                    >已得 {{ value(floor.star) }} 星</span
                  >
                </td>
                <td>
                  <ul v-if="roster(floor).length" class="chip-list">
                    <li v-for="(role, k) in roster(floor)" :key="k" class="chip">
                      {{
                        role.role_name ||
                        role.name ||
                        roleNames[role.role_id] ||
                        `角色 ${role.role_id ?? '未知'}`
                      }}<small v-if="role.role_level != null"
                        >Lv.{{ role.role_level }}</small
                      >
                    </li>
                  </ul>
                  <span v-else class="wuwa-muted">未提供</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="wuwa-muted">未提供分层数据</p>
        </section>
      </div>
    </template>
  </div>
</template>
