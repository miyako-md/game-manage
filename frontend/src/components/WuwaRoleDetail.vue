<script setup>
import { computed } from 'vue'
import { safeUrl } from '../calendar.js'
import { fieldLabels, list, value } from '../wuwa-display.js'
import WuwaFields from './WuwaFields.vue'
import InfoHint from './InfoHint.vue'
const props = defineProps({ data: { type: Object, default: () => ({}) } })
const stars = (n) => {
  const count = Number(n)
  return Number.isInteger(count) && count > 0 && count <= 6 ? count : 0
}
const chains = computed(() => list(props.data.chain_list))
const unlockedChains = computed(
  () => chains.value.filter((c) => c.unlocked === true).length,
)
const echoes = computed(() => list(props.data.phantom_data?.equip_phantom_list))
const SET_EFFECTS = ['first_description', 'second_description', 'triple_description']
// Five echoes usually share one or two sets: each set's effects show once.
const sets = computed(() => {
  const seen = new Map()
  for (const echo of echoes.value) {
    const set = echo.fetter_detail
    const effects = SET_EFFECTS.filter((k) => set?.[k]).map((k) => [
      fieldLabels[k],
      set[k],
    ])
    if (!set?.name || !effects.length) continue
    const key = `${set.name}\u0000${effects.flat().join('\u0000')}`
    if (!seen.has(key)) seen.set(key, { key, name: set.name, effects })
  }
  return [...seen.values()]
})
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
    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">角色基本信息</h3>
      <div class="wuwa-basics">
        <img
          v-if="safeUrl(data.role_skin?.skin_icon)"
          class="wuwa-skin"
          :src="safeUrl(data.role_skin.skin_icon)"
          alt="当前外观"
          loading="lazy"
        />
        <div class="wuwa-basics-body">
          <WuwaFields :data="data.role" />
          <div class="wuwa-field-group">
            <span class="wuwa-field-label" role="heading" aria-level="4">角色外观</span
            ><WuwaFields :data="data.role_skin" />
          </div>
          <dl class="wuwa-kv">
            <div>
              <dt>当前分支（来源编号）</dt>
              <dd>
                {{ value(data.active_branch_id) }}
                <InfoHint
                  text="分支编号仅为来源标识，不代表已解锁数量或练度。"
                  align="end"
                />
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </section>

    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">完整属性</h3>
      <dl
        v-if="list(data.role_attribute_list).length"
        class="kv-grid wuwa-attrs"
      >
        <div v-for="(p, i) in list(data.role_attribute_list)" :key="i">
          <dt>{{ p.attribute_name || '未知属性' }}</dt>
          <dd>{{ value(p.attribute_value) }}</dd>
        </div>
      </dl>
      <p v-else class="wuwa-muted">未提供属性</p>
    </section>

    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">实际装备武器</h3>
      <div v-if="data.weapon_data" class="wuwa-equip">
        <img
          v-if="safeUrl(data.weapon_data.weapon?.weapon_icon)"
          :src="safeUrl(data.weapon_data.weapon.weapon_icon)"
          alt="装备武器"
          loading="lazy"
        />
        <div class="wuwa-equip-body">
          <p class="wuwa-equip-name">
            <strong>{{
              data.weapon_data.weapon?.weapon_name || '名称未知'
            }}</strong
            ><span
              v-if="stars(data.weapon_data.weapon?.weapon_star_level)"
              class="stars"
              role="img"
              :aria-label="`${data.weapon_data.weapon.weapon_star_level} 星`"
              >{{
                '★'.repeat(stars(data.weapon_data.weapon.weapon_star_level))
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
          <p
            v-if="
              data.weapon_data.weapon?.weapon_effect_name ||
              data.weapon_data.weapon?.effect_description
            "
            class="wuwa-effect"
          >
            <strong>{{ data.weapon_data.weapon?.weapon_effect_name }}</strong>
            {{ data.weapon_data.weapon?.effect_description }}
          </p>
          <details class="wuwa-supplement">
            <summary>武器来源补充资料</summary>
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
        未提供装备武器<InfoHint text="角色列表中的武器类型不代表实际装备。" />
      </p>
    </section>

    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">技能</h3>
      <p v-if="!list(data.skill_list).length" class="wuwa-muted">未提供</p>
      <div v-else class="wuwa-tiles wuwa-skills">
        <article
          v-for="(entry, i) in list(data.skill_list)"
          :key="i"
          class="wuwa-tile"
        >
          <header class="wuwa-tile-head">
            <h4>{{ entry.skill?.name || '未知技能' }}</h4>
            <span v-if="entry.skill?.type" class="chip">{{
              entry.skill.type
            }}</span>
            <span class="wuwa-tile-end wuwa-gold">Lv.{{ value(entry.level) }}</span>
          </header>
          <ul class="chip-list wuwa-skill-meta">
            <li class="wuwa-meta">
              分支激活 {{ value(entry.active_branch) }}
            </li>
            <li
              v-for="(b, j) in list(entry.skill?.skill_branches)"
              :key="j"
              class="chip"
              :title="b?.description || undefined"
            >
              {{ b?.name || `分支 ${j + 1}` }}
            </li>
          </ul>
          <p v-if="entry.skill?.description" class="wuwa-description">
            {{ entry.skill.description }}
          </p>
          <details class="wuwa-supplement">
            <summary>分支说明与来源资料</summary>
            <WuwaFields
              :data="entry.skill"
              :exclude="['name', 'type', 'description']"
            />
            <WuwaFields
              :data="entry"
              :exclude="['skill', 'level', 'active_branch']"
            />
          </details>
        </article>
      </div>
    </section>

    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">
        共鸣链<span v-if="chains.length" class="wuwa-meta"
          >已解锁 {{ unlockedChains }} / {{ chains.length }}</span
        >
      </h3>
      <div v-if="chains.length" class="wuwa-chains">
        <details
          v-for="(chain, i) in chains"
          :key="i"
          class="wuwa-chain"
          :class="{ 'wuwa-locked': chain.unlocked === false }"
          open
        >
          <summary>
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
          </summary>
          <p v-if="chain.description" class="wuwa-description">
            {{ chain.description }}
          </p>
          <WuwaFields
            :data="chain"
            :exclude="['order', 'name', 'unlocked', 'description']"
          />
        </details>
      </div>
      <p v-else class="wuwa-muted">未提供</p>
    </section>

    <section class="wuwa-detail-section">
      <h3 class="wuwa-subhead">
        装备声骸<span class="wuwa-meta"
          >总 COST {{ value(data.phantom_data?.cost) }}</span
        >
      </h3>
      <div v-if="echoes.length" class="wuwa-tiles wuwa-echoes">
        <article v-for="(echo, i) in echoes" :key="i" class="wuwa-tile">
          <header class="wuwa-echo-head">
            <img
              v-if="safeUrl(echo.phantom_prop?.icon_url)"
              :src="safeUrl(echo.phantom_prop.icon_url)"
              alt="声骸"
              loading="lazy"
            />
            <div>
              <h4>{{ echo.phantom_prop?.name || '未知声骸' }}</h4>
              <p class="wuwa-inline">
                <span><span class="k">等级</span> <b>{{ value(echo.level) }}</b></span
                ><span><span class="k">COST</span> <b>{{ value(echo.cost) }}</b></span
                ><span><span class="k">品质</span> <b>{{ value(echo.quality) }}</b></span>
              </p>
            </div>
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
            <strong>{{ echo.fetter_detail?.name || '套装未知' }}</strong>
            <span class="wuwa-meta"
              >套装已装备数量 {{ value(echo.fetter_detail?.num) }}</span
            >
          </p>
          <details class="wuwa-supplement">
            <summary>声骸技能与来源资料</summary>
            <template v-if="echo.phantom_prop?.skill_description">
              <p class="wuwa-field-label">声骸技能</p>
              <p class="wuwa-description">
                {{ echo.phantom_prop.skill_description }}
              </p>
            </template>
            <div class="wuwa-subfields">
              <p class="wuwa-field-label">声骸资料</p>
              <WuwaFields
                :data="echo.phantom_prop"
                :exclude="['name', 'skill_description']"
              />
            </div>
            <div class="wuwa-subfields">
              <p class="wuwa-field-label">套装资料</p>
              <WuwaFields
                :data="echo.fetter_detail"
                :exclude="['name', 'num', ...SET_EFFECTS]"
              />
            </div>
            <div class="wuwa-subfields">
              <p class="wuwa-field-label">装备资料</p>
              <WuwaFields
                :data="echo"
                :exclude="[
                  'phantom_prop',
                  'fetter_detail',
                  'level',
                  'cost',
                  'quality',
                  'main_props',
                  'sub_props',
                ]"
              />
            </div>
          </details>
        </article>
      </div>
      <p v-else class="wuwa-muted">未提供装备声骸</p>
      <dl v-if="sets.length" class="wuwa-sets">
        <div v-for="set in sets" :key="set.key">
          <dt>{{ set.name }}</dt>
          <dd>
            <p v-for="[label, text] in set.effects" :key="label">
              <span class="k">{{ label }}</span> {{ text }}
            </p>
          </dd>
        </div>
      </dl>
      <WuwaFields
        :data="data.phantom_data"
        :exclude="['cost', 'equip_phantom_list']"
      />
    </section>

    <details class="wuwa-supplement">
      <summary>声骸汇总属性</summary>
      <p class="wuwa-field-label">声骸属性汇总</p>
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
      <p class="wuwa-field-label">声骸附加属性汇总（非单个声骸副词条）</p>
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
      ]"
    />
  </div>
</template>
