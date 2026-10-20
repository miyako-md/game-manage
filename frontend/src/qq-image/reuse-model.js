import {roleIdentity} from './models.js'
export function prepareReuse(c){
 const s=structuredClone(c.snapshot),d=s.display_data
 if(s.kind==='wuwa_role'){delete d.detail.equip_phantom_attribute_list;delete d.detail.equip_phantom_add_prop_list}
 for(const p of d.panels||[]){
  if(p.game==='wuthering_waves'&&p.capability==='combat'){
   const v=p.snapshot.payload
   if(v?.hologram?.data?.challenge_info)v.hologram.data.challenge_info=Object.fromEntries(Object.entries(v.hologram.data.challenge_info).flatMap(([key,records])=>{const tried=(Array.isArray(records)?records:[]).filter(r=>r&&(r.pass_time>0||r.roles?.length));return tried.length?[[key,[tried.reduce((a,b)=>b.difficulty>a.difficulty?b:a)]]]:[]}))
   for(const z of v?.slash?.data?.difficulty_list||[]){if(!z.difficulty_name?.startsWith('再生海域'))z.challenge_list=[];for(const ch of z.challenge_list||[])for(const h of ch.half_list||[]){delete h.buff_description;delete h.buff_name}}
   const walk=x=>{if(Array.isArray(x))x.forEach(walk);else if(x&&typeof x==='object'){if('role_id' in x&&('icon_url' in x||'role_name' in x))x.role_name=roleIdentity('wuthering_waves',x).name;Object.values(x).forEach(walk)}};walk(v)
  }
  if(p.game==='wuthering_waves'&&p.capability==='activities'&&p.snapshot.payload)p.snapshot.payload.sections=Object.fromEntries(Object.entries(p.snapshot.payload.sections||{}).flatMap(([key,raw])=>{const value={...raw};for(const k of ['badge_list','badge_num','max_badge_num','items'])delete value[k];return Object.keys(value).some(k=>!['title','sort'].includes(k)&&value[k]!=null)?[[key,value]]:[]}))
 }
 return s
}
