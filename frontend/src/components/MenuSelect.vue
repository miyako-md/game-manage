<script setup>
import { computed, nextTick, onBeforeUnmount, ref, useId } from 'vue'
import AppIcon from './AppIcon.vue'

// Web-rendered select (Option Pro MenuSelect / Radix select-only combobox).
// Focus stays on the trigger, which points at the highlighted option through
// aria-activedescendant; the list is fixed-positioned so cards and scroll
// containers never clip it. Options: [{ value, label }] or plain values.
const props = defineProps({
  modelValue: { type: [String, Number, Boolean], default: '' },
  options: { type: Array, required: true },
  label: { type: String, required: true },
  align: { type: String, default: 'start' },
  disabled: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'change'])
const id = useId()
const items = computed(() => props.options.map(option => (option !== null && typeof option === 'object' ? option : { value: option, label: String(option) })))
const same = (a, b) => String(a) === String(b)
const selectedIndex = computed(() => items.value.findIndex(item => same(item.value, props.modelValue)))
const open = ref(false)
const active = ref(-1)
const place = ref({ style: {}, up: false })
const trigger = ref(null)
const list = ref(null)
let typed = ''
let typedAt = 0

const EDGE = 12
const GAP = 6
function position() {
  const box = trigger.value?.getBoundingClientRect?.()
  if (!box) return
  const below = innerHeight - box.bottom - GAP - EDGE
  const above = box.top - GAP - EDGE
  const wanted = Math.min(288, items.value.length * 34 + 10)
  const up = below < wanted && above > below
  const style = { minWidth: `${box.width}px`, maxHeight: `${Math.max(120, Math.min(288, up ? above : below))}px` }
  if (up) style.bottom = `${innerHeight - box.top + GAP}px`
  else style.top = `${box.bottom + GAP}px`
  if (props.align === 'end') style.right = `${Math.max(EDGE, innerWidth - box.right)}px`
  else style.left = `${Math.max(EDGE, box.left)}px`
  place.value = { style, up }
}
// A list wider than the room left of the viewport edge slides back inside.
function clamp() {
  const el = list.value
  if (!el?.getBoundingClientRect || props.align === 'end') return
  const overflow = el.getBoundingClientRect().right - (innerWidth - EDGE)
  if (overflow > 0) place.value = { ...place.value, style: { ...place.value.style, left: `${Math.max(EDGE, parseFloat(place.value.style.left) - overflow)}px` } }
}
function scrollActive() {
  list.value?.querySelector?.('[data-active]')?.scrollIntoView?.({ block: 'nearest' })
}

function outside(event) {
  if (!trigger.value?.contains(event.target) && !list.value?.contains(event.target)) hide()
}
function scrolled(event) {
  if (!list.value?.contains(event.target)) hide()
}
function listen(on) {
  if (typeof document === 'undefined') return
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('pointerdown', outside, true)
  window[method]('scroll', scrolled, true)
  window[method]('resize', hide)
}

async function show(index = selectedIndex.value) {
  if (props.disabled || open.value || !items.value.length) return
  position()
  active.value = index >= 0 ? index : 0
  open.value = true
  listen(true)
  await nextTick()
  clamp()
  scrollActive()
}
function hide(returnFocus = false) {
  if (!open.value) return
  open.value = false
  listen(false)
  if (returnFocus === true) trigger.value?.focus?.()
}
function choose(index) {
  const item = items.value[index]
  if (!item) return
  if (!same(item.value, props.modelValue)) {
    emit('update:modelValue', item.value)
    emit('change', item.value)
  }
  hide(true)
}

function onKeydown(event) {
  const last = items.value.length - 1
  if (!open.value) {
    if (['ArrowDown', 'ArrowUp', 'Enter', ' '].includes(event.key)) {
      event.preventDefault()
      show(event.key === 'ArrowUp' && selectedIndex.value < 0 ? last : selectedIndex.value)
    }
    return
  }
  if (event.key === 'ArrowDown') active.value = Math.min(last, active.value + 1)
  else if (event.key === 'ArrowUp') active.value = Math.max(0, active.value - 1)
  else if (event.key === 'Home') active.value = 0
  else if (event.key === 'End') active.value = last
  else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); choose(active.value); return }
  else if (event.key === 'Escape') { event.preventDefault(); hide(true); return }
  else if (event.key === 'Tab') { hide(); return }
  else if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
    // Typeahead: letters typed in quick succession jump to the first match.
    const now = Date.now()
    typed = (now - typedAt > 600 ? '' : typed) + event.key.toLowerCase()
    typedAt = now
    const hit = items.value.findIndex(item => String(item.label).toLowerCase().startsWith(typed))
    if (hit >= 0) active.value = hit
    return
  } else return
  event.preventDefault()
  nextTick(scrollActive)
}

onBeforeUnmount(() => { if (open.value) listen(false) })
</script>

<template>
  <span class="menu-select" :class="{ open }">
    <button
      ref="trigger"
      type="button"
      class="menu-select-trigger"
      role="combobox"
      :aria-label="label"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="`${id}-list`"
      :aria-activedescendant="open && active >= 0 ? `${id}-${active}` : undefined"
      :disabled="disabled"
      @click="open ? hide() : show()"
      @keydown="onKeydown"
    ><span class="menu-select-value">{{ items[selectedIndex]?.label ?? '—' }}</span><AppIcon name="chevron" :size="12" /></button>
    <ul v-show="open" :id="`${id}-list`" ref="list" class="menu-select-list" :class="{ up: place.up }" role="listbox" :aria-label="label" :style="place.style">
      <li
        v-for="(item, index) in items"
        :id="`${id}-${index}`"
        :key="`${index}:${item.value}`"
        role="option"
        :data-value="String(item.value)"
        :aria-selected="index === selectedIndex"
        :data-active="index === active ? '' : undefined"
        @pointermove="active = index"
        @click="choose(index)"
      ><span>{{ item.label }}</span><AppIcon v-if="index === selectedIndex" name="check" :size="13" /></li>
    </ul>
  </span>
</template>

<style scoped>
.menu-select { display: inline-flex; position: relative; min-width: 0; max-width: 100%; vertical-align: middle; }
.menu-select-trigger { display: inline-flex; align-items: center; gap: 6px; width: 100%; min-width: 0; min-height: 30px; padding: 4px 8px 4px 10px; border: 1px solid var(--border-strong); border-radius: 7px; background: var(--card-bg); color: var(--text-body); font-size: 12px; font-weight: 400; line-height: 20px; text-align: left; box-shadow: 0 1px 2px rgba(24, 43, 68, .025); }
.menu-select-value { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.menu-select-trigger svg { flex-shrink: 0; color: var(--text-faint); transition: transform var(--duration-fast) var(--ease-smooth-out); }
.open .menu-select-trigger { border-color: color-mix(in srgb, var(--accent) 45%, var(--border-strong)); color: var(--accent-strong); }
.open .menu-select-trigger svg { transform: rotate(180deg); }
.menu-select-trigger:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 7px; }
.menu-select-trigger:disabled { cursor: not-allowed; opacity: .5; }
@media (hover: hover) and (pointer: fine) { .menu-select-trigger:not(:disabled):hover { background: var(--button-hover-bg); color: var(--text); } }
@media (pointer: coarse) { .menu-select-trigger { min-height: 40px; } }

/* Floating list: same surface and clock as Option Pro's select (200ms in). */
.menu-select-list { position: fixed; z-index: 60; max-width: calc(100vw - 24px); margin: 0; padding: 4px; overflow-y: auto; list-style: none; border: 1px solid var(--border-strong); border-radius: 10px; background: var(--card-bg); box-shadow: var(--popover-shadow); transform-origin: top left; animation: menu-select-in 200ms var(--ease-smooth-out); }
.menu-select-list.up { transform-origin: bottom left; }
@keyframes menu-select-in { from { opacity: 0; transform: scale(.97); } }
li { display: flex; align-items: center; justify-content: space-between; gap: 16px; min-height: 32px; padding: 6px 8px 6px 10px; border-radius: 6px; color: var(--text-body); font-size: 12px; line-height: 20px; white-space: nowrap; cursor: default; user-select: none; }
li[data-active] { background: var(--accent-soft); color: var(--accent-strong); }
li[aria-selected="true"] { font-weight: 600; }
li svg { flex-shrink: 0; color: var(--accent); }
@media (pointer: coarse) { li { min-height: 40px; } }
</style>
