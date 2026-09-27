<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getGuideCatalog, getGuideSource, safeGuideUrl } from '../nte-guides-api.js'
import { displayBeijing } from '../time.js'
import NteIcon from './NteIcon.vue'
import NteGuideVisual from './NteGuideVisual.vue'
import { nteRoleIcon } from '../nte-icons.js'

const props = defineProps({ roles: { type: Array, default: () => [] } })
const catalog = ref(null), selected = ref('黑羽'), search = ref(''), ownedOnly = ref(false)
const catalogLoading = ref(true), catalogError = ref(''), source = ref(null), sourceLoading = ref(false), sourceError = ref('')
const page = ref(1), imageFailed = ref(false)
const sourcePanel = ref(null)
let requestId = 0, disposed = false, sourceController = null
const catalogController = new AbortController()
const names = computed(() => new Set(props.roles.map(role => role.name)))
const isOwned = guide => [guide.name, ...(guide.aliases || [])].some(name => names.value.has(name))
const guides = computed(() => (catalog.value?.guides || []).filter(guide => (!ownedOnly.value || isOwned(guide))
  && [guide.name, guide.element, guide.role, ...(guide.aliases || [])].some(value => String(value || '').toLowerCase().includes(search.value.trim().toLowerCase()))))
const guide = computed(() => guides.value.find(item => item.id === selected.value) || guides.value[0])
const sourceMeta = computed(() => catalog.value?.sources?.find(item => item.id === guide.value?.source_id))
const currentImage = computed(() => safeGuideUrl(source.value?.images?.[page.value - 1], true))
const totalImages = computed(() => source.value?.images?.length || 0)
const reviewedCount = computed(() => catalog.value?.guides?.filter(item => item.status === 'reviewed').length || 0)
const originalLink = computed(() => safeGuideUrl(sourceMeta.value?.url))
const date = value => value ? displayBeijing(value) : '未提供'

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
async function showPage(value) { page.value = value; await nextTick(); sourcePanel.value?.scrollIntoView?.({ behavior:'smooth', block:'start' }) }
onMounted(loadCatalog)
onBeforeUnmount(() => { disposed = true; requestId++; sourceController?.abort(); catalogController.abort() })
</script>

<template>
  <section class="nte-guides" aria-label="异环角色攻略">
    <header class="guides-head"><div><p class="kicker">CHARACTER GUIDES</p><h2>角色攻略</h2><p class="muted">弧盘 · 配队 · 卡带 · 词条 · 技能加点</p></div><span v-if="catalog" class="catalog-count">{{ catalog.guides.length }} 名角色原图索引 <b>{{ reviewedCount }} 名已整理摘要</b></span></header>
    <p v-if="catalogLoading" class="notice" role="status">正在加载攻略目录…</p>
    <div v-else-if="catalogError" class="notice error" role="alert">{{ catalogError }} <button @click="loadCatalog">重试</button></div>
    <template v-else-if="catalog">
      <div class="guides-filters"><label class="search-label">查找角色<input v-model="search" type="search" placeholder="角色名、属性或定位" /></label><label><input v-model="ownedOnly" type="checkbox" />只看已拥有</label><span class="muted">{{ guides.length }} 名角色</span></div>
      <p v-if="ownedOnly && !roles.length" class="notice">尚无角色资料，可关闭“只看已拥有”浏览公开攻略，或登录并刷新角色数据。</p>
      <p v-else-if="!guides.length" class="notice">没有匹配的角色，试试其他关键词。</p>
      <div v-if="guide" class="guides-layout">
        <nav class="role-list" aria-label="攻略角色列表"><button v-for="item in guides" :key="item.id" :aria-pressed="guide.id === item.id" :aria-label="`查看${item.name}攻略`" @click="selected = item.id"><NteIcon :src="nteRoleIcon(item.name)" :name="item.name" /><span><strong>{{ item.name }}</strong><small>{{ item.element }} · {{ item.role }}</small></span><span class="guide-dot" :class="{ reviewed:item.status === 'reviewed' }" :title="item.status === 'reviewed' ? '已整理摘要' : '原图索引'" /></button></nav>
        <div class="guide-main">
          <header class="role-heading"><div><p class="kicker">{{ guide.element }} · {{ guide.role }}</p><h3>{{ guide.name }} <span>培养攻略</span></h3></div><span class="version">V{{ sourceMeta?.version || '未知' }} 资料</span></header>
          <p class="provenance">{{ sourceMeta?.author }} · 社区作者建议<span v-if="guide.reviewed_at"> · 摘要核对于 {{ guide.reviewed_at }}</span></p>
          <p class="version-note">按来源标注的版本与定位使用，不代表当前版本唯一最优解。</p>
          <p v-if="source?.summary_changed" class="notice warning" role="status">原帖有更新，文字摘要待复核；以下为此前核对内容，请优先查看最新原图。</p>
          <p v-if="sourceError || source?.error" class="notice warning" role="alert">{{ sourceError || source.error }}</p>
          <p v-else-if="sourceLoading" class="source-status" role="status">正在核对原帖与图片…</p>
          <p v-else-if="source?.stale" class="source-status">当前展示本机保存的旧版来源资料。</p>
          <p v-if="guide.status === 'original_only'" class="notice">文字推荐待整理。已定位到原图第 {{ guide.pages.join('、') }} 页，可查看该角色的五类配装信息。</p>
          <div v-if="guide.status === 'reviewed'" class="advice-grid"><article v-for="(section, index) in guide.sections" :key="section.key" class="advice-card"><header><span class="number">0{{ index + 1 }}</span><h4>{{ section.title }}</h4></header><ul v-if="section.items.length"><li v-for="(item, i) in section.items" :key="i"><NteGuideVisual :text="item" :section-key="section.key" :role-name="guide.name" /></li></ul><p v-else class="muted">暂无已整理的文字推荐</p><details v-if="section.note" class="section-note"><summary>适用条件与说明</summary><p>{{ section.note }}</p></details><button :disabled="sourceLoading || !source || !section.pages.some(n => n <= totalImages)" @click="showPage(section.pages[0])">查看对应原图 · 第 {{ section.pages.join('、') }} 页 ↗</button></article></div>
          <section ref="sourcePanel" class="source-card" aria-label="攻略原图与来源"><header><div><h4>原图与来源</h4><a v-if="originalLink" :href="originalLink" target="_blank" rel="noopener noreferrer">{{ sourceMeta.title }} ↗</a></div><button :disabled="sourceLoading" @click="loadSource(true)">{{ sourceLoading ? '读取中…' : '刷新原帖' }}</button></header>
            <p class="muted">读取时间：{{ date(source?.fetched_at) }}<span v-if="source?.published_at"> · 发布：{{ date(source.published_at) }}</span><span v-if="source?.edited_at"> · 编辑：{{ date(source.edited_at) }}</span></p>
            <p v-if="source?.refresh_deferred" class="muted">刚刚已尝试读取，同一原帖 30 秒内不重复刷新。</p>
            <template v-if="totalImages"><div class="image-toolbar"><span>原图第 {{ page }} / {{ totalImages }} 页</span><button v-for="n in totalImages" :key="n" :aria-pressed="page === n" :aria-label="`查看原图第${n}页`" @click="showPage(n)">{{ n }}</button><a v-if="currentImage" :href="currentImage" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">新窗口查看大图 ↗</a></div>
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
.nte-guides { color:var(--text);min-width:0; }.guides-head { display:flex;align-items:center;justify-content:space-between;gap:18px;padding:6px 0 24px; }.kicker { color:var(--accent);font-size:10px;letter-spacing:.14em;margin:0 0 8px; }.guides-head h2 { font-size:25px;margin-bottom:8px;font-weight:600; }.muted,.provenance,.source-status { color:var(--text-muted);font-size:12px;line-height:1.8; }.catalog-count { font-size:12px;color:var(--text-muted);text-align:right; }.catalog-count b { display:block;color:var(--accent);font-weight:500;margin-top:8px; }.guides-filters { display:flex;align-items:center;gap:20px;flex-wrap:wrap;border-bottom:1px solid var(--border);padding:0 0 20px;margin-bottom:22px;font-size:12px; }.guides-filters label { display:flex;align-items:center;gap:9px; }.search-label { flex:1;min-width:240px; }.search-label input { flex:1;max-width:340px;background:var(--card-bg,var(--bg));border:1px solid var(--border);border-radius:8px;padding:10px 12px;font:inherit;color:var(--text); }.guides-filters input[type=checkbox] { accent-color:var(--accent); }.guides-layout { display:grid;grid-template-columns:190px minmax(0,1fr);gap:26px;align-items:start; }.role-list { display:grid;gap:5px;position:sticky;top:18px;max-height:78vh;overflow:auto;padding-right:4px; }.role-list button { display:flex;gap:10px;align-items:center;text-align:left;padding:10px;border:1px solid transparent;border-radius:8px;background:transparent;color:var(--text);cursor:pointer; }.role-list button[aria-pressed=true] { background:var(--accent-soft);border-color:var(--border); }.role-mark { display:grid;place-items:center;flex-shrink:0;width:31px;height:35px;background:var(--card-bg);border:1px solid var(--border);border-radius:6px;color:var(--accent);font-size:14px; }.role-list strong { display:block;font-size:12px;font-weight:550; }.role-list small { display:block;color:var(--text-muted);font-size:10px;margin-top:5px; }.guide-dot { width:5px;height:5px;border-radius:50%;background:var(--border);margin-left:auto;flex-shrink:0; }.guide-dot.reviewed { background:var(--accent); }.guide-main { min-width:0; }.role-heading { display:flex;justify-content:space-between;gap:12px;align-items:center; }.role-heading h3 { font-size:24px;font-weight:600; }.role-heading h3 span { color:var(--text-muted);font-size:14px;font-weight:400;margin-left:7px; }.version { border:1px solid var(--border);border-radius:5px;padding:6px 9px;font-size:11px;color:var(--accent);white-space:nowrap; }.provenance { margin-top:12px; }.version-note { color:var(--text-muted);font-size:11px;margin:5px 0 20px; }.notice { padding:13px 15px;background:var(--card-bg);border:1px solid var(--border);border-radius:8px;font-size:12px;line-height:1.8;margin-bottom:15px; }.warning { border-color:var(--attention-border);color:var(--attention-text); }.error { color:var(--danger); }.source-status { margin:10px 0; }.advice-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:13px; }.advice-card { border:1px solid var(--border);border-radius:10px;padding:18px;background:var(--card-bg);min-width:0;display:flex;flex-direction:column; }.advice-card:last-child { grid-column:1/-1; }.advice-card header { display:flex;align-items:center;gap:9px;margin-bottom:13px; }.number { color:var(--accent);font-size:10px;letter-spacing:.1em;opacity:.8; }.advice-card h4 { font-size:14px;font-weight:550; }.advice-card ul { list-style:none;padding-left:0;display:grid;gap:9px;font-size:12px;line-height:1.8; }.section-note { font-size:11px;line-height:1.8;color:var(--text-muted);margin-top:12px; }.advice-card button { align-self:flex-start;margin-top:auto;padding-top:15px;border:0;background:none;color:var(--accent);font-size:11px;cursor:pointer; }.advice-card button:disabled { color:var(--text-muted);cursor:default;opacity:.6; }.source-card { margin-top:22px;border:1px solid var(--border);border-radius:10px;padding:20px; }.source-card>header { display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:12px; }.source-card h4 { font-size:14px;margin-bottom:9px; }.source-card a { color:var(--accent);font-size:12px;line-height:1.7; }.source-card button,.notice button { background:var(--card-bg);border:1px solid var(--border);border-radius:6px;padding:7px 10px;color:var(--text);font-size:11px;cursor:pointer; }.source-card button:disabled { opacity:.5; }.image-toolbar { display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:19px 0 12px;font-size:11px;color:var(--text-muted); }.image-toolbar button[aria-pressed=true] { color:var(--accent);border-color:var(--accent); }.image-toolbar a { margin-left:auto;font-size:11px; }.image-caption { font-size:10px;color:var(--text-muted);margin-bottom:10px; }.guide-image { display:block;width:100%;height:auto;border-radius:7px;background:var(--card-bg); }.original-text { border-top:1px solid var(--border);margin-top:18px;padding-top:14px;font-size:12px; }.original-text summary { color:var(--text-muted);cursor:pointer; }.original-text p { margin-top:12px;line-height:1.8;overflow-wrap:anywhere; }.nte-guides button:focus-visible,.nte-guides a:focus-visible { outline:2px solid var(--accent);outline-offset:3px; }
@media(max-width:1050px) { .guides-layout { grid-template-columns:155px minmax(0,1fr);gap:17px; }.advice-grid { grid-template-columns:1fr; } }
@media(max-width:650px) { .guides-head { align-items:flex-start; }.guides-head h2 { font-size:21px; }.catalog-count { font-size:10px;line-height:1.6; }.guides-layout { grid-template-columns:minmax(0,1fr); }.role-list { display:flex;position:static;max-height:none;overflow-x:auto;padding-bottom:8px; }.role-list button { flex-shrink:0;padding:8px; }.role-list .guide-dot { display:none; }.role-heading h3 { font-size:21px; }.role-heading h3 span { font-size:12px; }.source-card { padding:14px; }.source-card>header { align-items:flex-start; }.source-card>header button { white-space:nowrap; }.image-toolbar a { flex-basis:100%;margin-top:6px; }.search-label { min-width:100%; }.search-label input { min-width:0; }.advice-card { padding:16px; } }
</style>
