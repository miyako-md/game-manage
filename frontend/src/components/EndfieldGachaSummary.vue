<script setup>
import { computed } from 'vue'
import { displayBeijing } from '../time.js'
import { vReveal } from '../motion.js'
import { gachaPools, kindSummary } from '../endfield-gacha-summary.js'
const props = defineProps({ view: {type:Object,required:true}, refreshing:Boolean })
const emit = defineEmits(['details','refresh'])
const summary = computed(()=>props.view.snapshot?.payload?.schema_version === 1 ? props.view.snapshot.payload : null)
const report = computed(()=>summary.value?.report?.schema_version === 1 ? summary.value.report : null)
const show = value => value == null || value === '' ? '未知' : value
const total = computed(()=>report.value?.total ?? summary.value?.total)
// Operator headhunting and weapon requisition are separate currencies, so each gets its own line.
const kinds = computed(()=>['character','weapon'].map(kind=>kindSummary(gachaPools(summary.value),kind)).filter(Boolean))
</script>
<template>
  <section v-reveal class="ef-gacha-summary" aria-label="鹰角通行证寻访摘要">
    <header><div><h2>寻访摘要</h2></div><span v-if="view.snapshot?.stale" class="badge badge-stale">已有记录待更新</span></header>
    <div class="passport-identity"><strong>鹰角通行证 · {{ view.account?.nickname || '尚未读取' }}</strong><span v-if="view.account">角色编号 {{ view.account.role_id }}</span></div>
    <template v-if="summary">
      <ul v-if="kinds.length" class="gs-kinds">
        <li v-for="kind in kinds" :key="kind.kind"><span class="k">{{ kind.label }}</span><strong>{{ show(kind.total) }}<small v-if="kind.total != null">抽</small></strong>
          <span class="gs-kind-stats"><span class="six">6★ <b>{{ show(kind.six_star) }}</b></span><span class="five">5★ <b>{{ show(kind.five_star) }}</b></span><span>平均出 6★ <b>{{ kind.pace.average ?? '—' }}</b><template v-if="kind.pace.average != null"> 抽</template></span></span></li>
      </ul>
      <div v-else class="gs-center plain"><span class="k">已记录寻访</span><strong>{{ show(total) }}</strong></div>
      <div class="coverage"><span>同步于 {{ view.snapshot.fetched_at ? displayBeijing(view.snapshot.fetched_at) : '未知' }}（北京时间）</span><span>{{ report?.pending === true ? '部分待同步' : report?.pending === false ? '本轮同步完成' : '记录完整性未知' }}</span><span v-if="summary.errors?.length" class="gs-failed">{{ summary.errors.length }} 个卡池读取失败，详见寻访详情</span></div>
    </template>
    <div v-else class="gs-empty"><span class="gs-ghost" aria-hidden="true"></span><p>{{ view.message || '尚未同步寻访记录，请刷新数据。' }}</p></div>
    <footer><button type="button" class="ui-button primary" @click="emit('details')">查看寻访详情 →</button><button type="button" class="ui-button" :disabled="refreshing" @click="emit('refresh')">{{ refreshing ? '同步中…' : '刷新寻访数据' }}</button></footer>
  </section>
</template>
<style scoped>
/* The one tinted card of the overview (like the main overview's pulls card): the game tone at half strength. */
.ef-gacha-summary{--es-six:var(--chart-2,#d95926);--es-tone:var(--game-tone,var(--game-endfield-tone));--es-five:var(--chart-4,#c98500);min-width:0;display:flex;flex-direction:column;gap:14px;padding:20px;border:1px solid var(--card-border);border-radius:var(--radius-card);background:color-mix(in srgb,var(--es-tone) 55%,var(--card-bg));box-shadow:var(--card-shadow)}
.ef-gacha-summary header{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}
.ef-gacha-summary h2{font-size:16px;line-height:24px;font-weight:600;letter-spacing:-.02em}
.passport-identity{display:flex;gap:4px 14px;flex-wrap:wrap;align-items:baseline;overflow-wrap:anywhere;margin-top:-6px}
.passport-identity strong{font-size:14px;font-weight:500;color:var(--text)}
.passport-identity span,.coverage,p{font-size:13px;line-height:1.7;color:var(--text-muted)}
.k{color:var(--text-muted);font-size:12px;line-height:18px;font-weight:500}
.gs-kinds{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:8px;margin:0;padding:0;list-style:none}
.gs-kinds li{display:grid;gap:2px;padding:12px 14px;border-radius:var(--radius-well);background:var(--card-bg);min-width:0}
.gs-kinds strong{font-size:30px;line-height:36px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.gs-kinds strong small{margin-left:3px;color:var(--text-muted);font-size:13px;font-weight:500;letter-spacing:0}
.gs-kind-stats{display:flex;flex-wrap:wrap;gap:2px 14px;color:var(--text-muted);font-size:12px;line-height:18px;font-variant-numeric:tabular-nums}
.gs-kind-stats b{color:var(--text);font-weight:600}
.gs-kind-stats :is(.six,.five)::before{content:'';display:inline-block;width:7px;height:7px;margin-right:5px;border-radius:2px;background:var(--es-six)}
.gs-kind-stats .five::before{background:var(--es-five)}
.gs-center{display:grid;justify-items:center;gap:1px;line-height:1.1}
.gs-center strong{font-size:30px;line-height:34px;font-weight:550;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
.gs-center.plain{justify-items:start;padding:8px 0}
.gs-center.plain strong{font-size:44px;line-height:48px;letter-spacing:-.05em}
.coverage{display:flex;gap:4px 20px;flex-wrap:wrap}
.gs-failed{color:var(--stale-text)}
.gs-empty{display:flex;align-items:center;gap:18px;padding:6px 0}
.gs-ghost{flex:0 0 auto;width:72px;height:72px;border:10px solid var(--track);border-radius:50%}
.ef-gacha-summary footer{display:flex;gap:10px;flex-wrap:wrap;margin-top:auto;padding-top:2px}
@media(max-width:600px){.ef-gacha-summary{padding:16px;border-radius:22px}.passport-identity{align-items:start;flex-direction:column;gap:2px}.ef-gacha-summary footer .ui-button{flex:1}}
</style>
