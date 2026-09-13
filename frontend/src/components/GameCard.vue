<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getSnapshot, refreshGame } from '../api.js'
import AccountCard from './AccountCard.vue'
import AnnouncementList from './AnnouncementList.vue'
import CalabashCard from './CalabashCard.vue'
import ExplorationCard from './ExplorationCard.vue'
import MatchList from './MatchList.vue'
import ProgressCard from './ProgressCard.vue'
import StaminaCard from './StaminaCard.vue'
import VersionActivityCard from './VersionActivityCard.vue'

const props = defineProps({
  game: { type: Object, required: true },
})

const CAP_COMPONENTS = {
  stamina: StaminaCard,
  account: AccountCard,
  activity: VersionActivityCard,
  progress: ProgressCard,
  announcement: AnnouncementList,
  match: MatchList,
  exploration: ExplorationCard,
  calabash: CalabashCard,
}

// capability -> 快照对象（{payload, fetched_at, stale}），拉取失败时为 null
const snaps = ref({})
const refreshing = ref(false)
const refreshError = ref('')
let errorTimer = null

function capComponent(cap) {
  return CAP_COMPONENTS[cap] || null
}

async function loadSnapshots() {
  const caps = props.game.capabilities || []
  const results = await Promise.allSettled(
    caps.map((cap) => getSnapshot(props.game.game_id, cap)),
  )
  const next = {}
  caps.forEach((cap, i) => {
    next[cap] = results[i].status === 'fulfilled' ? results[i].value : null
  })
  snaps.value = next
}

function showError(message) {
  refreshError.value = message
  if (errorTimer) clearTimeout(errorTimer)
  errorTimer = setTimeout(() => {
    refreshError.value = ''
  }, 10000)
}

async function onRefresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    const data = await refreshGame(props.game.game_id)
    const failed = Object.entries(data?.results || {}).filter(
      ([, r]) => !r || r.ok !== true,
    )
    if (failed.length > 0) {
      showError(
        '刷新失败：' +
          failed.map(([, r]) => r?.error || '未知错误').join('；'),
      )
    }
  } catch (e) {
    showError('刷新失败：' + (e?.message || '请求异常'))
  } finally {
    refreshing.value = false
    await loadSnapshots()
  }
}

onMounted(loadSnapshots)

onBeforeUnmount(() => {
  if (errorTimer) clearTimeout(errorTimer)
})

// 供 App.vue 的 60 秒定时器通过模板引用触发重拉快照
defineExpose({ loadSnapshots })
</script>

<template>
  <section class="game-card">
    <div v-if="refreshError" class="error-bar" role="alert">
      {{ refreshError }}
    </div>

    <header class="card-head">
      <h2 class="game-name">{{ game.display_name }}</h2>
      <span
        v-if="!game.credentials_configured"
        class="badge badge-danger"
      >
        未配置凭据
      </span>
      <button
        type="button"
        class="refresh-btn"
        :disabled="refreshing"
        @click="onRefresh"
      >
        {{ refreshing ? '刷新中…' : '刷新' }}
      </button>
    </header>

    <div class="cap-list">
      <template v-for="cap in game.capabilities" :key="cap">
        <component :is="capComponent(cap)" v-if="capComponent(cap)" :snap="snaps[cap]" />
        <div v-else class="cap-card cap-coming">敬请期待</div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.game-card {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
}

.error-bar {
  background: var(--danger);
  color: #fff;
  padding: 8px 14px;
  font-size: 13px;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
}

.game-name {
  font-size: 16px;
  font-weight: 600;
  margin-right: auto;
}

.refresh-btn {
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  padding: 4px 14px;
  border-radius: 6px;
  cursor: pointer;
}

.refresh-btn:hover:not(:disabled) {
  border-color: var(--accent);
  color: var(--accent);
}

.refresh-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.cap-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
}

.cap-coming {
  color: var(--text-muted);
  text-align: center;
}
</style>
