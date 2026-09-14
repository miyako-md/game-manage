<script setup>
import { computed } from 'vue'
import { safeUrl, formatTime } from '../dashboard.js'

const props = defineProps({
  snap: { type: Object, default: null },
  capability: { type: String, default: 'announcement' },
})

function fmtDate(value) {
  if (!value) return ''
  return formatTime(value, { hour: undefined, minute: undefined })
}

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => ({ ...it, url: safeUrl(it.url), dateText: fmtDate(it.published_at) }))
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">{{ capability === 'news' ? '资讯' : '公告' }}<span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span></div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="item-list">
      <li v-for="(it, i) in rows" :key="i" class="item">
        <div class="item-main">
          <a
            v-if="it.url"
            class="item-title item-link"
            :href="it.url"
            target="_blank"
            rel="noopener noreferrer"
          >{{ it.title }}</a>
          <span v-else class="item-title">{{ it.title }}</span>
          <span v-if="it.dateText" class="item-date">{{ it.dateText }}</span>
        </div>
        <p v-if="it.summary" class="item-summary">{{ it.summary }}</p>
      </li>
    </ul>
    <p v-if="snap?.fetched_at" class="fetched-at">更新于 {{ formatTime(snap.fetched_at) }}</p>
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
