<script setup>
import { computed } from 'vue'
import { skinOf } from '../game-themes.js'
// 帮助 lists the registry lines exactly as the notice carries them ("说明：指令"); 我的账号 lists
// one card per authorized account (an account title followed by its "字段：值" lines).
const props = defineProps({ data: { type: Object, required: true }, variant: { type: String, default: 'help' } })
const GAMES = { wuthering_waves: '鸣潮', nte: '异环', endfield: '终末地' }
const SLOTS = { 游戏: '换成 鸣潮 / 异环 / 终末地', 精确名称: '写角色全名', 实际绑定码: '写网站生成的绑定码' }
const SECTION_SUBTITLES = {
  绑定与账号: '初次使用请先绑定网站账号',
  总览与角色: '查看总览面板、角色列表、详情与攻略',
  资源与进度: '查询探索进度、成长记录与刷新缓存',
  抽卡: '查看各游戏抽卡与寻访记录',
  活动与日历: '获取近期活动提醒与版本排期日历',
  鸣潮专项: '鸣潮高难挑战与星声贝币收入',
  异环专项: '异环房产、车辆资产与官方配队',
  终末地专项: '终末地帝江号、光荣之路、挑战与干员配装',
}

const split = text => {
  const i = typeof text === 'string' ? text.indexOf('：') : -1
  return i > 0 && i < text.length - 1 && i <= 18 ? [text.slice(0, i), text.slice(i + 1)] : null
}
const gameOf = title => Object.keys(GAMES).find(id => title.startsWith(GAMES[id]))
const pad = n => String(n).padStart(2, '0')

function iconKeyFor(desc, cmd) {
  const s = `${desc} ${cmd}`
  if (/绑定/.test(s)) return 'bind'
  if (/我的账号|授权/.test(s)) return 'account'
  if (/看板|入口/.test(s)) return 'dashboard'
  if (/帮助/.test(s)) return 'help'
  if (/总览/.test(s)) return 'overview'
  if (/角色详情|干员配装/.test(s)) return 'detail'
  if (/攻略/.test(s)) return 'guide'
  if (/角色列表|角色/.test(s)) return 'roster'
  if (/探索/.test(s)) return 'explore'
  if (/进度/.test(s)) return 'progress'
  if (/刷新/.test(s)) return 'refresh'
  if (/抽卡|寻访/.test(s)) return 'gacha'
  if (/近期活动/.test(s)) return 'upcoming'
  if (/日历/.test(s)) return 'calendar'
  if (/活动/.test(s)) return 'events'
  if (/挑战/.test(s)) return 'combat'
  if (/资源/.test(s)) return 'resources'
  if (/房产/.test(s)) return 'house'
  if (/车辆/.test(s)) return 'vehicle'
  if (/配队|队伍/.test(s)) return 'team'
  if (/帝江号/.test(s)) return 'ship'
  if (/光荣之路/.test(s)) return 'honor'
  return 'default'
}

const groups = computed(() => (props.data.sections || []).map(section => ({
  title: section.title,
  subtitle: SECTION_SUBTITLES[section.title] || '',
  game: section.game,
  skin: skinOf(section.game) || undefined,
  items: (section.items || []).map(text => {
    const kv = split(text)
    if (!kv) return { text, icon: 'default' }
    return {
      desc: kv[0],
      icon: iconKeyFor(kv[0], kv[1]),
      tokens: kv[1].split(/\s+/).filter(Boolean).map(word => ({ text: word, slot: word in SLOTS })),
    }
  }),
})))
const common = computed(() => {
  const list = groups.value.filter(g => !g.game)
  const flags = new Array(list.length).fill(false)
  for (let i = 0; i < list.length - 1; i++) {
    if (list[i].items.length <= 2 && list[i + 1].items.length <= 2) {
      flags[i] = true
      flags[i + 1] = true
      i++
    }
  }
  return list.map((g, idx) => ({ ...g, isHalf: flags[idx] }))
})
const games = computed(() => {
  const list = groups.value.filter(g => g.game)
  const flags = new Array(list.length).fill(false)
  for (let i = 0; i < list.length - 1; i++) {
    if (list[i].items.length <= 2 && list[i + 1].items.length <= 2) {
      flags[i] = true
      flags[i + 1] = true
      i++
    }
  }
  return list.map((g, idx) => ({ ...g, isHalf: flags[idx] }))
})

function itemsGridClass(group) {
  const n = group.items.length
  if (n <= 1) return 'cols-1'
  if (n === 2) return group.isHalf ? 'cols-1' : 'cols-2'
  if (n === 4) return 'cols-2'
  if (n % 3 === 0) return 'cols-3'
  if (n % 3 === 2) return 'cols-6-balanced tail-2'
  return n >= 7 ? 'cols-6-balanced tail-4' : 'cols-3'
}
const slots = computed(() => [...new Set(groups.value.flatMap(g => g.items.flatMap(i => (i.tokens || []).filter(t => t.slot).map(t => t.text))))])
const accounts = computed(() => (props.data.sections || []).map(section => {
  const cards = []; const loose = []
  for (const text of section.items || []) {
    const kv = split(text)
    if (!kv) {
      const game = gameOf(text)
      cards.push({ title: text, game, skin: skinOf(game) || undefined, fields: [] })
      continue
    }
    const field = { label: kv[0], value: kv[1], tone: /重新授权|不可用|失效/.test(kv[1]) ? 'warn' : kv[1] === '已授权' ? 'ok' : '' }
    if (cards.length) cards.at(-1).fields.push(field)
    else loose.push(field)
  }
  return { title: section.title, cards, loose }
}))
</script>
<template>
  <div class="help-sheet" :class="'hs-' + variant">
    <template v-if="variant === 'help'">
      <p v-if="slots.length" class="hs-legend">
        <span class="hs-legend-key">虚线框需替换</span>
        <span v-for="slot in slots" :key="slot" class="hs-legend-item">
          <span class="hs-slot">{{ slot }}</span>{{ SLOTS[slot] }}
        </span>
      </p>

      <section
        v-for="(g, i) in common"
        :key="g.title + i"
        class="hs-group"
        :class="g.isHalf ? 'is-half' : 'is-full'"
        data-render-block
      >
        <header class="hs-head hs-band-head">
          <span class="hs-square" aria-hidden="true"></span>
          <span class="hs-index number">{{ pad(i + 1) }}</span>
          <h2>{{ g.title }}</h2>
          <span v-if="g.subtitle" class="hs-sub">{{ g.subtitle }}</span>
          <small>{{ g.items.length }} 条</small>
        </header>
        <ul class="hs-items" :class="itemsGridClass(g)">
          <li v-for="(item, idx) in g.items" :key="idx" class="hs-item">
            <span class="hs-icon-tile" aria-hidden="true">
              <svg viewBox="0 0 24 24" class="hs-svg">
                <path v-if="item.icon === 'bind'" d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
                <path v-else-if="item.icon === 'account'" d="M12 12a4 4 0 1 0-4-4 4 4 0 0 0 4 4zm0 2c-4.4 0-8 2.2-8 5v2h16v-2c0-2.8-3.6-5-8-5z" fill="currentColor" />
                <path v-else-if="item.icon === 'dashboard'" d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" fill="currentColor" />
                <path v-else-if="item.icon === 'help'" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm0 15.2a1.2 1.2 0 1 1 1.2-1.2 1.2 1.2 0 0 1-1.2 1.2zm1.8-5.1c-.8.5-1 .9-1 1.7h-1.8c0-1.4.4-2.1 1.5-2.8.8-.5 1.2-.9 1.2-1.6a1.7 1.7 0 0 0-3.4 0H8.5a3.5 3.5 0 0 1 7 0c0 1.3-.7 2-1.7 2.7z" fill="currentColor" />
                <path v-else-if="item.icon === 'overview'" d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2Z" fill="currentColor" />
                <path v-else-if="item.icon === 'roster'" d="M4 5h7v6H4zm9 0h7v6h-7zM4 13h7v6H4zm9 0h7v6h-7z" fill="currentColor" />
                <path v-else-if="item.icon === 'detail'" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm2 16H8v-2h8zm0-4H8v-2h8zm-3-5V3.5L18.5 9z" fill="currentColor" />
                <path v-else-if="item.icon === 'guide'" d="M4 4.5A2.5 2.5 0 0 1 6.5 2H20v18H6.5A2.5 2.5 0 0 0 4 22.5V4.5zm3 1.5v2h9V6H7zm0 4v2h7v-2H7z" fill="currentColor" />
                <path v-else-if="item.icon === 'explore'" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm2.2 12.2L7 17l2.8-7.2L17 7z" fill="currentColor" />
                <path v-else-if="item.icon === 'progress'" d="M4 18h4V10H4zm6 0h4V5h-4zm6 0h4v-7h-4z" fill="currentColor" />
                <path v-else-if="item.icon === 'refresh'" d="M17.65 6.35A7.95 7.95 0 0 0 12 4a8 8 0 1 0 7.75 10h-2.1A6 6 0 1 1 12 6a5.9 5.9 0 0 1 4.22 1.78L13 11h7V4z" fill="currentColor" />
                <path v-else-if="item.icon === 'gacha'" d="M12 2l2.6 6.2L21 9.3l-4.8 4.4L17.6 20 12 16.7 6.4 20l1.4-6.3L3 9.3l6.4-1.1z" fill="currentColor" />
                <path v-else-if="item.icon === 'upcoming'" d="M12 2a10 10 0 1 0 10 10A10 10 0 0 0 12 2zm1 11h-5V7h2v4h3z" fill="currentColor" />
                <path v-else-if="item.icon === 'events'" d="M13 2L4 14h7l-1 8 9-12h-7z" fill="currentColor" />
                <path v-else-if="item.icon === 'calendar'" d="M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14z" fill="currentColor" />
                <path v-else-if="item.icon === 'combat'" d="M20.7 3.3l-4.2.7-7.9 7.9-2.1-2.1-1.4 1.4 2.1 2.1-4 4 1.4 1.4 4-4 2.1 2.1 1.4-1.4-2.1-2.1 7.9-7.9.7-4.2zM5 3l3.6.6-1.4 1.4 3.4 3.4-1.4 1.4L5.8 6.4 4.4 7.8z" fill="currentColor" />
                <path v-else-if="item.icon === 'resources'" d="M12 2l8 6-8 14L4 8l8-6zm0 3.2L6.8 9h10.4L12 5.2z" fill="currentColor" />
                <path v-else-if="item.icon === 'house'" d="M12 3L2 12h3v9h6v-6h2v6h6v-9h3z" fill="currentColor" />
                <path v-else-if="item.icon === 'vehicle'" d="M18.9 6c-.2-.6-.8-1-1.4-1h-11c-.7 0-1.2.4-1.4 1L3 12v8h2v-2h14v2h2v-8l-2.1-6zM6.5 15a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 6.5 15zm11 0a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 17.5 15zM5 10l1.5-4.5h11L19 10z" fill="currentColor" />
                <path v-else-if="item.icon === 'team'" d="M16 11a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm-8 0a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm0 2c-2.3 0-7 1.2-7 3.5V19h14v-2.5c0-2.3-4.7-3.5-7-3.5zm8 0c-.3 0-.6 0-1 .1 1.2.8 2 2 2 3.4V19h6v-2.5c0-2.3-4.7-3.5-7-3.5z" fill="currentColor" />
                <path v-else-if="item.icon === 'ship'" d="M12 2L4 7v10l8 5 8-5V7l-8-5zm0 3.2L17 8v8l-5 3.1L7 16V8l5-2.8z" fill="currentColor" />
                <path v-else-if="item.icon === 'honor'" d="M12 2a6 6 0 0 0-6 6c0 2.4 1.4 4.5 3.5 5.4L8 22l4-2.2L16 22l-1.5-8.6A6 6 0 0 0 18 8a6 6 0 0 0-6-6zm0 9a3 3 0 1 1 3-3 3 3 0 0 1-3 3z" fill="currentColor" />
                <polygon v-else points="12,3 21,12 12,21 3,12" fill="currentColor" />
              </svg>
            </span>
            <div class="hs-item-body">
              <template v-if="item.tokens">
                <span class="hs-desc">{{ item.desc }}</span>
                <code class="hs-cmd"><span v-for="(t, k) in item.tokens" :key="k" :class="{ 'hs-slot': t.slot }">{{ t.text }}</span></code>
              </template>
              <span v-else class="hs-desc">{{ item.text }}</span>
            </div>
          </li>
        </ul>
      </section>

      <div v-if="games.length" class="hs-games" :class="'count-' + games.length">
        <section
          v-for="(g, i) in games"
          :key="g.title + i"
          class="hs-group hs-game"
          :class="g.isHalf ? 'is-half' : 'is-full'"
          :data-skin="g.skin"
          data-render-block
        >
          <header class="hs-head hs-band-head">
            <span class="hs-mono">{{ GAMES[g.game][0] }}</span>
            <h2>{{ g.title }}</h2>
            <span v-if="g.subtitle" class="hs-sub">{{ g.subtitle }}</span>
            <small>{{ g.items.length }} 条</small>
          </header>
          <ul class="hs-items" :class="itemsGridClass(g)">
            <li v-for="(item, idx) in g.items" :key="idx" class="hs-item">
              <span class="hs-icon-tile" aria-hidden="true">
                <svg viewBox="0 0 24 24" class="hs-svg">
                  <path v-if="item.icon === 'detail'" d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm2 16H8v-2h8zm0-4H8v-2h8zm-3-5V3.5L18.5 9z" fill="currentColor" />
                  <path v-else-if="item.icon === 'gacha'" d="M12 2l2.6 6.2L21 9.3l-4.8 4.4L17.6 20 12 16.7 6.4 20l1.4-6.3L3 9.3l6.4-1.1z" fill="currentColor" />
                  <path v-else-if="item.icon === 'combat'" d="M20.7 3.3l-4.2.7-7.9 7.9-2.1-2.1-1.4 1.4 2.1 2.1-4 4 1.4 1.4 4-4 2.1 2.1 1.4-1.4-2.1-2.1 7.9-7.9.7-4.2zM5 3l3.6.6-1.4 1.4 3.4 3.4-1.4 1.4L5.8 6.4 4.4 7.8z" fill="currentColor" />
                  <path v-else-if="item.icon === 'resources'" d="M12 2l8 6-8 14L4 8l8-6zm0 3.2L6.8 9h10.4L12 5.2z" fill="currentColor" />
                  <path v-else-if="item.icon === 'house'" d="M12 3L2 12h3v9h6v-6h2v6h6v-9h3z" fill="currentColor" />
                  <path v-else-if="item.icon === 'vehicle'" d="M18.9 6c-.2-.6-.8-1-1.4-1h-11c-.7 0-1.2.4-1.4 1L3 12v8h2v-2h14v2h2v-8l-2.1-6zM6.5 15a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 6.5 15zm11 0a1.5 1.5 0 1 1 1.5-1.5A1.5 1.5 0 0 1 17.5 15zM5 10l1.5-4.5h11L19 10z" fill="currentColor" />
                  <path v-else-if="item.icon === 'team'" d="M16 11a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm-8 0a3 3 0 1 0-3-3 3 3 0 0 0 3 3zm0 2c-2.3 0-7 1.2-7 3.5V19h14v-2.5c0-2.3-4.7-3.5-7-3.5zm8 0c-.3 0-.6 0-1 .1 1.2.8 2 2 2 3.4V19h6v-2.5c0-2.3-4.7-3.5-7-3.5z" fill="currentColor" />
                  <path v-else-if="item.icon === 'ship'" d="M12 2L4 7v10l8 5 8-5V7l-8-5zm0 3.2L17 8v8l-5 3.1L7 16V8l5-2.8z" fill="currentColor" />
                  <path v-else-if="item.icon === 'honor'" d="M12 2a6 6 0 0 0-6 6c0 2.4 1.4 4.5 3.5 5.4L8 22l4-2.2L16 22l-1.5-8.6A6 6 0 0 0 18 8a6 6 0 0 0-6-6zm0 9a3 3 0 1 1 3-3 3 3 0 0 1-3 3z" fill="currentColor" />
                  <polygon v-else points="12,3 21,12 12,21 3,12" fill="currentColor" />
                </svg>
              </span>
              <div class="hs-item-body">
                <template v-if="item.tokens">
                  <span class="hs-desc">{{ item.desc }}</span>
                  <code class="hs-cmd"><span v-for="(t, k) in item.tokens" :key="k" :class="{ 'hs-slot': t.slot }">{{ t.text }}</span></code>
                </template>
                <span v-else class="hs-desc">{{ item.text }}</span>
              </div>
            </li>
          </ul>
        </section>
      </div>
    </template>

    <template v-else>
      <section v-for="(s, i) in accounts" :key="(s.title || '') + i" class="hs-group hs-accounts" data-render-block>
        <header class="hs-head">
          <span class="hs-index number">{{ pad(i + 1) }}</span>
          <h2>{{ s.title || '账号' }}</h2>
          <small>{{ s.cards.length }} 个账号</small>
        </header>
        <dl v-if="s.loose.length" class="hs-fields">
          <div v-for="(f, fi) in s.loose" :key="fi">
            <dt>{{ f.label }}</dt>
            <dd>{{ f.value }}</dd>
          </div>
        </dl>
        <div class="hs-account-grid">
          <article v-for="(card, ci) in s.cards" :key="ci" class="hs-account" :data-skin="card.skin">
            <header>
              <span class="hs-mono">{{ card.game ? GAMES[card.game][0] : '号' }}</span>
              <h3>{{ card.title }}</h3>
            </header>
            <dl class="hs-fields">
              <div v-for="(f, fi) in card.fields" :key="fi" :class="f.tone && 'is-' + f.tone">
                <dt>{{ f.label }}</dt>
                <dd>{{ f.value }}</dd>
              </div>
            </dl>
          </article>
        </div>
      </section>
    </template>

    <aside v-if="data.notices?.length" class="hs-notes" data-render-block>
      <h2>使用说明</h2>
      <p v-for="(n, idx) in data.notices" :key="idx">{{ n }}</p>
    </aside>
  </div>
</template>
<style>
/* 帮助 / 我的账号: High-craft balanced command matrix on unified overview skins (D3 / D7 / D9). */
.help-sheet {
  display: grid;
  gap: 16px;
  margin-top: 22px;
}

.help-sheet.hs-help {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: stretch;
}

.help-sheet .hs-legend,
.help-sheet .hs-games,
.help-sheet .hs-notes,
.help-sheet .hs-group.is-full {
  grid-column: 1 / -1;
}

.help-sheet .hs-group.is-half {
  display: flex;
  flex-direction: column;
}

.help-sheet .hs-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin: 0;
  padding: 10px 16px;
  font-size: 17px;
  line-height: 1.45;
  color: var(--skin-muted);
  background: rgba(var(--skin-tint-rgb), .06);
  border: 1px solid rgba(var(--skin-tint-rgb), .18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .05);
  border-radius: var(--skin-radius-tile);
}

.help-sheet .hs-legend-key {
  color: var(--skin-accent);
  font-weight: 700;
}

.help-sheet .hs-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.help-sheet .hs-legend .hs-slot {
  font-size: 17px;
}

.help-sheet .hs-group {
  background: linear-gradient(180deg, rgba(255, 255, 255, .03) 0%, rgba(0, 0, 0, .06) 100%), var(--skin-surface);
  border: 1px solid rgba(var(--skin-tint-rgb), .18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .07);
  border-radius: var(--skin-radius-card);
  padding: 14px 18px 16px;
  min-width: 0;
}

.help-sheet .hs-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding-bottom: 10px;
  margin-bottom: 12px;
  border-bottom: 1px solid rgba(var(--skin-tint-rgb), .14);
}

.help-sheet .hs-band-head {
  padding: 8px 14px;
  margin-bottom: 12px;
  border: 1px solid rgba(var(--skin-tint-rgb), .18);
  border-radius: var(--skin-radius-tile);
  background: rgba(var(--skin-tint-rgb), .07);
}

.help-sheet .hs-square {
  width: 12px;
  height: 12px;
  flex: none;
  border-radius: 2px;
  background: var(--skin-accent);
}

.help-sheet .hs-head h2 {
  font-size: 22px;
  line-height: 1.3;
  font-weight: 800;
  color: var(--skin-ink);
  margin: 0;
}

.help-sheet .hs-sub {
  font-size: 17px;
  line-height: 1.35;
  color: var(--skin-muted);
}

.help-sheet .hs-head small {
  margin-left: auto;
  font-size: 17px;
  font-weight: 600;
  color: var(--skin-muted);
}

.help-sheet .hs-index {
  font-size: 17px;
  font-weight: 800;
  letter-spacing: .06em;
  color: var(--skin-accent);
}

.help-sheet .hs-mono {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: var(--skin-radius-tile);
  background: var(--skin-accent);
  color: var(--skin-on-accent);
  font-size: 18px;
  font-weight: 800;
}

.help-sheet .hs-items {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.help-sheet .hs-items.cols-1 {
  grid-template-columns: minmax(0, 1fr);
}

.help-sheet .hs-items.cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.help-sheet .hs-items.cols-3 {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.help-sheet .hs-items.cols-6-balanced {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.help-sheet .hs-items.cols-6-balanced > .hs-item {
  grid-column: span 2;
}

.help-sheet .hs-items.cols-6-balanced.tail-2 > .hs-item:nth-last-child(-n + 2),
.help-sheet .hs-items.cols-6-balanced.tail-4 > .hs-item:nth-last-child(-n + 4) {
  grid-column: span 3;
}

.help-sheet .hs-item {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border-radius: var(--skin-radius-tile);
  background: rgba(8, 10, 16, .42);
  border: 1px solid rgba(var(--skin-tint-rgb), .14);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .04);
}

.help-sheet .hs-icon-tile {
  display: inline-grid;
  place-items: center;
  width: 44px;
  height: 44px;
  flex: none;
  border-radius: 10px;
  background: rgba(var(--skin-tint-rgb), .11);
  border: 1px solid rgba(var(--skin-tint-rgb), .26);
  color: var(--skin-accent);
}

.help-sheet .hs-svg {
  width: 22px;
  height: 22px;
}

.help-sheet .hs-item-body {
  display: grid;
  gap: 4px;
  min-width: 0;
  flex: 1;
}

.help-sheet .hs-desc {
  font-size: 18px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--skin-ink);
  overflow-wrap: anywhere;
}

.help-sheet .hs-cmd {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 5px;
  font-family: inherit;
  font-size: 17px;
  line-height: 1.35;
  font-weight: 700;
  color: var(--skin-accent);
}

.help-sheet .hs-slot {
  padding: 0 6px;
  border: 1px dashed var(--skin-line-strong);
  border-radius: 6px;
  color: var(--skin-ink);
  background: rgba(var(--skin-tint-rgb), .1);
  font-weight: 600;
}

.help-sheet .hs-games {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-items: stretch;
}

.help-sheet .hs-games.count-1 {
  grid-template-columns: minmax(0, 1fr);
}

.help-sheet .hs-game {
  border-color: rgba(var(--skin-tint-rgb), .24);
  border-top: 2px solid var(--skin-accent);
}

.help-sheet .hs-account-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.help-sheet .hs-account {
  padding: 16px 18px;
  border-radius: var(--skin-radius-tile);
  background: rgba(var(--skin-tint-rgb), .06);
  border: 1px solid rgba(var(--skin-tint-rgb), .2);
}

.help-sheet .hs-account header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.help-sheet .hs-account h3 {
  font-size: 21px;
  line-height: 1.4;
  font-weight: 700;
  color: var(--skin-ink);
  margin: 0;
}

.help-sheet .hs-fields {
  display: grid;
  gap: 6px;
  margin: 0;
}

.help-sheet .hs-fields > div {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  border-top: 1px solid rgba(var(--skin-tint-rgb), .12);
}

.help-sheet .hs-fields dt {
  font-size: 18px;
  color: var(--skin-muted);
}

.help-sheet .hs-fields dd {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--skin-ink);
  text-align: right;
}

.help-sheet .hs-fields .is-ok dd {
  color: var(--skin-accent);
}

.help-sheet .hs-fields .is-warn dd {
  padding: 1px 10px;
  border-radius: var(--skin-radius-chip);
  background: #f0b54a;
  color: #1b1406;
}

.help-sheet .hs-notes {
  display: grid;
  gap: 6px;
  padding: 14px 18px;
  border-radius: var(--skin-radius-card);
  border: 1px solid var(--skin-line);
  background: rgba(var(--skin-tint-rgb), .05);
}

.help-sheet .hs-notes h2 {
  font-size: 19px;
  line-height: 1.4;
  font-weight: 700;
  color: var(--skin-accent);
  margin: 0 0 2px;
}

.help-sheet .hs-notes p {
  font-size: 18px;
  line-height: 1.55;
  color: var(--skin-ink);
  margin: 0;
}
</style>
