<script setup>
import { computed, ref, watch } from 'vue'
import { formatTime } from '../dashboard.js'
import { ARTICLE_CATEGORIES, prepareArticles, contentNote } from '../articles.js'
import ArticleDetailDialog from './ArticleDetailDialog.vue'
const props = defineProps({ snap: { type: Object, default: null }, extraSnaps: { type: Array, default: () => [] }, capability: { type: String, default: 'news' }, gameId: { type: String, default: '' } })
const category = ref('all'), selectedKey = ref('')
const snapshots = computed(() => [props.snap, ...props.extraSnaps].filter(Boolean))
const rows = computed(() => prepareArticles(snapshots.value))
const selected = computed(() => rows.value.find(row => row.key === selectedKey.value))
const categories = computed(() => ARTICLE_CATEGORIES.map(rule => ({ ...rule, count: rows.value.filter(row => row.categoryId === rule.id).length })).filter(rule => rule.count))
const filtered = computed(() => category.value === 'all' ? rows.value : rows.value.filter(row => row.categoryId === category.value))
const stale = computed(() => snapshots.value.some(snap => snap.stale))
const errors = computed(() => [...new Set(snapshots.value.map(snap => snap.error || snap.poll_status?.error).filter(error => typeof error === 'string' && error))])
const fetchedAt = computed(() => snapshots.value.map(snap => snap.fetched_at).filter(Boolean).sort().at(-1))
function date(value) { return value ? formatTime(value, { hour: undefined, minute: undefined }) : '' }
watch(categories, value => { if (category.value !== 'all' && !value.some(item => item.id === category.value)) category.value = 'all' })
watch(() => props.gameId, () => { selectedKey.value = ''; category.value = 'all' })
</script>
<template>
  <section class="cap-card article-list">
    <div class="cap-title article-heading"><h2>公告与资讯</h2><span v-if="stale" class="badge badge-stale">数据可能过期</span><span v-if="fetchedAt" class="cap-meta">更新于 {{ formatTime(fetchedAt) }}</span><slot name="actions" /></div>
    <p v-for="error in errors" :key="error" class="article-error" role="status">{{ error }}</p>
    <nav v-if="rows.length" class="article-filters" aria-label="文章内容分类"><button type="button" :aria-pressed="category === 'all'" @click="category = 'all'">全部 <span>{{ rows.length }}</span></button><button v-for="item in categories" :key="item.id" type="button" :aria-pressed="category === item.id" @click="category = item.id">{{ item.label }} <span>{{ item.count }}</span></button></nav>
    <p v-if="!rows.length" class="empty">暂无公告与资讯</p>
    <ul v-else class="item-list">
      <li v-for="it in filtered" :key="it.key" class="item">
        <p class="item-title"><button type="button" class="item-link" @click="selectedKey = it.key">{{ it.title }}</button></p>
        <p class="item-meta"><span class="chip article-category">{{ it.categoryLabel }}</span><span v-if="it.source_name" class="item-source">{{ it.source_name }}</span><span v-if="it.source_stale" class="badge badge-stale">来源采集异常，保留旧记录</span><span v-if="date(it.published_at)" class="item-date">{{ date(it.published_at) }}</span></p>
        <p v-if="it.excerpt" class="item-summary">{{ it.excerpt }}</p><p v-else class="item-summary article-missing">{{ contentNote(it) || '正文仅包含图片，点击查看详情。' }}</p>
        <div v-if="it.tags.length" class="item-tags"><span v-for="tag in it.tags" :key="tag" class="chip">{{ tag }}</span></div>
        <div class="item-actions"><button type="button" @click="selectedKey = it.key">查看详情</button><a v-if="it.url" :href="it.url" target="_blank" rel="noopener noreferrer">原文 ↗</a></div>
      </li>
    </ul>
    <ArticleDetailDialog v-if="selected" :key="selected.key" :article="selected" @close="selectedKey = ''" />
  </section>
</template>
<style scoped>
.article-list{min-width:0}.article-heading{flex-wrap:wrap;gap:8px}.article-heading h2{font-size:14px;font-weight:600;margin:0}.article-heading .cap-meta{margin-left:auto}.article-filters{display:flex;flex-wrap:wrap;gap:6px;margin:16px 0 6px}.article-filters button{font:inherit;font-size:12px;border:1px solid var(--border);border-radius:6px;padding:6px 10px;background:var(--card-bg);color:var(--text-muted);cursor:pointer}.article-filters button[aria-pressed=true]{color:var(--accent);background:var(--accent-soft);border-color:var(--accent)}.article-filters button span{font-size:10px;opacity:.75;margin-left:4px}.item-list{display:flex;flex-direction:column}.item{padding:18px 0;border-bottom:1px solid var(--border)}.item:last-child{border-bottom:0;padding-bottom:0}.item-title{margin:0;font-size:14px;font-weight:550;line-height:1.6}.item-link{padding:0;border:0;background:none;text-align:left;color:var(--text);font:inherit;cursor:pointer;overflow-wrap:anywhere}.item-link:hover{color:var(--accent)}.item-meta{display:flex;align-items:center;flex-wrap:wrap;gap:7px;margin:8px 0 0}.item-source,.item-date{font-size:11px;color:var(--text-muted)}.item-date{margin-left:auto}.item-summary{margin:10px 0 0;font-size:12px;line-height:1.8;color:var(--text-muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.item-tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:9px}.item-tags .chip{font-size:10px;background:var(--panel-bg);color:var(--text-muted)}.item-actions{display:flex;align-items:center;gap:16px;margin-top:12px}.item-actions button,.item-actions a{border:0;background:none;padding:0;font:inherit;font-size:12px;color:var(--accent);cursor:pointer;text-decoration:none}.item-actions button:hover,.item-actions a:hover{text-decoration:underline}.article-error{font-size:12px;color:var(--danger);line-height:1.7;margin-top:10px}.article-list :focus-visible{outline:2px solid var(--accent);outline-offset:3px;border-radius:3px}.article-missing{font-size:11px}@media(max-width:600px){.item-date{margin-left:0}.article-heading .cap-meta{margin-left:0}.item{padding:16px 0}}
</style>