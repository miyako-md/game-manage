<script setup>
import { computed, ref, watch } from 'vue'
import { displayWuwaGuide, getWuwaGuide, guideSections, guideSourceUrl, guideUpdatedAt, guideVersion } from '../wuwa-guides.js'
import { characterIcon, namedIcon } from '../wuwa-icons.js'
import WuwaIcon from './WuwaIcon.vue'
import WuwaGuideVisual from './WuwaGuideVisual.vue'
import WuwaGuideUpdates from './WuwaGuideUpdates.vue'

const props = defineProps({ characterId: { type: [String, Number], required: true }, characterName: { type: String, default: '' }, attribute: { type: String, default: '' } })
const update = ref(null)
const original = computed(() => getWuwaGuide(props.characterId))
const guide = computed(() => displayWuwaGuide(props.characterId, update.value))
const draft = computed(() => update.value && guide.value !== update.value ? update.value : null)
watch(() => props.characterId, () => { update.value = null }, { flush: 'sync' })
const reviewedCount = computed(() => guide.value?.sections.filter(s => s.status === 'reviewed').length || 0)
const sourceFor = section => guide.value?.sources.find(s => s.id === section.sourceId)
const stateLabel = status => ({ reviewed: '已核对原帖', extracted: '自动提炼 · 待核查', partial: '部分资料', pending: '待核验' }[status] || '待核验')
function receiveGuide(value) {
  if (value && String(value.id) === String(props.characterId)) update.value = value
}
</script>

<template>
  <section class="wuwa-guide" aria-label="角色培养攻略">
    <header class="guide-heading">
      <WuwaIcon v-if="guide" :src="characterIcon(characterId) || namedIcon('roles', guide.name)" :name="guide.name" size="large" />
      <div class="guide-title">
        <p class="wuwa-kicker">BUILD GUIDE</p>
        <h3>{{ guide ? `${guide.name} · 培养攻略` : '培养攻略' }}</h3>
      </div>
      <span v-if="guide" class="guide-version">{{ guide.attribute }}</span>
    </header>
    <WuwaGuideUpdates :character-id="characterId" :name="original?.name || characterName" :attribute="original?.attribute || attribute" :sources="guide?.sources || []" @guide="receiveGuide" />
    <template v-if="guide">
      <p class="guide-intro">培养建议 · 各项保留版本、适用条件与核查状态</p>
      <p class="wuwa-meta">{{ guide.reviewedAt ? `资料核查于 ${guide.reviewedAt}` : guide.fetchedAt ? '原帖自动提炼，尚未人工核查' : `资料核查于 ${guideUpdatedAt}` }} · {{ reviewedCount }}/5 项已核对原帖<span v-if="reviewedCount < 5"> · 其余条目标明状态</span></p>
      <p v-if="guide.extractionNote" class="guide-note">{{ guide.extractionNote }}</p>
      <div class="guide-grid">
        <article v-for="(section, index) in guide.sections" :key="section.key" class="guide-card" :class="{ 'guide-incomplete': section.status !== 'reviewed' }">
          <header>
            <span class="guide-number">0{{ index + 1 }}</span>
            <h4>{{ guideSections[section.key] }}</h4>
            <span class="guide-state">{{ stateLabel(section.status) }}</span>
          </header>
          <WuwaGuideVisual v-if="section.text" :text="section.text" :section-key="section.key" :character-id="characterId" />
          <p v-else class="guide-advice">暂无已核实的推荐，暂不补写。</p>
          <p v-if="section.note" class="guide-note">{{ section.note }}</p>
          <footer v-if="sourceFor(section)">
            <span class="guide-version">{{ guideVersion(sourceFor(section)) }}</span>
            <span>{{ sourceFor(section).author }}</span>
            <a v-if="guideSourceUrl(sourceFor(section).url)" :href="guideSourceUrl(sourceFor(section).url)" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">查看原帖 ↗</a>
          </footer>
          <p v-if="section.locator" class="wuwa-meta guide-locator">出处：{{ section.locator }}</p>
        </article>
      </div>
      <details :key="guide.id" class="guide-sources">
        <summary>来源与补充资料 · {{ guide.sources.length }} 篇</summary>
        <p class="wuwa-meta">适用版本与发布时间分别列出；每项显示核查状态。点击检查更新可读取新帖图文并提炼。</p>
        <article v-for="source in guide.sources" :key="source.id" class="guide-source">
          <span class="guide-version">{{ guideVersion(source) }}</span>
          <a v-if="guideSourceUrl(source.url)" :href="guideSourceUrl(source.url)" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">{{ source.title }} ↗</a>
          <span v-else>{{ source.title }}</span>
          <p class="wuwa-meta">{{ source.author }} · 发布 {{ source.publishedAt || '时间未提供' }}</p>
          <p v-if="source.kind === 'preview'" class="guide-note">前瞻资料，仅供参考。</p>
        </article>
      </details>
    </template>
    <details v-if="draft" class="guide-sources">
      <summary>新攻略提炼结果 · 待核查</summary>
      <p class="wuwa-meta">已有的核查建议保留。以下为新帖的自动提炼，需核对原帖后再替换。</p>
      <article v-for="section in draft.sections" :key="section.key" class="guide-source">
        <h4>{{ guideSections[section.key] }} · {{ stateLabel(section.status) }}</h4>
        <WuwaGuideVisual v-if="section.text" :text="section.text" :section-key="section.key" :character-id="characterId" />
        <p v-if="section.note" class="guide-note">{{ section.note }}</p>
        <p class="wuwa-meta">出处：{{ section.locator || '尚未识别到明确来源' }}</p>
      </article>
      <a v-for="source in draft.sources" :key="source.id" :href="guideSourceUrl(source.url)" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer">{{ source.title }} · {{ guideVersion(source) }} ↗</a>
    </details>
    <p v-if="!guide" class="wuwa-muted">此角色形态暂未收录攻略。点击检查更新可生成有出处的培养建议。</p>
  </section>
</template>

<style scoped>
.wuwa-guide { padding: 20px 0; }
.guide-heading, .guide-card header { display: flex; align-items: center; gap: 12px; }
.guide-heading { justify-content: space-between; }
.guide-title { flex: 1; }
.guide-heading h3 { margin: 4px 0; font-size: 22px; }
.guide-intro { line-height: 1.8; color: var(--text-muted); margin: 12px 0 4px; }
.guide-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 22px; }
.guide-card { border: 1px solid var(--border-strong); border-radius: 14px; padding: 18px; background: var(--bg); min-width: 0; display: flex; flex-direction: column; }
.guide-card:last-child { grid-column: 1 / -1; }
.guide-card h4 { margin: 0; color: var(--text); font-size: 15px; }
.guide-number { color: var(--accent); font-size: 12px; font-variant-numeric: tabular-nums; }
.guide-state { margin-left: auto; color: var(--text-muted); font-size: 11px; white-space: nowrap; }
.guide-incomplete .guide-state { color: var(--stale-text); }
.guide-advice { line-height: 1.9; font-size: 14px; color: var(--text); overflow-wrap: anywhere; margin: 14px 0; }
.guide-note { color: var(--stale-text); line-height: 1.7; font-size: 12px; }
.guide-card footer { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding-top: 14px; border-top: 1px solid var(--border); margin-top: auto; font-size: 12px; color: var(--text-muted); }
.guide-version { display: inline-block; border: 1px solid var(--border-strong); color: var(--accent); background: var(--accent-dim); padding: 3px 8px; border-radius: 6px; font-size: 12px; white-space: nowrap; }
.wuwa-guide a { color: var(--accent); text-decoration: none; overflow-wrap: anywhere; }
.wuwa-guide a:hover { text-decoration: underline; }
.wuwa-guide a:focus-visible { outline: 2px solid var(--accent); outline-offset: 4px; }
.guide-card footer a { margin-left: auto; }
.guide-locator { margin-top: 8px; font-size: 11px; }
.guide-sources { margin-top: 20px; border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.guide-sources summary { cursor: pointer; }
.guide-source { padding: 14px 0; border-bottom: 1px solid var(--border); }
.guide-source:last-child { border-bottom: 0; padding-bottom: 0; }
.guide-source > a { margin-left: 10px; }
@media (max-width: 720px) {
  .guide-grid { grid-template-columns: minmax(0, 1fr); }
  .guide-card { padding: 14px; }
  .guide-card header { gap: 8px; flex-wrap: wrap; }
  .guide-heading h3 { font-size: 18px; }
}
</style>
