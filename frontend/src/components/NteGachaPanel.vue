<script setup>
import NteGachaLedger from './NteGachaLedger.vue'
import NteCommunityGacha from './NteCommunityGacha.vue'
import AppIcon from './AppIcon.vue'
import { ref } from 'vue'
defineProps({ snap: { type: Object, default: null }, accountId: { type: String, default: '' }, roles: { type: Array, default: () => [] } })
const ledgerOpen = ref(false)
</script>
<template>
  <div class="nte-gacha-panel"><NteCommunityGacha :snap="snap" :roles="roles" /><details class="community-gacha" @toggle="ledgerOpen = $event.target.open"><summary><span class="ledger-name">本地逐抽账本</span><span class="chip">可选工具</span><AppIcon name="chevron" :size="14" class="t-disclosure" /></summary><NteGachaLedger v-if="ledgerOpen" :account-id="accountId" /></details></div>
</template>
<style scoped>
.nte-gacha-panel { display:grid; gap:12px; min-width:0 }
.community-gacha > summary { display:flex; align-items:center; gap:8px; min-height:40px; padding:8px 14px; border:1px solid var(--border); border-radius:10px; background:var(--card-bg); box-shadow:var(--card-shadow); color:var(--text); font-size:13px; font-weight:600; list-style:none; cursor:pointer }
.community-gacha > summary::-webkit-details-marker { display:none }
.community-gacha > summary > svg { margin-left:auto; color:var(--text-faint) }
.community-gacha[open] > summary { margin-bottom:8px }
@media (hover:hover) and (pointer:fine) { .community-gacha > summary:hover { background:var(--button-hover-bg) } .community-gacha > summary:hover > svg { color:var(--text-body) } }
</style>
