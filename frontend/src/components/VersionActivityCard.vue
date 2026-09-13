<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)

function toLocal(value) {
  if (!value) return null
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleString()
}

const endText = computed(() => toLocal(payload.value?.end_at))

// 剩余天数徽标：已结束 / ≤3 天红色告急 / 常规灰色
const remainBadge = computed(() => {
  const end = payload.value?.end_at
  if (!end) return null
  const d = new Date(end)
  if (Number.isNaN(d.getTime())) return null
  const days = Math.ceil((d.getTime() - Date.now()) / 86400000)
  if (days < 0) return { text: '已结束', cls: 'badge-muted' }
  return {
    text: `剩余 ${days} 天`,
    cls: days <= 3 ? 'badge-danger' : 'badge-muted',
  }
})

// 核心奖励行：total>0 显示 cur/total 进度，total=0 仅名称 + status 徽标
// （0=进行中 灰 / 1=可领取 绿，参考 MatchList 三态徽标写法）
function rewardBadge(r) {
  if (r.status === 1) return { text: '可领取', cls: 'badge-win' }
  return { text: '进行中', cls: 'badge-muted' }
}

const rewardRows = computed(() => {
  const list = payload.value?.core_rewards
  if (!Array.isArray(list)) return []
  return list.map((r) => ({
    ...r,
    hasProgress: (r.total ?? 0) > 0,
    badge: rewardBadge(r),
  }))
})

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      版本活动
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <template v-else>
      <div class="act-main">
        <span class="act-title">{{ payload.title || '未命名活动' }}</span>
        <span
          v-if="remainBadge"
          class="badge"
          :class="remainBadge.cls"
        >{{ remainBadge.text }}</span>
      </div>
      <p v-if="endText" class="act-end">截止 {{ endText }}</p>

      <ul v-if="rewardRows.length > 0" class="reward-list">
        <li v-for="(r, i) in rewardRows" :key="i" class="reward-item">
          <span class="reward-name">{{ r.name || '-' }}</span>
          <span v-if="r.hasProgress" class="reward-progress">
            {{ r.cur ?? 0 }}/{{ r.total }}
          </span>
          <span v-else class="badge" :class="r.badge.cls">{{ r.badge.text }}</span>
        </li>
      </ul>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.act-main {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.act-title {
  font-size: 15px;
  font-weight: 600;
}

.act-end {
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.reward-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.reward-item {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.reward-item:last-child {
  border-bottom: none;
}

.reward-name {
  font-weight: 500;
}

.reward-progress {
  font-variant-numeric: tabular-nums;
  color: var(--text);
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
