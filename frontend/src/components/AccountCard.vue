<script setup>
import { computed } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const payload = computed(() => props.snap?.payload ?? null)
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">账号</div>

    <p v-if="payload == null" class="empty">暂无数据</p>
    <ul v-else class="account-info">
      <li>
        <span class="label">昵称</span>
        <span>{{ payload.nickname || '未知' }}</span>
      </li>
      <li>
        <span class="label">等级</span>
        <span>{{ payload.level ?? '未知' }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.account-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.account-info li {
  display: flex;
  gap: 12px;
}

.label {
  color: var(--text-muted);
  flex-shrink: 0;
}
</style>
