<script setup>
import NteGachaLedger from './NteGachaLedger.vue'
import NteCommunityGacha from './NteCommunityGacha.vue'
import { ref } from 'vue'
defineProps({ snap: { type: Object, default: null }, accountId: { type: String, default: '' }, roles: { type: Array, default: () => [] } })
const ledgerOpen = ref(false)
</script>
<template>
  <div class="nte-gacha-panel"><NteCommunityGacha :snap="snap" :roles="roles" /><details class="community-gacha" @toggle="ledgerOpen = $event.target.open"><summary>可选工具 · 本地逐抽账本</summary><NteGachaLedger v-if="ledgerOpen" :account-id="accountId" /></details></div>
</template>
<style scoped>
.nte-gacha-panel { display:grid;gap:20px;min-width:0 }.community-gacha>summary { cursor:pointer;padding:15px;color:var(--text-muted);font-size:13px;border:1px solid var(--border);border-radius:8px;margin-bottom:12px }
</style>
