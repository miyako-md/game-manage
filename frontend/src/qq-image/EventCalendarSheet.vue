<script setup>
import { computed } from 'vue'
import { gameVars } from '../dashboard.js'
import { skinOf } from '../game-themes.js'
import PosterCalendar from './PosterCalendar.vue'
import OverviewSectionHead from './OverviewSectionHead.vue'

const props = defineProps({
  input: { type: Object, required: true },
  model: { type: Object, required: true },
})

const panels = computed(() => (Array.isArray(props.model?.panels) ? props.model.panels : []))
const isRecent = computed(() => panels.value.some(p => p.type === 'upcoming'))
</script>

<template>
  <div class="ov-cal-sheet" :class="{ 'is-recent': isRecent }">
    <p v-if="!panels.length" class="ov-empty">暂无已收录的活动排期。</p>

    <template v-else-if="isRecent">
      <section v-for="(panel, idx) in panels" :key="idx" class="ov-up-section">
        <OverviewSectionHead
          :title="panel.title"
          :meta="panel.rows?.length ? `${panel.rows.length} 项` : '暂无'"
        />
        <div class="ov-cal-card ov-up-card">
          <div v-if="panel.rows?.length" class="upcoming-list ov-up-list">
            <article
              v-for="(r, rIdx) in panel.rows"
              :key="rIdx"
              class="upcoming-row ov-up-row"
              :class="{ 'has-game': !!r.game }"
              :data-skin="r.game && skinOf(r.gameId) || undefined"
              :style="r.game ? gameVars(r.gameId) : undefined"
            >
              <span v-if="r.game" class="upcoming-game ov-up-game">{{ r.game }}</span>
              <div class="upcoming-name ov-up-name">
                <h3>{{ r.name }}</h3>
                <small v-if="r.category">{{ r.category }}</small>
              </div>
              <span class="upcoming-time ov-up-time num-nowrap">{{ r.time }}</span>
              <strong class="upcoming-countdown ov-up-countdown num-nowrap" :class="{ urgent: r.urgent }">
                {{ r.countdown }}
              </strong>
            </article>
          </div>
          <p v-else class="ov-empty" style="padding: 16px 0">{{ panel.empty }}</p>
          <p v-if="panel.note" class="ov-up-note">{{ panel.note }}</p>
          <p v-if="panel.caption" class="ov-cal-caption" style="margin-top: 8px">{{ panel.caption }}</p>
        </div>
      </section>
    </template>

    <template v-else>
      <PosterCalendar :panels="panels" />
    </template>
  </div>
</template>
