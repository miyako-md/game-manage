<script setup>
import { computed } from 'vue'
import { displayValue as display, rows, sourceName as named } from '../endfield-reports.js'
import { displayBeijing } from '../time.js'
import endfieldIcons from '../endfield-icon-catalog.js'
import EndfieldArtwork from '../components/EndfieldArtwork.vue'
import OverviewSectionHead from './OverviewSectionHead.vue'
import { asset } from './models.js'
import { normalizeElementKey, normalizeWeaponKey } from './role-meta.js'

const props = defineProps({ input: { type: Object, required: true } })

const panel = computed(() => (props.input?.snapshot?.display_data?.panels || []).find(p => p.capability === 'operator_detail') || null)
const payload = computed(() => panel.value?.snapshot?.payload || {})
const operator = computed(() => payload.value.operator_detail || {})

const slotDefinitions = [
  ['bodyEquip', '护甲'],
  ['armEquip', '护手'],
  ['firstAccessory', '配件一'],
  ['secondAccessory', '配件二'],
]
const equipment = computed(() => rows(operator.value.equipment))
const slots = computed(() => slotDefinitions.map(([id, label]) => ({
  id,
  label,
  item: equipment.value.find(item => item.slot === id) || null,
})))
const extraEquipment = computed(() => equipment.value.filter((item, index) =>
  !slotDefinitions.some(([id]) => id === item.slot) || equipment.value.findIndex(other => other.slot === item.slot) !== index,
))

const weapon = computed(() => operator.value.weapon || null)
const weaponIconUrl = computed(() => weapon.value?.icon_url || asset(endfieldIcons.weapons?.[named(weapon.value)]?.icon) || '')
const gem = computed(() => weapon.value?.gem || null)
const gemTerms = computed(() => rows(gem.value?.terms))
const skills = computed(() => rows(operator.value.skills))
const tactical = computed(() => operator.value.tactical_item || null)

const rarity = computed(() => Number(operator.value.rarity))
const phase = computed(() => operator.value.evolve_phase ?? operator.value.phase)
const elemName = computed(() => named(operator.value.property))
const profName = computed(() => named(operator.value.profession))
const elemKey = computed(() => normalizeElementKey(elemName.value))
const weaponKey = computed(() => normalizeWeaponKey(profName.value))

const obtainedText = computed(() => {
  const v = operator.value.obtained_at
  return v == null || v === '' ? '未知' : displayBeijing(v)
})

const facts = computed(() => [
  ['职业', profName.value],
  ['属性', elemName.value],
  ['潜能', display(operator.value.potential)],
  ['精英阶段', display(phase.value)],
  ['获得时间', obtainedText.value],
].filter(([, v]) => v && v !== '未知'))

const cleanEffect = value => (typeof value === 'string' && value.trim()
  ? value.trim().replace(/<@(ba\.vup|tips\.purple|tips\.orange)>([^<>]*)<\/>/g, '$2')
  : null)
const tacticalActive = computed(() => cleanEffect(tactical.value?.active_effect))
const tacticalPassive = computed(() => cleanEffect(tactical.value?.passive_effect))
const skillCols = computed(() => Math.max(1, Math.min(skills.value.length || 1, 4)))
</script>
<template>
  <div class="ov-ef-operator rd-sheet">
    <!-- Hero Card: Left Tall Portrait Showcase + Right Industrial Facts & Embedded Weapon/Gem -->
    <section class="rd-hero ef-op-hero" data-render-block>
      <div class="rd-portrait-card ef-portrait-card">
        <div class="ef-op-portrait-stage">
          <EndfieldArtwork
            class="ef-op-portrait"
            role
            portrait
            :operator-id="operator.char_id || operator.id"
            :src="operator.avatar_url"
            :name="operator.name || '干员'"
          />
        </div>

        <div class="rd-top-left">
          <span v-if="Number.isFinite(rarity)" class="ef-op-rarity" :data-tier="rarity >= 6 ? 'top' : undefined">{{ rarity }}★</span>
        </div>

        <div class="rd-top-right">
          <span v-if="elemName !== '未知'" class="ao-elem-badge rd-badge-circle" :class="'elem-' + elemKey" :title="elemName">
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

          <span v-if="profName !== '未知'" class="rd-badge-circle rd-weapon-circle" :title="profName">
            <svg v-if="weaponKey === 'broadblade'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M18 3L21 6L9 18L5 19L6 15L18 3ZM4 20L7 17L9 19L6 22L4 20Z" fill="#ffd100" />
            </svg>
            <svg v-else-if="weaponKey === 'pistols'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M4 7H19L21 10L17 12H11L9 18H5L7 12H4V7Z" fill="#ffd100" />
            </svg>
            <svg v-else-if="weaponKey === 'gauntlets'" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M6 8L11 4L18 7L19 15L13 20L6 16Z" fill="#ffd100" />
            </svg>
            <svg v-else-if="weaponKey === 'rectifier'" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="5" fill="none" stroke="#ffd100" stroke-width="2" />
              <path d="M12 2V6M12 18V22M2 12H6M18 12H22" stroke="#ffd100" stroke-width="2" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <path d="M19 3L21 5L8.5 17.5L6.5 15.5L19 3ZM5 17L7 19L4 22L2 20L5 17Z" fill="#ffd100" />
            </svg>
          </span>
        </div>

        <div class="rd-portrait-foot">
          <div class="rd-portrait-title">
            <strong class="ef-op-name rd-char-name">{{ operator.name || '干员' }}</strong>
            <b class="ef-op-lv rd-char-lv">LV.{{ display(operator.level) }}</b>
          </div>
        </div>
      </div>

      <div class="rd-side-col">
        <!-- Industrial Facts Card -->
        <section class="rd-panel ef-op-dossier">
          <div class="rd-mini-head is-industrial">
            <span class="ef-op-cap-num">ID /</span>
            <h3>干员档案</h3>
          </div>
          <dl v-if="facts.length" class="ef-op-facts-grid">
            <div v-for="[k, v] in facts" :key="k" class="ef-op-fact-row" :class="{ 'is-wide': k === '获得时间' }">
              <dt>{{ k }}</dt>
              <dd>{{ v }}</dd>
            </div>
          </dl>
        </section>

        <!-- Embedded Weapon & Gem Module -->
        <section class="ef-op-weapon">
          <div class="ef-op-weapon-cap">
            <span class="ef-op-cap-num">00 /</span>
            <span>武器与基质</span>
          </div>
          <div v-if="weapon" class="ef-op-weapon-row">
            <EndfieldArtwork class="ef-op-weapon-art" :src="weaponIconUrl" :name="named(weapon)">
              <template #fallback>
                <svg viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                  <path d="M5 25L12 18M9 21L24 6L30 6L30 12L15 27Z" fill="none" stroke="#9aa4b2" stroke-width="2" stroke-linejoin="round" />
                  <path d="M18 12L24 6L30 6L30 12L24 18" fill="none" stroke="#ffd100" stroke-width="2.2" stroke-linejoin="round" />
                  <circle cx="11" cy="25" r="2.2" fill="#ffd100" />
                </svg>
              </template>
            </EndfieldArtwork>
            <div class="ef-op-weapon-body">
              <strong class="ef-op-weapon-name">{{ named(weapon) }}</strong>
              <p class="ef-op-weapon-meta">
                <span>LV. {{ display(weapon.level) }}</span>
                <span>精炼 {{ display(weapon.refine_level) }}</span>
                <span>突破 {{ display(weapon.breakthrough_level) }}</span>
              </p>
            </div>
          </div>
          <p v-else class="ef-op-muted">武器资料未知</p>

          <div v-if="gem" class="ef-op-gem">
            <EndfieldArtwork class="ef-op-gem-art" :src="gem.icon_url" :name="named(gem)">
              <template #fallback>
                <svg viewBox="0 0 32 32" class="ef-op-slot-svg" aria-hidden="true">
                  <polygon points="16,3 27,10 27,22 16,29 5,22 5,10" fill="none" stroke="#9aa4b2" stroke-width="2" />
                  <polygon points="16,7 23,12 16,25 9,12" fill="rgba(255,209,0,0.22)" stroke="#ffd100" stroke-width="1.8" />
                </svg>
              </template>
            </EndfieldArtwork>
            <div class="ef-op-gem-body">
              <p class="ef-op-gem-name"><span>基质</span><strong>{{ named(gem) }}</strong></p>
              <ul v-if="gemTerms.length" class="ef-op-gem-terms">
                <li v-for="(term, idx) in gemTerms" :key="idx">{{ named(term) }} <b>{{ display(term.cost) }}</b></li>
              </ul>
            </div>
          </div>
        </section>
      </div>
    </section>

    <!-- 01 / Equipment (4 Slots + Any Extra Legacy Slots) -->
    <section class="ao-section">
      <OverviewSectionHead title="装备" en="EQUIPMENT" index="01" />
      <div class="ef-op-equip-grid">
        <article v-for="slot in slots" :key="slot.id" class="ef-op-equip-card" :class="{ 'is-unknown': !slot.item }">
          <EndfieldArtwork
            class="ef-op-equip-art"
            :src="slot.item?.icon_url"
            :name="slot.item ? named(slot.item) : slot.label"
          >
            <template #fallback>
              <svg v-if="slot.id === 'bodyEquip'" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                <path d="M11 6L15 9H21L25 6L30 11L27 16V30H9V16L6 11Z" fill="none" stroke="#9aa4b2" stroke-width="2" stroke-linejoin="round" />
                <polygon points="18,12 22,16 18,22 14,16" fill="#ffd100" />
              </svg>
              <svg v-else-if="slot.id === 'armEquip'" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                <path d="M10 14L14 7H24L27 14V23L22 29H12L10 23Z" fill="none" stroke="#9aa4b2" stroke-width="2" stroke-linejoin="round" />
                <path d="M13 15H24M14 21H22" stroke="#ffd100" stroke-width="2.2" stroke-linecap="square" />
              </svg>
              <svg v-else-if="slot.id === 'firstAccessory'" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                <circle cx="18" cy="18" r="10" fill="none" stroke="#9aa4b2" stroke-width="2" />
                <circle cx="18" cy="18" r="4.2" fill="#ffd100" />
                <path d="M18 4V9M18 27V32M4 18H9M27 18H32" stroke="#ffd100" stroke-width="2" />
              </svg>
              <svg v-else viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                <rect x="9" y="9" width="18" height="18" fill="none" stroke="#9aa4b2" stroke-width="2" />
                <path d="M14 4V9M22 4V9M14 27V32M22 27V32M4 14H9M4 22H9M27 14H32M27 22H32" stroke="#9aa4b2" stroke-width="1.8" />
                <rect x="14" y="14" width="8" height="8" fill="#ffd100" />
              </svg>
            </template>
          </EndfieldArtwork>
          <div class="ef-op-equip-body">
            <span class="ef-op-slot-lbl">{{ slot.label }}</span>
            <strong class="ef-op-equip-name">{{ slot.item ? named(slot.item) : '资料未知' }}</strong>
            <span class="ef-op-equip-lv">{{ slot.item ? `等级 LV. ${display(slot.item.level)}` : '未提供该槽位资料' }}</span>
          </div>
        </article>
      </div>
      <div v-if="extraEquipment.length" class="ef-op-extra-grid">
        <article v-for="(item, idx) in extraEquipment" :key="item.id || idx" class="ef-op-equip-card">
          <EndfieldArtwork class="ef-op-equip-art" :src="item.icon_url" :name="named(item)">
            <template #fallback>
              <svg viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                <polygon points="18,5 30,12 30,24 18,31 6,24 6,12" fill="none" stroke="#9aa4b2" stroke-width="2" />
                <polygon points="18,11 24,18 18,25 12,18" fill="#ffd100" />
              </svg>
            </template>
          </EndfieldArtwork>
          <div class="ef-op-equip-body">
            <span class="ef-op-slot-lbl">{{ item.slot_label || item.slot_name || item.slot || '来源未标槽位' }}</span>
            <strong class="ef-op-equip-name">{{ named(item) }}</strong>
            <span class="ef-op-equip-lv">等级 LV. {{ display(item.level) }}</span>
          </div>
        </article>
      </div>
    </section>

    <!-- 02 / Skills -->
    <section class="ao-section">
      <OverviewSectionHead title="技能" en="SKILLS" index="02" />
      <div v-if="skills.length" class="ef-op-skills" :style="{ '--ef-skill-cols': skillCols }">
        <article v-for="(skill, idx) in skills" :key="skill.id || idx" class="ef-op-skill-card">
          <div class="skill-art ef-op-skill-art">
            <EndfieldArtwork class="ef-op-skill-icon" :src="skill.icon_url" :name="named(skill)">
              <template #fallback>
                <svg v-if="idx % 4 === 0" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                  <path d="M8 28L26 10M21 9H27V15" fill="none" stroke="#ffd100" stroke-width="2.4" stroke-linecap="square" />
                  <circle cx="14" cy="22" r="7" fill="none" stroke="#9aa4b2" stroke-width="1.8" stroke-dasharray="4 3" />
                </svg>
                <svg v-else-if="idx % 4 === 1" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                  <polygon points="18,4 22,14 32,18 22,22 18,32 14,22 4,18 14,14" fill="none" stroke="#ffd100" stroke-width="2.2" />
                  <circle cx="18" cy="18" r="3.5" fill="#f2f2ee" />
                </svg>
                <svg v-else-if="idx % 4 === 2" viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                  <circle cx="11" cy="24" r="5" fill="none" stroke="#9aa4b2" stroke-width="2" />
                  <circle cx="25" cy="12" r="5" fill="none" stroke="#ffd100" stroke-width="2.2" />
                  <path d="M15 20L21 16" stroke="#ffd100" stroke-width="2.2" />
                </svg>
                <svg v-else viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
                  <polygon points="18,4 30,11 30,25 18,32 6,25 6,11" fill="none" stroke="#9aa4b2" stroke-width="1.8" />
                  <polygon points="18,9 26,18 18,27 10,18" fill="rgba(255,209,0,0.22)" stroke="#ffd100" stroke-width="2" />
                  <circle cx="18" cy="18" r="2.8" fill="#ffd100" />
                </svg>
              </template>
            </EndfieldArtwork>
            <span class="skill-level ef-op-skill-lv" :aria-label="`等级 ${display(skill.level)}`">LV. {{ display(skill.level) }}</span>
          </div>
          <strong class="ef-op-skill-name">{{ named(skill) }}</strong>
          <span v-if="skill.mastery != null" class="ef-op-skill-mastery">专精 {{ display(skill.mastery) }}</span>
        </article>
      </div>
      <p v-else class="ov-empty">技能资料未知</p>
    </section>

    <!-- 03 / Tactical Item -->
    <section class="ao-section">
      <OverviewSectionHead title="战术道具" en="TACTICAL" index="03" />
      <div v-if="tactical" class="ef-op-tactical">
        <EndfieldArtwork class="ef-op-tactical-art" :src="tactical.icon_url" :name="named(tactical)">
          <template #fallback>
            <svg viewBox="0 0 36 36" class="ef-op-slot-svg" aria-hidden="true">
              <rect x="8" y="9" width="20" height="21" rx="2" fill="none" stroke="#9aa4b2" stroke-width="2" />
              <path d="M13 9V6H23V9" fill="none" stroke="#9aa4b2" stroke-width="2" />
              <path d="M18 14V24M13 19H23" stroke="#ffd100" stroke-width="2.4" stroke-linecap="square" />
            </svg>
          </template>
        </EndfieldArtwork>
        <div class="ef-op-tactical-body">
          <div class="ef-op-tactical-head">
            <strong>{{ named(tactical) }}</strong>
            <span class="ef-op-tactical-rarity">稀有度 {{ display(tactical.rarity) }}</span>
            <svg class="ef-op-barcode" viewBox="0 0 72 16" aria-hidden="true">
              <rect x="0" y="1" width="3" height="14" fill="currentColor" opacity="0.65" />
              <rect x="5" y="1" width="2" height="14" fill="currentColor" opacity="0.35" />
              <rect x="9" y="1" width="5" height="14" fill="currentColor" opacity="0.7" />
              <rect x="17" y="1" width="2" height="14" fill="currentColor" opacity="0.4" />
              <rect x="22" y="1" width="4" height="14" fill="#ffd100" opacity="0.85" />
              <rect x="29" y="1" width="2" height="14" fill="currentColor" opacity="0.5" />
              <rect x="34" y="1" width="6" height="14" fill="currentColor" opacity="0.65" />
              <rect x="43" y="1" width="2" height="14" fill="currentColor" opacity="0.35" />
              <rect x="48" y="1" width="3" height="14" fill="currentColor" opacity="0.7" />
              <rect x="54" y="1" width="5" height="14" fill="#ffd100" opacity="0.75" />
              <rect x="62" y="1" width="2" height="14" fill="currentColor" opacity="0.45" />
              <rect x="67" y="1" width="4" height="14" fill="currentColor" opacity="0.65" />
            </svg>
          </div>
          <p v-if="tacticalActive" class="ef-op-tactical-effect"><b>主动</b> {{ tacticalActive }}</p>
          <p v-if="tacticalPassive" class="ef-op-tactical-effect"><b>被动</b> {{ tacticalPassive }}</p>
          <p v-if="!tacticalActive && !tacticalPassive" class="ef-op-muted">来源未提供效果说明。</p>
        </div>
      </div>
      <p v-else class="ov-empty">来源未提供战术道具，无法判断当前装备状态。</p>
    </section>
  </div>
</template>
