<script setup>
import { displayRoleValue as display, roleId } from '../nte-roles.js'
import { nteNamedIcon, nteSkillIcon } from '../nte-icons.js'
import NteIcon from './NteIcon.vue'
import NteEquippedDetails from './NteEquippedDetails.vue'
import RoleAssessment from './RoleAssessment.vue'
import { ref } from 'vue'
defineProps({role:{type:Object,required:true},accountId:{type:[String,Object],default:''},imageMode:Boolean})
// The website reads the equipped score once (RoleAssessment auto-load) and hands it to the piece badges.
const live=ref(null)
const list=value=>Array.isArray(value)?value.filter(row=>row&&typeof row==='object'):[]
</script>
<template>
            <div class="detail-body">
              <div :data-render-block="imageMode ? '' : undefined"><RoleAssessment game="nte" auto-load :character-id="roleId(role)" :scope-key="accountId" :image-mode="imageMode" :initial-assessment="role.assessment" @assessment="live = $event" /></div>
              <section class="detail-group" :data-render-block="imageMode ? '' : undefined">
                <h4>弧盘</h4>
                <p v-if="role.weapon" class="weapon"><NteIcon :src="nteNamedIcon('weapons', role.weapon.name)" :name="role.weapon.name || '弧盘'" size="small" /><strong>{{ display(role.weapon.name) }}</strong><span class="chip">{{ display(role.weapon.quality) }}</span><span class="chip">Lv{{ display(role.weapon.level) }}</span><span class="chip">混频 <b>{{ display(role.weapon.mix_level) }}</b></span></p>
                <p v-else class="muted">暂无数据</p>
              </section>
              <section v-for="group in [{ name: '属性', rows: role.properties, value: 'value' }, { name: '战技', rows: role.skills, value: 'level' }, { name: '城区技能', rows: role.city_skills, value: 'level' }]" :key="group.name" class="detail-group" :data-render-block="imageMode ? '' : undefined">
                <h4>{{ group.name }}</h4>
                <dl v-if="list(group.rows).length" class="detail-rows"><div v-for="(entry, index) in list(group.rows)" :key="index"><dt class="skill-name"><NteIcon v-if="group.value === 'level'" :src="nteSkillIcon(role.id, entry.name)" :name="entry.name || '技能'" size="small" /><span :title="display(entry.name)">{{ display(entry.name) }}</span></dt><dd>{{ group.value === 'level' && display(entry[group.value]) !== '未提供' ? 'Lv' : '' }}{{ display(entry[group.value]) }}</dd></div></dl>
                <p v-else class="muted">暂无数据</p>
              </section>
              <NteEquippedDetails :role="role" :image-mode="imageMode" :assessment="imageMode ? role.assessment : live" />
            </div>
</template>
<style scoped>
.detail-body{display:grid;gap:14px;padding-top:12px}.detail-group{padding:12px;background:var(--surface-soft);border-radius:var(--radius-well)}h4{margin:0 0 8px;font-size:13px;color:var(--text-muted)}.weapon{display:flex;flex-wrap:wrap;align-items:center;gap:6px}.detail-rows{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:0 16px}.detail-rows>div{display:flex;justify-content:space-between;gap:8px;padding:4px 0;min-width:0}dt{color:var(--text-muted)}dd{margin:0}.skill-name{display:flex;gap:6px;align-items:center}.muted{color:var(--text-muted)}
</style>
