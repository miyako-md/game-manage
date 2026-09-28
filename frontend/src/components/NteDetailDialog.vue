<script setup>
import { useId } from 'vue'
import { useDialog } from '../use-dialog.js'
defineProps({title:{type:String,required:true}})
const emit=defineEmits(['close']), titleId=`nte-detail-${useId()}`
const { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded } = useDialog(() => emit('close'))
</script>
<template>
  <dialog ref="dialog" class="nte-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" :aria-labelledby="titleId" @cancel.prevent="requestClose" @pointerdown="backdropDown" @click="backdropClick" @animationend="animationEnded">
    <header class="nte-dialog-head"><div><p>NEVERNESS TO EVERNESS</p><h2 :id="titleId">{{ title }}</h2></div><button type="button" autofocus @click="requestClose">关闭详情</button></header>
    <div class="nte-dialog-body"><slot /></div>
  </dialog>
</template>
<style scoped>
.nte-dialog{position:fixed;inset:0;margin:auto;width:min(1200px,calc(100vw - 40px));max-width:none;max-height:calc(100dvh - 40px);padding:0;border:1px solid var(--border);border-radius:16px;background:var(--bg);color:var(--text);box-shadow:var(--popover-shadow)}.nte-dialog[open]{display:flex;flex-direction:column}.nte-dialog::backdrop{background:var(--scrim);backdrop-filter:blur(5px)}.nte-dialog-head{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:18px 25px;border-bottom:1px solid var(--border);flex-shrink:0}.nte-dialog-head p{font-size:9px;letter-spacing:.14em;color:var(--accent);margin-bottom:6px}.nte-dialog-head h2{font-size:21px}.nte-dialog-head button{padding:8px 12px;background:var(--card-bg);color:var(--text);border:1px solid var(--border);border-radius:7px;cursor:pointer}.nte-dialog-body{padding:22px;overflow-y:auto;overscroll-behavior:contain;min-height:0}.nte-dialog-body :deep(.cap-card){box-shadow:none}.nte-dialog-body :deep(.guides-layout){grid-template-columns:170px minmax(0,1fr)}@media(max-width:650px){.nte-dialog{width:calc(100vw - 16px);max-height:calc(100dvh - 16px)}.nte-dialog-head,.nte-dialog-body{padding:15px}.nte-dialog-body :deep(.guides-layout){grid-template-columns:minmax(0,1fr)}}
</style>
