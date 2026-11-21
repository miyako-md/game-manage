<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '../calendar.js'
import { list, starCount, value } from '../wuwa-display.js'
import { echoBadges, echoStatFlags, gradeTier, scoreHero, statTone } from '../assessment-display.js'
import { namedIcon } from '../wuwa-icons.js'
import wuwaIcons from '../wuwa-icon-catalog.js'
import { asset } from './models.js'
import {
  WUWA_CHAR_META,
  chainLabel,
  normalizeElementKey,
  normalizeWeaponKey,
  resolveWuwaIcon,
} from './role-meta.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import RoleStatIcon from './RoleStatIcon.vue'

const props = defineProps({ data: { type: Object, default: () => ({}) } })

const role = computed(() => props.data.role || {})
const meta = computed(() => {
  const name = role.value.role_name || ''
  return WUWA_CHAR_META[name] || WUWA_CHAR_META[name.replace(/（.*?）$/, '')] || {}
})

const pictures = computed(() => [...new Set([
  asset(safeUrl(role.value.role_pic_url)),
  asset(safeUrl(props.data.role_skin?.skin_icon)),
  asset(safeUrl(role.value.role_icon_url)),
  resolveWuwaIcon(role.value.role_name, role.value.role_id, null),
].filter(Boolean))])
const failed = ref(0)
watch(pictures, () => { failed.value = 0 })
const art = computed(() => pictures.value[failed.value] || '')

const stars = computed(() => starCount(role.value.star_level ?? meta.value.star))
const elemName = computed(() => role.value.attribute_name || meta.value.attr || '')
const elemKey = computed(() => normalizeElementKey(elemName.value))
const weaponTypeName = computed(() => role.value.weapon_type_name || meta.value.weapon || '')
const weaponKey = computed(() => normalizeWeaponKey(weaponTypeName.value))

const attributes = computed(() => list(Array.isArray(props.data.role_attribute_list) ? props.data.role_attribute_list : role.value.role_attribute_list))
const weapon = computed(() => props.data.weapon_data || null)
const weaponIcon = computed(() => {
  const w = weapon.value?.weapon
  if (!w) return ''
  return asset(safeUrl(w.weapon_icon)) || asset(namedIcon('weapons', w.weapon_name))
})
const weaponFailed = ref(false)
watch(weaponIcon, () => { weaponFailed.value = false })

const skills = computed(() => list(props.data.skill_list))
const chains = computed(() => list(props.data.chain_list))
const unlocked = computed(() => chains.value.filter(c => c.unlocked === true).length)

const pillFacts = computed(() => [
  elemName.value || null,
  weaponTypeName.value || null,
  role.value.breach != null ? `突破 ${role.value.breach}` : null,
  chains.value.length ? chainLabel('wuthering_waves', unlocked.value) : null,
].filter(Boolean))

const failedUrls = ref(new Set())
watch(() => props.data, () => { failedUrls.value = new Set() })
const markFailed = url => {
  if (url) failedUrls.value = new Set([...failedUrls.value, url])
}
const liveAsset = url => {
  const resolved = asset(safeUrl(url))
  return resolved && !failedUrls.value.has(resolved) ? resolved : ''
}

const skillIconUrl = entry => {
  const direct = liveAsset(entry?.skill?.icon_url)
  if (direct) return direct
  const byCat = wuwaIcons.characters?.[String(role.value.role_id)]?.skills?.[entry?.skill?.type]?.icon
  return liveAsset(byCat)
}

const romanNumerals = ['Ⅰ', 'Ⅱ', 'Ⅲ', 'Ⅳ', 'Ⅴ', 'Ⅵ']
const chainNumeral = (chain, idx) => romanNumerals[(Number(chain?.order) || idx + 1) - 1] || String(chain?.order || idx + 1)

const rawEchoes = computed(() => props.data.phantom_data?.equip_phantom_list)
const echoes = computed(() => list(rawEchoes.value).filter(e => typeof e === 'object'))
const echoIconUrl = echo => liveAsset(echo?.phantom_prop?.icon_url) || liveAsset(namedIcon('echoes', echo?.phantom_prop?.name))
const fetterIconUrl = echo => liveAsset(echo?.fetter_detail?.icon_url) || liveAsset(namedIcon('sets', echo?.fetter_detail?.name))

const score = computed(() => props.data.assessment || null)
const hero = computed(() => scoreHero(score.value))
const heroTier = computed(() => gradeTier(hero.value.grade))
const badges = computed(() => echoBadges(score.value, rawEchoes.value))
const flags = computed(() => echoStatFlags(score.value, rawEchoes.value))
const rows = v => Array.isArray(v) ? v.flatMap((p, j) => p && typeof p === 'object' ? [[p, j]] : []) : []
const tone = (echo, group, j) => statTone(flags.value.get(echo)?.get(`${group}:${j}`))
const totals = computed(() => list(props.data.equip_phantom_add_prop_list).filter(p => p?.attribute_name != null))

const attrTone = name => {
  const s = String(name || '')
  if (/共鸣效率/.test(s)) return 'is-cyan'
  if (/暴击|伤害加成/.test(s)) return 'is-gold'
  return ''
}
</script>
<template>
  <div class="rd-sheet role-sheet wuwa-role-detail-sheet" :data-element="elemKey || undefined">
    <!-- 1. Showcase Split Hero: Tall Left Portrait Card + Right Attributes & Weapon -->
    <section class="rd-hero" data-render-block>
      <div class="rd-portrait-card">
        <img
          v-if="art"
          :key="art"
          :src="art"
          :alt="role.role_name || '角色'"
          class="rd-portrait-img"
          @error="failed++"
        />
        <div v-else class="rd-portrait-fallback" aria-hidden="true">
          <span>{{ (role.role_name || '?').slice(0, 1) }}</span>
        </div>

        <div class="rd-top-left">
          <span v-if="stars" class="rd-stars-pill" :aria-label="`${stars} 星`">{{ '★'.repeat(stars) }}</span>
          <span v-if="data.role_skin?.skin_name" class="rd-skin-pill">{{ data.role_skin.skin_name }}</span>
        </div>

        <div class="rd-top-right">
          <span class="ao-elem-badge rd-badge-circle" :class="'elem-' + elemKey" :title="elemName">
            <svg v-if="elemKey === 'spectro'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2L14.2 8.8L21 9.5L15.6 13.8L17.5 20.5L12 16.6L6.5 20.5L8.4 13.8L3 9.5L9.8 8.8Z" fill="#ffe17d" />
            </svg>
            <svg v-else-if="elemKey === 'havoc'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M14.5 3.5A8.5 8.5 0 1 0 20.5 16.5A7 7 0 1 1 14.5 3.5Z" fill="#ff7aa8" />
              <circle cx="15" cy="9" r="2.2" fill="#ffd1e2" />
            </svg>
            <svg v-else-if="elemKey === 'electro'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M13.5 2L5.5 13H11.5L10 22L18.5 10.5H12.5L13.5 2Z" fill="#d09bff" />
            </svg>
            <svg v-else-if="elemKey === 'fusion'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12.5 2.5C12.5 2.5 18.5 7.5 18.5 13.5C18.5 17.6 15.4 21 11.5 21C7.6 21 5 17.6 5 13.8C5 10.5 7.2 7.8 7.2 7.8C7.2 7.8 7 10.8 9.2 11.5C8.5 8.2 12.5 2.5 12.5 2.5Z" fill="#ff8563" />
            </svg>
            <svg v-else-if="elemKey === 'glacio'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5Z" fill="#7be0ff" />
            </svg>
            <svg v-else-if="elemKey === 'aero'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 13C7.5 8 13.5 7 19.5 10C15.5 12.5 11.5 13.5 4 13ZM6 17.5C10 14.5 15 14 20 15.5C16.5 18 11.5 19 6 17.5Z" fill="#6bf2c3" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <polygon points="12,3 21,12 12,21 3,12" fill="#dbe3f0" />
            </svg>
          </span>

          <span v-if="weaponTypeName" class="rd-badge-circle rd-weapon-circle" :title="weaponTypeName">
            <svg v-if="weaponKey === 'broadblade'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M18 3L21 6L9 18L5 19L6 15L18 3ZM4 20L7 17L9 19L6 22L4 20Z" fill="#e6cfa3" />
            </svg>
            <svg v-else-if="weaponKey === 'pistols'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7H19L21 10L17 12H11L9 18H5L7 12H4V7Z" fill="#e6cfa3" />
            </svg>
            <svg v-else-if="weaponKey === 'gauntlets'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 8L11 4L18 7L19 15L13 20L6 16Z" fill="#e6cfa3" />
            </svg>
            <svg v-else-if="weaponKey === 'rectifier'" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="5" fill="none" stroke="#e6cfa3" stroke-width="2" />
              <path d="M12 2V6M12 18V22M2 12H6M18 12H22" stroke="#e6cfa3" stroke-width="2" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <path d="M19 3L21 5L8.5 17.5L6.5 15.5L19 3ZM5 17L7 19L4 22L2 20L5 17Z" fill="#e6cfa3" />
            </svg>
          </span>
        </div>

        <div class="rd-portrait-foot">
          <div class="rd-portrait-title">
            <strong class="rd-char-name">{{ role.role_name || '角色' }}</strong>
            <b class="rd-char-lv">Lv.{{ value(role.level) }}</b>
          </div>
          <div v-if="pillFacts.length" class="rd-portrait-pills">
            <span v-for="fact in pillFacts" :key="fact" class="rd-fact-chip">{{ fact }}</span>
          </div>
        </div>
      </div>

      <div class="rd-side-col">
        <!-- Block 1: Attributes -->
        <section class="rd-panel">
          <div class="rd-mini-head">
            <i class="rd-mini-line left" aria-hidden="true"></i>
            <h3>属性</h3>
            <i class="rd-mini-line right" aria-hidden="true"></i>
          </div>
          <div v-if="attributes.length" class="rd-attr-list" :class="{ 'is-two-col': attributes.length > 9 }">
            <div v-for="(p, i) in attributes" :key="i" class="rd-attr-row">
              <RoleStatIcon :src="p.icon_url || namedIcon('stats', p.attribute_name)" :name="p.attribute_name" :size="20" />
              <span class="rd-attr-k">{{ p.attribute_name || '未知属性' }}</span>
              <b class="rd-attr-v" :class="attrTone(p.attribute_name)">{{ value(p.attribute_value) }}</b>
            </div>
          </div>
          <p v-else class="rd-muted">未提供属性</p>
        </section>

        <!-- Block 2: Weapon Info -->
        <section class="rd-panel">
          <div class="rd-mini-head">
            <i class="rd-mini-line left" aria-hidden="true"></i>
            <h3>武器信息</h3>
            <i class="rd-mini-line right" aria-hidden="true"></i>
          </div>
          <div v-if="weapon" class="rd-weapon-card">
            <div class="rd-weapon-head">
              <div class="rd-weapon-frame">
                <img
                  v-if="weaponIcon && !weaponFailed"
                  :src="weaponIcon"
                  :alt="weapon.weapon?.weapon_name || '武器'"
                  class="rd-weapon-img"
                  @error="weaponFailed = true"
                />
                <svg v-else viewBox="0 0 24 24" class="rd-weapon-svg" aria-hidden="true">
                  <path d="M19 3L21 5L8.5 17.5L6.5 15.5L19 3ZM5 17L7 19L4 22L2 20L5 17Z" fill="currentColor" />
                </svg>
              </div>
              <div class="rd-weapon-copy">
                <div class="rd-weapon-title-row">
                  <strong class="rd-weapon-name">{{ weapon.weapon?.weapon_name || '名称未知' }}</strong>
                  <span class="rd-weapon-pill">谐振 {{ value(weapon.reson_level) }}</span>
                </div>
                <div class="rd-weapon-sub">
                  <span>Lv.{{ value(weapon.level) }} · 突破 {{ value(weapon.breach) }}</span>
                  <span v-if="starCount(weapon.weapon?.weapon_star_level)" class="rd-weapon-stars">{{ '★'.repeat(starCount(weapon.weapon.weapon_star_level)) }}</span>
                </div>
              </div>
            </div>
            <div v-if="list(weapon.main_prop_list).length" class="rd-weapon-props">
              <div v-for="(p, i) in list(weapon.main_prop_list)" :key="i" class="rd-attr-row">
                <RoleStatIcon :src="p.icon_url || namedIcon('stats', p.attribute_name)" :name="p.attribute_name" :size="18" />
                <span class="rd-attr-k">{{ p.attribute_name }}</span>
                <b class="rd-attr-v">{{ value(p.attribute_value) }}</b>
              </div>
            </div>
          </div>
          <p v-else class="rd-muted">暂无装备武器数据</p>
        </section>
      </div>
    </section>

    <!-- 2. Compact Skills Strip -->
    <section v-if="skills.length" class="rd-skills-band" data-render-block>
      <div class="rd-skills-row" :class="skills.length <= 5 ? 'is-inline-five' : 'is-grid-3'">
        <article v-for="(entry, i) in skills" :key="i" class="rd-skill-tile">
          <div class="rd-skill-frame">
            <img
              v-if="skillIconUrl(entry)"
              :src="skillIconUrl(entry)"
              :alt="entry.skill?.name || '技能'"
              class="rd-skill-img"
              @error="markFailed(skillIconUrl(entry))"
            />
            <svg v-else viewBox="0 0 24 24" class="rd-skill-svg" aria-hidden="true">
              <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2Z" fill="currentColor" />
            </svg>
          </div>
          <div class="rd-skill-info">
            <span class="rd-skill-type">{{ entry.skill?.type || '技能' }}</span>
            <span class="rd-skill-name">{{ entry.skill?.name || '未知技能' }}</span>
          </div>
          <b class="rd-skill-lv">Lv.{{ value(entry.level) }}</b>
        </article>
      </div>
    </section>

    <!-- 3. Resonance Chain Crest Bar -->
    <section v-if="chains.length" class="rd-chains-band" data-render-block>
      <div class="rd-chains-row">
        <div
          v-for="(chain, i) in chains"
          :key="i"
          class="rd-chain-node"
          :class="{ 'is-locked': chain.unlocked !== true }"
          :aria-label="`${chain.name || '共鸣链'}：${chain.unlocked === true ? '已解锁' : chain.unlocked === false ? '未解锁' : '解锁状态未知'}`"
        >
          <div class="rd-chain-crest">
            <svg viewBox="0 0 64 64" class="rd-chain-svg" aria-hidden="true">
              <polygon points="32,3 59,20 59,44 32,61 5,44 5,20" class="rd-chain-poly" />
              <polygon points="32,8 54,22 54,42 32,56 10,42 10,22" class="rd-chain-poly-inner" />
            </svg>
            <img
              v-if="liveAsset(chain.icon_url)"
              :src="liveAsset(chain.icon_url)"
              :alt="chain.name || '共鸣链'"
              class="rd-chain-img"
              @error="markFailed(liveAsset(chain.icon_url))"
            />
            <span v-else class="rd-chain-roman">{{ chainNumeral(chain, i) }}</span>
            <i class="rd-chain-order">{{ value(chain.order ?? i + 1) }}</i>
          </div>
          <span class="rd-chain-name">{{ chain.name }}</span>
        </div>
      </div>
    </section>

    <!-- 4. Echoes Information & 3-Column Showcase Grid -->
    <section class="ao-section rd-equip-section">
      <OverviewSectionHead title="声骸信息" :meta="'总 COST ' + value(data.phantom_data?.cost)" />

      <div v-if="echoes.length" class="rd-equip-wrap">
        <div v-if="hero.source" class="rd-template-bar">
          <span class="rd-template-tag">评分来源</span>
          <span class="rd-template-text">{{ hero.source }}</span>
        </div>

        <div v-if="totals.length" class="rd-totals-bar" data-render-block>
          <div v-for="(p, i) in totals" :key="i" class="rd-total-cell">
            <RoleStatIcon :src="p.icon_url || namedIcon('stats', p.attribute_name)" :name="p.attribute_name" :size="18" />
            <span class="rd-total-k">{{ p.attribute_name }}</span>
            <b class="rd-total-v" :class="attrTone(p.attribute_name)">{{ value(p.attribute_value) }}</b>
          </div>
        </div>

        <div class="rd-equip-grid">
          <!-- Slot 1: Echo Score Card -->
          <div
            v-if="hero.kind !== 'absent'"
            class="rd-score-cell"
            data-render-block
            :data-kind="hero.kind"
            :data-tier="heroTier ?? undefined"
          >
            <div class="rd-grade-ring-wrap">
              <div class="rd-grade-ring" :aria-label="hero.grade ? `等级 ${hero.grade}` : undefined">
                <span>{{ hero.grade || '—' }}</span>
              </div>
              <svg viewBox="0 0 24 24" class="rd-score-sparkle" aria-hidden="true">
                <path d="M12 1L14.6 9.4L23 12L14.6 14.6L12 23L9.4 14.6L1 12L9.4 9.4Z" fill="currentColor" />
              </svg>
            </div>
            <span class="rd-score-caption">声骸评级</span>
            <i class="rd-score-divider" aria-hidden="true"></i>
            <div class="rd-score-readout">
              <template v-if="hero.kind === 'scored'">
                <p class="rd-score-val"><b>{{ hero.value }}</b><span class="rd-score-unit">分</span><span v-if="hero.max" class="rd-score-max"> / {{ hero.max }}</span></p>
              </template>
              <template v-else-if="hero.kind === 'partial'">
                <p class="rd-score-val"><b>{{ hero.value }}</b><span class="rd-score-unit">分</span></p>
                <span class="rd-score-sub">部分可评 · 已评 {{ hero.count }} 件</span>
              </template>
              <p v-else-if="hero.kind === 'none'" class="rd-score-note">暂无默认权重</p>
              <p v-else class="rd-score-note">暂不可评分</p>
            </div>
            <span class="rd-score-caption">声骸评分</span>
            <span v-if="hero.source" class="rd-score-source">{{ hero.source }}</span>
          </div>

          <!-- Slots 2..N: Equipped Echoes -->
          <article
            v-for="(echo, i) in echoes"
            :key="i"
            class="rd-equip-card"
            data-render-block
            :data-tier="badges.get(echo) ? (gradeTier(badges.get(echo).grade) ?? undefined) : undefined"
          >
            <header class="rd-equip-head">
              <div class="rd-equip-icon">
                <img
                  v-if="echoIconUrl(echo)"
                  :src="echoIconUrl(echo)"
                  :alt="echo.phantom_prop?.name || '声骸'"
                  class="rd-equip-img"
                  @error="markFailed(echoIconUrl(echo))"
                />
                <svg v-else viewBox="0 0 24 24" class="rd-equip-svg" aria-hidden="true">
                  <circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="1.4" stroke-dasharray="3 2.5" />
                  <path d="M5 12h3l2-5 4 10 2-5h3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </div>
              <div class="rd-equip-title">
                <strong>{{ echo.phantom_prop?.name || '未知声骸' }}</strong>
                <span>Lv.{{ value(echo.level) }}</span>
              </div>
              <div
                v-if="badges.get(echo)"
                class="rd-equip-score-pill"
                :data-tier="gradeTier(badges.get(echo).grade) ?? undefined"
                :aria-label="`单件评分 ${badges.get(echo).value} / 50${badges.get(echo).grade ? ' 等级 ' + badges.get(echo).grade : ''}`"
              >
                <b>{{ badges.get(echo).value }}分</b>
                <span v-if="badges.get(echo).grade">{{ badges.get(echo).grade }}</span>
              </div>
            </header>

            <div v-if="rows(echo.main_props).length" class="rd-stat-rows is-main">
              <div v-for="[p, j] in rows(echo.main_props)" :key="j" class="rd-stat-row" :class="tone(echo, 'main_props', j)">
                <RoleStatIcon :src="p.icon_url || namedIcon('stats', p.attribute_name)" :name="p.attribute_name" :size="18" />
                <span class="rd-stat-k">{{ p.attribute_name }}</span>
                <b class="rd-stat-v">{{ value(p.attribute_value) }}</b>
              </div>
            </div>

            <div v-if="rows(echo.sub_props).length" class="rd-stat-rows is-sub">
              <div v-for="[p, j] in rows(echo.sub_props)" :key="j" class="rd-stat-row" :class="tone(echo, 'sub_props', j)">
                <RoleStatIcon :src="p.icon_url || namedIcon('stats', p.attribute_name)" :name="p.attribute_name" :size="18" />
                <span class="rd-stat-k">{{ p.attribute_name }}</span>
                <b class="rd-stat-v">{{ value(p.attribute_value) }}</b>
              </div>
            </div>

            <footer class="rd-equip-set">
              <img
                v-if="fetterIconUrl(echo)"
                :src="fetterIconUrl(echo)"
                :alt="echo.fetter_detail?.name || '套装'"
                class="rd-set-img"
                @error="markFailed(fetterIconUrl(echo))"
              />
              <svg v-else viewBox="0 0 24 24" class="rd-set-svg" aria-hidden="true">
                <polygon points="12,3 21,12 12,21 3,12" fill="currentColor" />
              </svg>
              <span class="rd-set-name">{{ echo.fetter_detail?.name || '套装未知' }}</span>
              <span class="rd-cost-pill">COST {{ value(echo.cost ?? echo.phantom_prop?.cost) }}</span>
            </footer>
          </article>
        </div>
      </div>

      <p v-else class="ov-empty">暂无装备声骸数据</p>
    </section>
  </div>
</template>
