<script setup>
import {computed} from 'vue'
import CalendarTimelineContent from '../components/CalendarTimelineContent.vue'
import {imageCalendarWindows} from './image-calendar.js'
const props=defineProps({events:Array,snapshots:Object,asOf:Number,full:Boolean})
const windows=computed(()=>imageCalendarWindows(props.events,props.asOf,props.full))
</script>
<template>
 <div class="cloud-calendar">
  <div v-for="(window,i) in windows" class="calendar-window"><h3 class="window-title">{{window.label}}<small>连续时间轴</small></h3><CalendarTimelineContent :events="events" :snapshots="snapshots" :range="window.range" :as-of="asOf" mode="image" :range-mode="full?'version':'fortnight'" :show-unplaced="i===windows.length-1" /></div>
  <CalendarTimelineContent v-if="!windows.length" :events="events" :snapshots="snapshots" :as-of="asOf" mode="image" />
 </div>
</template>
