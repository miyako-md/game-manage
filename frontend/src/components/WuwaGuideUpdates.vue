<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { guideSourceUrl } from '../wuwa-guides.js'

const props = defineProps({
  characterId: { type: [String, Number], required: true },
  name: { type: String, default: '' },
  attribute: { type: String, default: '' },
  sources: { type: Array, default: () => [] },
})
const emit = defineEmits(['guide'])
const result = ref(null), loading = ref(false), error = ref('')
let generation = 0, controller
const knownIds = computed(() => new Set(props.sources.map(source => String(source.id))))
const candidates = computed(() => (result.value?.candidates || []).filter(item => guideSourceUrl(item.url)))
const uncollected = computed(() => candidates.value.filter(item => !knownIds.value.has(item.id)).length)
const identity = () => JSON.stringify([String(props.characterId), props.name, props.attribute])
const date = value => value && !Number.isNaN(Date.parse(value))
  ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '时间未提供'
function cancel() { generation++; controller?.abort() }
async function request(check = false, postId = null) {
  cancel()
  if (!props.name) return
  const current = generation, owner = identity()
  controller = new AbortController()
  loading.value = true; error.value = ''
  const query = { character_id: String(props.characterId), name: props.name, attribute: props.attribute }
  try {
    const response = await fetch(`/api/wuwa/guides/updates${postId ? '/extract' : check ? '' : '?' + new URLSearchParams(query)}`, {
      signal: controller.signal, cache: 'no-store', referrerPolicy: 'no-referrer',
      ...(check ? { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Game-Assistant': '1' }, body: JSON.stringify(postId ? {...query, post_id:postId} : query) } : {}),
    })
    if (!response.ok) throw new Error('request failed')
    const data = await response.json()
    if (current !== generation || owner !== identity()) return
    if (String(data.character_id) !== query.character_id || data.name !== query.name || data.attribute !== query.attribute || !Array.isArray(data.candidates))
      throw new Error('response mismatch')
    result.value = data
    const guide = data.active_guide
    if (guide && String(guide.id) === query.character_id && guide.name === query.name && guide.attribute === query.attribute && Array.isArray(guide.sections) && Array.isArray(guide.sources)) emit('guide',guide)
  } catch (e) {
    if (current === generation && e.name !== 'AbortError') error.value = '检查失败，保留上次结果，请稍后重试。'
  } finally {
    if (current === generation) loading.value = false
  }
}
watch(identity, () => { result.value = null; error.value = ''; request() }, { immediate: true })
onBeforeUnmount(cancel)
</script>

<template>
  <section class="guide-updates" aria-label="攻略更新检查" v-if="name">
    <header>
      <div><h4>社区攻略更新</h4><p>查找 {{ name }} 的新攻略并提炼培养建议。</p></div>
      <button type="button" class="ui-button" :disabled="loading" @click="request(true)">{{ loading ? '正在检查与提炼…' : '检查更新' }}</button>
    </header>
    <p class="wuwa-meta" v-if="result?.checked_at">上次成功检查：{{ date(result.checked_at) }}（北京时间） · {{ uncollected }} 篇未收录来源</p>
    <p class="wuwa-meta" v-else>尚未成功检查，点击按钮查找社区新攻略。</p>
    <p role="status" v-if="error || result?.error" class="guide-check-error">{{ error || result.error }}</p>
    <p role="status" v-if="result?.extraction_error" class="guide-check-error">{{ result.extraction_error }}</p>
    <p v-if="result?.active_guide" class="wuwa-meta">{{ result.active_guide.sections.every(s => s.status === 'reviewed') ? '已生成并核对五项培养建议' : '已生成提炼结果，未核查项目单独标注' }} · {{ result.active_guide.sources[0]?.author }}</p>
    <p v-if="result?.deferred" class="wuwa-meta">距离上次检查不足 30 秒，显示已有结果。</p>
    <p v-if="result?.checked_at && !candidates.length && !error && !result.error" class="wuwa-meta">本次检索范围内没有发现可匹配的培养攻略。</p>
    <details v-if="candidates.length" :open="!result?.active_guide">
      <summary>检索结果 · {{ candidates.length }} 篇</summary>
      <article v-for="item in candidates" :key="item.id" class="guide-candidate">
        <a :href="guideSourceUrl(item.url)" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">{{ item.title }} ↗</a>
        <span class="candidate-state">{{ result?.active_guide?.sourceId === item.id ? '当前提炼来源' : knownIds.has(item.id) ? '已收录来源' : '未收录 · 待核查' }}</span>
        <button v-if="item.kind !== 'video'" type="button" class="ui-button small-button" :disabled="loading" @click="request(true,item.id)">{{ result?.active_guide?.sourceId === item.id ? '重新提炼' : '选择并提炼' }}</button>
        <p class="wuwa-meta">{{ item.author }} · {{ item.version ? `V${item.version}` : '版本未确认' }} · {{ item.kind === 'video' ? '视频 · 未转写' : '图文' }} · 发布 {{ date(item.published_at) }}</p>
      </article>
    </details>
    <p class="wuwa-meta scope-note">检索前 40 条最新相关结果{{ result?.limited ? '，仍有后续结果未读取' : '' }}。优先提炼轩儿的图文，其余按发布时间选择；可自行切换来源。正文与配图均保留出处，自动识别内容标明待核查。</p>
  </section>
</template>

<style scoped>
.guide-updates { margin: 18px 0; padding: 16px; border: 1px solid var(--border-strong); border-radius: 12px; background: var(--bg); }
.guide-updates header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.guide-updates h4 { margin: 0; color: var(--text); }
.guide-updates header p { margin: 6px 0; color: var(--text-muted); font-size: 12px; }
.guide-updates button { flex-shrink: 0; }
.guide-updates button:disabled { opacity: .6; cursor: wait; }
.guide-updates summary { cursor: pointer; font-size: 13px; padding: 10px 0; }
.guide-candidate { padding: 12px 0; border-top: 1px solid var(--border); }
.guide-candidate a { color: var(--accent); font-size: 14px; overflow-wrap: anywhere; }
.candidate-state { display: inline-block; margin-left: 8px; font-size: 11px; color: var(--text-muted); }
.guide-candidate p, .scope-note { line-height: 1.7; }
.guide-check-error { color: var(--stale-text); font-size: 13px; }
@media (max-width: 480px) { .guide-updates header { align-items: flex-start; flex-wrap: wrap; } }
</style>
