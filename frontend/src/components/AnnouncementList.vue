<script setup>
import { computed } from 'vue'
import { formatTime } from '../dashboard.js'
import { safeUrl } from '../calendar.js'

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
    <div class="cap-title">
      {{ capability === 'news' ? '资讯' : '公告' }}
      <span v-if="snap?.stale" class="badge badge-stale">数据可能过期</span>
      <span v-if="snap?.fetched_at" class="cap-meta">更新于 {{ formatTime(snap.fetched_at) }}</span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="item-list">
      <li v-for="(it, i) in rows" :key="i" class="item" :style="{ '--i': Math.min(i, 11) }">
        <p class="item-title">
          <a v-if="it.url" class="item-link" :href="it.url" target="_blank" rel="noopener noreferrer">{{ it.title }}</a>
          <span v-else>{{ it.title }}</span>
        </p>
        <p class="item-meta">
          <span v-if="it.source_name" class="chip">{{ it.source_name }}</span>
          <span v-if="it.source_stale" class="badge badge-stale">来源采集异常，保留旧记录</span>
          <span v-if="it.dateText" class="item-date">{{ it.dateText }}</span>
        </p>
        <p v-if="it.summary" class="item-summary" :title="it.summary">{{ it.summary }}</p>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.item-list {
  display: flex;
  flex-direction: column;
}

.item {
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.item-title {
  margin: 0;
  font-size: 13px;
  font-weight: 500;
  line-height: 18px;
}

.item-link {
  color: var(--accent);
  text-decoration: none;
}

.item-link:hover {
  text-decoration: underline;
}

.item-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin: 4px 0 0;
}

.item-date {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-faint);
  white-space: nowrap;
}

.item-summary {
  margin: 4px 0 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
