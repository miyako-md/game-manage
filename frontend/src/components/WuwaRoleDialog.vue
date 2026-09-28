<script setup>
import GameDialog from './GameDialog.vue'
defineProps({ title: { type: String, required: true }, eyebrow: { type: String, default: 'WUTHERING WAVES' } })
const emit = defineEmits(['close'])
</script>

<template>
  <GameDialog class="wuwa-role-dialog" :title="title" :eyebrow="eyebrow" @close="emit('close')"><slot /></GameDialog>
</template>
