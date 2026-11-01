<script setup>
import { formatBeijingDateTime, formatBrowserDateTime, browserCalendarBoundary, safeUrl } from '../calendar.js'
import { gameStyle } from '../dashboard.js'

const props = defineProps({ calendars:{type:Array,default:()=>[]}, mode:{type:String,default:'screen'} })
const formatTime = value => (props.mode === 'image' ? formatBeijingDateTime : formatBrowserDateTime)(value)
function versionBoundary(version,side) {
  if (!version[side+'_at'] && !version[side+'_date']) return '未知'
  return props.mode === 'image' ? version[side+'_at'] ? formatBeijingDateTime(version[side+'_at']) : version[side+'_date'] : browserCalendarBoundary(version,side,true)
}
const gameAccent = id => gameStyle(id).color
const versionLabel = version => version.id ? `${version.id}版本活动` : '已公布活动'
function sources(calendar) {
  const seen = new Map()
  for (const event of calendar.events) {
    const key = [event.source_name,event.source_title,event.source_url].join('|')
    if (!seen.has(key)) seen.set(key,{key,name:event.source_name||'来源',title:event.source_title||'来源未提供',url:safeUrl(event.source_url),stale:event.stale,fetchedAt:event.fetchedAt})
  }
  return [...seen.values()]
}
</script>
<template>
  <section v-for="calendar in calendars" :key="calendar.key" class="version-metadata" :style="{'--game-accent':gameAccent(calendar.gameId)}">
    <h3>{{ calendar.gameName }} · {{ versionLabel(calendar.version) }}</h3>
    <p>版本开放：{{ versionBoundary(calendar.version,'start') }}；版本结束：{{ versionBoundary(calendar.version,'end') }}</p>
    <p>{{ calendar.version.source_stale ? '数据可能过期。' : '' }}{{ calendar.version.coverage === 'partial' ? '部分来源不可用。' : '' }}</p>
    <p v-for="diagnostic in calendar.version.diagnostics || []" :key="diagnostic">{{ diagnostic.replace('有界来源列表可能遗漏公告', '公告列表可能遗漏补充内容') }}</p>
    <div class="version-sources"><strong>来源与读取状态</strong><p v-for="source in sources(calendar)" :key="source.key"><strong>{{ source.name }}</strong> · <a v-if="source.url" :href="source.url" target="_blank" rel="noopener noreferrer">{{ source.title }}</a><span v-else>{{ source.title }}</span>{{ source.stale ? ' · 数据可能过期' : '' }} · 更新于 {{ formatTime(source.fetchedAt) }}</p></div>
  </section>
</template>
<style scoped>
.version-metadata { margin:12px 0; line-height:1.7; }
.version-metadata h3 { color:var(--game-accent); font-size:inherit; font-weight:500; }
.version-metadata p { margin:5px 0; overflow-wrap:anywhere; }
.version-sources { margin:8px 0; }
.version-sources a { color:var(--accent); }
</style>
