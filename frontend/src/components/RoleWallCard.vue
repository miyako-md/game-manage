<script setup>
import { displayBeijing } from '../time.js'
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

function toLocal(value) {
  if (!value) return null
  return displayBeijing(value)
}

const payload = computed(() => props.snap?.payload ?? null)

const roles = computed(() => (Array.isArray(payload.value) ? payload.value : []))

// 顶部统计条：角色总数 / 满级 / 6链 / 五星
const stats = computed(() => ({
  total: roles.value.length,
  full: roles.value.filter((r) => r.level === 90).length,
  chain6: roles.value.filter((r) => (r.chain ?? 0) === 6).length,
  five: roles.value.filter((r) => r.star_level === 5).length,
}))

const fetchedAt = computed(() => toLocal(props.snap?.fetched_at))
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      角色练度
      <span v-if="snap?.stale" class="badge badge-stale">
        数据可能过期
      </span>
    </div>

    <p v-if="roles.length === 0" class="empty">暂无数据</p>
    <template v-else>
      <p class="stats">
        角色总数 {{ stats.total }} · 满级(Lv90) {{ stats.full }} ·
        6链 {{ stats.chain6 }} · 五星 {{ stats.five }}
      </p>

      <ul class="role-grid">
        <li v-for="(r, i) in roles" :key="i" class="role-cell">
          <span v-if="r.star_level === 5" class="star-badge" title="五星">★</span>
          <img
            v-if="r.icon_url"
            class="role-avatar"
            :src="r.icon_url"
            :alt="r.name || '角色'"
            loading="lazy"
          />
          <span v-else class="role-avatar role-avatar-empty">
            {{ (r.name || '?').slice(0, 1) }}
          </span>
          <span class="role-level">Lv{{ r.level ?? '-' }}</span>
          <span class="role-attr">{{ r.attribute || '—' }}</span>
          <span v-if="(r.chain ?? 0) > 0" class="role-chain">{{ r.chain }}链</span>
        </li>
      </ul>
    </template>

    <p v-if="fetchedAt" class="fetched-at">更新于 {{ fetchedAt }}</p>
  </div>
</template>

<style scoped>
.stats {
  font-size: 13px;
  color: var(--text-muted);
}

.role-grid {
  margin-top: 8px;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(56px, 1fr));
  gap: 8px;
}

.role-cell {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  text-align: center;
}

.role-avatar {
  width: 52px;
  height: 52px;
  border-radius: 8px;
  object-fit: cover;
  background: var(--bg);
  border: 1px solid var(--border);
}

.role-avatar-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  color: var(--text-muted);
}

/* 五星金星角标（复用既有 stale 深金色，避免引入新色值） */
.star-badge {
  position: absolute;
  top: -5px;
  right: 2px;
  z-index: 1;
  font-size: 11px;
  line-height: 1;
  color: var(--stale-text);
  text-shadow: 0 0 2px var(--card-bg);
}

.role-level {
  font-size: 12px;
  font-weight: 600;
}

.role-attr {
  font-size: 10px;
  color: var(--text-muted);
}

.role-chain {
  font-size: 10px;
  color: var(--accent);
}
</style>
