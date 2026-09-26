<script setup>
import { computed } from 'vue'
import { fieldLabels, value } from '../wuwa-display.js'
import WuwaFields from './WuwaFields.vue'
import WuwaStatus from './WuwaStatus.vue'
import InfoHint from './InfoHint.vue'
const props = defineProps({ snap: { default: null } })
const sections = computed(() =>
  Object.entries(props.snap?.payload?.sections || {}).sort(
    (a, b) => (a[1]?.sort ?? 999) - (b[1]?.sort ?? 999),
  ),
)
const countable = (v) => v == null || typeof v === 'number'
// Sections arrive with arbitrary keys. Only an explicit X / max_X pair of plain
// numbers is shown as "current / limit" with a meter; everything else stays a
// labelled field.
const tiles = computed(() => {
  let bars = 0
  return sections.value.map(([key, raw]) => {
    const section = raw && typeof raw === 'object' ? raw : {}
    const used = ['title']
    const pairs = []
    for (const [k, cur] of Object.entries(section)) {
      const capKey = `max_${k}`
      if (k.startsWith('max_') || !(capKey in section)) continue
      const cap = section[capKey]
      if (!countable(cur) || !countable(cap) || (cur == null && cap == null))
        continue
      used.push(k, capKey)
      pairs.push({
        key: k,
        // Every bar on the page takes the next series colour.
        series: `var(--chart-${bars++ % 6 + 1})`,
        label: fieldLabels[k] || k,
        cur,
        cap,
        pct:
          typeof cur === 'number' && typeof cap === 'number' && cap > 0
            ? Math.min(100, Math.round((cur / cap) * 100))
            : null,
      })
    }
    const rank =
      section.rank != null && typeof section.rank !== 'object'
        ? section.rank
        : null
    if (rank != null) used.push('rank')
    return { key, section, title: section.title || '未命名玩法', pairs, rank, used }
  })
})
</script>
<template>
  <section class="wuwa-panel">
    <header class="cap-title">
      <h2>玩法进度</h2>
      <InfoHint text="按当前来源返回的玩法展示，名称与内容随版本变化。" />
      <WuwaStatus :snap="snap" />
    </header>
    <div v-if="tiles.length" class="wuwa-tiles wuwa-activities">
      <article v-for="tile in tiles" :key="tile.key" class="wuwa-tile">
        <header class="wuwa-tile-head">
          <h3>{{ tile.title }}</h3>
          <span v-if="tile.rank != null" class="badge wuwa-rank wuwa-tile-end"
            >{{ fieldLabels.rank }} {{ tile.rank }}</span
          >
        </header>
        <div v-for="p in tile.pairs" :key="p.key" class="wuwa-pair">
          <p class="wuwa-pair-line">
            <span class="k">{{ p.label }}</span
            ><span class="v"
              ><b>{{ value(p.cur) }}</b> / {{ value(p.cap) }}</span
            ><span v-if="p.pct != null" class="wuwa-pct">{{ p.pct }}%</span>
          </p>
          <span class="meter"
            ><i
              :style="{ '--pct': (p.pct ?? 0) + '%', '--series': p.series }"
            ></i
          ></span>
        </div>
        <WuwaFields :data="tile.section" :exclude="tile.used" />
      </article>
    </div>
    <p v-else class="wuwa-muted">尚未获得玩法数据</p>
  </section>
</template>
