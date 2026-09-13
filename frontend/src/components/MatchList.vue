<script setup>
import { computed, ref } from 'vue'
import { getMatchDetail } from '../api.js'
import MatchDetailPanel from './MatchDetailPanel.vue'

const props = defineProps({
  snap: { type: Object, default: null },
  gameId: { type: String, default: '' },
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

// ---- 对局详情按需展开（同时只展开一行）----
const expandedId = ref(null)
const detail = ref(null)
const detailLoading = ref(false)
const detailError = ref('')

async function toggleDetail(row) {
  if (expandedId.value === row.match_id) {
    expandedId.value = null
    detail.value = null
    detailError.value = ''
    return
  }
  expandedId.value = row.match_id
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  try {
    const data = await getMatchDetail(props.gameId, row.match_id)
    if (data?.error) {
      detailError.value = data.error
    } else {
      detail.value = data?.payload ?? null
    }
  } catch (e) {
    detailError.value = e?.message || '请求异常'
  } finally {
    detailLoading.value = false
  }
}
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
          <span class="item-actions">
            <span v-if="it.dateText" class="item-date">{{ it.dateText }}</span>
            <button
              type="button"
              class="detail-btn"
              @click="toggleDetail(it)"
            >
              {{ expandedId === it.match_id ? '收起' : '详情' }}
            </button>
          </span>
        </div>
        <div class="item-sub">
          <span>{{ it.kda }}</span>
          <span>{{ it.durationText }}</span>
        </div>
        <MatchDetailPanel
          v-if="expandedId === it.match_id"
          :detail="detail"
          :loading="detailLoading"
          :error="detailError"
        />
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

.item-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.detail-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-muted);
  font-size: 12px;
  padding: 1px 10px;
  border-radius: 999px;
  cursor: pointer;
}

.detail-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.item-sub {
  display: flex;
  gap: 12px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.badge-win {
  color: var(--success);
  background: var(--success-bg);
}

.badge-muted {
  color: var(--text-muted);
  background: var(--bg);
}
</style>
