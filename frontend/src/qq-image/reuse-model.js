import {roleIdentity} from './models.js'
export function prepareReuse(c){
 const s=structuredClone(c.snapshot),d=s.display_data
 for(const p of d.panels||[]){
  if(p.game==='wuthering_waves'&&p.capability==='combat'){
   const v=p.snapshot.payload
   if(v?.hologram?.data?.challenge_info)v.hologram.data.challenge_info=Object.fromEntries(Object.entries(v.hologram.data.challenge_info).flatMap(([key,records])=>{const tried=(Array.isArray(records)?records:[]).filter(r=>r&&(r.pass_time>0||r.roles?.length));return tried.length?[[key,[tried.reduce((a,b)=>b.difficulty>a.difficulty?b:a)]]]:[]}))
   for(const z of v?.slash?.data?.difficulty_list||[])if(!z.difficulty_name?.startsWith('再生海域'))z.challenge_list=[]
   const walk=x=>{if(Array.isArray(x))x.forEach(walk);else if(x&&typeof x==='object'){if('role_id' in x&&('icon_url' in x||'role_name' in x))x.role_name=roleIdentity('wuthering_waves',x).name;Object.values(x).forEach(walk)}};walk(v)
  }
 }
 return s
}
