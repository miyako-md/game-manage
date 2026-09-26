<script setup>
import { computed } from 'vue'
import InfoHint from './InfoHint.vue'

const props = defineProps({
  detail: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})

const championName = (p) => p.champion_name || `英雄 #${p.champion_id ?? '?'}`
const kda = (p) => `${p.kills ?? 0}/${p.deaths ?? 0}/${p.assists ?? 0}`
const fmtNum = (v) => (v == null ? '-' : Number(v).toLocaleString())

// 我方队伍在前（后端已排序，这里兜底），队内保持后端顺序
const teams = computed(() => {
  const list = props.detail?.teams ?? []
  return [...list].sort(
    (a, b) => Number(b.participants.some((p) => p.is_own)) -
      Number(a.participants.some((p) => p.is_own)),
  )
})

const isOwnTeam = (team) => team.participants.some((p) => p.is_own)
const teamResult = (team) => {
  if (team.win === true) return { text: '胜利', cls: 'team-win' }
  if (team.win === false) return { text: '失败', cls: 'team-lose' }
  return { text: '-', cls: '' }
}
</script>

<template>
  <div class="detail-panel t-panel">
    <p v-if="loading" class="empty">对局详情加载中…</p>
    <div v-else-if="error" class="detail-error" role="alert">{{ error }}</div>
    <div v-else-if="detail" class="teams">
      <div
        v-for="team in teams"
        :key="team.team_id"
        class="team-col"
        :class="{ 'team-own': isOwnTeam(team) }"
      >
        <div class="team-head">
          <span class="team-result" :class="teamResult(team).cls">
            {{ teamResult(team).text }}
          </span>
          <span v-if="isOwnTeam(team)" class="team-own-tag">我方</span>
        </div>
        <div class="table-scroll">
          <table class="data-table">
            <thead>
              <tr>
                <th>英雄</th>
                <th>昵称</th>
                <th class="num">KDA</th>
                <th class="num">伤害</th>
                <th class="num">金币</th>
                <th>装备<InfoHint text="装备当前仅显示编号，图标将在后续版本接入。" align="end" /></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(p, i) in team.participants"
                :key="`${team.team_id}-${i}`"
                :class="{ 'player-own': p.is_own }"
              >
                <td>{{ championName(p) }} <small class="muted">Lv{{ p.level ?? '-' }}</small></td>
                <td class="muted">{{ p.role_name || '-' }}</td>
                <td class="num">{{ kda(p) }}</td>
                <td class="num">{{ fmtNum(p.damage) }}</td>
                <td class="num">{{ fmtNum(p.gold) }}</td>
                <td class="muted items-cell" :title="(p.items || []).join(' · ')">{{ (p.items || []).join('·') || '-' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.detail-panel {
  margin-top: 8px;
}

.detail-error {
  background: var(--danger-bg);
  color: var(--danger);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
}

.teams {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.team-col {
  flex: 1 1 300px;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px;
  min-width: 260px;
}

.team-col.team-own {
  border-color: var(--game-lol);
  order: -1;
}

.team-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.team-result {
  font-size: 12px;
  font-weight: 600;
}

.team-win {
  color: var(--success);
}

.team-lose {
  color: var(--danger);
}

.team-own-tag {
  font-size: 11px;
  color: var(--game-lol);
  border: 1px solid var(--game-lol);
  border-radius: 999px;
  padding: 0 6px;
}

.table-scroll {
  overflow-x: auto;
}

/* Nicknames and champion names are unbroken CJK strings with no natural line-
   break point; without nowrap the browser wraps them one character per line
   instead of scrolling the table, which is far harder to read. */
.team-col .data-table th,
.team-col .data-table td {
  white-space: nowrap;
}

.team-col .data-table {
  min-width: 320px;
}

.muted {
  color: var(--text-muted);
}

.items-cell {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-own td {
  background: color-mix(in srgb, var(--game-lol) 12%, transparent);
}
</style>
