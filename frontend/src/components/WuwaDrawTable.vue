<script setup>
import { value } from '../wuwa-display.js'
defineProps({
  rows: { type: Array, default: () => [] },
  // Pool id → pool name from the archive summary, so the column reads as a name.
  poolNames: { type: Object, default: () => ({}) },
})
// Record times stay in the source time zone: only the layout changes
// ("2026-09-21T19:43:49" → "09-21 19:43"), never the clock.
const TIME = /^(\d{4})-(\d{2}-\d{2})[T ](\d{2}:\d{2})/
function shortTime(v) {
  const match = typeof v === 'string' ? v.match(TIME) : null
  return match ? `${match[2]} ${match[3]}` : value(v)
}
const fullTime = (v) =>
  typeof v === 'string' && TIME.test(v) ? v.replace('T', ' ') : undefined
</script>
<template>
  <div class="wuwa-table-wrap">
    <table class="data-table wuwa-draws">
      <thead>
        <tr>
          <th>时间（来源时区）</th>
          <th>卡池</th>
          <th>获得物品</th>
          <th class="num">星级</th>
          <th class="num">数量</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in rows"
          :key="row.draw_id || i"
          :class="{
            'wuwa-gold-row': String(row.rarity) === '5',
            'wuwa-four-row': String(row.rarity) === '4',
          }"
        >
          <td :title="fullTime(row.time)">{{ shortTime(row.time) }}</td>
          <td>{{ poolNames[row.pool] || value(row.pool) }}</td>
          <td>
            {{ row.name || '名称未知' }}
            <small v-if="row.resource_type">{{ row.resource_type }}</small>
          </td>
          <td class="num wuwa-rarity">{{ value(row.rarity) }}</td>
          <td class="num">{{ value(row.count) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="empty">本页无记录</p>
  </div>
</template>
