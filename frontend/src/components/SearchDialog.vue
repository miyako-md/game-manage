<script setup>
import { computed, nextTick, ref, useId, watch } from 'vue'
import AppIcon from './AppIcon.vue'
import GameIcon from './GameIcon.vue'
import { useDialog } from '../use-dialog.js'
import { gameStyle } from '../dashboard.js'
import { KIND_LABELS, buildSearchIndex, groupResults, searchItems } from '../search-index.js'

// Jump-to search (⌘K): it only finds places in the app and opens them; it
// never asks a server for anything.
const props = defineProps({
  pages: { type: Array, default: () => [] }, games: { type: Array, default: () => [] },
  snapshots: { type: Object, default: () => ({}) }, now: { type: Number, default: () => Date.now() },
})
const emit = defineEmits(['select', 'close'])
const { dialog, closing, requestClose, backdropDown, backdropClick, animationEnded } = useDialog(() => emit('close'))
const listId = `search-${useId()}`
const query = ref('')
const active = ref(0)
const index = computed(() => buildSearchIndex(props))
const groups = computed(() => groupResults(searchItems(index.value, query.value)))
const flat = computed(() => groups.value.flatMap(group => group.items))
const activeItem = computed(() => flat.value[active.value] || null)
const optionId = item => `${listId}-o${flat.value.indexOf(item)}`
watch(query, () => { active.value = 0 })

function move(step) {
  if (!flat.value.length) return
  active.value = (active.value + step + flat.value.length) % flat.value.length
  nextTick(() => document.getElementById(optionId(activeItem.value))?.scrollIntoView?.({ block: 'nearest' }))
}
function onKey(event) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); move(event.key === 'ArrowDown' ? 1 : -1) }
  else if (event.key === 'Enter' && activeItem.value && !event.isComposing) { event.preventDefault(); emit('select', activeItem.value.href) }
}
// A modified click keeps the browser's own behaviour (open in a new tab).
function choose(item, event) {
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
  event.preventDefault()
  emit('select', item.href)
}
</script>

<template>
  <dialog ref="dialog" class="search-dialog t-dialog" :data-closing="closing ? '' : undefined" aria-modal="true" aria-label="搜索并跳转" @cancel.prevent="requestClose" @pointerdown="backdropDown" @click="backdropClick" @animationend="animationEnded">
    <div class="search-field">
      <AppIcon name="search" :size="18" />
      <input v-model="query" type="text" role="combobox" aria-autocomplete="list" aria-expanded="true" :aria-controls="listId" :aria-activedescendant="activeItem ? optionId(activeItem) : undefined" aria-label="搜索页面、游戏、栏目、活动和角色" placeholder="搜索页面、游戏、栏目、活动和角色" autocomplete="off" spellcheck="false" autofocus @keydown="onKey" />
      <button type="button" class="search-close" aria-label="关闭搜索" @click="requestClose"><kbd aria-hidden="true">Esc</kbd></button>
    </div>
    <div :id="listId" class="search-results" role="listbox" aria-label="搜索结果">
      <div v-for="group in groups" :key="group.kind" role="group" :aria-labelledby="`${listId}-${group.kind}`">
        <p :id="`${listId}-${group.kind}`" class="search-label">{{ group.label }}</p>
        <a v-for="item in group.items" :id="optionId(item)" :key="item.key" class="search-result" role="option" tabindex="-1" :aria-selected="item === activeItem" :href="item.href" @click="choose(item, $event)" @pointermove="active = flat.indexOf(item)">
          <span class="search-mark" :style="{ '--mark-tone': item.gameId ? gameStyle(item.gameId).tone : undefined }" aria-hidden="true">
            <GameIcon v-if="item.gameId" :game-id="item.gameId" />
            <AppIcon v-else :name="item.icon || 'grid'" :size="17" />
          </span>
          <span class="search-copy"><strong>{{ item.title }}</strong><small v-if="item.hint">{{ item.hint }}</small></span>
          <span class="search-kind">{{ KIND_LABELS[item.kind] }}</span>
        </a>
      </div>
      <p v-if="!flat.length" class="search-empty">没有找到「{{ query.trim() }}」。试试游戏名、活动名或角色名。</p>
    </div>
    <footer class="search-foot"><span class="search-keys">↑ ↓ 选择，回车打开</span><span>{{ flat.length }} 项</span></footer>
  </dialog>
</template>

<style scoped>
.search-dialog { position:fixed; inset:0; margin:min(17dvh, 150px) auto auto; width:min(600px, calc(100vw - 32px)); max-width:none; max-height:calc(100dvh - min(17dvh, 150px) - 32px); padding:0; overflow:hidden; border:1px solid var(--card-border); border-radius:20px; background:var(--card-bg); color:var(--text); box-shadow:var(--modal-shadow, var(--popover-shadow)); }
.search-dialog[open] { display:flex; flex-direction:column; }
.search-dialog::backdrop { background:var(--scrim); }
.search-field { display:flex; align-items:center; gap:12px; padding:12px 14px 12px 22px; border-bottom:1px solid var(--border); color:var(--text-muted); }
.search-field input { flex:1; min-width:0; min-height:44px; padding:0; border:0; outline:0; background:transparent; color:var(--text); font-size:15px; }
.search-field input::placeholder { color:var(--text-muted); }
.search-close { display:grid; place-items:center; min-width:44px; min-height:44px; padding:0; border:0; border-radius:10px; background:transparent; }
.search-close kbd { padding:2px 6px; border-radius:5px; background:var(--control-track); color:var(--text-muted); font:500 11px/16px var(--font-sans); }
@media(hover:hover) and (pointer:fine) { .search-close:hover kbd { color:var(--text); } }
.search-results { flex:1; min-height:0; overflow-y:auto; overscroll-behavior:contain; padding:8px 10px 12px; }
.search-label { padding:10px 12px 6px; color:var(--text-muted); font-size:12px; }
.search-result { display:flex; align-items:center; gap:12px; min-height:56px; padding:9px 12px; border-radius:12px; color:var(--text); text-decoration:none; cursor:pointer; }
.search-result[aria-selected="true"] { background:var(--accent-soft); }
.search-mark { display:grid; place-items:center; flex-shrink:0; width:34px; height:34px; overflow:hidden; border-radius:10px; background:var(--mark-tone, var(--control-track)); color:var(--text-muted); box-shadow:inset 0 0 0 1px var(--card-border); }
.search-mark :deep(.game-icon) { width:100%; height:100%; font-size:14px; font-weight:600; }
.search-copy { display:grid; min-width:0; }
.search-copy strong { overflow:hidden; font-size:14px; font-weight:500; white-space:nowrap; text-overflow:ellipsis; }
.search-copy small { overflow:hidden; color:var(--text-muted); font-size:12px; white-space:nowrap; text-overflow:ellipsis; }
.search-kind { flex-shrink:0; margin-left:auto; padding:2px 7px; border-radius:5px; background:var(--control-track); color:var(--text-muted); font-size:12px; }
.search-empty { padding:28px 16px; color:var(--text-muted); font-size:13px; text-align:center; }
.search-foot { display:flex; justify-content:space-between; gap:12px; padding:10px 22px; border-top:1px solid var(--border); background:var(--panel-bg); color:var(--text-muted); font-size:12px; }
@media(pointer:coarse) { .search-keys { visibility:hidden; } }
@media(max-width:720px) { .search-dialog { margin-top:12px; max-height:calc(100dvh - 24px); width:calc(100vw - 24px); } .search-field input { font-size:16px; } }
</style>
