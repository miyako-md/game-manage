import {fieldLabels} from '../wuwa-display.js'
import {collectVersionCalendars,collectCalendarEvents,formatBeijingDateTime} from '../calendar.js'
import nteIcons from '../nte-icon-catalog.js'
import wuwaIcons from '../wuwa-icon-catalog.js'
import endfieldIcons from '../endfield-icon-catalog.js'
import {nteNamedIcon,nteRoleIcon} from '../nte-icons.js'
const list=v=>Array.isArray(v)?v.filter(Boolean):[]
const display=v=>v===undefined||v===null||v===''?'未提供':typeof v==='boolean'?(v?'是':'否'):typeof v==='number'?v.toLocaleString('zh-CN',{maximumFractionDigits:3}):String(v)
const pct=(v,m)=>typeof v==='number'&&typeof m==='number'&&m>0?Math.max(0,Math.min(100,v/m*100)):null
const kv=(label,value)=>({label,value:display(value)})
const metric=(label,cur,max,extra='')=>({label,cur:display(cur),max:max==null?null:display(max),pct:pct(cur,max),extra})
const bar=(label,cur,max,extra='')=>({label,cur:display(cur),max:max==null?null:display(max),pct:pct(cur,max),extra})
const names={wuthering_waves:'鸣潮',nte:'异环',endfield:'终末地',all:'游戏管家'}
const caps={account:'账号档案',stamina:'体力',roles:'角色',exploration:'探索进度',progress:'成长进度',combat:'挑战',calabash:'数据坞',activities:'活动进度',resources:'资源报告',news:'公告',realestate:'房产',vehicles:'车辆',teams:'队伍',record:'档案',gacha:'抽卡',training:'全员练度',regions:'地区建设',ship:'帝江号',honor:'光荣之路'}
let roleMaps={wuthering_waves:{},nte:{}},allAssets={},endfieldPortraits={},endfieldOperators=[]
export function configure(cases,assets){
 roleMaps={wuthering_waves:{},nte:{}};endfieldPortraits={};endfieldOperators=[]
 allAssets=assets
 for(const [name,e] of Object.entries(wuwaIcons.roles))if(e.characterId)roleMaps.wuthering_waves[String(e.characterId)]={name,icon:e.icon}
 for(const [name,e] of Object.entries(nteIcons.roles))roleMaps.nte[String(e.id)]={name,icon:e.icon}
 for(const c of cases){
  const d=c.snapshot.display_data
  for(const p of d.panels||[])if(p.game==='endfield'){
   const operators=list(p.snapshot.payload?.report?.training?.items)
   if(operators.length)endfieldOperators=operators
   for(const r of operators)if(r.name&&r.avatar_url)endfieldPortraits[r.name]=r.avatar_url
  }
  for(const p of d.panels||[])if(p.capability==='roles')for(const r of list(Array.isArray(p.snapshot.payload)?p.snapshot.payload:p.snapshot.payload?.entries)){roleMaps[p.game]??={};roleMaps[p.game][String(r.role_id||r.id)]={...r,name:r.name||r.role_name,icon:r.icon_url||r.role_icon_url}}
  if(c.snapshot.kind==='nte_role')for(const r of list(d.snapshot.payload.entries))roleMaps.nte[String(r.id)]={...r,icon:r.icon_url}
 }
}
function asset(url){return url&&allAssets[url]?.file?'/'+allAssets[url].file:url&&allAssets[url]===true?url:''}
export function knownRoles(game){return Object.entries(roleMaps[game]||{}).map(([id,r])=>({id,name:r.name,icon_url:r.icon}))}
export function roleIdentity(game,r){
 const saved=roleMaps[game]?.[String(r.role_id??r.id)]
 const original=r.role_name||r.name
 const valid=original&&!/^\d+$|^(?:角色|共鸣者)[\s#]*\d+$|fork_|CHARACTER_/.test(original)
 let name=valid?original:saved?.name||'名称未提供'
 if(name==='漂泊者'&&saved?.attribute)name+=`（${saved.attribute}）`
 return {name,icon:r.icon_url||r.role_icon_url||saved?.icon,level:r.role_level||r.level}
}
function portraits(game,rows){return list(rows).map(r=>{const id=roleIdentity(game,r);return {...id,name:r.name||id.name,image:asset(id.icon),meta:[r.attribute||r.element,r.star_level?`${r.star_level} 星`:r.quality,r.level!=null?`Lv.${r.level}`:null,r.chain!=null?`共鸣链 ${r.chain}`:r.awaken_level!=null?`觉醒 ${r.awaken_level}`:null].filter(Boolean).join('　') }})}
function team(game,roles){return list(roles).map(r=>roleIdentity(game,r).name).join(' / ')||'队伍未提供'}
function guideIndex(guides){return guides.map(g=>{
 const existing=g.image?.startsWith('/asset-cache/')?g.image:asset(g.image)
 const variants=g.game==='nte'&&g.name==='主角·零'?[nteRoleIcon('1046'),nteRoleIcon('1051')]:[]
 const fallback=g.game==='nte'?nteRoleIcon(g.name):Object.values(wuwaIcons.characters).find(r=>r.name===g.name||r.name===g.name+'·'+g.attribute)?.icon
 const images=variants.length?variants.map(asset).filter(Boolean):[existing||asset(fallback)].filter(Boolean)
 return {...g,images,avatarLabels:variants.length?['男','女']:[]}
})}
function fields(obj,keys){return keys.map(k=>kv(fieldLabels[k]||({nickname:'昵称',server_name:'区服',character_count:'角色数',tycoon_level:'大亨等级',owned_count:'已拥有',affinity_exp:'好感经验',awaken_level:'觉醒',mix_level:'混频',activation_count:'激活数量'}[k])||k,obj?.[k]))}
function rowsProps(rows){return list(rows).map(r=>kv(r.attribute_name||r.name,r.attribute_value??r.value))}
function note(title,text){return {title,type:'text',text}}
function bars(title,rows,caption){
 if(rows.every(r=>r.max==null)){const largest=Math.max(...rows.map(r=>Number(r.cur.replaceAll(',',''))||0));if(largest>0)rows=rows.map(r=>({...r,pct:Number.isFinite(Number(r.cur.replaceAll(',','')))?Number(r.cur.replaceAll(',',''))/largest*100:null}))}
 return {title,type:'bars',bars:rows,caption}
}
function metricPanel(title,metrics,fields=[],caption){return {title,type:'metrics',metrics,fields,caption}}
function table(title,headers,rows,caption){return {title,type:'table',headers,rows,caption}}
function attrib(title,rows,caption){return {title,type:'attributes',fields:rows,caption}}
function equipment(title,entries,caption){return {title,type:'equipment',entries,caption}}
function stateNotes(s){return [s?.state==='auth_expired'?'登录已过期，请在看板重新登录。':null,s?.stale?'当前为缓存快照，来源可能过期。':null].filter(Boolean)}

function timelineGroups(c){
 const s=c.snapshot,d=s.display_data,now=Date.parse(s.as_of)
 const groups=s.kind==='calendar'?collectVersionCalendars(d.games,d.snapshots,'',now):(d.panels||[]).filter(p=>['events','recent_events'].includes(p.capability)).map(p=>({gameId:p.game,gameName:names[p.game],version:{id:list(p.snapshot.payload)[0]?.version},events:collectCalendarEvents([{game_id:p.game,display_name:names[p.game]}],{[p.game]:{events:p.snapshot}})}))
 return groups.map(g=>({title:`${g.gameName}　${g.version?.id?g.version.id+' 版本':'活动日历'}`,type:'cloud_calendar',events:g.events,snapshots:d.snapshots||{},asOf:now,caption:'北京时间。展示前天起的 14 天；左右箭头表示活动持续到当前日期范围外。“预计”标记保留来源的时间精度。'}))
}

function combat(p){
 const v=p||{},out=[]
 for(const z of list(v.tower?.data?.difficulty_list)){
  const areas=list(z.tower_area_list)
  out.push(bars('逆境深塔 · '+z.difficulty_name,areas.map(a=>bar(a.area_name,a.star,a.max_star))))
  const rows=areas.flatMap(a=>list(a.floor_list).map(f=>[a.area_name,`${f.floor} 层`,`${display(f.star)} 星`,team('wuthering_waves',f.role_list)]))
  if(rows.length)out.push(table(z.difficulty_name+' · 楼层记录',['区域','楼层','星数','共鸣者'],rows))
 }
 const bosses=Object.values(v.hologram?.data?.challenge_info||{}).flatMap(records=>{
  const attempted=list(records).filter(r=>Number(r.pass_time)>0||list(r.roles).length||r.attempted===true)
  if(!attempted.length)return []
  const best=attempted.reduce((a,b)=>Number(b.difficulty)>Number(a.difficulty)?b:a)
  return [[best.boss_name,`难度 ${best.difficulty}`,Number(best.pass_time)>0?`通关 ${best.pass_time} 秒`:'结果未提供',team('wuthering_waves',best.roles)]]
 })
 out.push(table('战术全息 · 最高挑战记录',['首领','难度','结果','共鸣者'],bosses,'每位首领只保留实际挑战过的最高难度。0 秒且无队伍的空记录不作为挑战证据。'))
 for(const z of list(v.slash?.data?.difficulty_list)){
  out.push(metricPanel('冥歌海墟 · '+z.difficulty_name,[metric('总得分',z.all_score,z.max_score)]))
  if(!z.difficulty_name?.startsWith('再生海域'))continue
  const rows=list(z.challenge_list).map(ch=>({name:ch.challenge_name,score:display(ch.score),rank:ch.rank,halves:list(ch.half_list).map((h,i)=>({name:h.half_name||`${i===0?'上':'下'}半场`,score:display(h.score),team:team('wuthering_waves',h.role_list),pct:typeof h.score==='number'&&ch.score>0?h.score/ch.score*100:null}))}))
  out.push({title:z.difficulty_name+' · 关卡记录',type:'sea',challenges:rows})
 }
 return out
}

function activities(p){
 const out=[]
 for(const s of Object.values(p?.sections||{}).sort((a,b)=>(a.sort||0)-(b.sort||0))){
  const pairs=[]
  for(const [k,v] of Object.entries(s)){
   if(['badge_list','badge_num','max_badge_num','items','sort','title'].includes(k)||k.startsWith('max_'))continue
   if(v&&typeof v==='object'&&!Array.isArray(v)&&typeof v.count==='number'&&typeof v.total==='number'&&v.total>0)pairs.push(metric(fieldLabels[k]||k,v.count,v.total))
   else if(typeof v==='number'){
    let max=s['max_'+k]??(k==='card_num'?s.card_total_num:k==='exp'?s.next_exp:undefined)
    if(typeof max==='number'&&max>0)pairs.push(metric(k==='item_num'?'纪念品进度':fieldLabels[k]||k,v,max))
   }
  }
  const extra=['level','level_name','rank'].filter(k=>s[k]!=null).map(k=>kv(fieldLabels[k],s[k]))
  if(!pairs.length&&!extra.length)continue
  out.push(metricPanel(s.title,pairs,extra))
 }
 return out.length?out:[note('活动进度','当前没有可展示的活动数据。')]
}

function wuwaRole(data){
 const d=data.detail,r=d.role||{},out=[]
 const hero={name:r.role_name,image:asset(d.role_skin?.skin_icon||r.role_icon_url),meta:[r.attribute_name,r.weapon_type_name,`${r.star_level} 星`,`Lv.${r.level}`,d.role_skin?.skin_name].filter(Boolean)}
 out.push(attrib('角色属性',rowsProps(d.role_attribute_list||r.role_attribute_list)))
 const w=d.weapon_data||{},weapon=w.weapon||{}
 out.push(equipment('装备武器',[{name:weapon.weapon_name,image:asset(weapon.weapon_icon),meta:[`Lv.${display(w.level)}`,`${display(weapon.weapon_star_level)} 星`,`谐振 ${display(w.reson_level)}`,`突破 ${display(w.breach)}`],fields:rowsProps(w.main_prop_list),text:[weapon.weapon_effect_name,weapon.effect_description].filter(Boolean).join('：')}]))
 out.push(table('技能',['技能名称','类型','等级'],list(d.skill_list).map(e=>[e.skill?.name||'名称未提供',e.skill?.type||'类型未提供',`Lv.${display(e.level)}`])))
 out.push(table('共鸣链',['名称','解锁状态'],list(d.chain_list).map(ch=>[ch.name,ch.unlocked===true?'已解锁':ch.unlocked===false?'未解锁':'状态未提供'])))
 out.push(equipment('装备声骸',list(d.phantom_data?.equip_phantom_list).map(e=>({name:e.phantom_prop?.name,image:asset(e.phantom_prop?.icon_url),meta:[`Lv.${display(e.level)}`,`COST ${display(e.cost)}`,`品质 ${display(e.quality)}`,e.fetter_detail?.name].filter(Boolean),fields:rowsProps(e.main_props),subfields:rowsProps(e.sub_props)})),`总 COST ${display(d.phantom_data?.cost)}；主词条、副词条分区显示。`))
 const sets=[...new Map(list(d.phantom_data?.equip_phantom_list).filter(e=>e.fetter_detail?.name).map(e=>[e.fetter_detail.name,e.fetter_detail])).values()]
 out.push({title:'套装效果',type:'textlines',lines:sets.map(s=>({name:s.name,text:[s.first_description,s.second_description,s.triple_description].filter(Boolean).join('\n')}))})
 return {hero,panels:out}
}

function nteRole(data){
 const r=list(data.snapshot.payload.entries)[0],out=[]
 const hero={name:r.name,image:asset(r.icon_url||nteRoleIcon(r.id)),meta:[r.element,r.quality,`Lv.${r.level}`,`觉醒 ${display(r.awaken_level)}`,`混频 ${display(r.mix_level)}`]}
 out.push(attrib('角色属性',rowsProps(r.properties)))
 const w=r.weapon||{}
 out.push(equipment('装备弧盘',[{name:w.name,image:asset(nteNamedIcon('weapons',w.name)),meta:[w.quality,`Lv.${display(w.level)}`,`混频 ${display(w.mix_level)}`,`突破 ${display(w.breakthrough_level)}`].filter(Boolean),fields:rowsProps(w.properties)}]))
 out.push(table('战技',['名称','等级'],list(r.skills).map(e=>[e.name,`Lv.${display(e.level)}`])))
 out.push(table('城区技能',['名称','等级'],list(r.city_skills).map(e=>[e.name,`Lv.${display(e.level)}`])))
 if(r.suit){
  out.push(note('装备卡带',r.suit.name+'　激活 '+display(r.suit.activation_count)+' 件\n'+[r.suit.description_two,r.suit.description_four].filter(Boolean).join('\n')))
  out.push(equipment('驱动块',list(r.suit.core).map(e=>({name:e.name+' · 核心',meta:[`Lv.${display(e.level)}`],fields:rowsProps(e.main_properties),subfields:rowsProps(e.properties)})).concat(list(r.suit.pie).map((e,i)=>({name:e.name+` · ${i+1}`,meta:[`Lv.${display(e.level)}`],fields:rowsProps(e.main_properties),subfields:rowsProps(e.properties)}))),'品质、面积未由来源提供时不推算。'))
 }
 return {hero,panels:out}
}

function nteGacha(d){
 return [{title:'异环 · 抽卡统计',type:'cloud_gacha',snapshot:d.snapshot,roles:d.roles?.length?d.roles:knownRoles('nte'),caption:'横条、评价色彩与四列结构沿用云端看板。比例表示本次出 S 抽数，时间在右栏；未导入完整逐抽账本。'}]
}

function endfield(cap,p){
 const out=[],report=p?.report,profile=p||{}
 if(cap==='gacha')return [{title:'终末地 · 寻访战报',type:'cloud_endfield_gacha',snapshot:{payload:p}}]
 if(cap==='combat')return list(p.reports).map(r=>({title:r.title||'终末地挑战',type:'cloud_endfield_challenge',report:r}))
 if(cap==='operator_detail'){
  const r=p.operator_detail||{}
  out.push(equipment('干员档案',[{name:r.name,image:asset(r.avatar_url),meta:[`Lv.${display(r.level)}`,`${display(r.rarity)} 星`,r.profession,r.property,`潜能 ${display(r.potential)}`].filter(Boolean),fields:[]}]))
  const w=r.weapon||{}
  out.push(equipment('装备武器',[{name:w.name||'未提供',image:asset(w.icon_url),meta:[`Lv.${display(w.level)}`,`精炼 ${display(w.refine_level)}`,`突破 ${display(w.breakthrough_level)}`],fields:[],text:w.gem?.name}]))
  out.push(equipment('装备护具',list(r.equipment).map(e=>({name:e.name,image:asset(e.icon_url),meta:[e.slot_label||e.slot_name,`Lv.${display(e.level)}`,e.rarity].filter(Boolean),fields:[]}))))
  out.push(table('技能',['名称','等级'],list(r.skills).map(s=>[s.name,`Lv.${display(s.level)}`])))
  if(r.tactical_item)out.push(equipment('战术道具',[{name:r.tactical_item.name,image:asset(r.tactical_item.icon_url),meta:[r.tactical_item.rarity],fields:[]}]))
  return out
 }
 if(report?.training){
  if(['roles','training'].includes(cap)){
   const summary=report.training.summary||{}
   out.push(metricPanel('练度总览',[metric('已记录干员',summary.listed_count),metric('平均等级',summary.average_level),metric('最高等级',summary.max_level)]))
   out.push({title:'干员档案',type:'portraits',roles:list(report.training.items).map(r=>({name:r.name,image:asset(r.avatar_url),meta:`Lv.${display(r.level)}　${display(r.rarity)} 星　潜能 ${display(r.potential)}　${r.profession||''}`}))})
  }else if(['account','progress','stamina'].includes(cap)){
   const v=report.overview||{},b=v.base||{},s=v.stamina||{}
   if(cap!=='stamina')out.push(metricPanel('管理员档案',[metric('账号等级',b.level),metric('探索等级',b.world_level),metric('干员数',b.char_count)],[kv('名称',b.name)],b.main_mission||undefined))
   out.push(metricPanel('理智',[metric('理智',s.current,s.maximum)],s.expected_full_at?[kv('预计回满',formatBeijingDateTime(s.expected_full_at))]:[]))
   if(cap!=='stamina')out.push(bars('每日与通行证',list(v.progress).map(r=>bar(r.name||r.label,r.current??r.cur,r.total,r.note))))
  }else if(['exploration','regions'].includes(cap))for(const r of list(report.regions.items)){
   out.push(metricPanel(r.name,[metric('地区等级',r.level),metric('地区调度券',r.money?.current,r.money?.total)]))
   out.push(bars('据点建设',list(r.settlements).map(x=>bar(x.name,x.coupon?.current,x.coupon?.total,`Lv.${display(x.level)}　派驻：${list(x.officers).map(o=>o.name).join(' / ')||'未提供'}`))))
   for(const a of list(r.areas))out.push(bars(r.name+' · '+a.name,list(a.collections).map(x=>bar(x.label,x.current,x.total))))
  }else if(cap==='ship'){
   const summary=report.ship.summary||{}
   out.push(metricPanel('帝江号总览',[metric('房间',summary.room_count),metric('已派驻房间',summary.staffed_rooms),metric('干员槽位',summary.operator_slots)],[],'心情与信赖使用项目现有换算模型；信赖上限为 200%。未知观测值不计为零。'))
   for(const r of list(report.ship.rooms)){out.push(table(r.name+' · Lv.'+display(r.level),['干员','心情','信赖'],list(r.operators).map(x=>[x.name||'名称未提供',x.mood_percent==null?'未提供':x.mood_percent.toFixed(1)+'%',x.trust_percent==null?'未提供':x.trust_percent.toFixed(1)+'%'])))}
  }else if(['honor','record'].includes(cap)){
   out.push(metricPanel('光荣之路总览',[metric('已记录奖章',report.honor.summary.listed_count,report.honor.summary.declared_count)]))
   out.push(table('光荣之路',['奖章','分类','等级 / 镀层','获得日期'],list(report.honor.items).map(m=>[m.name,m.category||'未提供',`${display(m.level)} · ${m.is_plated?'已镀层':'未镀层'}`,m.obtained_at?formatBeijingDateTime(m.obtained_at).slice(0,10):'未提供'])))
  }
  return out.length?out:[note(caps[cap]||'终末地数据','当前来源没有此项记录。')]
 }
 if(['roles','training'].includes(cap))out.push({title:'干员档案',type:'portraits',roles:list(profile.operators).map(r=>({name:r.name,image:asset(r.avatar_url||r.icon_url||endfieldPortraits[r.name]),meta:`Lv.${display(r.level)}　${display(r.rarity)} 星　潜能 ${display(r.potential)}　${r.profession||''}`}))})
 else if(['account','progress','stamina'].includes(cap)){
  if(profile.base)out.push(attrib('管理员档案',[kv('名称',profile.base.name),kv('等级',profile.base.level),kv('主线',profile.base.main_mission)]))
  const s=profile.stamina||profile
  if('current' in s)out.push(metricPanel('理智',[metric('理智',s.current,s.maximum)]))
  if(profile.progress)out.push(bars('成长进度',list(profile.progress).map(r=>bar(r.name,r.cur,r.total))))
 }else if(['exploration','regions'].includes(cap))for(const r of list(profile.regions)){
  out.push(attrib(r.name,list(r.settlements).map(x=>kv(x.name,`Lv.${display(x.level)}`))))
  for(const x of list(r.settlements))if(x.money!=null)out.push(metricPanel(x.name+' · 建设资金',[metric('资金',x.money,x.money_max)]))
  for(const [i,x] of list(r.collections).entries())out.push(bars(x.name||`探索区域 ${i+1}`,[bar('解谜',x.puzzle_count,null),bar('宝箱',x.chest_count,null),bar('物资箱',x.piece_count,null),bar('黑匣子',x.blackbox_count,null)]))
 }
 else if(cap==='ship')for(const r of list(profile.ship)){
  const map=new Map(list(profile.operators).map(x=>[x.id,x.name]))
  out.push(attrib(r.name,[kv('等级',r.level)]));out.push(table('进驻干员',['干员','体力','好感'],list(r.operators).map(x=>[x.name||map.get(x.charId)||'名称未提供',display(x.physicalStrength),display(x.favorability)])))
 }
 else if(['honor','record'].includes(cap)){out.push(metricPanel('勋章总览',[metric('勋章数量',profile.achievements?.count)]));out.push({title:'光荣之路',type:'textlines',lines:list(profile.achievements?.medals).map(m=>({name:m.name,text:[m.category,`等级 ${display(m.level)}`,m.is_plated?'已镀层':'未镀层',m.description,m.obtained_at?formatBeijingDateTime(m.obtained_at):null].filter(Boolean).join('\n')}))})}
 return out.length?out:[note(caps[cap]||'终末地数据','当前来源没有可展示的数据，请在云端看板读取后查看。')]
}

function gamePanel(panel){
 const {game,capability:cap}=panel,s=panel.snapshot,p=s.payload,out=[],title=names[game]+' · '+(caps[cap]||cap)
 if(!p)return [note(title,cap==='teams'?'当前来源没有提供队伍数据。':'当前缓存没有可展示数据。')]
 if(cap==='news')return [{title,type:'news',articles:list(p).map(a=>({name:a.title,text:a.summary?.replace(/\[图片\]/g,'').replace(/\s+/g,' ').trim(),date:formatBeijingDateTime(a.published_at),source:a.source_name,image:(a.images||[]).map(asset).find(Boolean),stale:a.source_stale})),caption:'官方公告快照；保留标题、来源、发布时间与可用配图。'}]
 if(game==='endfield')return endfield(cap,p)
 if(game==='nte'&&cap==='teams')return [{title:'官方配队推荐',type:'cloud_teams',snapshot:s,roles:knownRoles('nte'),caption:'塔吉多官方推荐。主选、备选及推荐说明按原始来源展示。'}]
 if(cap==='roles')return [{title,type:'portraits',roles:portraits(game,Array.isArray(p)?p:p.entries)}]
 if(cap==='account'){
  out.push(metricPanel(title,[metric('账号等级',p.level),metric('活跃天数',p.extra?.profile?.active_days??p.active_days),metric('世界等级',p.extra?.profile?.world_level??p.world_level)],[kv('昵称',p.nickname),kv('区服',p.extra?.server_name||p.server_name)]))
  if(game==='nte')out.push(metricPanel('收藏进度',[metric('成就',p.achievement_count,p.achievement_total),metric('房产',p.house_count,p.house_total),metric('车辆',p.vehicle_count,p.vehicle_total)], [kv('大亨等级',p.tycoon_level),kv('角色数',p.character_count)]))
  else if(p.extra?.profile){const v=p.extra.profile;out.push(attrib('探索档案',fields(v,['achievement_count','achievement_star','big_count','small_count'])));out.push(bars('奇藏箱',list(v.treasure_box_list||v.box_list).map(r=>bar(r.name||r.box_name,r.num,null))))}
 }else if(cap==='stamina'){
  const ms=[metric(game==='wuthering_waves'?'结晶波片':'体力',p.current,p.maximum)]
  if('city_current' in p)ms.push(metric('城区体力',p.city_current,p.city_maximum))
  const f=[];if(p.expected_full_at)f.push(kv('预计回满',formatBeijingDateTime(p.expected_full_at)))
  if(p.daily_activity!=null)ms.push(metric('每日活跃',p.daily_activity,100))
  out.push(metricPanel(title,ms,f))
 }else if(cap==='progress'){
  if(Array.isArray(p))out.push(bars(title,p.map(r=>bar(r.name,r.cur,r.total,r.refresh_at?'刷新 '+formatBeijingDateTime(r.refresh_at):''))))
  else{out.push(metricPanel(title,[metric('成就',p.completed,p.total)],['bronze','silver','gold'].map(k=>kv({bronze:'铜级',silver:'银级',gold:'金级'}[k],p[k]))));out.push(bars('成就分类',list(p.categories).map(r=>bar(r.name,r.current,r.total))))}
 }else if(cap==='exploration'){
  if(game==='wuthering_waves'){
   out.push(metricPanel('声骸探测',[metric('已探测',p.detections?.total)],Object.entries(p.detections?.by_level||{}).map(([k,v])=>kv(k,v))))
   for(const r of list(p.country_groups)){out.push(bars(r.name,list(r.areas).map(a=>bar(a.name,a.progress??a.current,a.total??100))))}
  }else for(const a of list(p.areas)){out.push(metricPanel(a.name,[metric('探索进度',a.current,a.total)]));out.push(bars('探索细项',list(a.details).map(r=>bar(r.name,r.current,r.total))))}
 }else if(cap==='combat')out.push(...combat(p))
 else if(cap==='activities')out.push(...activities(p))
 else if(cap==='calabash')out.push(metricPanel(title,[metric('数据坞等级',p.level),metric('捕获品质',p.catch_quality),metric('可收集上限',p.max_count)],[kv('基础捕获率',p.base_catch),kv('当前经验',p.cur_exp)]))
 else if(cap==='resources'){
  const r=p.current?.data||{};out.push(metricPanel(title,[metric('贝币',r.total_coin),metric('星声',r.total_star)],[],`${p.current?.period||''} 资源收入；环比未提供时不计算。`))
  for(const [key,label] of [['coin_list','贝币来源'],['star_list','星声来源']]){const rows=list(r[key]);const total=rows.reduce((n,x)=>n+(x.num||0),0);out.push(bars(label,rows.map(x=>bar(x.type,x.num,total))))}
 }else if(['realestate','vehicles'].includes(cap)){
  out.push(metricPanel(title,[metric('已拥有',p.owned_count,p.total)],p.show_name?[kv('展示车辆',p.show_name)]:[]))
  const entries=[]
  for(const e of list(p.entries)){
   const imageUrl=game==='nte'&&cap==='vehicles'?`https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/verhicle/wide/${e.id}.png`:cap==='realestate'?`https://webstatic.tajiduo.com/bbs/yh-game-records-web-source/realestate/detail/${e.id}.png`:null
   const f=[kv('拥有状态',e.owned?'已拥有':'未拥有')]
   for(const r of list(e.base))f.push(kv(r.name,r.value))
   if(e.resident_ids?.length)f.push(kv('住户',team('nte',e.resident_ids.map(id=>({id})))))
   if(e.furniture?.length)f.push(kv('家具条目',e.furniture.length))
   entries.push({name:e.name,image:asset(imageUrl),meta:[e.owned?'已拥有':'未拥有'],fields:f,subfields:list(e.advanced).map(r=>kv(r.name,display(r.value)+(r.maximum!=null?' / '+display(r.maximum):'')))})
  }
  out.push(equipment(cap==='vehicles'?'车辆档案':'房产档案',entries))
 }else if(cap==='record')out.push(attrib(title,list(p.cards).flatMap(c=>[kv('昵称',c.nickname),kv('等级',c.level),kv('区服',c.server_name)])))
 else if(cap==='gacha')out.push(note(title,game==='wuthering_waves'?'尚未导入可核验的抽卡记录，请在看板导入。':'请使用独立抽卡指令查看社区统计。'))
 else out.push(note(title,'当前数据未提供。'))
 return out.map(x=>({...x,notices:stateNotes(s)}))
}

export function viewModel(c){
 const s=c.snapshot,d=s.display_data
 let result={title:s.title||c.command,game:names[s.game]||'游戏管家',command:c.command,asOf:formatBeijingDateTime(s.as_of),origin:c.origin,panels:[],hero:null}
 if(s.kind==='calendar'||d.panels?.some(p=>['events','recent_events'].includes(p.capability)))result.panels=timelineGroups(c)
 else if(s.kind==='wuwa_role')Object.assign(result,wuwaRole(d))
 else if(s.kind==='nte_role'&&d.snapshot.display_mode==='detail')Object.assign(result,nteRole(d))
 else if(s.kind==='nte_role')result.panels=[{title:'异环角色',type:'portraits',roles:portraits('nte',d.snapshot.payload.entries)}]
 else if(s.kind==='nte_gacha')result.panels=nteGacha(d)
 else if(s.kind==='wuwa_gacha')result.panels=[note('鸣潮抽卡档案',d.archive.coverage?.message||'尚未导入抽卡记录，请在云端看板导入。'),metricPanel('记录覆盖',[metric('记录数',d.archive.total)],[kv('覆盖状态',d.archive.coverage?.complete===true?'完整':'尚未确认完整')])]
 else if(s.kind==='game_snapshot')result.panels=d.panels.flatMap(gamePanel).concat((d.notices||[]).map(n=>note('说明',n)))
 else if(s.kind==='guide_index')result.panels=[{title:'角色攻略',type:'guide_index',guides:guideIndex(d.guides),caption:'使用“游戏 攻略 精确角色名”。社区推荐保留原始版本与出处；未收录角色不推测。'}]
 else if(s.kind==='guide'){
  const g=d.guide;result.hero={name:g.name+' · 攻略',image:asset(g.image|| (s.game==='nte'?nteRoleIcon(g.id||g.name):wuwaIcons.characters[String(g.id)]?.icon)),meta:[g.attribute||g.element,g.role,g.sources?.map(s=>'V'+s.version).join(' / '),g.status==='original_only'?'仅原图索引':'已整理的社区建议'].filter(Boolean)}
  result.panels=g.sections.map(sec=>({title:sec.title,type:'guide_visual',game:s.game,characterId:g.id,roleName:g.name,sectionKey:sec.key,text:sec.text||sec.items?.join('\n')||'暂无已核验文字摘要，请查看来源原图。',caption:sec.note,source:g.sources?.find(s=>String(s.id)===String(sec.sourceId))?.title||g.sources?.[0]?.title}))
  result.panels.push({title:'攻略来源',type:'textlines',lines:g.sources.map(src=>({name:src.title,text:`${src.author}　V${src.version}\n${src.url}`})),caption:'社区建议的原始版本可能早于当前版本；适用性请按装备和版本判断。'})
 }else if(s.game==='endfield'&&/攻略/.test(c.command)){
  const publicRole=Object.values(endfieldIcons.roles).find(r=>r.name==='伊冯')
  const role=endfieldOperators.find(r=>r.name==='伊冯')||endfieldOperators[0]||(publicRole?{name:publicRole.name,avatar_url:publicRole.icon}:null)
  result.panels=[{title:'攻略收录状态',type:'guide_context',role,text:'当前项目尚未收录可核验的终末地角色攻略。',caption:'角色资料与装备图标已可复用；攻略内容待收录。',command:role?'终末地 角色 '+role.name:''}]
 }else{
  result.panels=(d.sections||[]).map(sec=>({title:sec.title,type:'textlines',lines:(sec.items||[]).map(x=>({text:x}))}))
  if(!result.panels.length)result.panels=[note(d.title||s.title,(d.notices||[]).join('\n')||'暂无说明')]
  else if(d.notices?.length)result.panels.push(note('使用说明',[...new Set(d.notices)].join('\n')))
 }
 return result
}
