<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '../calendar.js'
import { displayRoleValue as display } from '../nte-roles.js'
import { nteNamedIcon, nteRoleIcon, nteSkillIcon } from '../nte-icons.js'
import { gradeTier, nteBadges, nteStatFlags, statTone } from '../assessment-display.js'
import { driveCells, driveQuality, driveShape } from '../nte-drive-shapes.js'
import NteIcon from './NteIcon.vue'
import RoleScoreHero from './RoleScoreHero.vue'
// The QQ role image (role sheet) for one NTE role: official art with name, level and the arc disk;
// the attributes; the skills; then the equipment score card and the cartridge and drives, three a row,
// each stat coloured by whether the score counts it. The website keeps NteRoleDetail.
const props = defineProps({ role: { type: Object, required: true } })
const rows = value => Array.isArray(value) ? value.filter(row => row && typeof row === 'object') : []
// The official half-length art, else the catalog icon; a picture that fails to load is dropped, never
// left for the image's alt-text stand-in over the name.
const pictures = computed(() => [...new Set([safeUrl(props.role.icon_url), nteRoleIcon(props.role.id), nteRoleIcon(props.role.name)].filter(Boolean))])
const failed = ref(0)
watch(pictures, () => { failed.value = 0 })
const art = computed(() => pictures.value[failed.value] || '')
const weapon = computed(() => props.role.weapon || null)
// Unknown awakening or mix level reads 未提供, never 0; a missing element is simply left out.
const facts = computed(() => [...(props.role.element ? [['元素', props.role.element]] : []), ['觉醒', props.role.awaken_level], ['混频', props.role.mix_level]])
// The core attributes always show; any other that is exactly zero is left out and counted.
const CORE = new Set(['生命值', '攻击力', '防御力', '暴击率', '暴击伤害', '充能效率', '环合强度'])
const isZero = v => typeof v === 'number' ? v === 0 : typeof v === 'string' && /^0+(?:\.0+)?%?$/.test(v.trim())
const attributes = computed(() => rows(props.role.properties).filter(p => CORE.has(p.name) || !isZero(p.value)))
const zeroCount = computed(() => rows(props.role.properties).length - attributes.value.length)
const skills = computed(() => rows(props.role.skills))
const suit = computed(() => props.role.suit && typeof props.role.suit === 'object' ? props.role.suit : null)
// The upstream groups are `core` and `pie`: the game's 卡带 and 驱动.
const pieces = computed(() => ['core', 'pie'].flatMap(group => rows(suit.value?.[group]).map(item => ({ item, group }))))
const score = computed(() => props.role.assessment || null)
const badges = computed(() => nteBadges(score.value, suit.value))
const flags = computed(() => nteStatFlags(score.value, suit.value))
const tone = (item, kind, stat) => statTone(flags.value.get(item)?.get(`${kind}:${String(stat?.id ?? '').toLowerCase()}`))
</script>
<template>
  <div class="nte-role-sheet role-sheet">
    <section class="sheet-hero" :class="{ 'has-art': art }" data-render-block>
      <img v-if="art" :key="art" class="rs-art" :src="art" :alt="role.name || '角色'" @error="failed++" />
      <div class="rs-copy">
        <p class="hero-name"><strong>{{ display(role.name) }}</strong><b>Lv{{ display(role.level) }}</b><span v-if="role.quality" class="hero-rank" :class="`rank-${role.quality}`">{{ role.quality }}</span></p>
        <dl class="hero-facts"><div v-for="[k, v] in facts" :key="k"><dt>{{ k }}</dt><dd>{{ display(v) }}</dd></div></dl>
        <section v-if="weapon" class="sheet-weapon">
          <NteIcon :src="nteNamedIcon('weapons', weapon.name)" :name="weapon.name || '弧盘'" size="xl" />
          <div class="weapon-body">
            <p class="weapon-name"><strong>{{ display(weapon.name) }}</strong><span v-if="weapon.quality" class="hero-rank" :class="`rank-${weapon.quality}`">{{ weapon.quality }}</span></p>
            <p class="weapon-meta"><span>Lv{{ display(weapon.level) }}</span><span>混频 {{ display(weapon.mix_level) }}</span><span>突破 {{ display(weapon.breakthrough_level) }}</span></p>
            <p v-if="rows(weapon.properties).length" class="weapon-props"><span v-for="(p, i) in rows(weapon.properties)" :key="i">{{ display(p.name) }} <b>{{ display(p.value) }}</b></span></p>
          </div>
        </section>
        <p v-else class="sheet-muted">弧盘 暂无数据</p>
      </div>
    </section>

    <section class="sheet-card" data-render-block>
      <h3 class="sheet-title">属性<span v-if="zeroCount" class="sheet-meta">其余 {{ zeroCount }} 项为 0，未列出</span></h3>
      <dl v-if="attributes.length" class="sheet-attrs"><div v-for="(p, i) in attributes" :key="i"><dt>{{ display(p.name) }}</dt><dd>{{ display(p.value) }}</dd></div></dl>
      <p v-else class="sheet-muted">暂无数据</p>
    </section>

    <section class="sheet-card" data-render-block>
      <h3 class="sheet-title">战技</h3>
      <div v-if="skills.length" class="sheet-row sheet-skills" :style="{ '--row-count': Math.max(1, Math.min(skills.length, 6)) }">
        <article v-for="(entry, i) in skills" :key="i" class="sheet-skill">
          <NteIcon :src="nteSkillIcon(role.id, entry.name)" :name="entry.name || '技能'" size="large" />
          <b class="rs-skill-level">Lv{{ display(entry.level) }}</b>
          <span class="rs-skill-name">{{ display(entry.name) }}</span>
        </article>
      </div>
      <p v-else class="sheet-muted">暂无数据</p>
    </section>

    <section class="sheet-card">
      <h3 class="sheet-title">卡带与驱动<span v-if="suit" class="sheet-meta">{{ display(suit.name) }} · 激活 {{ display(suit.activation_count) }}</span></h3>
      <div v-if="score && pieces.length" class="equip-overview" data-render-block><RoleScoreHero :score="score" label="装备评分" /></div>
      <div v-if="pieces.length" class="sheet-pieces">
        <article v-for="({ item, group }, i) in pieces" :key="i" class="sheet-piece" data-render-block :data-quality="driveQuality(item.id) || undefined">
          <header class="piece-head">
            <span v-if="group === 'pie' && driveShape(item.id)" class="piece-shape" role="img" :aria-label="`${display(item.name)} 形状`">
              <span v-for="(line, r) in driveShape(item.id)" :key="r" class="shape-row"><i v-for="(filled, c) in line" :key="c" :class="{ filled }"></i></span>
            </span>
            <span v-else-if="group === 'pie'" class="piece-shape is-count" role="img" :aria-label="`${driveCells(item.id) ?? '未知'} 格`"><span class="shape-row"><i v-for="c in driveCells(item.id) || 0" :key="c" class="filled"></i></span></span>
            <NteIcon v-else :src="nteNamedIcon('sets', suit?.name)" :name="display(item.name)" size="large" />
            <div class="piece-title"><strong>{{ display(item.name) }}</strong><span>{{ group === 'core' ? '卡带' : '驱动' }} · Lv{{ display(item.level) }}</span></div>
            <p v-if="badges.get(item)" class="piece-score" :data-tier="gradeTier(badges.get(item).grade) ?? undefined" :aria-label="`单件评分 ${badges.get(item).value} / ${badges.get(item).max}${badges.get(item).grade ? ' 等级 ' + badges.get(item).grade : ''}`"><b>{{ badges.get(item).value }}</b><span v-if="badges.get(item).grade">{{ badges.get(item).grade }}</span></p>
          </header>
          <dl class="piece-stats is-main"><div v-for="(p, j) in rows(item.main_properties)" :key="j" :class="tone(item, 'main', p)"><dt>{{ display(p.name) }}</dt><dd>{{ display(p.value) }}</dd></div></dl>
          <dl class="piece-stats is-sub"><div v-for="(p, j) in rows(item.properties)" :key="j" :class="tone(item, 'sub', p)"><dt>{{ display(p.name) }}</dt><dd>{{ display(p.value) }}</dd></div></dl>
        </article>
      </div>
      <p v-else class="sheet-muted">{{ suit ? '驱动件 未提供' : '未装备' }}</p>
    </section>
  </div>
</template>
<style scoped>
.lab-sheet #render-content .nte-role-sheet{display:grid;gap:18px;color:var(--skin-ink,var(--text))}
.lab-sheet #render-content .nte-role-sheet p,.lab-sheet #render-content .nte-role-sheet dl,.lab-sheet #render-content .nte-role-sheet dd{margin:0}
.lab-sheet #render-content .sheet-card{min-width:0;padding:20px 22px;border-radius:var(--skin-radius-card,20px);background:var(--skin-surface,var(--card-bg));box-shadow:inset 0 0 0 1px var(--skin-line,var(--border))}
.lab-sheet #render-content .sheet-title{display:flex;align-items:baseline;flex-wrap:wrap;gap:12px;margin:0 0 14px}
.lab-sheet #render-content .sheet-meta{color:var(--skin-muted);font-size:var(--qq-min-text,17px)!important;font-weight:500}
.lab-sheet #render-content .sheet-muted{color:var(--skin-muted)}

/* Hero: the official half-length art on the right; name, facts and the arc disk on the left. */
.lab-sheet #render-content .sheet-hero{position:relative;min-height:400px;padding:28px 30px;border-radius:var(--skin-radius-card,20px);overflow:hidden;background:var(--skin-surface);box-shadow:inset 0 0 0 1px var(--skin-line-strong,var(--border))}
.lab-sheet #render-content .rs-art{position:absolute;right:-30px;bottom:0;height:100%;max-width:68%;object-fit:contain;object-position:right bottom}
.lab-sheet #render-content .rs-copy{position:relative;z-index:1;display:grid;align-content:start;gap:16px;max-width:54%}
.lab-sheet #render-content .hero-name{display:flex;align-items:baseline;flex-wrap:wrap;gap:14px}
.lab-sheet #render-content .hero-name strong{font-size:48px!important;font-weight:800;line-height:1.15!important}
.lab-sheet #render-content .hero-name b{color:var(--skin-accent);font-size:28px!important}
.lab-sheet #render-content .hero-rank{padding:0 10px;border-radius:8px;background:rgba(var(--skin-tint-rgb),.16);color:var(--skin-accent);font-weight:800}
.lab-sheet #render-content .hero-rank.rank-S{background:#f2c14e;color:#1b1407}
.lab-sheet #render-content .hero-facts{display:flex;flex-wrap:wrap;gap:8px}
.lab-sheet #render-content .hero-facts>div{display:flex;gap:8px;padding:4px 12px;border-radius:999px;background:rgba(10,8,16,.62);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .hero-facts dt{color:var(--skin-muted)}
.lab-sheet #render-content .hero-facts dd{font-weight:600}
.lab-sheet #render-content .sheet-weapon{display:flex;align-items:center;gap:14px;padding:14px 16px;border-radius:var(--skin-radius-tile,14px);background:rgba(10,8,16,.7);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .weapon-body{display:grid;gap:4px;min-width:0}
.lab-sheet #render-content .weapon-name{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.lab-sheet #render-content .weapon-name strong{color:var(--skin-accent);font-size:24px!important}
.lab-sheet #render-content .weapon-meta,.lab-sheet #render-content .weapon-props{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--skin-muted)}
.lab-sheet #render-content .weapon-props b{color:var(--skin-ink);font-variant-numeric:tabular-nums}

.lab-sheet #render-content .sheet-attrs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
.lab-sheet #render-content .sheet-attrs>div{display:flex;justify-content:space-between;gap:12px;padding:7px 2px;border-bottom:1px solid var(--line)}
.lab-sheet #render-content .sheet-attrs dt{color:var(--skin-muted)}
.lab-sheet #render-content .sheet-attrs dd{color:var(--skin-hot,var(--skin-ink));font-weight:600;font-variant-numeric:tabular-nums}

.lab-sheet #render-content .sheet-row{display:grid;grid-template-columns:repeat(var(--row-count,6),minmax(0,1fr));gap:10px}
.lab-sheet #render-content .sheet-skill{display:grid;justify-items:center;align-content:start;gap:4px;min-width:0;padding:12px 6px;border-radius:var(--skin-radius-tile,14px);background:rgba(var(--skin-tint-rgb),.06);text-align:center}
.lab-sheet #render-content .rs-skill-level{color:var(--skin-accent);font-size:22px!important}
.lab-sheet #render-content .rs-skill-name{color:var(--skin-ink);font-size:var(--qq-min-text,17px)!important;line-height:1.3!important;overflow-wrap:anywhere}

.lab-sheet #render-content .equip-overview{margin-bottom:16px}
.lab-sheet #render-content .sheet-pieces{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.lab-sheet #render-content .sheet-piece{--quality:#9aa3ad;display:grid;align-content:start;gap:8px;min-width:0;padding:14px;border-radius:var(--skin-radius-tile,14px);background:rgba(var(--skin-tint-rgb),.06);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .sheet-piece[data-quality="orange"]{--quality:#f0a040}
.lab-sheet #render-content .sheet-piece[data-quality="purple"]{--quality:#b67dff}
.lab-sheet #render-content .sheet-piece[data-quality="blue"]{--quality:#5aa7ff}
.lab-sheet #render-content .piece-head{display:flex;align-items:center;gap:10px}
.lab-sheet #render-content .piece-shape{display:grid;flex:none;place-content:center;gap:3px;width:56px;height:56px;border-radius:10px;background:rgba(0,0,0,.28)}
.lab-sheet #render-content .shape-row{display:flex;gap:3px;justify-content:center}
.lab-sheet #render-content .shape-row i{width:11px;height:11px;border-radius:2px}
.lab-sheet #render-content .shape-row i.filled{background:var(--quality)}
.lab-sheet #render-content .piece-title{display:grid;flex:1;min-width:0}
.lab-sheet #render-content .piece-title strong{line-height:1.3!important;overflow-wrap:anywhere}
.lab-sheet #render-content .piece-title span{color:var(--skin-muted);white-space:nowrap}
.lab-sheet #render-content .piece-score{display:grid;justify-items:center;flex:none;min-width:64px;padding:4px 8px;border-radius:10px;background:color-mix(in srgb,var(--tier,#9aa3ad) 20%,transparent);box-shadow:inset 0 0 0 1px var(--tier,#9aa3ad);font-variant-numeric:tabular-nums}
.lab-sheet #render-content .piece-score b{color:var(--tier,#9aa3ad);font-size:22px!important;line-height:1.2!important}
.lab-sheet #render-content .piece-score span{color:var(--tier,#9aa3ad);font-weight:800}
.lab-sheet #render-content .piece-stats{display:grid}
.lab-sheet #render-content .piece-stats>div{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)}
.lab-sheet #render-content .piece-stats.is-main>div:last-child{border-bottom:2px solid var(--skin-line-strong,var(--line))}
.lab-sheet #render-content .piece-stats dd{font-variant-numeric:tabular-nums}
.lab-sheet #render-content .piece-stats>.stat-effective :is(dt,dd){color:var(--skin-accent);font-weight:700}
.lab-sheet #render-content .piece-stats>.stat-ineffective :is(dt,dd){color:var(--skin-muted);opacity:.75}
</style>
