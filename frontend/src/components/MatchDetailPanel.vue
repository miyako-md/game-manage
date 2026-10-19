<script setup>
import { computed } from 'vue'

const props = defineProps({
  detail: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  // 重开局客户端仍记了一方胜一方负，这里不当胜负显示（与列表口径一致）。
  remake: { type: Boolean, default: false },
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
  if (props.remake) return { text: '重开', cls: 'team-remake' }
  if (team.win === true) return { text: '胜利', cls: 'team-win' }
  if (team.win === false) return { text: '失败', cls: 'team-lose' }
  return { text: '-', cls: '' }
}

// 每行伤害条以这场里伤害最高的人为满格。
const topDamage = computed(() => Math.max(1, ...teams.value.flatMap((team) => team.participants.map((p) => (Number.isFinite(p.damage) ? p.damage : 0)))))
const damagePct = (p) => `${Number.isFinite(p.damage) ? Math.round((p.damage / topDamage.value) * 100) : 0}%`

// 两队击杀、伤害、金币的合计对比：一条两段的条，左段是我方。
const sum = (team, field) => team.participants.reduce((total, p) => total + (Number.isFinite(p[field]) ? p[field] : 0), 0)
const compare = computed(() => {
  if (teams.value.length !== 2 || !teams.value.some(isOwnTeam)) return []
  const [own, other] = teams.value
  return [['击杀', 'kills'], ['伤害', 'damage'], ['金币', 'gold']].map(([label, field]) => ({ label, a: sum(own, field), b: sum(other, field) }))
    .filter((row) => row.a + row.b > 0)
    .map((row) => ({ ...row, share: (row.a / (row.a + row.b)) * 100 }))
})
</script>

<template>
  <div class="detail-panel t-panel">
    <p v-if="loading" class="empty">对局详情加载中…</p>
    <div v-else-if="error" class="detail-error" role="alert">{{ error }}</div>
    <template v-else-if="detail">
      <div v-if="compare.length" class="compare" aria-label="两队合计对比">
        <ul class="legend"><li style="--series: var(--game-vivid)">我方</li><li style="--series: var(--text-faint)">对方</li></ul>
        <div v-for="row in compare" :key="row.label" class="compare-row">
          <span class="compare-label">{{ row.label }}</span>
          <span class="compare-bar"><i :style="{ width: `${row.share}%` }"></i></span>
          <span class="compare-values">{{ fmtNum(row.a) }} : {{ fmtNum(row.b) }}</span>
        </div>
      </div>
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
          <div class="table-scroll">
            <table class="data-table">
              <thead>
                <tr>
                  <th>英雄</th>
                  <th>昵称</th>
                  <th class="num">KDA</th>
                  <th class="num">伤害</th>
                  <th class="num">金币</th>
                  <th>装备编号</th>
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
                  <td class="num"><span class="dmg"><span class="meter" aria-hidden="true"><i :style="{ '--pct': damagePct(p) }"></i></span><span>{{ fmtNum(p.damage) }}</span></span></td>
                  <td class="num">{{ fmtNum(p.gold) }}</td>
                  <td class="items-cell"><span v-for="(item, k) in p.items || []" :key="k" class="item-id">{{ item }}</span><span v-if="!(p.items || []).length" class="muted">-</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
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
  border: 1px solid var(--danger-border);
  padding: 8px 12px;
  border-radius: var(--radius-control);
  font-size: 13px;
}

/* Team totals: kills, damage and gold as one two-part bar each; our side keeps the game line, theirs steps back. */
.compare {
  display: grid;
  gap: 8px;
  margin-bottom: 14px;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius-well);
  background: var(--panel-bg);
}

.compare .legend {
  margin: 0 0 2px;
}

.compare-row {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr) minmax(90px, auto);
  align-items: center;
  gap: 12px;
  font-size: 12px;
}

.compare-label {
  color: var(--text-muted);
}

.compare-bar {
  display: block;
  height: 8px;
  overflow: hidden;
  border-radius: 4px;
  background: color-mix(in srgb, var(--text-faint) 45%, var(--track));
}

.compare-bar i {
  display: block;
  height: 100%;
  border-radius: 4px;
  background: var(--game-vivid);
}

.compare-values {
  color: var(--text);
  font-weight: 500;
  text-align: right;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.teams {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

/* Each side is a hairline block with its own table; our side comes first and says so. */
.team-col {
  flex: 1 1 640px;
  border: 1px solid var(--border);
  border-radius: var(--radius-well);
  background: var(--card-bg);
  padding: 10px 12px;
  min-width: 0;
}

.team-col.team-own {
  order: -1;
}

.team-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.team-result {
  padding: 0 8px;
  border-radius: var(--radius-chip);
  background: var(--control-track);
  color: var(--text-body);
  font-size: 12px;
  font-weight: 600;
  line-height: 22px;
}

.team-win {
  color: var(--success);
  background: var(--success-bg);
}

.team-lose {
  color: var(--danger);
  background: var(--danger-bg);
}

.team-remake {
  color: var(--text-muted);
}

.team-own-tag {
  font-size: 12px;
  font-weight: 500;
  color: var(--game-accent);
  background: var(--game-tone);
  border-radius: var(--radius-chip);
  padding: 0 8px;
  line-height: 22px;
}

.table-scroll {
  overflow-x: auto;
}

/* A table wider than its block fades out at the right edge until it has been scrolled to the end, so cut-off columns read as "more this way". */
@property --table-fade {
  syntax: '<length>';
  inherits: false;
  initial-value: 0px;
}
@keyframes table-edge {
  from { --table-fade: 28px; }
  to { --table-fade: 0px; }
}
@supports (animation-timeline: scroll(self inline)) {
  .table-scroll {
    animation: table-edge linear both;
    animation-timeline: scroll(self inline);
    -webkit-mask-image: linear-gradient(to right, #000 calc(100% - var(--table-fade)), transparent);
    mask-image: linear-gradient(to right, #000 calc(100% - var(--table-fade)), transparent);
  }
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

.team-col .data-table small {
  font-size: 12px;
}

.team-col .data-table td.num {
  font-variant-numeric: tabular-nums;
}

.muted {
  color: var(--text-muted);
}

/* Damage: the number with a thin bar beside it, full length for the match's top damage. */
.team-col .data-table .dmg {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.team-col .data-table .dmg .meter {
  flex: 0 0 44px;
  height: 4px;
}

/* Up to six item ids per player: small wrapping chips, all of them readable. */
.team-col .data-table td.items-cell {
  min-width: 150px;
  white-space: normal;
}

.item-id {
  display: inline-block;
  margin: 1px 3px 1px 0;
  padding: 0 6px;
  border-radius: var(--radius-chip);
  background: var(--control-track);
  color: var(--text-muted);
  font-size: 12px;
  line-height: 18px;
}

.player-own td {
  background: color-mix(in srgb, var(--game-tone) 70%, transparent);
}
</style>
