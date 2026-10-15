<script setup>
import { computed, provide } from 'vue'
import { cloudGameView } from '../cloud-view-model.js'
import GameCard from './GameCard.vue'
import CloudSnapshotStatus from './CloudSnapshotStatus.vue'
const props = defineProps({ account: {type:Object,required:true}, role: {type:String,required:true}, userId: {type:String,default:''}, snapshots: {type:Object,default:()=>({})}, publicSnapshots: {type:Object,default:()=>({})}, refreshing: Boolean, isAdmin: Boolean, initialSection:{type:String,default:'overview'}, showSnapshotStatus:{type:Boolean,default:true} })
const emit = defineEmits(['calendar','refresh'])
provide('cloudPermissions', computed(()=>({isAdmin:props.isAdmin})))
const view = computed(()=>cloudGameView(props.account,props.snapshots,props.publicSnapshots))
const scope = computed(()=>({user_id:props.userId,account_id:props.account.account_id,role_id:props.role,provider:props.account.provider}))
</script>
<template>
  <p v-if="!view.caps.length" class="cap-card">此授权尚未提供云端数据能力，请在账号设置检查授权状态。</p>
  <template v-else><GameCard :game="view.game" :collection-status="view.collection" :external-snapshots="view.snapshots" :external-refreshing="refreshing" :cloud-account="account" :cloud-role="role" :cloud-scope="scope" :is-admin="isAdmin" :initial-section="initialSection" @calendar="emit('calendar')" @refresh="emit('refresh')" /><CloudSnapshotStatus v-if="showSnapshotStatus" :snapshots="view.snapshots" :capabilities="view.game.capabilities" /></template>
</template>
