<script setup>
import { useId } from 'vue'
import { useDialog } from '../use-dialog.js'
defineProps({ title: { type: String, required: true }, eyebrow: { type: String, default: 'WUTHERING WAVES' } })
const headingId = `wuwa-dialog-${useId()}`
const emit = defineEmits(['close'])
const { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded } = useDialog(() => emit('close'))
</script>

<template>
  <dialog ref="dialog" class="wuwa-role-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" :aria-labelledby="headingId" @cancel.prevent="requestClose" @pointerdown="backdropDown" @click="backdropClick" @animationend="animationEnded">
    <header class="role-dialog-heading">
      <div><p class="wuwa-kicker">{{ eyebrow }}</p><h2 :id="headingId">{{ title }}</h2></div>
      <button type="button" class="ui-button small-button" autofocus @click="requestClose">关闭详情</button>
    </header>
    <div class="role-dialog-body"><slot /></div>
  </dialog>
</template>

<style scoped>
.wuwa-role-dialog { position: fixed; inset: 0; margin: auto; width: min(1180px, calc(100vw - 48px)); max-width: none; max-height: calc(100dvh - 48px); padding: 0; border: 1px solid var(--border-strong); border-radius: 12px; background: var(--card-bg); color: var(--text); box-shadow: var(--popover-shadow); }
.wuwa-role-dialog[open] { display: flex; flex-direction: column; }
.wuwa-role-dialog::backdrop { background: var(--scrim); backdrop-filter: blur(6px); }
.role-dialog-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 26px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.role-dialog-heading h2 { font-size: 18px; margin: 2px 0 0; }
.role-dialog-body { overflow-y: auto; overscroll-behavior: contain; padding: 20px 26px 28px; min-height: 0; }
@media (max-width: 640px) {
  .wuwa-role-dialog { width: calc(100vw - 16px); max-height: calc(100dvh - 16px); border-radius: 12px; }
  .role-dialog-heading, .role-dialog-body { padding: 16px; }
  .role-dialog-heading h2 { font-size: 18px; }
}
</style>
