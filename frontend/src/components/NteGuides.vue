<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getGuideCatalog, getGuideSource, safeGuideUrl } from '../nte-guides-api.js'
import { displayBeijing } from '../time.js'
import { friendlyDataError } from '../cloud-display.js'
import NteIcon from './NteIcon.vue'
import NteGuideVisual from './NteGuideVisual.vue'
import { nteRoleIcon } from '../nte-icons.js'
import { filterGuides,guideForCharacter,ownedGuideRoles } from '../guide-search.js'
import { characterId as entryCharacterId, characterLabel, normalizeSearch } from '../character-search.js'

const props = defineProps({ canMaintain: {type:Boolean,default:true}, roles: { type: Array, default: () => [] }, characterId: {type:String,default:''} })
const emit=defineEmits(['role'])
const targetId=ref(props.characterId)
watch(()=>props.characterId,id=>{targetId.value=id})
function selectGuide(id){targetId.value='';selected.value=id}
const catalog = ref(null), selected = ref('黑羽'), search = ref(''), ownedOnly = ref(false)
const catalogLoading = ref(true), catalogError = ref(''), source = ref(null), sourceLoading = ref(false), sourceError = ref('')
const page = ref(1), imageFailed = ref(false)
const sourcePanel = ref(null), roleList = ref(null)
let requestId = 0, disposed = false, sourceController = null
const catalogController = new AbortController()
const isOwned = guide => ownedGuideRoles('nte',guide,props.roles).length>0
const guides = computed(() => filterGuides('nte',(catalog.value?.guides || []).filter(guide => !ownedOnly.value || isOwned(guide)),search.value))
const guide = computed(() => targetId.value ? guideForCharacter('nte',guides.value,targetId.value) : guides.value.find(item => item.id === selected.value) || (!normalizeSearch(search.value) ? guides.value[0] : null))
const owned = computed(() => guide.value ? ownedGuideRoles('nte',guide.value,props.roles) : [])
const sourceMeta = computed(() => catalog.value?.sources?.find(item => item.id === guide.value?.source_id))
const currentImage = computed(() => safeGuideUrl(source.value?.images?.[page.value - 1], true))
const totalImages = computed(() => source.value?.images?.length || 0)
const reviewedCount = computed(() => catalog.value?.guides?.filter(item => item.status === 'reviewed').length || 0)
const originalLink = computed(() => safeGuideUrl(sourceMeta.value?.url))
const date = value => value ? displayBeijing(value) : '未提供'
// A role found only through the author's new post has no element or position yet.
const roleMeta = item => item.discovered ? '新帖 · 仅原图' : `${item.element} · ${item.role}`
const newerLink = computed(() => safeGuideUrl(guide.value?.newer_source?.url))

async function loadCatalog() {
  catalogLoading.value = true; catalogError.value = ''
  try {
    const value = await getGuideCatalog(catalogController.signal)
    if (!disposed) catalog.value = value
  } catch (error) { if (!disposed && error.name !== 'AbortError') catalogError.value = error.message }
  finally { if (!disposed) catalogLoading.value = false }
}
async function loadSource(refresh = false) {
  const id = guide.value?.source_id, seq = ++requestId
  sourceController?.abort(); sourceController = new AbortController()
  if (!id) { source.value = null; sourceLoading.value = false; return }
  sourceLoading.value = true; sourceError.value = ''
  try {
    const value = await getGuideSource(id, refresh, sourceController.signal)
    if (disposed || seq !== requestId) return
    source.value = value
    if (page.value > value.images?.length) page.value = Math.max(1, value.images?.length || 1)
  } catch (error) { if (!disposed && seq === requestId && error.name !== 'AbortError') sourceError.value = error.message }
  finally { if (!disposed && seq === requestId) sourceLoading.value = false }
}
watch(() => guide.value?.source_id, () => { source.value = null; sourceError.value = ''; loadSource() })
watch(() => guide.value?.id, () => { page.value = guide.value?.pages?.[0] || 1 })
watch(currentImage, () => { imageFailed.value = false })
// The roles form one row; the chosen one stays in view when a link from the roster opens its guide.
watch(() => guide.value?.id, async () => { await nextTick(); roleList.value?.querySelector?.('[aria-pressed="true"]')?.scrollIntoView?.({ inline: 'center', block: 'nearest' }) })
async function showPage(value) { page.value = value; await nextTick(); sourcePanel.value?.scrollIntoView?.({ behavior:'smooth', block:'start' }) }
onMounted(loadCatalog)
onBeforeUnmount(() => { disposed = true; requestId++; sourceController?.abort(); catalogController.abort() })
</script>

<template>
  <section class="nte-guides" aria-label="异环角色攻略">
    <header class="guides-head"><div><h2>角色攻略</h2></div><span v-if="catalog" class="catalog-count">{{ catalog.guides.length }} 名角色原图索引 <b>{{ reviewedCount }} 名已整理摘要</b></span></header>
    <p v-if="catalogLoading" class="notice" role="status">正在加载攻略目录…</p>
    <div v-else-if="catalogError" class="notice error" role="alert">{{ catalogError }} <button type="button" class="ui-button small-button" @click="loadCatalog">重试</button></div>
    <template v-else-if="catalog">
      <div class="guides-filters"><label class="search-label">查找角色<input v-model="search" type="search" placeholder="名称、别名、拼音、首字母、属性或定位" /></label><label><input v-model="ownedOnly" type="checkbox" />只看已拥有</label><span class="muted">{{ guides.length }} 名角色</span></div>
      <p v-if="targetId && !guide" class="notice">未找到该角色形态的已确认攻略，不套用同名或其他形态资料。<button type="button" class="ui-button small-button" @click="targetId=''">浏览公开攻略</button></p>
      <p v-if="ownedOnly && !roles.length" class="notice">尚无角色资料，可关闭“只看已拥有”浏览公开攻略，或登录并刷新角色数据。</p>
      <p v-else-if="!guides.length" class="notice">没有匹配的角色，试试其他关键词。</p>
      <nav v-if="!guide && guides.length && !targetId" class="role-list" aria-label="攻略角色候选"><button v-for="item in guides" :key="item.id" :aria-label="`查看${item.name}攻略`" @click="selectGuide(item.id)">{{ item.name }}</button></nav>
      <div v-if="guide" class="guides-layout">
        <p class="muted">完整目录 {{ catalog.guides.length }} 名 · {{ reviewedCount }} 名完整摘要；可搜索角色或横向滚动目录。</p><nav ref="roleList" class="role-list" aria-label="攻略角色列表"><button v-for="item in guides" :key="item.id" :aria-pressed="guide.id === item.id" :aria-label="`查看${item.name}攻略`" @click="selectGuide(item.id)"><NteIcon :src="nteRoleIcon(item.name)" :name="item.name" /><span><strong>{{ item.name }}</strong><small>{{ roleMeta(item) }}</small></span><span class="guide-dot" :class="{ reviewed:item.status === 'reviewed' }" :title="item.status === 'reviewed' ? '已整理摘要' : '原图索引'" /></button></nav>
        <div class="guide-main">
          <button v-for="role in owned" :key="entryCharacterId(role)" type="button" class="ui-button soft small-button" :aria-label="`查看本人${characterLabel('nte',role)}`" @click="emit('role',entryCharacterId(role))">查看本人 {{ characterLabel('nte',role) }} 面板</button>
          <header class="role-heading"><NteIcon :src="nteRoleIcon(guide.name)" :name="guide.name" size="xl" /><div><p class="kicker">{{ roleMeta(guide) }}</p><h3>{{ guide.name }} <span>培养攻略</span></h3></div><span class="version">V{{ sourceMeta?.version || '未知' }} 资料</span></header>
          <p class="provenance">{{ sourceMeta?.author }}</p>
          <details data-render-collapsed><summary>资料详情</summary><p v-if="guide.reviewed_at">摘要核对于 {{ guide.reviewed_at }}</p>
          <p v-if="source?.summary_changed" class="notice warning" role="status">原帖有更新，文字摘要待复核；以下为此前核对内容，请优先查看最新原图。</p>
          <p v-if="sourceError || source?.error" class="notice warning" role="alert">{{ friendlyDataError(sourceError || source.error) }}</p>
          <p v-else-if="sourceLoading" class="source-status" role="status">正在核对原帖与图片…</p>
          <p v-else-if="source?.stale" class="source-status">当前展示旧版缓存资料。</p></details>
          <p v-if="guide.newer_source" class="notice warning" role="status">作者已发布更新版本：<a v-if="newerLink" :href="newerLink" target="_blank" rel="noopener noreferrer">{{ guide.newer_source.title }} ↗</a><span v-else>{{ guide.newer_source.title }}</span>（发布 {{ date(guide.newer_source.published_at) }}，北京时间）；以下摘要仍按旧版原图整理。</p>
          <p v-if="guide.discovered" class="notice">这是作者新发布的攻略帖，文字推荐尚未整理，请直接查看下方原图（共 {{ guide.pages.length }} 页）。</p>
          <p v-else-if="guide.status === 'original_only'" class="notice">{{ guide.partial_reviewed_at ? '部分文字已核对，完整推荐待整理。' : '文字推荐待整理。' }}已定位到原图第 {{ guide.pages.join('、') }} 页，可查看该角色的五类配装信息。{{ guide.gap_note }}<span v-if="guide.partial_reviewed_at">部分核对：{{ guide.partial_reviewed_at }}</span></p>
          <div v-if="guide.status === 'reviewed' || guide.sections?.some(section=>section.items.length)" class="advice-grid"><article v-for="(section, index) in guide.sections" :key="section.key" class="advice-card"><header><h4>{{ section.title }}</h4></header><ul v-if="section.items.length"><li v-for="(item, i) in section.items" :key="i"><NteGuideVisual :text="item" :section-key="section.key" :role-name="guide.name" /></li></ul><p v-else class="muted">暂无已整理的文字推荐</p><details v-if="section.note" class="section-note"><summary>适用条件与说明</summary><p>{{ section.note }}</p></details><button type="button" class="text-link" :disabled="sourceLoading || !source || !section.pages.some(n => n <= totalImages)" @click="showPage(section.pages[0])">查看对应原图 · 第 {{ section.pages.join('、') }} 页 ↗</button></article></div>
          <section ref="sourcePanel" class="source-card" aria-label="攻略原图与来源"><header><div><h4>原图与来源</h4><a v-if="originalLink" :href="originalLink" target="_blank" rel="noopener noreferrer">{{ sourceMeta.title }} ↗</a></div><button v-if="canMaintain" type="button" class="ui-button small-button" :disabled="sourceLoading" @click="loadSource(true)">{{ sourceLoading ? '读取中…' : '刷新原帖' }}</button></header>
            <p class="muted">更新于 {{ date(source?.fetched_at) }}（北京时间）<span v-if="source?.published_at"> · 发布：{{ date(source.published_at) }}（北京时间）</span><span v-if="source?.edited_at"> · 编辑：{{ date(source.edited_at) }}（北京时间）</span></p>
            <p v-if="source?.refresh_deferred" class="muted">刚刚已尝试刷新，请稍后重试。</p>
            <template v-if="totalImages"><div class="image-toolbar"><span>原图第 {{ page }} / {{ totalImages }} 页</span><nav class="segmented" aria-label="原图页码"><button v-for="n in totalImages" :key="n" type="button" :aria-pressed="page === n" :aria-label="`查看原图第${n}页`" @click="showPage(n)">{{ n }}</button></nav><a v-if="currentImage" :href="currentImage" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">新窗口查看大图 ↗</a></div>
              <p class="image-caption">{{ sourceMeta.author }} 原作 · 保留署名与水印 · {{ guide.name }} 对应第 {{ guide.pages.join('、') }} 页</p>
              <img v-if="currentImage && !imageFailed" class="guide-image" :src="currentImage" :alt="`${sourceMeta.title} 第 ${page} 页`" loading="lazy" referrerpolicy="no-referrer" @error="imageFailed = true" />
              <p v-else class="notice">原图暂时无法显示，请通过来源链接查看。</p>
            </template><p v-else-if="!sourceLoading" class="muted">原图尚未取得，可重试或打开原帖。</p>
            <details v-if="source?.paragraphs?.length" class="original-text"><summary>查看原帖文字</summary><p v-for="(paragraph,i) in source.paragraphs" :key="i">{{ paragraph }}</p></details>
          </section>
        </div>
      </div>
    </template>
  </section>
</template>

<style scoped>
/* Only ever shown inside the detail sheet, so its layout answers to the sheet's width (container
   queries), not the window's. */
.nte-guides { container-type:inline-size; color:var(--text); min-width:0; }
.guides-head { display:flex; align-items:center; justify-content:flex-start; padding:0 0 16px; }
.kicker { color:var(--accent); font-size:12px; margin:0 0 4px; font-weight:500; }
/* The sheet's header already says 角色攻略; the heading stays for screen readers only. */
.guides-head h2 { position:absolute; width:1px; height:1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; }
.muted, .provenance, .source-status { color:var(--text-muted); font-size:12px; line-height:1.8; }
.catalog-count { font-size:12px; color:var(--text-muted); }
.catalog-count b { display:block; color:var(--accent); font-weight:500; margin-top:2px; }
.guides-filters { display:flex; align-items:center; gap:12px 20px; flex-wrap:wrap; margin-bottom:16px; font-size:13px; }
.guides-filters label { display:flex; align-items:center; gap:9px; }
.search-label { flex:1; min-width:240px; }
.search-label input { flex:1; max-width:360px; min-height:38px; background:var(--card-bg); border:1px solid var(--border); border-radius:var(--radius-control); padding:7px 13px; font:inherit; font-size:13px; color:var(--text); }
.guides-filters input[type=checkbox] { accent-color:var(--accent); }
.guides-layout { display:grid; grid-template-columns:minmax(0,1fr); gap:18px; align-items:start; }
/* The roles are one scrolling row of portrait tiles; the chosen one is filled with the tone. */
.role-list { display:flex; gap:10px; overflow-x:auto; overscroll-behavior-x:contain; scroll-snap-type:x proximity; padding:6px 4px 12px; margin:0 -4px; scrollbar-width:thin; }
.role-list::-webkit-scrollbar { height:6px; }.role-list::-webkit-scrollbar-thumb{background:var(--border-strong);border-radius:4px}
.role-list button { position:relative; flex:0 0 auto; display:grid; justify-items:center; align-content:start; gap:8px; width:100px; padding:14px 6px 12px; border:0; border-radius:var(--radius-tile); background:var(--surface-soft); box-shadow:inset 0 0 0 1px var(--overlay-2); color:var(--text); text-align:center; cursor:pointer; scroll-snap-align:start; }
.role-list .nte-icon { --size:56px; }
.role-list strong { display:block; max-width:88px; overflow:hidden; font-size:13px; font-weight:600; text-overflow:ellipsis; white-space:nowrap; }
.role-list small { display:block; max-width:88px; margin-top:2px; overflow:hidden; color:var(--text-muted); font-size:12px; text-overflow:ellipsis; white-space:nowrap; }
.role-list button[aria-pressed=true] { background:var(--game-tone); box-shadow:none; }
.role-list button[aria-pressed=true] .nte-icon { background:var(--card-bg); }
.role-list button[aria-pressed=true] small { color:var(--game-accent); }
@media(hover:hover) and (pointer:fine) { .role-list button:not([aria-pressed=true]):hover { box-shadow:inset 0 0 0 1px var(--border-strong); } }
.role-list button:active { transform:translateY(1px); }
.guide-dot { position:absolute; top:10px; right:10px; width:7px; height:7px; border-radius:50%; background:var(--border-strong); flex-shrink:0; }
.guide-dot.reviewed { background:var(--game-vivid); }
.role-list button[aria-pressed=true] .guide-dot.reviewed { background:var(--game-accent); }
/* Before one is chosen, the matches are plain buttons. */
.nte-guides > .role-list { flex-wrap:wrap; overflow:visible; padding:0; margin:0 0 14px; }
.nte-guides > .role-list button { width:auto; padding:6px 14px; border:1px solid var(--border); border-radius:var(--radius-control); background:var(--card-bg); box-shadow:none; font-size:13px; }
.guide-main { min-width:0; }
.guide-main > .ui-button { margin:0 8px 12px 0; }
.role-heading { display:flex; gap:16px; align-items:center; padding:16px 18px; border-radius:var(--radius-tile); background:var(--game-tone); }
.role-heading .nte-icon { background:var(--card-bg); }
.role-heading > div { min-width:0; flex:1; }
.role-heading .kicker { color:var(--game-accent); }
.role-heading h3 { color:var(--text); font-size:22px; line-height:30px; font-weight:600; letter-spacing:-.03em; }
.role-heading h3 span { color:var(--game-accent); font-size:14px; font-weight:400; margin-left:7px; letter-spacing:0; }
.version { border-radius:var(--radius-chip); background:var(--card-bg); padding:3px 12px; font-size:12px; color:var(--game-accent); white-space:nowrap; }
.provenance { margin-top:12px; }
.notice { padding:12px 16px; background:var(--surface-soft); border-radius:var(--radius-well); font-size:13px; line-height:1.7; margin-bottom:14px; }
.warning { color:var(--attention-text); background:var(--attention-bg); }
.error { color:var(--danger); background:var(--danger-bg); }
.source-status { margin:10px 0; }
/* Five advice cards, two across; a lone last one takes the full row. */
.advice-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; margin-top:14px; }
.advice-card { border:1px solid var(--card-border); border-radius:var(--radius-tile); padding:16px; background:var(--card-bg); min-width:0; display:flex; flex-direction:column; }
.advice-card:last-child:nth-child(odd) { grid-column:1/-1; }
.advice-card header { display:flex; align-items:center; gap:9px; margin-bottom:12px; }
.advice-card header::before { content:''; width:10px; height:10px; border-radius:3px; background:var(--game-vivid); }
.advice-card h4 { margin:0; font-size:15px; font-weight:600; }
.advice-card ul { list-style:none; padding-left:0; display:grid; gap:10px; font-size:13px; line-height:1.8; }
.section-note { font-size:12px; line-height:1.8; color:var(--text-muted); margin-top:12px; }
.advice-card .text-link { align-self:flex-start; margin-top:auto; padding-top:14px; }
.source-card { margin-top:18px; border:1px solid var(--card-border); border-radius:var(--radius-tile); background:var(--card-bg); padding:18px; }
.source-card>header { display:flex; align-items:center; justify-content:space-between; gap:14px; margin-bottom:12px; }
.source-card h4 { margin:0 0 6px; font-size:15px; font-weight:600; }
.source-card a { color:var(--accent); font-size:13px; line-height:1.7; }
.image-toolbar { display:flex; align-items:center; gap:7px; flex-wrap:wrap; margin:16px 0 12px; font-size:12px; color:var(--text-muted); }
.image-toolbar a { margin-left:auto; font-size:12px; }
.image-caption { font-size:12px; color:var(--text-muted); margin-bottom:10px; }
.guide-image { display:block; width:100%; height:auto; border-radius:var(--radius-well); background:var(--surface-soft); }
.original-text { margin-top:16px; font-size:13px; }
.original-text summary { color:var(--text-muted); cursor:pointer; }
.original-text p { margin-top:12px; line-height:1.8; overflow-wrap:anywhere; }
.role-list button:focus-visible { border-radius:var(--radius-tile); }
.nte-guides > .role-list button:focus-visible { border-radius:var(--radius-control); }
@container (max-width:560px) {
  .guides-head { align-items:flex-start; }
  .catalog-count { line-height:1.6; }
  .role-heading { flex-wrap:wrap; padding:14px; }
  .role-heading h3 span { font-size:12px; }
  .source-card { padding:14px; }
  .source-card>header { align-items:flex-start; }
  .image-toolbar a { flex-basis:100%; margin-top:6px; }
  .search-label { min-width:100%; }
  .search-label input { min-width:0; }
  .advice-grid { grid-template-columns:minmax(0,1fr); }
  .advice-card { padding:14px; }
}
</style>
