// Export only the project's existing reviewed public catalogs, never accounts.
import fs from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'
import {execFileSync} from 'node:child_process'
import wuwa from '../frontend/src/wuwa-guides-catalog.js'
import wwIcons from '../frontend/src/wuwa-icon-catalog.js'
import endfield from '../frontend/src/endfield-icon-catalog.js'
import {tokenizeGuide,characterIcon,guideAliases} from '../frontend/src/wuwa-icons.js'
import {tokenizeNteGuide,nteRoleIcon} from '../frontend/src/nte-icons.js'
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
const catalog=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c','import json;from game_assistant.nte_guides_catalog import guide_catalog;print(json.dumps(guide_catalog(),ensure_ascii=False))'],{cwd:root,encoding:'utf8',env:{...process.env,PYTHONPATH:path.join(root,'src'),PYTHONIOENCODING:'utf-8'}}))
const titles={weapons:'武器推荐',teams:'配队推荐',echo_sets:'声骸配装',echo_stats:'声骸词条',skill_priority:'技能加点优先级'}
const guides={wuthering_waves:wuwa.guides.map(g=>({...g,game:'wuthering_waves',image:characterIcon(g.id),sections:g.sections.map(s=>({...s,title:titles[s.key]}))})),nte:catalog.guides.map(g=>({...g,game:'nte',image:nteRoleIcon(g.name),sources:catalog.sources.filter(s=>String(s.id)===String(g.source_id)),sections:g.sections.map(s=>({...s,sourceId:g.source_id,text:s.items?.join('\n')||''}))}))}
for(const [game,rows] of Object.entries(guides))for(const g of rows){
 const urls=new Set([g.image].filter(Boolean))
 if(game==='nte'&&g.name==='主角·零')for(const id of ['1046','1051'])urls.add(nteRoleIcon(id))
 for(const section of g.sections){
  const text=section.text||'',tokens=game==='nte'?tokenizeNteGuide(text,section.key,g.name):tokenizeGuide(text,section.key,g.id)
  if(tokens.map(t=>t.text).join('')!==text)throw Error('source_text_changed')
  for(const token of tokens)if(token.icon)urls.add(token.icon)
 }
 g.asset_hints=[...urls].filter(Boolean)
}
const endfieldRole=Object.values(endfield.roles).find(r=>r.name==='伊冯')
const output={version:1,guides,endfield_role:endfieldRole?{name:endfieldRole.name,avatar_url:endfieldRole.icon}:null,wuwa_guide_aliases:guideAliases}
const target=path.join(root,'src/game_assistant/qq/role_guides.json'),text=JSON.stringify(output,null,2)+'\n'
// --check (CI): the committed JSON must equal a fresh export of the reviewed catalogs.
const check=process.argv.includes('--check')
if(!check)await fs.writeFile(target,text)
else if((await fs.readFile(target,'utf8')).replaceAll('\r\n','\n')!==text){console.error('role_guides.json is stale; run node scripts/export_qq_guides.mjs and review.');process.exit(1)}
console.log(JSON.stringify({public_guides:Object.fromEntries(Object.entries(guides).map(([game,rows])=>[game,rows.length])),endfield_guide_collected:false,checked:check}))
