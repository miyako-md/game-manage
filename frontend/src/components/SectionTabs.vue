<script setup>
defineProps({
  sections: { type: Array, required: true },
})

const active = defineModel({ default: 'pc' })

const LABELS = { pc: 'PC 游戏', mobile: '手游' }
</script>

<template>
  <nav class="tabs">
    <button
      v-for="s in sections"
      :key="s"
      type="button"
      class="tab"
      :class="{ active: active === s }"
      @click="active = s"
    >
      {{ LABELS[s] || s }}
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 8px;
  align-self: flex-start;
}

.tab {
  border: none;
  background: transparent;
  padding: 6px 20px;
  border-radius: 6px;
  cursor: pointer;
  color: var(--text-muted);
}

.tab.active {
  background: var(--accent);
  color: #fff;
}

.tab:hover:not(.active) {
  background: var(--bg);
  color: var(--text);
}
</style>
