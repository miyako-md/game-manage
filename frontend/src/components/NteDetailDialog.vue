<script setup>
import GameDialog from './GameDialog.vue'
defineProps({ title: { type: String, required: true } })
const emit = defineEmits(['close'])
</script>

<template>
  <GameDialog class="nte-dialog" :title="title" eyebrow="NEVERNESS TO EVERNESS" @close="emit('close')"><slot /></GameDialog>
</template>

<style scoped>
.nte-dialog { --dialog-width:1200px; }
.nte-dialog :deep(.cap-card) { box-shadow:none; }
.nte-dialog :deep(.guides-layout) { grid-template-columns:170px minmax(0,1fr); }
@media (max-width:650px) { .nte-dialog :deep(.guides-layout) { grid-template-columns:minmax(0,1fr); } }
</style>
