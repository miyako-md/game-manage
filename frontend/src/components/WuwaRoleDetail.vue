<script setup>
import { safeUrl } from '../calendar.js'
import { list, value } from '../wuwa-display.js'
import WuwaFields from './WuwaFields.vue'
defineProps({ data: { type: Object, default: () => ({}) } })
</script>
<template>
  <div class="wuwa-stack">
    <section class="wuwa-inset">
      <h3>角色基本信息</h3>
      <WuwaFields :data="data.role" />
      <details>
        <summary>当前分支与来源资料</summary>
        <p>当前分支（来源编号） {{ value(data.active_branch_id) }}</p>
        <p class="wuwa-meta">分支编号仅为来源标识，不代表已解锁数量或练度。</p>
      </details>
    </section>
    <section class="wuwa-inset">
      <h3>角色外观</h3>
      <div class="wuwa-equipment">
        <img
          v-if="safeUrl(data.role_skin?.skin_icon)"
          :src="safeUrl(data.role_skin.skin_icon)"
          alt="当前外观"
          loading="lazy"
        />
        <WuwaFields :data="data.role_skin" />
      </div>
    </section>
    <section>
      <h3>完整属性</h3>
      <dl class="wuwa-stat-grid">
        <div v-for="(p, i) in list(data.role_attribute_list)" :key="i">
          <dt>{{ p.attribute_name || '未知属性' }}</dt>
          <dd>{{ value(p.attribute_value) }}</dd>
        </div>
      </dl>
      <p v-if="!list(data.role_attribute_list).length" class="wuwa-muted">
        未提供属性
      </p>
    </section>
    <section class="wuwa-inset">
      <h3>实际装备武器</h3>
      <div v-if="data.weapon_data" class="wuwa-equipment">
        <img
          v-if="safeUrl(data.weapon_data.weapon?.weapon_icon)"
          :src="safeUrl(data.weapon_data.weapon.weapon_icon)"
          alt="装备武器"
          loading="lazy"
        />
        <div>
          <h4>{{ data.weapon_data.weapon?.weapon_name || '名称未知' }}</h4>
          <p>
            等级 {{ value(data.weapon_data.level) }} · 突破
            {{ value(data.weapon_data.breach) }} · 谐振
            {{ value(data.weapon_data.reson_level) }} ·
            {{ value(data.weapon_data.weapon?.weapon_star_level) }} 星
          </p>
          <dl>
            <div
              v-for="(p, i) in list(data.weapon_data.main_prop_list)"
              :key="i"
            >
              <dt>{{ p.attribute_name }}</dt>
              <dd>{{ value(p.attribute_value) }}</dd>
            </div>
          </dl>
          <strong>{{ data.weapon_data.weapon?.weapon_effect_name }}</strong>
          <p class="wuwa-description">
            {{ data.weapon_data.weapon?.effect_description }}
          </p>
          <details>
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
        未提供装备武器；角色列表中的武器类型不代表实际装备。
      </p>
    </section>
    <section>
      <h3>技能</h3>
      <p v-if="!list(data.skill_list).length" class="wuwa-muted">未提供</p>
      <div class="wuwa-grid">
        <article
          v-for="(entry, i) in list(data.skill_list)"
          :key="i"
          class="wuwa-inset"
        >
          <h4>
            {{ entry.skill?.name || '未知技能' }}
            <span class="wuwa-gold">Lv.{{ value(entry.level) }}</span>
          </h4>
          <p class="wuwa-meta">
            {{ entry.skill?.type }} · 分支激活 {{ value(entry.active_branch) }}
          </p>
          <p class="wuwa-description">{{ entry.skill?.description }}</p>
          <WuwaFields
            v-if="list(entry.skill?.skill_branches).length"
            :data="entry.skill.skill_branches"
          />
          <details>
            <summary>技能来源补充资料</summary>
            <WuwaFields
              :data="entry.skill"
              :exclude="['name', 'type', 'description', 'skill_branches']"
            />
            <WuwaFields
              :data="entry"
              :exclude="['skill', 'level', 'active_branch']"
            />
          </details>
        </article>
      </div>
    </section>
    <section>
      <h3>共鸣链</h3>
      <div class="wuwa-grid">
        <article
          v-for="(chain, i) in list(data.chain_list)"
          :key="i"
          class="wuwa-inset"
          :class="{ 'wuwa-locked': chain.unlocked === false }"
        >
          <h4>
            {{ value(chain.order) }} · {{ chain.name }}
            <span class="wuwa-meta">{{
              chain.unlocked === true
                ? '已解锁'
                : chain.unlocked === false
                  ? '未解锁'
                  : '解锁状态未知'
            }}</span>
          </h4>
          <p class="wuwa-description">{{ chain.description }}</p>
          <WuwaFields
            :data="chain"
            :exclude="['order', 'name', 'unlocked', 'description']"
          />
        </article>
      </div>
      <p v-if="!list(data.chain_list).length" class="wuwa-muted">未提供</p>
    </section>
    <section>
      <h3>
        装备声骸
        <span class="wuwa-meta"
          >总 COST {{ value(data.phantom_data?.cost) }}</span
        >
      </h3>
      <div class="wuwa-grid">
        <article
          v-for="(echo, i) in list(data.phantom_data?.equip_phantom_list)"
          :key="i"
          class="wuwa-inset"
        >
          <div class="wuwa-equipment">
            <img
              v-if="safeUrl(echo.phantom_prop?.icon_url)"
              :src="safeUrl(echo.phantom_prop.icon_url)"
              alt="声骸"
              loading="lazy"
            />
            <div>
              <h4>{{ echo.phantom_prop?.name || '未知声骸' }}</h4>
              <p>
                等级 {{ value(echo.level) }} · COST {{ value(echo.cost) }} ·
                品质 {{ value(echo.quality) }}
              </p>
            </div>
          </div>
          <h4>主词条</h4>
          <dl>
            <div v-for="(p, j) in list(echo.main_props)" :key="j">
              <dt>{{ p.attribute_name }}</dt>
              <dd>{{ value(p.attribute_value) }}</dd>
            </div>
          </dl>
          <p v-if="!list(echo.main_props).length">未提供</p>
          <h4>副词条</h4>
          <p v-if="!list(echo.sub_props).length">未提供</p>
          <dl v-else>
            <div v-for="(p, j) in echo.sub_props" :key="j">
              <dt>{{ p.attribute_name }}</dt>
              <dd>{{ value(p.attribute_value) }}</dd>
            </div>
          </dl>
          <h4>{{ echo.fetter_detail?.name || '套装未知' }}</h4>
          <p>套装已装备数量 {{ value(echo.fetter_detail?.num) }}</p>
          <p
            v-for="key in [
              'first_description',
              'second_description',
              'triple_description',
            ]"
            :key="key"
            class="wuwa-description"
          >
            {{ echo.fetter_detail?.[key] }}
          </p>
          <details v-if="echo.phantom_prop?.skill_description">
            <summary>声骸技能</summary>
            <p class="wuwa-description">
              {{ echo.phantom_prop.skill_description }}
            </p>
          </details>
          <details>
            <summary>声骸与套装来源补充资料</summary>
            <h4>声骸资料</h4>
            <WuwaFields
              :data="echo.phantom_prop"
              :exclude="['name', 'skill_description']"
            />
            <h4>套装资料</h4>
            <WuwaFields
              :data="echo.fetter_detail"
              :exclude="[
                'name',
                'num',
                'first_description',
                'second_description',
                'triple_description',
              ]"
            />
            <h4>装备资料</h4>
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
          </details>
        </article>
      </div>
      <p
        v-if="!list(data.phantom_data?.equip_phantom_list).length"
        class="wuwa-muted"
      >
        未提供装备声骸
      </p>
      <WuwaFields
        :data="data.phantom_data"
        :exclude="['cost', 'equip_phantom_list']"
      />
    </section>
    <details>
      <summary>声骸汇总属性</summary>
      <h4>声骸属性汇总</h4>
      <WuwaFields :data="data.equip_phantom_attribute_list" />
      <h4>声骸附加属性汇总（非单个声骸副词条）</h4>
      <WuwaFields :data="data.equip_phantom_add_prop_list" />
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
