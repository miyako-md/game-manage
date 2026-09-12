<script setup>
defineProps({
  notify: { type: Object, required: true },
})
</script>

<template>
  <span v-if="!notify.enabled" class="chip chip-warn">
    微信推送未配置（功能已就绪）
  </span>
  <span v-else class="chip chip-ok">
    微信推送已启用{{ notify.provider ? `（${notify.provider}）` : '' }}
  </span>
</template>

<style scoped>
.chip {
  display: inline-block;
  padding: 3px 12px;
  border-radius: 999px;
  font-size: 12px;
  line-height: 20px;
}

.chip-warn {
  color: var(--stale-text);
  background: var(--stale-bg);
}

.chip-ok {
  color: #1a7f37;
  background: #dafbe1;
}
</style>
