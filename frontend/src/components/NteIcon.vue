<script setup>
import { computed, ref, watch } from 'vue'
import { safeNteIcon } from '../nte-icons.js'
const props=defineProps({src:{type:String,default:''},name:{type:String,default:''},size:{type:String,default:'medium'}})
const failed=ref(false),url=computed(()=>safeNteIcon(props.src))
watch(url,()=>{failed.value=false})
</script>
<template><span class="nte-icon" :data-size="size" :title="name"><img v-if="url && !failed" :src="url" :alt="name" loading="lazy" referrerpolicy="no-referrer" @error="failed = true" /><span v-else class="icon-fallback" aria-hidden="true">{{ name.slice(0,2) || '?' }}</span></span></template>
<style scoped>
.nte-icon{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;width:38px;height:42px;overflow:hidden;border-radius:7px;background:var(--accent-soft);border:1px solid var(--border);vertical-align:middle}.nte-icon img{width:100%;height:100%;object-fit:contain}.icon-fallback{font-size:11px;color:var(--accent);line-height:1}.nte-icon[data-size=small]{width:28px;height:30px;border-radius:5px}.nte-icon[data-size=large]{width:54px;height:60px}.nte-icon[data-size=skill]{width:36px;height:36px;background:var(--surface-soft)}
</style>
