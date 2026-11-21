<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  title: { type: String, required: true },
  gameTag: { type: String, default: '游戏管家' },
  subTag: { type: String, default: '' },
  extraTag: { type: String, default: '' },
  avatarUrl: { type: String, default: '' },
  heroStats: { type: Array, default: () => [] },
  notices: { type: Array, default: () => [] },
  asOf: { type: String, default: '' },
  command: { type: String, default: '' },
  exampleLabel: { type: String, default: '' },
})

const failed = ref(false)
watch(() => props.avatarUrl, () => { failed.value = false })
</script>
<template>
  <div class="ao-canvas ov-canvas">
    <!-- Top Capsule Hero Banner -->
    <header class="ao-capsule-banner ov-capsule-banner">
      <div class="ao-identity-pill">
        <div class="ao-avatar-ring">
          <img
            v-if="avatarUrl && !failed"
            :src="avatarUrl"
            :alt="title"
            class="ao-avatar-img"
            @error="failed = true"
          />
          <svg v-else class="ao-avatar-svg" viewBox="0 0 64 64" aria-hidden="true">
            <defs>
              <linearGradient id="ov-crest-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#f2d9a6" />
                <stop offset="100%" stop-color="#b8904c" />
              </linearGradient>
            </defs>
            <circle cx="32" cy="32" r="28" fill="#181c28" />
            <path d="M32 10 L37 25 L52 30 L37 35 L32 50 L27 35 L12 30 L27 25 Z" fill="url(#ov-crest-grad)" opacity="0.9" />
            <circle cx="32" cy="30" r="5" fill="#12141c" />
          </svg>
        </div>
        <div class="ao-identity-meta">
          <div class="ao-name-row">
            <svg class="ao-star-emblem" viewBox="0 0 24 24" aria-hidden="true">
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

      <div v-if="heroStats.length" class="ao-hero-stats">
        <div v-for="hs in heroStats" :key="hs.label" class="ao-hero-col" :class="{ 'is-accent': hs.isAccent }">
          <strong class="ao-hero-val">{{ hs.value }}</strong>
          <span class="ao-hero-lbl">{{ hs.label }}</span>
        </div>
      </div>
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
