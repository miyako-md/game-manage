<script setup>
import { computed } from 'vue'
import { list, value } from '../wuwa-display.js'
import WuwaTower from './WuwaTower.vue'
import WuwaStatus from './WuwaStatus.vue'
import WuwaFields from './WuwaFields.vue'
const props = defineProps({
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
const roleName = (role) =>
  role.role_name ||
  role.name ||
  props.roleNames[role.role_id] ||
  `角色 ${role.role_id ?? '未知'}`
const share = (score, max) =>
  typeof score === 'number' && typeof max === 'number' && max > 0
    ? Math.min(100, Math.round((score / max) * 100))
    : null
</script>
<template>
  <div class="wuwa-stack">
    <p v-if="snap?.stale || snap?.error" class="wuwa-banner">
      <WuwaStatus :snap="snap" />
    </p>
    <section class="wuwa-panel">
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
    <section class="wuwa-panel">
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
                  {{ role.role_name || '未知角色'
                  }}<small v-if="role.role_level != null"
                    >Lv.{{ role.role_level }}</small
                  >
                </li>
              </ul>
              <span v-else class="wuwa-muted">队伍未提供</span>
            </li>
          </ul>
        </details>
      </div>
      <p v-else class="wuwa-muted">未提供挑战记录</p>
    </section>
    <section class="wuwa-panel">
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
          <div class="bar-row wuwa-slash-total">
            <span class="k">{{
              zone.difficulty_name || `难度 ${value(zone.difficulty)}`
            }}</span
            ><span class="meter"
              ><i
                :style="{
                  '--pct': (share(zone.all_score, zone.max_score) ?? 0) + '%',
                  '--series': 'var(--game-wuwa)',
                }"
              ></i></span
            ><span class="v"
              >{{ value(zone.all_score) }}<small> / {{ value(zone.max_score) }}</small></span
            >
          </div>
          <div class="wuwa-tiles wuwa-slash">
            <section
              v-for="(challenge, j) in list(zone.challenge_list)"
              :key="j"
              class="wuwa-tile"
            >
              <header class="wuwa-tile-head">
                <h3>{{ challenge.challenge_name }}</h3>
                <span class="wuwa-tile-end wuwa-score">{{
                  value(challenge.score)
                }}</span
                ><span class="badge wuwa-rank"
                  ><span class="sr-only">评级 </span
                  >{{ value(challenge.rank) }}</span
                >
              </header>
              <ul class="wuwa-halves">
                <li v-for="(half, k) in list(challenge.half_list)" :key="k">
                  <span class="wuwa-half-name">{{
                    half.half_name || `第 ${k + 1} 半场`
                  }}</span
                  ><b class="wuwa-half-score">{{ value(half.score) }}</b>
                  <ul v-if="list(half.role_list).length" class="chip-list">
                    <li
                      v-for="(role, m) in list(half.role_list)"
                      :key="m"
                      class="chip"
                    >
                      {{ roleName(role) }}
                    </li>
                  </ul>
                  <span v-else class="wuwa-muted">队伍未提供</span>
                  <p
                    v-if="half.buff_name || half.buff_description"
                    class="wuwa-buff"
                  >
                    <strong>{{ half.buff_name || '增益' }}</strong>
                    {{ half.buff_description }}
                  </p>
                  <WuwaFields
                    :data="half"
                    :exclude="[
                      'role_list',
                      'score',
                      'half_name',
                      'buff_name',
                      'buff_description',
                    ]"
                  />
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
