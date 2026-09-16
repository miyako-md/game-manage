<script setup>
import { value } from '../wuwa-display.js'
defineProps({ rows: { type: Array, default: () => [] } })
</script>
<template>
  <div class="wuwa-table-wrap">
    <table>
      <thead>
        <tr>
          <th>记录时间（来源时区）</th>
          <th>卡池</th>
          <th>获得物品</th>
          <th>稀有度</th>
          <th>数量</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(row, i) in rows"
          :key="row.draw_id || i"
          :class="{ 'wuwa-gold-row': String(row.rarity) === '5' }"
        >
          <td>{{ value(row.time) }}</td>
          <td>{{ value(row.pool) }}</td>
          <td>
            {{ row.name || '名称未知' }} <small>{{ row.resource_type }}</small>
          </td>
          <td>{{ value(row.rarity) }}</td>
          <td>{{ value(row.count) }}</td>
        </tr>
      </tbody>
    </table>
    <p v-if="!rows.length" class="wuwa-muted">本页无记录</p>
  </div>
</template>
