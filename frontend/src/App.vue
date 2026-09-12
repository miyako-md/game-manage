<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { getGames, getStatus } from './api.js'
import StatusChip from './components/StatusChip.vue'
import SectionTabs from './components/SectionTabs.vue'
import GameCard from './components/GameCard.vue'

const SECTIONS = ['pc', 'mobile']

const games = ref([])
const notify = ref(null)
const loadError = ref('')
const activeSection = ref('pc')

const cardEls = new Map()
let timer = null

const activeGames = computed(
  () => games.value.filter((g) => g.section === activeSection.value),
)

function setCardRef(el, gameId) {
  if (el) cardEls.set(gameId, el)
  else cardEls.delete(gameId)
}

function pullSnapshots() {
  cardEls.forEach((card) => card.loadSnapshots && card.loadSnapshots())
}

onMounted(async () => {
  const [gamesRes, statusRes] = await Promise.allSettled([
    getGames(),
    getStatus(),
  ])
  if (gamesRes.status === 'fulfilled') {
    games.value = Array.isArray(gamesRes.value) ? gamesRes.value : []
    const preferred = SECTIONS.find((s) =>
      games.value.some((g) => g.section === s),
    )
    activeSection.value = preferred || SECTIONS[0]
  } else {
    loadError.value = '后端连接失败，请确认服务已启动（127.0.0.1:8000）'
  }
  if (statusRes.status === 'fulfilled' && statusRes.value?.notify) {
    notify.value = statusRes.value.notify
  }
  timer = setInterval(pullSnapshots, 60000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="app">
    <header class="topbar">
      <h1 class="title">个人游戏资讯助手</h1>
      <StatusChip v-if="notify" :notify="notify" />
    </header>

    <main class="content">
      <p v-if="loadError" class="page-hint">{{ loadError }}</p>

      <p v-else-if="games.length === 0" class="page-hint">暂无已接入游戏</p>

      <template v-else>
        <SectionTabs v-model="activeSection" :sections="SECTIONS" />
        <div class="card-grid">
          <GameCard
            v-for="g in activeGames"
            :key="g.game_id"
            :ref="(el) => setCardRef(el, g.game_id)"
            :game="g"
          />
        </div>
        <p v-if="activeGames.length === 0" class="page-hint">
          该板块暂无游戏
        </p>
      </template>
    </main>
  </div>
</template>

<style scoped>
.app {
  max-width: 1080px;
  margin: 0 auto;
  padding: 0 16px 40px;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 16px 0;
}

.title {
  font-size: 20px;
  font-weight: 600;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.page-hint {
  padding: 48px 0;
  text-align: center;
  color: var(--text-muted);
}
</style>
