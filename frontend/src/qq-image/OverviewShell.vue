<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  gameTag: { type: String, default: '游戏管家' },
  subTag: { type: String, default: '' },
  extraTag: { type: String, default: '' },
  avatarUrl: { type: String, default: '' },
  heroStats: { type: Array, default: () => [] },
  heroRing: { type: Object, default: null },
  heroBadge: { type: Object, default: null },
  notices: { type: Array, default: () => [] },
  asOf: { type: String, default: '' },
  command: { type: String, default: '' },
  exampleLabel: { type: String, default: '' },
  game: { type: String, default: 'all' },
  skin: { type: String, default: 'wuwa' },
  isCalendar: { type: Boolean, default: false },
})

const failed = ref(false)
watch(() => props.avatarUrl, () => { failed.value = false })

const RING_C = 2 * Math.PI * 26
const ringStrokeOffset = computed(() => {
  const pct = Math.max(0, Math.min(100, Number(props.heroRing?.pct ?? 0)))
  return RING_C * (1 - pct / 100)
})
const emblemKind = computed(() => {
  if (props.game === 'all') return 'multi'
  if (props.skin === 'nte' || props.game === 'nte') return 'nte'
  if (props.skin === 'endfield' || props.game === 'endfield') return 'endfield'
  return 'wuwa'
})
</script>
<template>
  <div class="ao-canvas ov-canvas">
    <!-- Top Capsule Hero Banner -->
    <header class="ao-capsule-banner ov-capsule-banner" :class="{ 'is-calendar-banner': isCalendar }">
      <div class="ao-identity-pill">
        <div class="ao-avatar-ring">
          <img
            v-if="avatarUrl && !failed"
            :src="avatarUrl"
            :alt="title"
            class="ao-avatar-img"
            @error="failed = true"
          />
          <svg v-else-if="emblemKind === 'multi'" class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
            <circle cx="32" cy="32" r="28" fill="#131622" />
            <ellipse cx="32" cy="32" rx="20" ry="12" transform="rotate(-24 32 32)" fill="none" stroke="#8a95ad" stroke-width="1.8" stroke-opacity="0.55" />
            <ellipse cx="32" cy="32" rx="20" ry="12" transform="rotate(34 32 32)" fill="none" stroke="#c79bff" stroke-width="1.6" stroke-opacity="0.55" />
            <circle cx="17" cy="24" r="4.5" fill="#dfc38d" />
            <circle cx="48" cy="24" r="4.5" fill="#c79bff" />
            <circle cx="32" cy="49" r="4.5" fill="#ffd100" />
            <polygon points="32,23 39,30 32,37 25,30" fill="#4fe3e0" />
          </svg>
          <svg v-else-if="emblemKind === 'nte'" class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
            <circle cx="32" cy="32" r="28" fill="#110e20" />
            <polygon points="32,9 51,32 32,55 13,32" fill="none" stroke="#4fe3e0" stroke-width="2.2" />
            <polygon points="32,16 44,32 32,48 20,32" fill="rgba(199,155,255,0.22)" stroke="#c79bff" stroke-width="2" />
            <circle cx="32" cy="32" r="4" fill="#f4f1fb" />
          </svg>
          <svg v-else-if="emblemKind === 'endfield'" class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
            <circle cx="32" cy="32" r="28" fill="#15181e" />
            <polygon points="32,10 51,21 51,43 32,54 13,43 13,21" fill="none" stroke="#ffd100" stroke-width="2.4" />
            <path d="M32 17V25M32 39V47M18 32H25M39 32H46" stroke="#ffd100" stroke-width="2.2" stroke-linecap="square" />
            <polygon points="32,26 38,32 32,38 26,32" fill="#f2f2ee" />
          </svg>
          <svg v-else class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
            <circle cx="32" cy="32" r="28" fill="#151824" />
            <circle cx="32" cy="32" r="20" fill="none" stroke="#dfc38d" stroke-opacity="0.45" stroke-width="1.6" stroke-dasharray="5 4" />
            <path d="M32 11 L36.5 26.5 L52 31 L36.5 35.5 L32 51 L27.5 35.5 L12 31 L27.5 26.5 Z" fill="#ecd39f" />
            <circle cx="32" cy="31" r="4.5" fill="#141824" />
          </svg>
        </div>
        <div class="ao-identity-meta">
          <div class="ao-name-row">
            <svg v-if="emblemKind === 'endfield'" class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
              <polygon points="12,2 21,7 21,17 12,22 3,17 3,7" fill="none" stroke="#ffd100" stroke-width="2.2" />
              <circle cx="12" cy="12" r="3.2" fill="#ffd100" />
            </svg>
            <svg v-else-if="emblemKind === 'nte'" class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
              <polygon points="12,2 21,12 12,22 3,12" fill="#c79bff" />
              <polygon points="12,7 17,12 12,17 7,12" fill="#4fe3e0" />
            </svg>
            <svg v-else-if="emblemKind === 'multi'" class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="9" fill="none" stroke="#8a95ad" stroke-width="1.6" />
              <circle cx="7" cy="9" r="2.4" fill="#dfc38d" />
              <circle cx="17" cy="9" r="2.4" fill="#c79bff" />
              <circle cx="12" cy="17.5" r="2.4" fill="#ffd100" />
            </svg>
            <svg v-else class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 1 L14.8 9.2 L23 12 L14.8 14.8 L12 23 L9.2 14.8 L1 12 L9.2 9.2 Z" fill="#e6c98f" />
            </svg>
            <h1 class="ao-nickname ov-title">{{ title }}</h1>
            <span class="ao-game-tag">{{ gameTag }}</span>
          </div>
          <div v-if="subTag || extraTag" class="ao-subtag-row">
            <span v-if="subTag" class="ao-subtag-pill">{{ subTag }}</span>
            <span v-if="extraTag" class="ao-extra-pill">{{ extraTag }}</span>
          </div>
        </div>
      </div>

      <div v-if="heroRing" class="ov-hero-ring">
        <div class="ov-ring-wrap">
          <svg viewBox="0 0 68 68" class="ov-ring-svg" aria-hidden="true">
            <circle cx="34" cy="34" r="26" fill="none" stroke="rgba(199, 155, 255, 0.22)" stroke-width="6" />
            <circle
              cx="34"
              cy="34"
              r="26"
              fill="none"
              stroke="#4fe3e0"
              stroke-width="6"
              stroke-linecap="round"
              :stroke-dasharray="RING_C"
              :stroke-dashoffset="ringStrokeOffset"
              transform="rotate(-90 34 34)"
            />
          </svg>
          <span class="ov-ring-pct">{{ heroRing.pct }}%</span>
        </div>
        <div class="ov-ring-copy">
          <strong class="ov-ring-sub">{{ heroRing.sub }}</strong>
          <span class="ov-ring-lbl">{{ heroRing.label }}</span>
        </div>
      </div>

      <div v-else-if="heroBadge" class="ov-hero-badge" :class="heroBadge.tone">
        <span class="ov-hero-badge-k">{{ heroBadge.kicker }}</span>
        <strong class="ov-hero-badge-v">✦ {{ heroBadge.title }}</strong>
      </div>

      <div v-else-if="heroStats.length" class="ao-hero-stats">
        <div v-for="hs in heroStats" :key="hs.label" class="ao-hero-col" :class="{ 'is-accent': hs.isAccent }">
          <strong class="ao-hero-val">{{ hs.value }}</strong>
          <span class="ao-hero-lbl">{{ hs.label }}</span>
        </div>
      </div>

      <svg v-if="isCalendar" class="ov-cal-banner-trim" viewBox="0 0 1000 8" preserveAspectRatio="none" aria-hidden="true">
        <polyline
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          points="0,7 12,1 24,7 36,1 48,7 60,1 72,7 84,1 96,7 108,1 120,7 132,1 144,7 156,1 168,7 180,1 192,7 204,1 216,7 228,1 240,7 252,1 264,7 276,1 288,7 300,1 312,7 324,1 336,7 348,1 360,7 372,1 384,7 396,1 408,7 420,1 432,7 444,1 456,7 468,1 480,7 492,1 504,7 516,1 528,7 540,1 552,7 564,1 576,7 588,1 600,7 612,1 624,7 636,1 648,7 660,1 672,7 684,1 696,7 708,1 720,7 732,1 744,7 756,1 768,7 780,1 792,7 804,1 816,7 828,1 840,7 852,1 864,7 876,1 888,7 900,1 912,7 924,1 936,7 948,1 960,7 972,1 984,7 1000,1"
        />
      </svg>
    </header>

    <p v-if="exampleLabel" class="ov-example-label">{{ exampleLabel }}</p>

    <div class="ov-body">
      <slot />
    </div>

    <!-- Unified Notices Strip -->
    <div v-if="notices.length" class="ao-notices">
      <p v-for="(note, idx) in notices" :key="idx" class="ao-notice-item">✦ {{ note }}</p>
    </div>

    <!-- Unified Centered Footer -->
    <footer class="ao-footer">
      <span>Power by GameAssistant · 游戏管家</span>
      <span>·</span>
      <span>更新于 {{ asOf }}</span>
      <span>·</span>
      <span>指令：{{ command }}</span>
    </footer>
  </div>
</template>
