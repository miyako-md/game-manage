<script setup>
import { computed } from 'vue'
import { gameVars } from '../dashboard.js'
import { skinOf } from '../game-themes.js'
import EndfieldArtwork from '../components/EndfieldArtwork.vue'
import OverviewSectionHead from './OverviewSectionHead.vue'
import { asset } from './models.js'

const props = defineProps({
  input: { type: Object, required: true },
  model: { type: Object, required: true },
})

const snap = computed(() => props.input?.snapshot || {})
const data = computed(() => snap.value.display_data || {})
const guideContext = computed(() => (props.model?.panels || []).find(p => p.type === 'guide_context') || null)
const sections = computed(() => (Array.isArray(data.value.sections) ? data.value.sections.filter(Boolean) : []))
const notices = computed(() => {
  const list = Array.isArray(data.value.notices) ? data.value.notices.filter(Boolean) : []
  return [...new Set(list)]
})

function splitItem(text) {
  if (typeof text !== 'string') return null
  const idx = text.indexOf('：')
  if (idx <= 0 || idx >= text.length - 1 || idx > 18) return null
  return [text.slice(0, idx), text.slice(idx + 1)]
}
</script>

<template>
  <div class="ov-notice-sheet">
    <!-- 1. Endfield guide收录提示（保留猫冬MT出处与干员上下文卡，绝不伪造外链） -->
    <template v-if="guideContext">
      <OverviewSectionHead :title="guideContext.title || '攻略收录状态'" en="GUIDE STATUS" :index="1" />
      <div class="ov-nt-callouts is-featured">
        <p class="ov-nt-callout">
          <span class="ov-nt-mark" aria-hidden="true">✦</span>
          <span>{{ guideContext.text }}</span>
        </p>
      </div>

      <div v-if="guideContext.role" class="guide-role-context ov-guide-context ov-nt-role-card">
        <EndfieldArtwork
          :src="asset(guideContext.role.avatar_url)"
          :name="guideContext.role.name"
        />
        <div>
          <h3>{{ guideContext.role.name }}</h3>
          <p class="ov-nt-role-status">角色资料已收录</p>
          <p v-if="guideContext.command" class="ov-nt-role-cmd">
            查看本人面板：<code class="ov-nt-code">{{ guideContext.command }}</code>
          </p>
          <p v-if="guideContext.caption" class="ov-nt-role-cap">{{ guideContext.caption }}</p>
        </div>
      </div>
    </template>

    <!-- 2. 标准结构化通知 / 引导 / 下线说明 -->
    <template v-else>
      <section
        v-for="(sec, idx) in sections"
        :key="idx"
        class="ov-nt-section"
        :data-skin="skinOf(sec.game) || undefined"
        :style="sec.game ? gameVars(sec.game) : undefined"
      >
        <OverviewSectionHead
          v-if="sec.title"
          :title="sec.title"
          en="NOTICE"
          :index="idx + 1"
          :meta="`${sec.items?.length || 0} 项`"
        />
        <div class="ov-ds-card ov-nt-card">
          <ul class="ov-nt-list">
            <li v-for="(item, j) in sec.items || []" :key="j" class="ov-nt-row">
              <div v-if="splitItem(item)" class="ov-nt-kv">
                <span class="ov-nt-k">{{ splitItem(item)[0] }}</span>
                <code class="ov-nt-code">{{ splitItem(item)[1] }}</code>
              </div>
              <p v-else class="ov-nt-text">{{ item }}</p>
            </li>
          </ul>
        </div>
      </section>

      <template v-if="notices.length">
        <OverviewSectionHead
          v-if="sections.length"
          title="使用说明"
          en="GUIDE"
          :index="sections.length + 1"
        />
        <OverviewSectionHead
          v-else
          title="说明与引导"
          en="GUIDE"
          :index="1"
        />
        <div class="ov-nt-callouts" :class="{ 'is-featured': !sections.length }">
          <p v-for="(text, idx) in notices" :key="idx" class="ov-nt-callout">
            <span class="ov-nt-mark" aria-hidden="true">✦</span>
            <span>{{ text }}</span>
          </p>
        </div>
      </template>

      <div v-if="!sections.length && !notices.length" class="ov-empty-card">
        <p class="ov-empty-title">{{ data.title || snap.title || '暂无说明' }}</p>
      </div>
    </template>
  </div>
</template>
