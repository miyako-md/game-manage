<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

// MM-DD HH:mm（本地时区）；解析失败/缺失返回 null（占位 "—"）
function fmt(value) {
  if (!value) return null
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 事件按 end_at 升序（无截止时间排最后）
const rows = computed(() => {
  const items = Array.isArray(payload.value) ? payload.value : []
  return items
    .map((e) => {
      const startText = fmt(e.start_at)
      const endText = fmt(e.end_at)
      return {
        ...e,
        // 开始为相对描述（"版本更新后"）解析不出 → 显示"版本更新后开始"
        rangeText: `${startText ?? '版本更新后开始'} ~ ${endText ?? '—'}`,
        remainBadge: remainBadge(e.end_at),
      }
    })
    .sort((a, b) => {
      const ta = a.end_at ? new Date(a.end_at).getTime() : Infinity
      const tb = b.end_at ? new Date(b.end_at).getTime() : Infinity
      return ta - tb
    })
})

// 剩余天数徽标：已结束灰 / ≤3 天红 / 其余常规灰（沿用全局徽标样式）
function remainBadge(end) {
  if (!end) return null
  const d = new Date(end)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.ceil((d.getTime() - Date.now()) / 86400000)
  if (days < 0) return { text: '已结束', cls: 'badge-muted' }
  return {
    text: `剩余 ${days} 天`,
    cls: days <= 3 ? 'badge-danger' : 'badge-muted',
  }
}

const fetchedAt = computed(() => {
  if (!props.snap?.fetched_at) return null
  const d = new Date(props.snap.fetched_at)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString()
})
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      活动日历
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">
      暂无版本公告
    </p>
    <p v-else-if="rows.length === 0" class="empty">
      当前版本公告未解析到活动
    </p>
    <ul v-else class="event-list">
      <li v-for="(e, i) in rows" :key="i" class="event-item">
        <div class="event-main">
          <span class="event-name">{{ e.name || '未命名活动' }}</span>
          <span v-if="e.category" class="badge badge-muted">{{ e.category }}</span>
          <span v-if="e.remainBadge" class="badge" :class="e.remainBadge.cls">
            {{ e.remainBadge.text }}
          </span>
        </div>
        <p class="event-time">{{ e.rangeText }}</p>
      </li>
    </ul>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.event-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.event-item {
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.event-item:last-child {
  border-bottom: none;
}

.event-main {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
  flex-wrap: wrap;
}

.event-name {
  font-weight: 600;
}

.event-time {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.badge-muted {
  color: var(--text-muted);
  background: var(--bg);
}
</style>
