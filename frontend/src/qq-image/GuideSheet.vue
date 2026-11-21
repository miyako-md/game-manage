<script setup>
import { computed, ref, watch } from 'vue'
import WuwaGuideVisual from '../components/WuwaGuideVisual.vue'
import NteGuideVisual from '../components/NteGuideVisual.vue'
import { guideLines } from './guide-presentation.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import { normalizeElementKey } from './role-meta.js'

const props = defineProps({
  input: { type: Object, required: true },
  model: { type: Object, required: true },
})

const elemKey = computed(() => {
  const g = props.input?.snapshot?.display_data?.guide
  const raw = g?.attribute || g?.element
  return raw ? normalizeElementKey(raw) : ''
})

const portraitFailed = ref(false)
watch(() => props.model?.hero?.image, () => {
  portraitFailed.value = false
})

const hasPortrait = computed(() => Boolean(props.model?.hero?.image && !portraitFailed.value))
const hero = computed(() => props.model?.hero || null)

const panels = computed(() => (Array.isArray(props.model?.panels) ? props.model.panels : []))
const statusPanel = computed(() => panels.value.find(p => p.type === 'textlines' && p.title === '攻略状态') || null)
const sourcePanel = computed(() => panels.value.find(p => p.type === 'textlines' && p.title === '攻略来源') || null)

const WIDE_KEYS = new Set(['teams'])
const rawVisuals = computed(() => panels.value.filter(p => p.type === 'guide_visual'))

const visualCards = computed(() => {
  const list = rawVisuals.value
  const isBaseWide = p => Boolean(p.plain || WIDE_KEYS.has(p.sectionKey) || (p.text || '').length > 140)
  // Determine full-width spans while preserving exact source order so no compact card leaves an orphan half-row.
  const flags = list.map(p => isBaseWide(p))
  let pendingCompact = -1
  for (let i = 0; i < list.length; i++) {
    if (flags[i]) {
      if (pendingCompact !== -1) {
        flags[pendingCompact] = true
        pendingCompact = -1
      }
    } else if (pendingCompact === -1) {
      pendingCompact = i
    } else {
      pendingCompact = -1
    }
  }
  if (pendingCompact !== -1) flags[pendingCompact] = true
  return list.map((p, idx) => ({ panel: p, isWide: flags[idx] }))
})

const extraTextPanels = computed(() =>
  panels.value.filter(p => p !== statusPanel.value && p !== sourcePanel.value && p.type !== 'guide_visual'),
)
</script>

<template>
  <div class="ov-guide-sheet" :data-element="elemKey || undefined">
    <!-- Preserves .guide-role-context > div full-width contract when no portrait is present -->
    <div v-if="hero" class="guide-role-context ov-guide-context" :class="{ 'has-portrait': hasPortrait }">
      <img
        v-if="hasPortrait"
        :src="hero.image"
        :alt="hero.name"
        @error="portraitFailed = true"
      />
      <div>
        <h2>{{ hero.name }}</h2>
        <div v-if="hero.meta?.length" class="ov-guide-chips">
          <span v-for="(tag, idx) in hero.meta" :key="idx" class="ov-guide-chip">{{ tag }}</span>
        </div>
      </div>
    </div>

    <template v-if="statusPanel && statusPanel.lines?.length">
      <OverviewSectionHead title="攻略状态" meta="时效与原帖说明" />
      <div class="ov-ds-card ov-guide-status">
        <p v-for="(line, i) in statusPanel.lines" :key="i" class="ov-guide-status-line">
          <span class="ov-guide-status-mark" aria-hidden="true">✦</span>
          <span>{{ line.text }}</span>
        </p>
      </div>
    </template>

    <OverviewSectionHead
      title="培养建议"
      :meta="visualCards.length ? `${visualCards.length} 项建议` : '仅原图索引'"
    />

    <div v-if="visualCards.length" class="ov-guide-grid">
      <section
        v-for="({ panel, isWide }, idx) in visualCards"
        :key="panel.sectionKey || idx"
        class="ov-ds-card ov-guide-card"
        :class="{ 'is-wide': isWide }"
      >
        <header class="ov-guide-card-head">
          <h3>{{ panel.title }}</h3>
          <span v-if="panel.source" class="ov-guide-card-src">{{ panel.source }}</span>
        </header>
        <p v-if="panel.caption" class="ov-guide-card-caption">{{ panel.caption }}</p>

        <div class="guide-visual" :class="{ 'is-teams-grid': panel.sectionKey === 'teams' && guideLines(panel).length >= 2 }">
          <div v-for="(line, lIdx) in guideLines(panel)" :key="lIdx" class="guide-source-line">
            <span v-if="panel.plain" class="guide-plain">{{ line }}</span>
            <WuwaGuideVisual
              v-else-if="panel.game === 'wuthering_waves'"
              :text="line"
              :section-key="panel.sectionKey"
              :character-id="panel.characterId"
              image-mode
            />
            <NteGuideVisual
              v-else
              :text="line"
              :section-key="panel.sectionKey"
              :role-name="panel.roleName"
              image-mode
            />
          </div>
        </div>
      </section>
    </div>
    <div v-else class="ov-ds-card">
      <p class="ov-ds-muted" style="margin: 0">
        本条目当前为仅原图索引，暂未收录结构化文字摘要，请查看下方原帖来源链接。
      </p>
    </div>

    <template v-for="(panel, idx) in extraTextPanels" :key="`extra-${idx}`">
      <OverviewSectionHead :title="panel.title" />
      <div class="ov-ds-card ov-guide-sources">
        <template v-if="panel.lines?.length">
          <div v-for="(line, lIdx) in panel.lines" :key="lIdx" class="ov-guide-src-item">
            <strong v-if="line.name">{{ line.name }}</strong>
            <p>{{ line.text }}</p>
          </div>
        </template>
        <p v-else class="ov-guide-src-caption">{{ panel.text }}</p>
      </div>
    </template>

    <template v-if="sourcePanel">
      <OverviewSectionHead title="攻略来源" :meta="`${sourcePanel.lines?.length || 0} 篇引用`" />
      <div class="ov-ds-card ov-guide-sources">
        <div v-for="(line, idx) in sourcePanel.lines || []" :key="idx" class="ov-guide-src-item">
          <strong v-if="line.name">{{ line.name }}</strong>
          <p class="ov-guide-src-body">{{ line.text }}</p>
        </div>
        <p v-if="sourcePanel.caption" class="ov-guide-src-caption">{{ sourcePanel.caption }}</p>
      </div>
    </template>
  </div>
</template>
