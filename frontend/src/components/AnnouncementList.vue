<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

function fmtDate(value) {
  if (!value) return ''
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => ({ ...it, dateText: fmtDate(it.published_at) }))
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">公告</div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="item-list">
      <li v-for="(it, i) in rows" :key="i" class="item">
        <div class="item-main">
          <a
            v-if="it.url"
            class="item-title item-link"
            :href="it.url"
            target="_blank"
            rel="noopener"
          >{{ it.title }}</a>
          <span v-else class="item-title">{{ it.title }}</span>
          <span v-if="it.dateText" class="item-date">{{ it.dateText }}</span>
        </div>
        <p v-if="it.summary" class="item-summary">{{ it.summary }}</p>
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

.item-link {
  color: var(--accent);
  text-decoration: none;
}

.item-link:hover {
  text-decoration: underline;
}

.item-date {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.item-summary {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}
</style>
