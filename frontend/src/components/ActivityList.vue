<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  snap: { type: Object, default: null },
})

const view = ref('list')

const rows = computed(() => {
  const payload = props.snap?.payload
  const items = Array.isArray(payload) ? payload : []
  return items.map((it) => {
    let badge = null
    if (it.end_at) {
      const end = new Date(it.end_at)
      if (!Number.isNaN(end.getTime())) {
        const days = Math.ceil((end.getTime() - Date.now()) / 86400000)
        badge = {
          text: days < 0 ? '已结束' : `剩余 ${days} 天`,
          danger: days <= 3,
        }
      }
    }
    return {
      ...it,
      badge,
      startText: it.start_at ? fmtDate(it.start_at) : '',
      endText: it.end_at ? fmtDate(it.end_at) : '',
    }
  })
})

// 日历视图：start_at 非空者按本地日期分组（同日归一组），组按日期升序；
// start_at 为空或无法解析的活动归入末尾"未定日期"组
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

const groups = computed(() => {
  const dated = new Map()
  const undated = []
  for (const it of rows.value) {
    const d = it.start_at ? new Date(it.start_at) : null
    if (!d || Number.isNaN(d.getTime())) {
      undated.push(it)
      continue
    }
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`
    if (!dated.has(key)) {
      dated.set(key, {
        key,
        sort: new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime(),
        label:
          `${String(d.getMonth() + 1).padStart(2, '0')}月` +
          `${String(d.getDate()).padStart(2, '0')}日 周${WEEKDAYS[d.getDay()]}`,
        items: [],
      })
    }
    dated.get(key).items.push(it)
  }
  const list = [...dated.values()].sort((a, b) => a.sort - b.sort)
  if (undated.length > 0) {
    list.push({ key: 'undated', label: '未定日期', items: undated })
  }
  return list
})

// 列表视图 = 单一无组头的组，两个视图共用同一套条目渲染
const displayGroups = computed(() =>
  view.value === 'calendar'
    ? groups.value
    : [{ key: 'all', label: '', items: rows.value }],
)

function fmtDate(value) {
  const d = new Date(value)
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleDateString()
}
</script>

<template>
  <div class="cap-card">
    <div class="cap-title">
      活动
      <span class="view-toggle">
        <button
          type="button"
          class="view-btn"
          :class="{ active: view === 'list' }"
          @click="view = 'list'"
        >
          列表
        </button>
        <button
          type="button"
          class="view-btn"
          :class="{ active: view === 'calendar' }"
          @click="view = 'calendar'"
        >
          日历
        </button>
      </span>
    </div>

    <p v-if="rows.length === 0" class="empty">暂无数据</p>
    <template v-else>
      <section v-for="g in displayGroups" :key="g.key" class="group">
        <div v-if="g.label" class="group-head">{{ g.label }}</div>
        <ul class="item-list">
          <li v-for="(it, i) in g.items" :key="i" class="item">
            <div class="item-main">
              <span class="item-title">{{ it.title }}</span>
              <span
                v-if="it.badge"
                class="badge"
                :class="it.badge.danger ? 'badge-danger' : 'badge-muted'"
              >
                {{ it.badge.text }}
              </span>
            </div>
            <div v-if="it.startText || it.endText" class="item-dates">
              <span v-if="it.startText">开始 {{ it.startText }}</span>
              <span v-if="it.endText">结束 {{ it.endText }}</span>
            </div>
          </li>
        </ul>
      </section>
    </template>
  </div>
</template>

<style scoped>
.view-toggle {
  margin-left: auto;
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.view-btn {
  border: none;
  background: transparent;
  padding: 2px 10px;
  font-size: 12px;
  cursor: pointer;
  color: var(--text-muted);
}

.view-btn + .view-btn {
  border-left: 1px solid var(--border);
}

.view-btn.active {
  background: var(--accent);
  color: #fff;
}

.view-btn:hover:not(.active) {
  background: var(--bg);
  color: var(--text);
}

.group + .group {
  margin-top: 12px;
}

.group-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  padding-bottom: 4px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.item-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item {
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.item:last-child {
  border-bottom: none;
}

.item-main {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}

.item-title {
  font-weight: 500;
}

.item-dates {
  display: flex;
  gap: 12px;
  margin-top: 2px;
  font-size: 12px;
  color: var(--text-muted);
}

.badge-muted {
  color: var(--text-muted);
  background: var(--bg);
}
</style>
