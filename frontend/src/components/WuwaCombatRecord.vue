<script setup>
import { computed } from 'vue'
import { list, value } from '../wuwa-display.js'
import { share } from '../chart-math.js'
import RingGauge from './RingGauge.vue'
import WuwaTower from './WuwaTower.vue'
import WuwaStatus from './WuwaStatus.vue'
import WuwaCombatRole from './WuwaCombatRole.vue'
const props = defineProps({
  mode: { type: String, default: 'tower' },
  roleNames: { type: Object, default: () => ({}) },
  snap: { default: null },
})
const payload = computed(() => props.snap?.payload || {})
const bossGroups = computed(() => {
  const groups = new Map()
  for (const [sourceId, records] of Object.entries(
    payload.value.hologram?.data?.challenge_info || {},
  )) {
    for (const record of list(records)) {
      const key = record.boss_name || `unknown:${sourceId}`
      if (!groups.has(key))
        groups.set(key, {
          key,
          name: record.boss_name || '未知首领',
          records: [],
        })
      groups.get(key).records.push(record)
    }
  }
  return [...groups.values()]
})
const amount = (v) => (typeof v === 'number' ? v.toLocaleString('zh-CN') : value(v))
const percent = (done, cap) => {
  const r = share(done, cap)
  return r == null ? '—' : `${Math.round(r * 100)}%`
}
// The two halves of a challenge as parts of its score; unknown halves take no room.
const halfShare = (half) => (typeof half.score === 'number' && half.score > 0 ? half.score : 0)
</script>
<template>
  <div class="wuwa-board">
    <p v-if="snap?.stale || snap?.error" class="wuwa-banner">
      <WuwaStatus :snap="snap" />
    </p>
    <section v-if="mode === 'tower'" class="wuwa-panel">
      <header class="cap-title">
        <h2>逆境深塔</h2>
        <WuwaStatus :snap="payload.tower || snap" />
      </header>
      <WuwaTower
        v-if="payload.tower?.data"
        :data="payload.tower.data"
        :role-names="roleNames"
      />
      <p v-else class="wuwa-muted">深塔数据暂不可用</p>
    </section>
    <section v-if="mode === 'hologram'" class="wuwa-panel">
      <header class="cap-title">
        <h2>战术全息</h2>
        <WuwaStatus :snap="payload.hologram" />
      </header>
      <p v-if="payload.hologram?.data?.is_unlock === false" class="wuwa-muted">
        尚未解锁
      </p>
      <div v-else-if="bossGroups.length" class="wuwa-tiles wuwa-holograms">
        <details
          v-for="group in bossGroups"
          :key="group.key"
          class="wuwa-tile wuwa-disclosure"
        >
          <summary>
            <span class="boss-mark" aria-hidden="true">{{ group.name.slice(0, 1) }}</span>
            <strong>{{ group.name }}</strong>
            <span class="wuwa-meta">{{ group.records.length }} 条记录</span>
          </summary>
          <ul class="wuwa-records">
            <li v-for="(boss, i) in group.records" :key="i">
              <span class="wuwa-inline"
                ><span><span class="k">难度</span> <b>{{ value(boss.difficulty) }}</b></span
                ><span><span class="k">等级</span> <b>{{ value(boss.boss_level) }}</b></span
                ><span><span class="k">通关时间</span> <b>{{ value(boss.pass_time) }}</b></span></span
              >
              <ul v-if="list(boss.roles).length" class="chip-list">
                <li v-for="(role, j) in list(boss.roles)" :key="j" class="chip">
                  <WuwaCombatRole :role="role" :role-names="roleNames" />
                </li>
              </ul>
              <span v-else class="wuwa-muted">队伍未提供</span>
            </li>
          </ul>
        </details>
      </div>
      <p v-else class="wuwa-muted">未提供挑战记录</p>
    </section>
    <section v-if="mode === 'slash'" class="wuwa-panel">
      <header class="cap-title">
        <h2>冥歌海墟</h2>
        <WuwaStatus :snap="payload.slash" />
      </header>
      <p v-if="payload.slash?.data?.is_unlock === false" class="wuwa-muted">
        尚未解锁
      </p>
      <template v-else
        ><article
          v-for="(zone, i) in list(payload.slash?.data?.difficulty_list)"
          :key="i"
          class="wuwa-slash-zone"
        >
          <div class="slash-zone-head">
            <RingGauge
              :value="zone.all_score"
              :max="zone.max_score"
              :label="zone.difficulty_name || `难度 ${value(zone.difficulty)}`"
              :size="88"
              :stroke="9"
              color="var(--wuwa-vivid)"
            >
              <span class="ring-pct">{{ percent(zone.all_score, zone.max_score) }}</span>
            </RingGauge>
            <div class="slash-copy">
              <span class="k">{{
                zone.difficulty_name || `难度 ${value(zone.difficulty)}`
              }}</span>
              <strong class="slash-score"
                >{{ amount(zone.all_score) }}<small> / {{ amount(zone.max_score) }}</small></strong
              >
            </div>
          </div>
          <div class="wuwa-tiles wuwa-slash">
            <section
              v-for="(challenge, j) in list(zone.challenge_list)"
              :key="j"
              class="wuwa-tile"
            >
              <header class="wuwa-tile-head">
                <h3>{{ challenge.challenge_name }}</h3>
                <span class="wuwa-tile-end wuwa-score"
                  ><span class="wuwa-meta">得分 </span
                  >{{ amount(challenge.score) }}</span
                ><span class="badge wuwa-rank"
                  >评级 {{ value(challenge.rank) }}</span
                >
              </header>
              <div
                v-if="list(challenge.half_list).filter((half) => halfShare(half)).length > 1"
                class="stack-bar"
                aria-hidden="true"
              >
                <i
                  v-for="(half, k) in list(challenge.half_list)"
                  v-show="halfShare(half)"
                  :key="k"
                  :style="{ flex: halfShare(half), '--series': `var(--chart-${k + 1})` }"
                ></i>
              </div>
              <ul class="wuwa-halves">
                <li
                  v-for="(half, k) in list(challenge.half_list)"
                  :key="k"
                  :style="{ '--series': `var(--chart-${k + 1})` }"
                >
                  <span class="wuwa-half-name">{{
                    half.half_name || `第 ${k + 1} 半场`
                  }}</span
                  ><b class="wuwa-half-score"
                    ><span class="wuwa-meta">得分 </span
                    >{{ amount(half.score) }}</b
                  >
                  <ul v-if="list(half.role_list).length" class="chip-list">
                    <li
                      v-for="(role, m) in list(half.role_list)"
                      :key="m"
                      class="chip"
                    >
                      <WuwaCombatRole :role="role" :role-names="roleNames" />
                    </li>
                  </ul>
                  <span v-else class="wuwa-muted">队伍未提供</span>
                </li>
              </ul>
            </section>
          </div>
        </article>
        <p
          v-if="!list(payload.slash?.data?.difficulty_list).length"
          class="wuwa-muted"
        >
          未提供海墟记录
        </p></template
      >
    </section>
  </div>
</template>
