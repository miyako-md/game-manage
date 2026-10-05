<script setup>
import { useId } from 'vue'
import { useDialog } from '../use-dialog.js'
import { contentNote } from '../articles.js'
import { formatTime } from '../dashboard.js'
defineProps({ article: { type: Object, required: true } })
const emit = defineEmits(['close']), headingId = `article-${useId()}`
const { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded } = useDialog(() => emit('close'))
</script>
<template>
  <dialog ref="dialog" class="article-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" :aria-labelledby="headingId" @cancel.prevent="requestClose" @pointerdown="backdropDown" @click="backdropClick" @animationend="animationEnded">
    <header class="article-dialog-head"><div><p class="article-kicker">{{ article.categoryLabel }}<span v-if="article.source_name"> · {{ article.source_name }}</span></p><h2 :id="headingId">{{ article.title }}</h2></div><button type="button" class="ui-button" autofocus @click="requestClose">关闭详情</button></header>
    <div class="article-dialog-body">
      <p v-if="article.published_at" class="article-muted">{{ formatTime(article.published_at) }}</p>
      <p v-if="article.source_stale" class="article-note" role="status">来源采集异常或数据可能过期，保留旧记录。</p>
      <p v-if="contentNote(article)" class="article-note" role="status">{{ contentNote(article) }}</p>
      <div v-if="article.tags.length" class="article-tags"><span v-for="tag in article.tags" :key="tag" class="chip">{{ tag }}</span></div>
      <div v-if="article.body && !['video', 'external'].includes(article.content_status)" class="article-body">{{ article.body }}</div>
      <p v-else-if="article.excerpt" class="article-body">{{ article.excerpt }}</p>
      <div v-if="article.images.length && !['video', 'external'].includes(article.content_status)" class="article-images"><img v-for="(url, index) in article.images" :key="url" :src="url" :alt="`${article.title} · 原文图片 ${index + 1}`" loading="lazy" referrerpolicy="no-referrer" /></div>
      <footer class="article-links"><a v-for="(link, index) in article.links" :key="link.url" :href="link.url" target="_blank" rel="noopener noreferrer">{{ index === 0 ? '查看原文 ↗' : `其他来源 · ${link.name} ↗` }}</a><span v-if="!article.links.length" class="article-muted">来源未提供有效原文链接</span></footer>
    </div>
  </dialog>
</template>
<style scoped>
.article-dialog{position:fixed;inset:0;margin:auto;width:min(920px,calc(100vw - 40px));max-width:none;max-height:calc(100dvh - 40px);padding:0;border:1px solid var(--border-strong);border-radius:12px;background:var(--card-bg);color:var(--text);box-shadow:var(--popover-shadow)}.article-dialog[open]{display:flex;flex-direction:column}.article-dialog::backdrop{background:var(--scrim);backdrop-filter:blur(5px)}.article-dialog-head{display:flex;justify-content:space-between;align-items:start;gap:20px;padding:22px 26px;border-bottom:1px solid var(--border);flex-shrink:0}.article-dialog-head h2{font-size:20px;line-height:1.5;overflow-wrap:anywhere;margin-top:6px}.article-dialog-head button{flex-shrink:0}.article-kicker,.article-muted{font-size:12px;color:var(--text-muted);line-height:1.6}.article-dialog-body{overflow-y:auto;overscroll-behavior:contain;min-height:0;padding:22px 26px}.article-body{white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px;line-height:1.95;margin-top:20px}.article-note{font-size:12px;line-height:1.7;padding:10px 12px;background:var(--accent-soft);border-left:2px solid var(--accent);margin-top:12px}.article-tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}.article-images{display:grid;gap:14px;margin-top:20px}.article-images img{display:block;max-width:100%;height:auto;border-radius:6px}.article-links{display:flex;flex-wrap:wrap;gap:12px;margin-top:24px;padding-top:18px;border-top:1px solid var(--border)}.article-links a{font-size:13px;color:var(--accent);text-decoration:none}.article-links a:hover{text-decoration:underline}@media(max-width:640px){.article-dialog{width:calc(100vw - 16px);max-height:calc(100dvh - 16px)}.article-dialog-head,.article-dialog-body{padding:16px}.article-dialog-head h2{font-size:17px}.article-dialog-head{gap:12px}}
</style>
