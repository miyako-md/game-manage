<script setup>
import { ref, watch } from 'vue'
import EndfieldArtwork from '../components/EndfieldArtwork.vue'

const props = defineProps({
  role: { type: Object, required: true },
  detailed: { type: Boolean, default: false },
})

const failed = ref(false)
watch(() => props.role?.image, () => { failed.value = false })
</script>
<template>
  <article
    class="ao-role-card"
    :class="[role.isGold ? 'is-rarity-gold' : 'is-rarity-purple', { 'is-detailed': detailed, 'ef-operator': role.game === 'endfield' && detailed }]"
  >
    <div class="ao-role-portrait" :class="{ 'ef-avatar': role.game === 'endfield' && detailed }">
      <EndfieldArtwork
        v-if="role.game === 'endfield' && role.portraitMode"
        role
        portrait
        :operator-id="role.operatorId"
        :src="role.rawAvatarUrl"
        :name="role.name"
        class="ao-ef-portrait"
      />
      <img
        v-else-if="role.image && !failed"
        :src="role.image"
        :alt="role.name"
        class="ao-role-img"
        @error="failed = true"
      />
      <svg v-else class="ao-role-fallback" viewBox="0 0 120 120" aria-hidden="true">
        <circle cx="60" cy="52" r="32" fill="rgba(255,255,255,0.04)" stroke="rgba(214,188,138,0.22)" stroke-width="1.2" />
        <text x="60" y="64" text-anchor="middle" fill="rgba(240,218,172,0.34)" font-size="34" font-weight="800">{{ (role.name || '?').slice(0, 1) }}</text>
      </svg>
      <div class="ao-rarity-glow"></div>

      <!-- Optional Top-Left Rarity Badge (roster mode) -->
      <span v-if="detailed && role.rarityTag" class="ao-rarity-tag role-rarity" :data-tier="role.isGold ? 'top' : undefined">{{ role.rarityTag }}</span>

      <!-- Top-Right Element Badge -->
      <span class="ao-elem-badge" :class="'elem-' + role.elemKey" :title="role.attr">
        <svg v-if="role.elemKey === 'spectro'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 2L14.2 8.8L21 9.5L15.6 13.8L17.5 20.5L12 16.6L6.5 20.5L8.4 13.8L3 9.5L9.8 8.8Z" fill="#ffe17d" />
        </svg>
        <svg v-else-if="role.elemKey === 'havoc'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M14.5 3.5A8.5 8.5 0 1 0 20.5 16.5A7 7 0 1 1 14.5 3.5Z" fill="#ff7aa8" />
          <circle cx="15" cy="9" r="2.2" fill="#ffd1e2" />
        </svg>
        <svg v-else-if="role.elemKey === 'electro'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M13.5 2L5.5 13H11.5L10 22L18.5 10.5H12.5L13.5 2Z" fill="#d09bff" />
        </svg>
        <svg v-else-if="role.elemKey === 'fusion'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12.5 2.5C12.5 2.5 18.5 7.5 18.5 13.5C18.5 17.6 15.4 21 11.5 21C7.6 21 5 17.6 5 13.8C5 10.5 7.2 7.8 7.2 7.8C7.2 7.8 7 10.8 9.2 11.5C8.5 8.2 12.5 2.5 12.5 2.5Z" fill="#ff8563" />
        </svg>
        <svg v-else-if="role.elemKey === 'glacio'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5Z" fill="#7be0ff" />
        </svg>
        <svg v-else-if="role.elemKey === 'aero'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 13C7.5 8 13.5 7 19.5 10C15.5 12.5 11.5 13.5 4 13ZM6 17.5C10 14.5 15 14 20 15.5C16.5 18 11.5 19 6 17.5Z" fill="#6bf2c3" />
        </svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <polygon points="12,3 21,12 12,21 3,12" fill="#dbe3f0" />
        </svg>
      </span>

      <!-- Bottom-Right Weapon Emblem -->
      <span class="ao-weapon-badge" :title="role.weaponType">
        <img v-if="role.weaponIcon" :src="role.weaponIcon" :alt="role.weaponType" class="ao-weapon-img" />
        <svg v-else-if="role.weaponKey === 'broadblade'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M18 3L21 6L9 18L5 19L6 15L18 3ZM4 20L7 17L9 19L6 22L4 20Z" fill="#e6cfa3" />
        </svg>
        <svg v-else-if="role.weaponKey === 'pistols'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4 7H19L21 10L17 12H11L9 18H5L7 12H4V7Z" fill="#e6cfa3" />
        </svg>
        <svg v-else-if="role.weaponKey === 'gauntlets'" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M6 8L11 4L18 7L19 15L13 20L6 16Z" fill="#e6cfa3" />
        </svg>
        <svg v-else-if="role.weaponKey === 'rectifier'" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="5" fill="none" stroke="#e6cfa3" stroke-width="2" />
          <path d="M12 2V6M12 18V22M2 12H6M18 12H22" stroke="#e6cfa3" stroke-width="2" />
        </svg>
        <svg v-else viewBox="0 0 24 24" aria-hidden="true">
          <path d="M19 3L21 5L8.5 17.5L6.5 15.5L19 3ZM5 17L7 19L4 22L2 20L5 17Z" fill="#e6cfa3" />
        </svg>
      </span>

      <!-- Bottom-Left Character Name Overlay -->
      <span class="ao-role-name-tag">{{ role.name }}</span>
    </div>

    <!-- Card Footer: Chain/Awakening/Potential Pill + Level -->
    <div class="ao-role-footer">
      <span class="ao-chain-pill" :class="role.chainCls">{{ role.chainText }}</span>
      <span class="ao-role-lv">{{ role.level != null ? `LV.${role.level}` : 'LV.—' }}</span>
    </div>

    <!-- Optional Secondary Meta Row (roster mode) -->
    <div v-if="detailed && (role.phaseLabel || role.subline)" class="ao-role-substrip">
      <span v-if="role.phaseLabel" class="ao-role-phase">
        <i v-if="role.phaseTone" class="ao-phase-dot" :style="{ background: role.phaseTone }" aria-hidden="true"></i>
        <span>{{ role.phaseLabel }}</span>
      </span>
      <span v-if="role.subline" class="ao-role-subtext">{{ role.subline }}</span>
    </div>
  </article>
</template>
