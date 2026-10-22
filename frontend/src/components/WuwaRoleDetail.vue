<script setup>
import { computed, provide, ref } from 'vue'
import { safeUrl } from '../calendar.js'
import { list, starCount, value } from '../wuwa-display.js'
import WuwaFields from './WuwaFields.vue'
import WuwaIcon from './WuwaIcon.vue'
import RoleAssessment from './RoleAssessment.vue'
import { echoBadges, isNoDefault, scoreLine } from '../assessment-display.js'
// liveAssessment: the detail on screen is the account's current one, so the website reads its equipped score.
// The score lives in the echo section (header total and source, a badge per echo), never as a block of its own.
const props = defineProps({ data: { type: Object, default: () => ({}) }, imageMode:{type:Boolean,default:false}, liveAssessment:{type:Boolean,default:false} })
provide('wuwaImageMode', computed(() => props.imageMode))
const attributes = computed(() => Array.isArray(props.data.role_attribute_list)
  ? list(props.data.role_attribute_list) : list(props.data.role?.role_attribute_list))
const chains = computed(() => list(props.data.chain_list))
const unlockedChains = computed(
  () => chains.value.filter((c) => c.unlocked === true).length,
)
const echoes = computed(() => list(props.data.phantom_data?.equip_phantom_list))
// Per-echo badges (R1 slot): images carry the projected assessment, the website the one RoleAssessment read.
const liveScore = ref(null), editor = ref(null), editorState = ref({ loading: false, error: '', opened: false })
const live = computed(() => props.liveAssessment && !props.imageMode)
const score = computed(() => props.imageMode ? props.data.assessment : live.value ? liveScore.value : null)
const badges = computed(() => echoBadges(score.value, props.data.phantom_data?.equip_phantom_list))
const line = computed(() => scoreLine(score.value))
const toggleEditor = () => editorState.value.opened ? editor.value?.close() : editor.value?.open()
// Image layout (R1): the cached detail has no full-length art, so the portrait is the
// outfit picture, else the role icon; skills and chains each fill one row.
const portrait = computed(() => safeUrl(props.data.role_skin?.skin_icon) || safeUrl(props.data.role?.role_icon_url))
const skillCount = computed(() => Math.max(1, Math.min(list(props.data.skill_list).length, 7)))
const chainCount = computed(() => Math.max(1, Math.min(chains.value.length, 6)))
// Attribute rows made only of { attribute_name, attribute_value } read as a
// key-value grid; anything with extra fields keeps the generic renderer so no
// field is dropped.
const ATTRIBUTE_KEYS = new Set(['attribute_name', 'attribute_value'])
const isAttributeList = (v) =>
  list(v).length > 0 &&
  list(v).every(
    (p) =>
      p?.attribute_name != null &&
      Object.keys(p).every((k) => ATTRIBUTE_KEYS.has(k)),
  )
</script>
<template>
  <div class="wuwa-role-detail">
    <!-- History entries keep the stand-alone editor block; the live detail and images embed the score below. -->
    <RoleAssessment v-if="!imageMode && !liveAssessment" game="wuthering_waves" :character-id="String(data.role?.role_id || '')" />
    <section class="wuwa-detail-section wuwa-detail-basics">
      <figure v-if="imageMode" class="wuwa-portrait">
        <img v-if="portrait" :src="portrait" :alt="data.role?.role_name || '角色'" />
        <span v-else class="wuwa-portrait-fallback" aria-hidden="true">{{ (data.role?.role_name || '?').slice(0, 1) }}</span>
        <figcaption><strong>{{ data.role?.role_name || '角色' }}</strong> <b>Lv.{{ value(data.role?.level) }}</b></figcaption>
      </figure>
      <h3 class="wuwa-subhead role-profile-heading"><WuwaIcon v-if="!imageMode" :src="data.role?.role_icon_url" :name="data.role?.role_name || '角色'" size="large" /><span>{{ data.role?.role_name }} · 角色基本信息</span></h3>
      <div class="wuwa-basics">
        <img
          v-if="!imageMode && safeUrl(data.role_skin?.skin_icon)"
          class="wuwa-skin"
          :src="safeUrl(data.role_skin.skin_icon)"
          alt="当前外观"
           :loading="imageMode ? 'eager' : 'lazy'"
        />
        <div class="wuwa-basics-body">
          <WuwaFields :data="data.role" :exclude="['role_attribute_list']" />
          <div class="wuwa-field-group">
            <span class="wuwa-field-label" role="heading" aria-level="4">角色外观</span
            ><WuwaFields :data="data.role_skin" />
          </div>
        </div>
      </div>
    </section>

    <section class="wuwa-detail-section wuwa-detail-attrs">
      <h3 class="wuwa-subhead">完整属性</h3>
      <dl
        v-if="attributes.length"
        class="kv-grid wuwa-attrs"
      >
        <div v-for="(p, i) in attributes" :key="i">
          <dt class="role-profile-heading"><WuwaIcon :src="p.icon_url" :name="p.attribute_name || '属性'" size="small" />{{ p.attribute_name || '未知属性' }}</dt>
          <dd>{{ value(p.attribute_value) }}</dd>
        </div>
      </dl>
      <p v-else class="wuwa-muted">未提供属性</p>
    </section>

    <section class="wuwa-detail-section wuwa-detail-weapon">
      <h3 class="wuwa-subhead">装备武器</h3>
      <div v-if="data.weapon_data" class="wuwa-equip">
        <WuwaIcon :src="data.weapon_data.weapon?.weapon_icon" :name="data.weapon_data.weapon?.weapon_name || '武器'" />
        <div class="wuwa-equip-body">
          <p class="wuwa-equip-name">
            <strong>{{
              data.weapon_data.weapon?.weapon_name || '名称未知'
            }}</strong
            ><span
              v-if="starCount(data.weapon_data.weapon?.weapon_star_level)"
              class="stars"
              role="img"
              :aria-label="`${data.weapon_data.weapon.weapon_star_level} 星`"
              >{{
                '★'.repeat(starCount(data.weapon_data.weapon.weapon_star_level))
              }}</span
            ><span v-else class="wuwa-meta"
              >{{ value(data.weapon_data.weapon?.weapon_star_level) }} 星</span
            >
          </p>
          <p class="wuwa-inline">
            <span><span class="k">等级</span> <b>{{ value(data.weapon_data.level) }}</b></span
            ><span><span class="k">突破</span> <b>{{ value(data.weapon_data.breach) }}</b></span
            ><span><span class="k">谐振</span> <b>{{ value(data.weapon_data.reson_level) }}</b></span
            ><span
              v-for="(p, i) in list(data.weapon_data.main_prop_list)"
              :key="i"
              ><span class="k">{{ p.attribute_name }}</span> <b>{{
                value(p.attribute_value)
              }}</b></span
            >
          </p>
          <details v-if="!imageMode" class="wuwa-supplement">
            <summary>武器补充资料</summary>
            <WuwaFields
              :data="data.weapon_data.weapon"
              :exclude="[
                'weapon_name',
                'weapon_star_level',
                'weapon_effect_name',
                'effect_description',
              ]"
            />
            <WuwaFields
              :data="data.weapon_data"
              :exclude="[
                'weapon',
                'level',
                'breach',
                'reson_level',
                'main_prop_list',
              ]"
            />
          </details>
        </div>
      </div>
      <p v-else class="wuwa-muted">
        暂无装备武器数据
      </p>
    </section>

    <section class="wuwa-detail-section wuwa-detail-skills">
      <h3 class="wuwa-subhead">技能</h3>
      <p v-if="!list(data.skill_list).length" class="wuwa-muted">未提供</p>
      <div v-else class="wuwa-tiles wuwa-skills" :style="imageMode ? { '--row-count': skillCount } : undefined">
        <article
          v-for="(entry, i) in list(data.skill_list)"
          :key="i"
          class="wuwa-tile"
        >
          <header class="wuwa-tile-head">
            <WuwaIcon :src="entry.skill?.icon_url" :name="entry.skill?.name || '技能'" />
            <h4>{{ entry.skill?.name || '未知技能' }}</h4>
            <span v-if="entry.skill?.type" class="chip">{{
              entry.skill.type
            }}</span>
            <span class="wuwa-tile-end wuwa-gold">Lv.{{ value(entry.level) }}</span>
          </header>
        </article>
      </div>
    </section>

    <section class="wuwa-detail-section wuwa-detail-chains">
      <h3 class="wuwa-subhead">
        共鸣链<span v-if="chains.length" class="wuwa-meta"
          >已解锁 {{ unlockedChains }} / {{ chains.length }}</span
        >
      </h3>
      <div v-if="chains.length" class="wuwa-chains" :style="imageMode ? { '--row-count': chainCount } : undefined">
        <div
          v-for="(chain, i) in chains"
          :key="i"
          class="wuwa-chain"
          :class="{ 'wuwa-locked': chain.unlocked === false }"
        >
          <div class="wuwa-chain-head">
            <WuwaIcon :src="chain.icon_url" :name="chain.name || '共鸣链'" size="small" />
            <span class="wuwa-chain-order">{{ value(chain.order) }}</span
            ><span class="wuwa-chain-name">{{ chain.name }}</span
            ><span
              class="badge"
              :class="chain.unlocked === true ? 'wuwa-badge-on' : 'wuwa-badge-off'"
              >{{
                chain.unlocked === true
                  ? '已解锁'
                  : chain.unlocked === false
                    ? '未解锁'
                    : '解锁状态未知'
              }}</span
            >
          </div>
        </div>
      </div>
      <p v-else class="wuwa-muted">未提供</p>
    </section>

    <section class="wuwa-detail-section wuwa-detail-echoes">
      <h3 class="wuwa-subhead">
        装备声骸<span class="wuwa-meta"
          >总 COST {{ value(data.phantom_data?.cost) }}</span
        ><b v-if="line.total" class="wuwa-echo-total">{{ line.total }}</b
        ><span v-if="(line.total || badges.size) && line.source" class="wuwa-meta wuwa-echo-source"
          >{{ line.source }}</span
        ><template v-if="live"
          ><span v-if="editorState.loading" class="wuwa-meta wuwa-echo-status" role="status">正在读取评分…</span
          ><span v-else-if="editorState.error" class="wuwa-meta wuwa-echo-status wuwa-warning" role="alert">评分读取失败：{{ editorState.error }}</span
          ><span v-else-if="isNoDefault(score)" class="wuwa-meta wuwa-echo-status">暂无默认权重</span
          ><button type="button" class="ui-button small-button wuwa-echo-weights" :aria-expanded="editorState.opened" :disabled="!data.role?.role_id" @click="toggleEditor">{{ editorState.opened ? '收起权重设置' : '权重设置' }}</button></template
        >
      </h3>
      <div v-if="echoes.length" class="wuwa-tiles wuwa-echoes">
        <article v-for="(echo, i) in echoes" :key="i" class="wuwa-tile">
          <header class="wuwa-echo-head">
            <WuwaIcon :src="echo.phantom_prop?.icon_url" :name="echo.phantom_prop?.name || '声骸'" />
            <div>
              <h4>{{ echo.phantom_prop?.name || '未知声骸' }}</h4>
              <p class="wuwa-inline">
                <span><span class="k">等级</span> <b>{{ value(echo.level) }}</b></span
                ><span><span class="k">COST</span> <b>{{ value(echo.cost) }}</b></span
                ><span><span class="k">品质</span> <b>{{ value(echo.quality) }}</b></span>
              </p>
            </div>
            <p v-if="badges.get(echo)" class="wuwa-echo-score" :aria-label="`单件评分 ${badges.get(echo).value} / 50${badges.get(echo).grade ? ' 等级 ' + badges.get(echo).grade : ''}`">
              <b>{{ badges.get(echo).value }}</b><span v-if="badges.get(echo).grade">{{ badges.get(echo).grade }}</span>
            </p>
          </header>
          <div class="wuwa-props">
            <h5>主词条</h5>
            <p v-if="!list(echo.main_props).length" class="wuwa-muted">未提供</p>
            <dl v-else class="wuwa-kv">
              <div v-for="(p, j) in list(echo.main_props)" :key="j">
                <dt>{{ p.attribute_name }}</dt>
                <dd>{{ value(p.attribute_value) }}</dd>
              </div>
            </dl>
            <h5>副词条</h5>
            <p v-if="!list(echo.sub_props).length" class="wuwa-muted">未提供</p>
            <dl v-else class="wuwa-kv">
              <div v-for="(p, j) in echo.sub_props" :key="j">
                <dt>{{ p.attribute_name }}</dt>
                <dd>{{ value(p.attribute_value) }}</dd>
              </div>
            </dl>
          </div>
          <p class="wuwa-set">
            <WuwaIcon :src="echo.fetter_detail?.icon_url" :name="echo.fetter_detail?.name || '套装'" size="small" />
            <strong>{{ echo.fetter_detail?.name || '套装未知' }}</strong>
            <span class="wuwa-meta"
              >套装已装备 {{ value(echo.fetter_detail?.num) }} 件</span
            >
          </p>
        </article>
      </div>
      <p v-else class="wuwa-muted">暂无装备声骸数据</p>
      <RoleAssessment v-if="live" ref="editor" class="wuwa-echo-editor" embedded auto-load game="wuthering_waves" :character-id="String(data.role?.role_id || '')" @assessment="liveScore = $event" @state="editorState = $event" />
      <WuwaFields
        :data="data.phantom_data"
        :exclude="['cost', 'equip_phantom_list']"
      />
    </section>

    <details v-if="!imageMode" class="wuwa-supplement">
      <summary>声骸汇总属性</summary>
      <dl
        v-if="isAttributeList(data.equip_phantom_attribute_list)"
        class="wuwa-kv"
      >
        <div
          v-for="(p, i) in list(data.equip_phantom_attribute_list)"
          :key="i"
        >
          <dt>{{ p.attribute_name }}</dt>
          <dd>{{ value(p.attribute_value) }}</dd>
        </div>
      </dl>
      <WuwaFields v-else :data="data.equip_phantom_attribute_list" />
      <p class="wuwa-field-label">声骸附加属性汇总</p>
      <dl
        v-if="isAttributeList(data.equip_phantom_add_prop_list)"
        class="wuwa-kv"
      >
        <div
          v-for="(p, i) in list(data.equip_phantom_add_prop_list)"
          :key="i"
        >
          <dt>{{ p.attribute_name }}</dt>
          <dd>{{ value(p.attribute_value) }}</dd>
        </div>
      </dl>
      <WuwaFields v-else :data="data.equip_phantom_add_prop_list" />
    </details>
    <WuwaFields
      :data="data"
      :exclude="[
        'role',
        'active_branch_id',
        'role_attribute_list',
        'weapon_data',
        'skill_list',
        'chain_list',
        'phantom_data',
        'equip_phantom_attribute_list',
        'equip_phantom_add_prop_list',
        'role_skin',
        // The image layout already prints the level on the portrait card.
        ...(imageMode ? ['level'] : []),
      ]"
    />
  </div>
</template>

<style scoped>
.role-profile-heading{display:flex;align-items:center;gap:8px}
/* The echo's score sits at the end of its head: the value, then the grade as a tone tag. */
.wuwa-echo-score{display:inline-flex;flex:none;align-items:baseline;gap:6px;margin:0 0 0 auto;font-variant-numeric:tabular-nums}
.wuwa-echo-score b{color:var(--text);font-size:15px;font-weight:600}
.wuwa-echo-score span{padding:0 8px;border-radius:var(--radius-chip);background:var(--wuwa-tone);color:var(--wuwa-ink);font-size:12px;font-weight:600;line-height:20px}
.wuwa-echo-total{color:var(--wuwa-ink);font-weight:600;font-variant-numeric:tabular-nums}
.wuwa-echo-weights{margin-left:auto}
.wuwa-echo-editor{margin-top:12px}
</style>
