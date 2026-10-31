<script setup>
import { computed, ref, watch } from 'vue'
import { safeUrl } from '../calendar.js'
import { list, starCount, value } from '../wuwa-display.js'
import { echoBadges, echoStatFlags, gradeTier, statTone } from '../assessment-display.js'
import WuwaIcon from './WuwaIcon.vue'
import RoleScoreHero from './RoleScoreHero.vue'
// The QQ role image (role sheet): official art with name, level and the weapon; attributes; one row
// each of skills and chains; then the echo score card, the echo totals and three echoes a row, each
// stat coloured by whether the score counts it. The website keeps WuwaRoleDetail's own layout.
const props = defineProps({ data: { type: Object, default: () => ({}) } })
const role = computed(() => props.data.role || {})
// The official cut-out art first; the outfit or role icon when it is missing or fails to load, then the
// initial. A failed picture is dropped rather than left for the image's alt-text stand-in over the name.
const pictures = computed(() => [...new Set([role.value.role_pic_url, props.data.role_skin?.skin_icon, role.value.role_icon_url].map(safeUrl).filter(Boolean))])
const failed = ref(0)
watch(pictures, () => { failed.value = 0 })
const art = computed(() => pictures.value[failed.value] || '')
const cutout = computed(() => Boolean(art.value) && art.value === safeUrl(role.value.role_pic_url))
const stars = computed(() => starCount(role.value.star_level))
const attributes = computed(() => list(Array.isArray(props.data.role_attribute_list) ? props.data.role_attribute_list : role.value.role_attribute_list))
const weapon = computed(() => props.data.weapon_data || null)
const skills = computed(() => list(props.data.skill_list))
const chains = computed(() => list(props.data.chain_list))
const unlocked = computed(() => chains.value.filter(c => c.unlocked === true).length)
const facts = computed(() => [
  ['属性', role.value.attribute_name], ['武器', role.value.weapon_type_name], ['突破', role.value.breach],
  ['共鸣链', chains.value.length ? `${unlocked.value} / ${chains.value.length}` : null], ['外观', props.data.role_skin?.skin_name],
].filter(([, v]) => v != null && v !== ''))
const rawEchoes = computed(() => props.data.phantom_data?.equip_phantom_list)
const echoes = computed(() => list(rawEchoes.value).filter(e => typeof e === 'object'))
const score = computed(() => props.data.assessment || null)
const badges = computed(() => echoBadges(score.value, rawEchoes.value))
const flags = computed(() => echoStatFlags(score.value, rawEchoes.value))
// Rows keep their source position: the score names them `main_props:<row>` / `sub_props:<row>`.
const rows = v => Array.isArray(v) ? v.flatMap((p, j) => p && typeof p === 'object' ? [[p, j]] : []) : []
const tone = (echo, group, j) => statTone(flags.value.get(echo)?.get(`${group}:${j}`))
// The role-level totals the echoes add (the source's own summary list).
const totals = computed(() => list(props.data.equip_phantom_add_prop_list).filter(p => p?.attribute_name != null))
const skillCount = computed(() => Math.max(1, Math.min(skills.value.length, 7)))
const chainCount = computed(() => Math.max(1, Math.min(chains.value.length, 6)))
</script>
<template>
  <div class="wuwa-role-sheet role-sheet">
    <section class="sheet-hero wuwa-detail-basics" :class="{ 'is-cutout': cutout }" data-render-block>
      <figure class="wuwa-portrait">
        <img v-if="art" :key="art" :src="art" :alt="role.role_name || '角色'" @error="failed++" />
        <span v-else class="wuwa-portrait-fallback" aria-hidden="true">{{ (role.role_name || '?').slice(0, 1) }}</span>
        <figcaption><strong>{{ role.role_name || '角色' }}</strong> <b>Lv.{{ value(role.level) }}</b></figcaption>
      </figure>
      <div class="rs-copy">
        <p v-if="stars" class="hero-stars" role="img" :aria-label="`${stars} 星`">{{ '★'.repeat(stars) }}</p>
        <dl v-if="facts.length" class="hero-facts"><div v-for="[k, v] in facts" :key="k"><dt>{{ k }}</dt><dd>{{ v }}</dd></div></dl>
        <section class="sheet-weapon wuwa-detail-weapon">
          <template v-if="weapon">
            <WuwaIcon :src="weapon.weapon?.weapon_icon" :name="weapon.weapon?.weapon_name || '武器'" size="large" />
            <div class="weapon-body">
              <p class="weapon-name"><strong>{{ weapon.weapon?.weapon_name || '名称未知' }}</strong><span v-if="starCount(weapon.weapon?.weapon_star_level)" class="weapon-stars" role="img" :aria-label="`${weapon.weapon.weapon_star_level} 星`">{{ '★'.repeat(starCount(weapon.weapon.weapon_star_level)) }}</span></p>
              <p class="weapon-meta"><span>Lv.{{ value(weapon.level) }}</span><span>突破 {{ value(weapon.breach) }}</span><span>谐振 {{ value(weapon.reson_level) }}</span></p>
              <p class="weapon-props"><span v-for="(p, i) in list(weapon.main_prop_list)" :key="i">{{ p.attribute_name }} <b>{{ value(p.attribute_value) }}</b></span></p>
            </div>
          </template>
          <p v-else class="sheet-muted">暂无装备武器数据</p>
        </section>
      </div>
    </section>

    <section class="sheet-card wuwa-detail-attrs" data-render-block>
      <h3 class="sheet-title">完整属性</h3>
      <dl v-if="attributes.length" class="sheet-attrs">
        <div v-for="(p, i) in attributes" :key="i"><dt><WuwaIcon :src="p.icon_url" :name="p.attribute_name || '属性'" size="small" />{{ p.attribute_name || '未知属性' }}</dt><dd>{{ value(p.attribute_value) }}</dd></div>
      </dl>
      <p v-else class="sheet-muted">未提供属性</p>
    </section>

    <section class="sheet-card wuwa-detail-skills" data-render-block>
      <h3 class="sheet-title">技能</h3>
      <div v-if="skills.length" class="sheet-row sheet-skills" :style="{ '--row-count': skillCount }">
        <article v-for="(entry, i) in skills" :key="i" class="sheet-skill">
          <WuwaIcon :src="entry.skill?.icon_url" :name="entry.skill?.name || '技能'" size="large" />
          <span class="skill-type">{{ entry.skill?.type || '技能' }}</span>
          <b class="rs-skill-level">Lv.{{ value(entry.level) }}</b>
          <span class="rs-skill-name">{{ entry.skill?.name || '未知技能' }}</span>
        </article>
      </div>
      <p v-else class="sheet-muted">未提供</p>
    </section>

    <section class="sheet-card wuwa-detail-chains" data-render-block>
      <h3 class="sheet-title">共鸣链<span v-if="chains.length" class="sheet-meta">已解锁 {{ unlocked }} / {{ chains.length }}</span></h3>
      <div v-if="chains.length" class="sheet-row sheet-chains" :style="{ '--row-count': chainCount }">
        <div v-for="(chain, i) in chains" :key="i" class="sheet-chain wuwa-chain" :class="{ 'is-locked': chain.unlocked !== true }" :aria-label="`${chain.name || '共鸣链'}：${chain.unlocked === true ? '已解锁' : chain.unlocked === false ? '未解锁' : '解锁状态未知'}`">
          <span class="chain-icon"><WuwaIcon :src="chain.icon_url" :name="chain.name || '共鸣链'" size="large" /><i>{{ value(chain.order) }}</i></span>
          <span class="chain-name">{{ chain.name }}</span>
        </div>
      </div>
      <p v-else class="sheet-muted">未提供</p>
    </section>

    <section class="sheet-card wuwa-detail-echoes">
      <h3 class="sheet-title">装备声骸<span class="sheet-meta">总 COST {{ value(data.phantom_data?.cost) }}</span></h3>
      <div v-if="echoes.length && (score || totals.length)" class="echo-overview" data-render-block :class="{ 'no-score': !score, 'no-totals': !totals.length }">
        <RoleScoreHero :score="score" label="声骸评分" />
        <dl v-if="totals.length" class="echo-totals">
          <div v-for="(p, i) in totals" :key="i"><dt><WuwaIcon :src="p.icon_url" :name="p.attribute_name" size="small" />{{ p.attribute_name }}</dt><dd>{{ value(p.attribute_value) }}</dd></div>
        </dl>
      </div>
      <div v-if="echoes.length" class="sheet-echoes">
        <article v-for="(echo, i) in echoes" :key="i" class="sheet-echo" data-render-block>
          <header class="wuwa-echo-head">
            <WuwaIcon :src="echo.phantom_prop?.icon_url" :name="echo.phantom_prop?.name || '声骸'" />
            <div class="echo-title"><strong>{{ echo.phantom_prop?.name || '未知声骸' }}</strong><span>Lv.{{ value(echo.level) }} · COST {{ value(echo.cost ?? echo.phantom_prop?.cost) }}</span></div>
            <p v-if="badges.get(echo)" class="wuwa-echo-score" :data-tier="gradeTier(badges.get(echo).grade) ?? undefined" :aria-label="`单件评分 ${badges.get(echo).value} / 50${badges.get(echo).grade ? ' 等级 ' + badges.get(echo).grade : ''}`"><b>{{ badges.get(echo).value }}</b><span v-if="badges.get(echo).grade">{{ badges.get(echo).grade }}</span></p>
          </header>
          <dl class="echo-stats is-main"><div v-for="[p, j] in rows(echo.main_props)" :key="j" :class="tone(echo, 'main_props', j)"><dt>{{ p.attribute_name }}</dt><dd>{{ value(p.attribute_value) }}</dd></div></dl>
          <dl class="echo-stats is-sub"><div v-for="[p, j] in rows(echo.sub_props)" :key="j" :class="tone(echo, 'sub_props', j)"><dt>{{ p.attribute_name }}</dt><dd>{{ value(p.attribute_value) }}</dd></div></dl>
          <p class="echo-set"><WuwaIcon :src="echo.fetter_detail?.icon_url" :name="echo.fetter_detail?.name || '套装'" size="small" />{{ echo.fetter_detail?.name || '套装未知' }}</p>
        </article>
      </div>
      <p v-else class="sheet-muted">暂无装备声骸数据</p>
    </section>
  </div>
</template>
<style scoped>
.lab-sheet #render-content .wuwa-role-sheet{display:grid;gap:18px;color:var(--skin-ink,var(--text))}
.lab-sheet #render-content .wuwa-role-sheet p,.lab-sheet #render-content .wuwa-role-sheet dl,.lab-sheet #render-content .wuwa-role-sheet dd,.lab-sheet #render-content .wuwa-role-sheet figure{margin:0}
.lab-sheet #render-content .sheet-card{min-width:0;padding:20px 22px;border-radius:var(--skin-radius-card,20px);background:var(--skin-surface,var(--card-bg));box-shadow:inset 0 0 0 1px var(--skin-line,var(--border))}
.lab-sheet #render-content .sheet-title{display:flex;align-items:baseline;gap:12px;margin:0 0 14px}
.lab-sheet #render-content .sheet-meta{color:var(--skin-muted);font-size:var(--qq-min-text,17px)!important;font-weight:500}
.lab-sheet #render-content .sheet-muted{color:var(--skin-muted)}

/* Hero: the cut-out art fills the right of a wide card; name, facts and weapon sit on the left. */
.lab-sheet #render-content .sheet-hero{position:relative;display:grid;grid-template-columns:minmax(0,1fr) 46%;min-height:420px;padding:28px 30px;border-radius:var(--skin-radius-card,20px);overflow:hidden;background:var(--skin-surface);box-shadow:inset 0 0 0 1px var(--skin-line-strong,var(--border))}
.lab-sheet #render-content .sheet-hero .wuwa-portrait{display:contents}
.lab-sheet #render-content .sheet-hero .wuwa-portrait img{position:absolute;right:-40px;bottom:0;height:100%;width:auto;max-width:72%;object-fit:contain;object-position:right bottom}
.lab-sheet #render-content .sheet-hero:not(.is-cutout) .wuwa-portrait img{right:30px;top:30px;bottom:auto;height:auto;width:300px;border-radius:var(--skin-radius-tile,14px);box-shadow:inset 0 0 0 2px var(--skin-line-strong)}
.lab-sheet #render-content .wuwa-portrait-fallback{position:absolute;right:60px;top:60px;display:grid;place-items:center;width:240px;height:240px;border-radius:50%;background:rgba(var(--skin-tint-rgb),.1);color:rgba(var(--skin-tint-rgb),.5);font-size:96px!important;font-weight:700}
.lab-sheet #render-content .sheet-hero figcaption{position:relative;z-index:1;grid-column:1;display:flex;align-items:baseline;gap:16px;flex-wrap:wrap}
.lab-sheet #render-content .sheet-hero figcaption strong{font-size:48px!important;font-weight:800;line-height:1.15!important;letter-spacing:.02em!important}
.lab-sheet #render-content .sheet-hero figcaption b{color:var(--skin-accent);font-size:28px!important;font-weight:700}
.lab-sheet #render-content .rs-copy{position:relative;z-index:1;grid-column:1;display:grid;align-content:start;gap:16px;margin-top:10px}
.lab-sheet #render-content .hero-stars,.lab-sheet #render-content .weapon-stars{color:#f2c14e;letter-spacing:.12em!important}
.lab-sheet #render-content .hero-stars{font-size:22px!important}
.lab-sheet #render-content .hero-facts{display:flex;flex-wrap:wrap;gap:8px}
.lab-sheet #render-content .hero-facts>div{display:flex;gap:8px;padding:4px 12px;border-radius:999px;background:rgba(10,12,18,.62);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .hero-facts dt{color:var(--skin-muted)}
.lab-sheet #render-content .hero-facts dd{font-weight:600}
.lab-sheet #render-content .sheet-weapon{display:flex;align-items:center;gap:14px;max-width:440px;margin-top:6px;padding:14px 16px;border-radius:var(--skin-radius-tile,14px);background:rgba(10,12,18,.7);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .weapon-body{display:grid;gap:4px;min-width:0}
.lab-sheet #render-content .weapon-name{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.lab-sheet #render-content .weapon-name strong{color:var(--skin-accent);font-size:24px!important}
.lab-sheet #render-content .weapon-meta,.lab-sheet #render-content .weapon-props{display:flex;flex-wrap:wrap;gap:4px 14px;color:var(--skin-muted)}
.lab-sheet #render-content .weapon-props b{color:var(--skin-ink);font-variant-numeric:tabular-nums}

/* Attributes: two columns of icon, name and value. */
.lab-sheet #render-content .sheet-attrs{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 28px}
.lab-sheet #render-content .sheet-attrs>div{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:7px 2px;border-bottom:1px solid var(--line)}
.lab-sheet #render-content .sheet-attrs dt,.lab-sheet #render-content .echo-totals dt{display:flex;align-items:center;gap:8px;color:var(--skin-muted)}
.lab-sheet #render-content .sheet-attrs dd,.lab-sheet #render-content .echo-totals dd{color:var(--skin-hot,var(--skin-ink));font-weight:600;font-variant-numeric:tabular-nums}

/* Skills and chains: one row each, a centred column per entry. */
.lab-sheet #render-content .sheet-row{display:grid;grid-template-columns:repeat(var(--row-count,6),minmax(0,1fr));gap:10px}
.lab-sheet #render-content .sheet-skill,.lab-sheet #render-content .sheet-chain{display:grid;justify-items:center;align-content:start;gap:4px;min-width:0;padding:12px 6px;border-radius:var(--skin-radius-tile,14px);background:rgba(var(--skin-tint-rgb),.06);text-align:center}
.lab-sheet #render-content .skill-type{color:var(--skin-ink);font-weight:600}
.lab-sheet #render-content .rs-skill-level{color:var(--skin-accent);font-size:22px!important}
.lab-sheet #render-content .rs-skill-name,.lab-sheet #render-content .chain-name{color:var(--skin-muted);font-size:var(--qq-min-text,17px)!important;line-height:1.3!important;overflow-wrap:anywhere}
.lab-sheet #render-content .chain-icon{position:relative}
.lab-sheet #render-content .chain-icon i{position:absolute;right:-6px;bottom:-4px;display:grid;place-items:center;width:28px;height:28px;border-radius:50%;background:var(--skin-accent);color:#111;font-size:var(--qq-min-text,17px)!important;font-style:normal;font-weight:700}
.lab-sheet #render-content .sheet-chain.is-locked .chain-icon{opacity:.35;filter:grayscale(1)}
.lab-sheet #render-content .sheet-chain.is-locked .chain-icon i{background:rgba(var(--skin-tint-rgb),.35)}
.lab-sheet #render-content .sheet-chain:not(.is-locked) .chain-name{color:var(--skin-ink)}

/* Echoes: the score card beside the totals, then three echoes a row. */
.lab-sheet #render-content .echo-overview{display:grid;grid-template-columns:380px minmax(0,1fr);gap:18px;align-items:stretch;margin-bottom:16px}
.lab-sheet #render-content .echo-overview.no-totals,.lab-sheet #render-content .echo-overview.no-score{grid-template-columns:1fr}
.lab-sheet #render-content .echo-totals{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 22px;align-content:center}
.lab-sheet #render-content .echo-totals>div{display:flex;justify-content:space-between;align-items:center;gap:6px;padding:6px 0;border-bottom:1px solid var(--line);min-width:0}
.lab-sheet #render-content .echo-totals dt{min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.lab-sheet #render-content .sheet-echoes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.lab-sheet #render-content .sheet-echo{display:grid;align-content:start;gap:8px;min-width:0;padding:14px;border-radius:var(--skin-radius-tile,14px);background:rgba(var(--skin-tint-rgb),.06);box-shadow:inset 0 0 0 1px var(--skin-line)}
.lab-sheet #render-content .wuwa-echo-head{display:flex;align-items:flex-start;gap:10px}
.lab-sheet #render-content .echo-title{display:grid;flex:1;min-width:0}
.lab-sheet #render-content .echo-title strong{font-size:var(--qq-body,20px)!important;line-height:1.3!important;overflow-wrap:anywhere}
.lab-sheet #render-content .echo-title span{color:var(--skin-muted);white-space:nowrap}
.lab-sheet #render-content .wuwa-echo-score{display:grid;justify-items:center;flex:none;min-width:64px;padding:4px 8px;border-radius:10px;background:color-mix(in srgb,var(--tier,#9aa3ad) 20%,transparent);box-shadow:inset 0 0 0 1px var(--tier,#9aa3ad);font-variant-numeric:tabular-nums}
.lab-sheet #render-content .wuwa-echo-score b{color:var(--tier,#9aa3ad);font-size:22px!important;line-height:1.2!important}
.lab-sheet #render-content .wuwa-echo-score span{color:var(--tier,#9aa3ad);font-weight:800}
.lab-sheet #render-content .echo-stats{display:grid}
.lab-sheet #render-content .echo-stats>div{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)}
.lab-sheet #render-content .echo-stats.is-main>div:last-child{border-bottom:2px solid var(--skin-line-strong,var(--line))}
.lab-sheet #render-content .echo-stats dd{font-variant-numeric:tabular-nums}
/* Effective stats take the game accent and weight; the others recede. Unknown keeps the plain ink. */
.lab-sheet #render-content .echo-stats>.stat-effective :is(dt,dd){color:var(--skin-accent);font-weight:700}
.lab-sheet #render-content .echo-stats>.stat-ineffective :is(dt,dd){color:var(--skin-muted);opacity:.75}
.lab-sheet #render-content .echo-set{display:flex;align-items:center;gap:8px;color:var(--skin-muted)}
</style>
