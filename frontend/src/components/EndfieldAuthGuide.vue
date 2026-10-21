<script setup>
import { computed } from 'vue'
import AppIcon from './AppIcon.vue'
import { endfieldProviderLabel, endfieldSourceLabel } from '../endfield-accounts.js'

// Cloud only. Says which authorization this page lacks and what it unlocks; with several
// unpaired entries of that provider it asks for a choice instead of guessing one.
const props = defineProps({ need: { type: String, required: true }, passport: Boolean, candidates: { type: Array, default: () => [] } })
const UNLOCKS = { skland: '概览档案、全员练度、地区建设、帝江号、光荣之路、挑战记录和蓝图收藏', hypergryph: '寻访抽卡统计' }
const label = computed(() => endfieldProviderLabel(props.need))
const ambiguous = computed(() => props.candidates.length > 1)
const oneClick = computed(() => props.need === 'skland' && props.passport)
const href = computed(() => props.need === 'skland' ? '#/accounts?focus=skland' : '#/accounts')
</script>

<template>
  <section class="cap-card ef-auth-guide" aria-label="终末地授权引导">
    <template v-if="ambiguous">
      <div class="cap-title"><AppIcon name="user" :size="16" />请选择对应角色</div>
      <p>当前角色没有已配对的{{ label }}，而{{ label }}有多个入口，无法判断哪一个是同一角色。请在“查看角色”中选择对应角色：</p>
      <ul class="ef-auth-candidates"><li v-for="choice in candidates" :key="choice.key">{{ endfieldSourceLabel(choice) }} · {{ endfieldProviderLabel(choice.account.provider) }}</li></ul>
    </template>
    <template v-else>
      <div class="cap-title"><AppIcon name="shield" :size="16" />需要补授权：{{ label }}</div>
      <p>当前角色尚未连接{{ label }}。补上后可查看{{ UNLOCKS[need] }}。</p>
      <p v-if="oneClick" class="hint">已有鹰角授权，可在「账号与授权」的森空岛档案授权中选择此角色一键连接。</p>
      <a class="ui-button" :class="{ primary: oneClick }" :href="href">{{ oneClick ? '一键连接森空岛档案' : '前往账号与授权' }}<AppIcon name="arrow" :size="14" /></a>
    </template>
  </section>
</template>

<style scoped>
.ef-auth-guide { display:grid; gap:10px; justify-items:start; }
.ef-auth-guide p { margin:0; line-height:1.6; }
.ef-auth-guide .cap-title { display:flex; align-items:center; gap:8px; }
.ef-auth-candidates { display:grid; gap:6px; margin:0; padding-left:20px; }
</style>
