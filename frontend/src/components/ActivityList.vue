<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => {
    let badge = null
    if (it.end_at) {
      const end = new Date(it.end_at)
      if (!Number.isNaN(end.getTime())) {
        const days = Math.ceil((end.getTime() - Date.now()) / 86400000)
        badge = {
          text: days < 0 ? '已结束' : `剩余 ${days} 天`,
          danger: days <= 3,
        }
      }
    }
    return {
      ...it,
      badge,
      startText: it.start_at ? fmtDate(it.start_at) : '',
      endText: it.end_at ? fmtDate(it.end_at) : '',
    }
  })
})

function fmtDate(value) {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">活动</div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="item-list">
      <li v-for="(it, i) in rows" :key="i" class="item">
        <div class="item-main">
          <span class="item-title">{{ it.title }}</span>
          <span
            v-if="it.badge"
            class="badge"
            :class="it.badge.danger ? 'badge-danger' : 'badge-muted'"
          >
            {{ it.badge.text }}
          </span>
        </div>
        <div v-if="it.startText || it.endText" class="item-dates">
          <span v-if="it.startText">开始 {{ it.startText }}</span>
          <span v-if="it.endText">结束 {{ it.endText }}</span>
        </div>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.item-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.item-title {
  font-weight: 500;
}

.item-dates {
  display: flex;
  gap: 12px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.badge-muted {
  color: var(--text-muted);
  background: var(--bg);
}
</style>
