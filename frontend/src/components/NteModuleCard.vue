<script setup>
import { computed, ref, watch } from 'vue'
import { nteModuleMetrics, nteModuleTitles } from '../nte-modules.js'
import { displayBeijing } from '../time.js'
import NteDetailDialog from './NteDetailDialog.vue'
import AppIcon from './AppIcon.vue'
import NteIcon from './NteIcon.vue'
import { nteRoleIcon } from '../nte-icons.js'
import SummaryMetrics from './SummaryMetrics.vue'
const props=defineProps({capability:{type:String,required:true},snap:{default:null},accountId:{type:String,default:''}})
const opened=ref(false),title=computed(()=>nteModuleTitles[props.capability]||props.capability)
const metrics=computed(()=>nteModuleMetrics(props.capability,props.snap))
const inline=computed(()=>['stamina','record'].includes(props.capability))
const error=computed(()=>props.snap?.error||props.snap?.source_status?.error)
const readAt=computed(()=>props.capability==='stamina' ? props.snap?.payload?.updated_at || props.snap?.fetched_at : props.snap?.fetched_at)
const previews=computed(()=>props.capability==='guides' ? ['黑羽','残虹','灵可','伊洛伊','娜娜莉'].map(name=>({name,icon:nteRoleIcon(name)}))
  : props.capability==='roles' && props.snap?.payload?.schema_version===1 ? (props.snap.payload.entries || []).slice(0,8).map(role=>({name:role.name,icon:nteRoleIcon(role.id)})) : [])
watch(()=>props.accountId,()=>{opened.value=false})
watch(()=>props.capability,()=>{opened.value=false})
</script>
<template>
  <section class="nte-module-card" :class="`module-${capability}`">
    <header><span class="module-mark"><AppIcon :name="capability === 'roles' || capability === 'account' ? 'user' : capability === 'gacha' ? 'spark' : capability === 'guides' ? 'menu' : 'grid'" :size="22" /></span><h2>{{ title }}</h2><button v-if="!inline" type="button" @click="opened = true">查看{{ title }}</button></header>
    <div v-if="capability === 'record'" class="inline-content"><slot /></div>
    <SummaryMetrics v-else-if="metrics.length" :metrics="metrics" :compact="!inline" />
    <p v-else class="module-state">{{ snap?.payload && snap.payload.schema_version !== 1 ? '数据格式已更新，请刷新' : '暂无数据，请登录后刷新' }}</p>
    <template v-if="capability === 'stamina'">
      <p class="source-note">来源：塔吉多角色面板。体力和都市活力可能延迟或不准确，请以游戏内为准。</p>
      <p class="module-state">周本剩余 · {{ snap?.payload?.schema_version === 1 ? snap.payload.weekly_remaining ?? '未提供' : '未提供' }}</p>
    </template>
    <slot name="preview" />
    <div v-if="previews.length" class="module-previews"><span v-for="(role,index) in previews" :key="index"><NteIcon :src="role.icon" :name="role.name || '角色'" /><small>{{ role.name }}</small></span></div>
    <p v-if="error" class="module-error" role="status">{{ error }}</p>
    <footer><span v-if="snap?.stale" class="old">旧数据</span><span v-if="readAt">{{ displayBeijing(readAt) }}</span><span v-else-if="capability === 'guides' || capability === 'teams'">公开资料</span></footer>
    <NteDetailDialog v-if="!inline && opened" :title="title" @close="opened = false"><slot /></NteDetailDialog>
  </section>
</template>
<style scoped>
.module-account,.module-stamina{grid-column:1/-1}
.inline-content :deep(.cap-card){padding:0;border:0;background:none;box-shadow:none;margin-top:16px}
.inline-content :deep(.cap-title),.inline-content :deep(.fetched-at){display:none}
.source-note{margin-top:15px;padding:10px 12px;border-left:2px solid var(--accent);background:var(--accent-dim);font-size:11px;color:var(--text-muted);line-height:1.8}.module-state{margin-top:12px}
.module-previews{display:flex;flex-wrap:wrap;gap:10px;margin-top:17px}.module-previews>span{display:grid;justify-items:center;gap:5px}.module-previews small{font-size:10px;color:var(--text-muted);max-width:55px;text-align:center}
.nte-module-card{min-width:0;padding:23px;border:1px solid var(--border);background:var(--card-bg);border-radius:12px}.nte-module-card>header{display:flex;align-items:center;gap:11px}.module-mark{display:grid;place-items:center;width:39px;height:42px;border-radius:9px;border:1px solid var(--border);color:var(--accent);background:var(--accent-dim)}.nte-module-card h2{font-size:17px;font-weight:550}.nte-module-card>header>button{margin-left:auto;cursor:pointer;padding:8px 10px;border:1px solid var(--border);background:transparent;border-radius:7px;color:var(--accent);font:inherit;font-size:12px}.module-metrics{display:flex;gap:22px;flex-wrap:wrap;margin:24px 0 15px}.module-metrics>div{display:grid;gap:9px;min-width:75px}.module-metrics span,.module-state{font-size:11px;color:var(--text-muted)}.module-metrics strong{font-size:20px;font-weight:550;overflow-wrap:anywhere}.module-error{color:var(--danger);font-size:12px;line-height:1.7;margin-top:10px}.nte-module-card footer{display:flex;gap:10px;color:var(--text-muted);font-size:10px;min-height:12px;margin-top:17px}.old{color:var(--accent)}@media(max-width:650px){.nte-module-card{padding:17px}.nte-module-card>header{flex-wrap:wrap}.nte-module-card h2{font-size:15px}.module-metrics{gap:16px}}
</style>
