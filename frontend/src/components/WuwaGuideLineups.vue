<script setup>
import { computed, ref, watch } from 'vue'
import { safeWuwaIcon } from '../wuwa-icons.js'
const props = defineProps({ guide: { type: Object, required: true } })
const index = ref(0), failed = ref(false)
const images = computed(() => (props.guide.lineupImages || []).map(safeWuwaIcon).filter(Boolean))
const current = computed(() => images.value[index.value])
watch(() => props.guide.id, () => { index.value = 0 })
watch(current, () => { failed.value = false })
</script>
<template>
  <section v-if="images.length" class="guide-lineups" :aria-label="`${guide.scope}原帖阵容`">
    <div class="wuwa-tabs" role="group" aria-label="选择阵容图">
      <button v-for="(src, i) in images" :key="src" type="button" :aria-pressed="index === i" @click="index = i">阵容图 {{ i + 1 }}</button>
    </div>
    <figure>
      <a :href="current" target="_blank" rel="noopener noreferrer" referrerpolicy="no-referrer" :aria-label="`打开${guide.scope}阵容图 ${index + 1}大图`">
        <img v-if="!failed" :key="current" :src="current" :alt="`${guide.author} · ${guide.scope} · 阵容图 ${index + 1}`" loading="lazy" decoding="async" referrerpolicy="no-referrer" @error="failed = true" />
        <span v-else class="wuwa-muted">图片暂未加载，点击重试查看大图，或通过下方入口查看原帖。</span>
      </a>
      <figcaption class="wuwa-meta">{{ guide.author }} 原帖配图 · {{ index + 1 }}/{{ images.length }} · 点击图片查看大图</figcaption>
    </figure>
  </section>
</template>
<style scoped>
.guide-lineups { margin: 16px 0; }
.guide-lineups .wuwa-tabs { flex-wrap: wrap; margin-bottom: 14px; }
figure { margin: 0; }
figure a { display: block; max-width: 680px; margin: 0 auto; }
figure img { display: block; width: 100%; height: auto; border-radius: 8px; }
figcaption { text-align: center; margin-top: 10px; }
</style>
