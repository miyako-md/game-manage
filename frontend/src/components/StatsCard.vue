<script setup>
import { fetchedLabel } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)
const fetchedAt = computed(() => fetchedLabel(props.snap?.fetched_at))

const pct = (v) => (v == null ? '-' : `${v}%`)
const avg = (v) => (v == null ? '-' : String(v))

const topChampions = computed(() => {
  const list = payload.value?.top_champions ?? []
  return list.map((c) => ({
    ...c,
    winrate: c.games > 0 ? Math.round((c.wins / c.games) * 100) : null,
  }))
})

const records = computed(() => payload.value?.records ?? [])
const maxGames = computed(() => Math.max(1, ...topChampions.value.map((c) => c.games || 0)))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      生涯统计
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="fetchedAt" class="cap-meta">更新于 {{ fetchedAt }}</span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div class="stats-body">
        <div class="stats-figures">
          <dl class="kv-grid tiles" style="--kv-min:92px">
            <div><dt>近20场</dt><dd>{{ payload.total_games }}</dd></div>
            <div><dt>胜率</dt><dd>{{ pct(payload.winrate) }}<small v-if="payload.wins != null">{{ payload.wins }}胜</small></dd></div>
            <div class="kda-tile"><dt>平均 KDA</dt><dd>{{ avg(payload.avg_kills) }}/{{ avg(payload.avg_deaths) }}/{{ avg(payload.avg_assists) }}</dd></div>
          </dl>
          <div v-if="records.length > 0" class="block">
            <p class="block-title">名场面</p>
            <dl class="kv-grid tiles" style="--kv-min:100px">
              <div v-for="r in records" :key="r.label"><dt>{{ r.label }}</dt><dd>{{ r.value }}</dd></div>
            </dl>
          </div>
        </div>
        <div v-if="topChampions.length > 0" class="block">
          <p class="block-title">常用英雄 <span class="legend-inline"><i class="w"></i>胜 <i class="l"></i>负</span></p>
          <ul class="champions">
            <li v-for="c in topChampions" :key="c.champion_id">
              <span class="name">{{ c.champion_name || `英雄 #${c.champion_id}` }}</span>
              <span class="wl-track" :title="`${c.games} 场 ${c.wins} 胜 ${c.games - c.wins} 负`">
                <span class="wl-fill" :style="{ width: `${(c.games / maxGames) * 100}%` }">
                  <i v-if="c.wins" class="w" :style="{ flex: c.wins }"></i><i v-if="c.games - c.wins" class="l" :style="{ flex: c.games - c.wins }"></i>
                </span>
              </span>
              <span class="games">{{ c.games }} 场</span>
              <span class="rate">{{ c.winrate == null ? '-' : `${c.winrate}%` }}</span>
            </li>
          </ul>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.block {
  margin-top: 12px;
}

/* Wide card: figures on the left, the champion bars on the right. */
.stats-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 4px 24px;
  align-items: start;
}

.stats-body > .block {
  margin-top: 0;
}

@media (max-width: 900px) {
  .stats-body { grid-template-columns: minmax(0, 1fr); }
  .stats-body > .block { margin-top: 12px; }
}

.block-title {
  font-size: 11px;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 6px;
}

/* 常用英雄: bar length = games, split into wins (green) and losses (red). */
.legend-inline { display: inline-flex; align-items: center; gap: 4px; margin-left: 8px; color: var(--text-faint); font-weight: 400; }
.legend-inline i { width: 7px; height: 7px; margin-left: 4px; border-radius: 2px; }
.champions { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
.champions li { display: grid; grid-template-columns: minmax(64px, 30%) minmax(60px, 1fr) 40px 36px; align-items: center; gap: 10px; min-height: 28px; font-size: 13px; }
.champions .name { min-width: 0; overflow: hidden; color: var(--text-body); text-overflow: ellipsis; white-space: nowrap; }
.wl-track { display: block; height: 8px; border-radius: 999px; background: var(--track); overflow: hidden; }
.wl-fill { display: flex; gap: 2px; height: 100%; border-radius: 999px; overflow: hidden; }
.wl-fill i, .legend-inline i { display: block; }
.w { background: var(--success); }
.l { background: color-mix(in srgb, var(--danger) 80%, transparent); }
.games { color: var(--text-muted); font-size: 12px; text-align: right; white-space: nowrap; }
.rate { color: var(--text); font-size: 12px; font-weight: 600; text-align: right; white-space: nowrap; }

.kda-tile dd {
  font-size: 14px;
  line-height: 19px;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
}
</style>
