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
</script>
<template>
  <div class="wuwa-stack">
    <WuwaStatus v-if="snap?.stale || snap?.error" :snap="snap" />
    <section class="wuwa-panel">
      <h2>逆境深塔</h2>
      <WuwaStatus :snap="payload.tower || snap" /><WuwaTower
        v-if="payload.tower?.data"
        :data="payload.tower.data"
        :role-names="roleNames"
      />
      <p v-else class="wuwa-muted">深塔数据暂不可用</p>
    </section>
    <section class="wuwa-panel">
      <h2>战术全息</h2>
      <WuwaStatus :snap="payload.hologram" />
      <p v-if="payload.hologram?.data?.is_unlock === false">尚未解锁</p>
      <div v-else-if="bossGroups.length" class="wuwa-grid">
        <details
          v-for="group in bossGroups"
          :key="group.key"
          class="wuwa-inset"
        >
          <summary>
            {{ group.name }} · {{ group.records.length }} 条记录
          </summary>
          <article
            v-for="(boss, i) in group.records"
            :key="i"
            class="wuwa-floor"
          >
            <p>
              等级 {{ value(boss.boss_level) }} · 难度
              {{ value(boss.difficulty) }}
            </p>
            <p>通关时间 {{ value(boss.pass_time) }}</p>
            <p>
              队伍：<span
                v-for="(role, j) in list(boss.roles)"
                :key="j"
                class="wuwa-tag"
                >{{ role.role_name || '未知角色' }} Lv.{{
                  value(role.role_level)
                }}</span
              ><span v-if="!list(boss.roles).length">未提供</span>
            </p>
          </article>
        </details>
      </div>
      <p v-else class="wuwa-muted">未提供挑战记录</p>
    </section>
    <section class="wuwa-panel">
      <h2>冥歌海墟</h2>
      <WuwaStatus :snap="payload.slash" />
      <p v-if="payload.slash?.data?.is_unlock === false">尚未解锁</p>
      <template v-else
        ><article
          v-for="(zone, i) in list(payload.slash?.data?.difficulty_list)"
          :key="i"
        >
          <h3>
            {{ zone.difficulty_name || `难度 ${value(zone.difficulty)}` }} ·
            {{ value(zone.all_score) }} / {{ value(zone.max_score) }}
          </h3>
          <div class="wuwa-grid">
            <article
              v-for="(challenge, j) in list(zone.challenge_list)"
              :key="j"
              class="wuwa-inset"
            >
              <h4>{{ challenge.challenge_name }}</h4>
              <p>
                得分 {{ value(challenge.score) }} · 评级
                {{ value(challenge.rank) }}
              </p>
              <div
                v-for="(half, k) in list(challenge.half_list)"
                :key="k"
                class="wuwa-floor"
              >
                <h4>{{ half.half_name || `第 ${k + 1} 半场` }}</h4>
                <p>得分 {{ value(half.score) }}</p>
                <p>
                  队伍：<span
                    v-for="(role, m) in list(half.role_list)"
                    :key="m"
                    class="wuwa-tag"
                    >{{
                      role.role_name ||
                      role.name ||
                      roleNames[role.role_id] ||
                      `角色 ${role.role_id ?? '未知'}`
                    }}</span
                  ><span v-if="!list(half.role_list).length">未提供</span>
                </p>
                <WuwaFields
                  :data="half"
                  :exclude="['role_list', 'score', 'half_name']"
                />
              </div>
            </article>
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
