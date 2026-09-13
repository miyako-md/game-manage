<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

function toLocal(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString()
}

// start_at 仅显示月-日
function fmtMonthDay(value) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return ''
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${mm}-${dd}`
}

function fmtDuration(seconds) {
  if (seconds == null) return '-'
  return `${Math.round(seconds / 60)}分钟`
}

function kdaText(it) {
  if (it.kills == null || it.deaths == null || it.assists == null) return '-'
  return `${it.kills}/${it.deaths}/${it.assists}`
}

function winBadge(win) {
  if (win === true) return { text: '胜', cls: 'badge-win' }
  if (win === false) return { text: '负', cls: 'badge-danger' }
  return { text: '-', cls: 'badge-muted' }
}

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => ({
    ...it,
    badge: winBadge(it.win),
    dateText: fmtMonthDay(it.start_at),
    durationText: fmtDuration(it.duration_seconds),
    kda: kdaText(it),
  }))
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      对局
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <ul v-else class="item-list">
      <li v-for="(it, i) in rows" :key="i" class="item">
        <div class="item-main">
          <span class="match-mode">
            <span class="badge" :class="it.badge.cls">{{ it.badge.text }}</span>
            <span class="item-title">{{ it.mode || '-' }}</span>
          </span>
          <span v-if="it.dateText" class="item-date">{{ it.dateText }}</span>
        </div>
        <div class="item-sub">
          <span>{{ it.kda }}</span>
          <span>{{ it.durationText }}</span>
        </div>
      </li>
    </ul>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
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

.match-mode {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-title {
  font-weight: 500;
}

.item-date {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--text-muted);
}

.item-sub {
  display: flex;
  gap: 12px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.badge-win {
  color: #1a7f37;
  background: #dafbe1;
}

.badge-muted {
  color: var(--text-muted);
  background: var(--bg);
}
</style>
