<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '../calendar.js'
import { displayRoleValue as display } from '../nte-roles.js'
import { nteNamedIcon, nteRoleIcon, nteSkillIcon } from '../nte-icons.js'
import { gradeTier, nteBadges, nteStatFlags, scoreHero, statTone } from '../assessment-display.js'
import { driveCells, driveQuality, driveShape } from '../nte-drive-shapes.js'
import { asset } from './models.js'
import { chainLabel, normalizeElementKey } from './role-meta.js'
import OverviewSectionHead from './OverviewSectionHead.vue'
import RoleStatIcon from './RoleStatIcon.vue'

const props = defineProps({ role: { type: Object, required: true } })

const rows = value => (Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : [])

const pictures = computed(() => [...new Set([
  asset(safeUrl(props.role.icon_url)),
  asset(nteRoleIcon(props.role.id)),
  asset(nteRoleIcon(props.role.name)),
].filter(Boolean))])
const failed = ref(0)
watch(pictures, () => { failed.value = 0 })
const art = computed(() => pictures.value[failed.value] || '')

const failedUrls = ref(new Set())
watch(() => props.role, () => { failedUrls.value = new Set() })
const markFailed = url => {
  if (url) failedUrls.value = new Set([...failedUrls.value, url])
}
const liveAsset = url => {
  const resolved = asset(safeUrl(url))
  return resolved && !failedUrls.value.has(resolved) ? resolved : ''
}

const elemName = computed(() => props.role.element || '')
const elemKey = computed(() => normalizeElementKey(elemName.value))
const quality = computed(() => String(props.role.quality || '').toUpperCase())
const weapon = computed(() => props.role.weapon || null)
const weaponIcon = computed(() => weapon.value ? (liveAsset(weapon.value.icon_url) || liveAsset(nteNamedIcon('weapons', weapon.value.name))) : '')

const pillFacts = computed(() => [
  elemName.value ? `${elemName.value}属性` : null,
  chainLabel('nte', props.role.awaken_level, { preserveUnknown: true }),
  props.role.mix_level != null ? `混频 ${props.role.mix_level}` : null,
].filter(Boolean))

const CORE = new Set(['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '充能效率', '环合强度'])
const isZero = v => typeof v === 'number' ? v === 0 : typeof v === 'string' && /^0+(?:\.0+)?%?$/.test(v.trim())
const attributes = computed(() => rows(props.role.properties).filter(p => CORE.has(p.name) || !isZero(p.value)))
const zeroCount = computed(() => rows(props.role.properties).length - attributes.value.length)

const skills = computed(() => rows(props.role.skills))
const skillIconUrl = entry => liveAsset(entry?.icon_url) || liveAsset(nteSkillIcon(props.role.id, entry?.name))

const suit = computed(() => props.role.suit && typeof props.role.suit === 'object' ? props.role.suit : null)
const suitIconUrl = computed(() => suit.value ? liveAsset(nteNamedIcon('sets', suit.value.name)) : '')
const suitMeta = computed(() => suit.value ? `${display(suit.value.name)} · 激活 ${display(suit.value.activation_count)}` : '')
const pieces = computed(() => ['core', 'pie'].flatMap(group => rows(suit.value?.[group]).map(item => ({ item, group }))))

const score = computed(() => props.role.assessment || null)
const hero = computed(() => scoreHero(score.value))
const heroTier = computed(() => gradeTier(hero.value.grade))
const badges = computed(() => nteBadges(score.value, suit.value))
const flags = computed(() => nteStatFlags(score.value, suit.value))
const tone = (item, kind, stat) => statTone(flags.value.get(item)?.get(`${kind}:${String(stat?.id ?? '').toLowerCase()}`))

const attrTone = name => {
  const s = String(name || '')
  if (/充能效率|环合强度/.test(s)) return 'is-cyan'
  if (/暴击|伤害/.test(s)) return 'is-gold'
  return ''
}
</script>
<template>
  <div class="rd-sheet role-sheet nte-role-detail-sheet">
    <!-- 1. Showcase Split Hero: Tall Left Portrait Card + Right Attributes & Arc Disk -->
    <section class="rd-hero" data-render-block>
      <div class="rd-portrait-card">
        <img
          v-if="art"
          :key="art"
          :src="art"
          :alt="role.name || '角色'"
          class="rd-portrait-img"
          @error="failed++"
        />
        <div v-else class="rd-portrait-fallback" aria-hidden="true">
          <span>{{ (display(role.name) || '?').slice(0, 1) }}</span>
        </div>

        <div class="rd-top-left">
          <span v-if="quality" class="rd-rank-badge" :class="`rank-${quality}`">{{ quality }}</span>
        </div>

        <div class="rd-top-right">
          <span v-if="elemName" class="ao-elem-badge rd-badge-circle" :class="'elem-' + elemKey" :title="elemName">
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
        </div>

        <div class="rd-portrait-foot">
          <div class="rd-portrait-title">
            <strong class="rd-char-name">{{ display(role.name) }}</strong>
            <b class="rd-char-lv">Lv{{ display(role.level) }}</b>
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
            <span v-if="zeroCount" class="rd-mini-note">其余 {{ zeroCount }} 项为 0，未列出</span>
            <i class="rd-mini-line right" aria-hidden="true"></i>
          </div>
          <div v-if="attributes.length" class="rd-attr-list" :class="{ 'is-two-col': attributes.length > 9 }">
            <div v-for="(p, i) in attributes" :key="i" class="rd-attr-row">
              <RoleStatIcon :name="display(p.name)" :size="20" />
              <span class="rd-attr-k">{{ display(p.name) }}</span>
              <b class="rd-attr-v" :class="attrTone(p.name)">{{ display(p.value) }}</b>
            </div>
          </div>
          <p v-else class="rd-muted">暂无数据</p>
        </section>

        <!-- Block 2: Arc Disk Info -->
        <section class="rd-panel">
          <div class="rd-mini-head">
            <i class="rd-mini-line left" aria-hidden="true"></i>
            <h3>弧盘信息</h3>
            <i class="rd-mini-line right" aria-hidden="true"></i>
          </div>
          <div v-if="weapon" class="rd-weapon-card">
            <div class="rd-weapon-head">
              <div class="rd-weapon-frame">
                <img
                  v-if="weaponIcon"
                  :src="weaponIcon"
                  :alt="weapon.name || '弧盘'"
                  class="rd-weapon-img"
                  @error="markFailed(weaponIcon)"
                />
                <svg v-else viewBox="0 0 24 24" class="rd-weapon-svg" aria-hidden="true">
                  <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" stroke-width="2" />
                  <circle cx="12" cy="12" r="2.5" fill="currentColor" />
                  <path d="M12 2V5M12 19V22M2 12H5M19 12H22" stroke="currentColor" stroke-width="2" />
                </svg>
              </div>
              <div class="rd-weapon-copy">
                <div class="rd-weapon-title-row">
                  <strong class="rd-weapon-name">{{ display(weapon.name) }}</strong>
                  <span v-if="weapon.quality" class="rd-rank-badge is-inline" :class="`rank-${String(weapon.quality).toUpperCase()}`">{{ weapon.quality }}</span>
                  <span class="rd-weapon-pill">混频 {{ display(weapon.mix_level) }}</span>
                </div>
                <div class="rd-weapon-sub">
                  <span>Lv{{ display(weapon.level) }} · 突破 {{ display(weapon.breakthrough_level) }}</span>
                </div>
              </div>
            </div>
            <div v-if="rows(weapon.properties).length" class="rd-weapon-props">
              <div v-for="(p, i) in rows(weapon.properties)" :key="i" class="rd-attr-row">
                <RoleStatIcon :name="display(p.name)" :size="18" />
                <span class="rd-attr-k">{{ display(p.name) }}</span>
                <b class="rd-attr-v">{{ display(p.value) }}</b>
              </div>
            </div>
          </div>
          <p v-else class="rd-muted">弧盘 暂无数据</p>
        </section>
      </div>
    </section>

    <!-- 2. Combat Skills -->
    <section class="ao-section" data-render-block>
      <OverviewSectionHead title="战技" />
      <div v-if="skills.length" class="rd-skills-row is-grid-3">
        <article v-for="(entry, i) in skills" :key="i" class="rd-skill-tile">
          <div class="rd-skill-frame">
            <img
              v-if="skillIconUrl(entry)"
              :src="skillIconUrl(entry)"
              :alt="entry.name || '技能'"
              class="rd-skill-img"
              @error="markFailed(skillIconUrl(entry))"
            />
            <svg v-else viewBox="0 0 24 24" class="rd-skill-svg" aria-hidden="true">
              <path d="M12 2L14.8 9.2L22 12L14.8 14.8L12 22L9.2 14.8L2 12L9.2 9.2Z" fill="currentColor" />
            </svg>
          </div>
          <div class="rd-skill-info">
            <span class="rd-skill-name">{{ display(entry.name) }}</span>
          </div>
          <b class="rd-skill-lv">Lv{{ display(entry.level) }}</b>
        </article>
      </div>
      <p v-else class="ov-empty">暂无战技数据</p>
    </section>

    <!-- 3. Cartridge & Drives Showcase Grid (preserves .sheet-pieces / .sheet-piece / .piece-title contracts) -->
    <section class="ao-section rd-equip-section">
      <OverviewSectionHead title="卡带与驱动" :meta="suitMeta" />

      <div v-if="pieces.length" class="rd-equip-wrap">
        <div v-if="hero.source" class="rd-template-bar">
          <span class="rd-template-tag">评分来源</span>
          <span class="rd-template-text">{{ hero.source }}</span>
        </div>

        <div class="rd-equip-grid sheet-pieces">
          <!-- Slot 1: Equipment Score Card (when present) -->
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
            <span class="rd-score-caption">装备评级</span>
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
            <span class="rd-score-caption">装备评分</span>
            <span v-if="hero.source" class="rd-score-source">{{ hero.source }}</span>
          </div>

          <!-- Slots 2..N: Cartridge (core) & Drive (pie) cards -->
          <article
            v-for="({ item, group }, i) in pieces"
            :key="i"
            class="rd-equip-card sheet-piece"
            data-render-block
            :data-quality="driveQuality(item.id) || undefined"
            :data-tier="badges.get(item) ? (gradeTier(badges.get(item).grade) ?? undefined) : undefined"
          >
            <header class="rd-equip-head">
              <span v-if="group === 'pie' && driveShape(item.id)" class="piece-shape" role="img" :aria-label="`${display(item.name)} 形状`">
                <span v-for="(line, r) in driveShape(item.id)" :key="r" class="shape-row">
                  <i v-for="(filled, c) in line" :key="c" :class="{ filled }"></i>
                </span>
              </span>
              <span v-else-if="group === 'pie'" class="piece-shape is-count" role="img" :aria-label="`${driveCells(item.id) ?? '未知'} 格`">
                <span class="shape-row">
                  <i v-for="c in driveCells(item.id) || 0" :key="c" class="filled"></i>
                </span>
              </span>
              <div v-else class="rd-equip-icon">
                <img
                  v-if="suitIconUrl"
                  :src="suitIconUrl"
                  :alt="display(item.name)"
                  class="rd-equip-img"
                  @error="markFailed(suitIconUrl)"
                />
                <svg v-else viewBox="0 0 24 24" class="rd-equip-svg" aria-hidden="true">
                  <rect x="4" y="3" width="16" height="18" rx="2" fill="none" stroke="currentColor" stroke-width="1.8" />
                  <rect x="7" y="6" width="10" height="5" rx="1" fill="currentColor" />
                  <circle cx="9" cy="16" r="1.4" fill="currentColor" />
                  <circle cx="15" cy="16" r="1.4" fill="currentColor" />
                </svg>
              </div>

              <div class="rd-equip-title piece-title">
                <strong>{{ display(item.name) }}</strong>
                <span>{{ group === 'core' ? '卡带' : '驱动' }} · Lv{{ display(item.level) }}</span>
              </div>

              <div
                v-if="badges.get(item)"
                class="rd-equip-score-pill"
                :data-tier="gradeTier(badges.get(item).grade) ?? undefined"
                :aria-label="`单件评分 ${badges.get(item).value} / ${badges.get(item).max}${badges.get(item).grade ? ' 等级 ' + badges.get(item).grade : ''}`"
              >
                <b>{{ badges.get(item).value }}</b>
                <span v-if="badges.get(item).grade">{{ badges.get(item).grade }}</span>
              </div>
            </header>

            <div v-if="rows(item.main_properties).length" class="rd-stat-rows is-main">
              <div v-for="(p, j) in rows(item.main_properties)" :key="j" class="rd-stat-row" :class="tone(item, 'main', p)">
                <RoleStatIcon :name="display(p.name)" :size="18" />
                <span class="rd-stat-k">{{ display(p.name) }}</span>
                <b class="rd-stat-v">{{ display(p.value) }}</b>
              </div>
            </div>

            <div v-if="rows(item.properties).length" class="rd-stat-rows is-sub">
              <div v-for="(p, j) in rows(item.properties)" :key="j" class="rd-stat-row" :class="tone(item, 'sub', p)">
                <RoleStatIcon :name="display(p.name)" :size="18" />
                <span class="rd-stat-k">{{ display(p.name) }}</span>
                <b class="rd-stat-v">{{ display(p.value) }}</b>
              </div>
            </div>
          </article>
        </div>
      </div>

      <p v-else class="ov-empty">{{ suit ? '驱动件 未提供' : '未装备' }}</p>
    </section>
  </div>
</template>
