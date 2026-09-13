<script setup>
import { computed } from 'vue'

const props = defineProps({
  detail: { type: Object, default: null }, // MatchDetail payload
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
  <div class="detail-panel">
    <p v-if="loading" class="empty">对局详情加载中…</p>
    <div v-else-if="error" class="detail-error" role="alert">{{ error }}</div>
    <template v-else-if="detail">
      <div class="teams">
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
          <div
            v-for="(p, i) in team.participants"
            :key="`${team.team_id}-${i}`"
            class="player"
            :class="{ 'player-own': p.is_own }"
          >
            <div class="player-main">
              <span class="champ">{{ championName(p) }}</span>
              <span class="lv">Lv{{ p.level ?? '-' }}</span>
              <span class="role">{{ p.role_name || '-' }}</span>
            </div>
            <div class="player-sub">
              <span class="kda">{{ kda(p) }}</span>
              <span class="dmg">{{ fmtNum(p.damage) }}</span>
              <span class="gold">{{ fmtNum(p.gold) }}</span>
            </div>
            <div class="items">
              <span
                v-for="(item, i) in (p.items || []).slice(0, 6)"
                :key="i"
                class="item-box"
                :title="`装备 #${item}`"
              >{{ item }}</span>
            </div>
          </div>
        </div>
      </div>
      <p class="detail-legend">
        每行：英雄 / 等级 / 昵称 · KDA · 伤害 · 金币 · 装备（图标后续版本接入）
      </p>
    </template>
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
  gap: 10px;
  flex-wrap: wrap;
}

.team-col {
  flex: 1 1 240px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px;
  min-width: 240px;
}

.team-col.team-own {
  border-color: var(--accent);
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
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 999px;
  padding: 0 6px;
}

.player {
  padding: 6px 4px;
  border-top: 1px solid var(--border);
}

.player:first-of-type {
  border-top: none;
}

.player-own {
  background: var(--success-bg);
  border-radius: 6px;
}

.player-main {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.champ {
  font-weight: 500;
}

.lv,
.role {
  font-size: 12px;
  color: var(--text-muted);
}

.role {
  margin-left: auto;
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.player-sub {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.kda {
  color: var(--text);
}

.items {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.item-box {
  width: 28px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: var(--text-muted);
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 4px;
}

.detail-legend {
  margin-top: 6px;
  font-size: 11px;
  color: var(--text-muted);
}
</style>
