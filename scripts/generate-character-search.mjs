// Public catalogs are the ID authority. Transcription here is reviewed linguistic
// metadata, not a downloaded alias file or an account snapshot.
import { readFileSync, writeFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import nte from '../frontend/src/nte-icon-catalog.js'
import wuwa from '../frontend/src/wuwa-icon-catalog.js'
import guides from '../frontend/src/wuwa-guides-catalog.js'
const syllables = Object.fromEntries(`明音:ming yin;早雾:zao wu;翳:yi;娜娜莉:na na li;薄荷:bo he;哈尼娅:ha ni ya;埃德嘉:ai de jia;白藏:bai zang;哈索尔:ha suo er;阿德勒:a de le;法帝娅:fa di ya;异能者·零(男):yi neng zhe ling nan;异能者·零(女):yi neng zhe ling nv;达芙蒂尔:da fu di er;九原:jiu yuan;海月:hai yue;小吱:xiao zhi;安魂曲:an hun qu;浔:xun;卡厄斯:ka e si;伊洛伊:yi luo yi;真红:zhen hong;残虹:can hong;灵可:ling ke;黑羽:hei yu;绯雪:fei xue;莫宁:mo ning;清宵:qing xiao;穗穗:sui sui;秧秧·玄翎:yang yang xuan ling;洛瑟菈:luo se la;露西:lu xi;丽贝卡:li bei ka;达妮娅:da ni ya;爱弥斯:ai mi si;琳奈:lin nai;千咲:qian xiao;尤诺:you nuo;弗洛洛:fu luo luo;露帕:lu pa;夏空:xia kong;卡提希娅:ka ti xi ya;赞妮:zan ni;坎特蕾拉:kan te lei la;菲比:fei bi;洛可可:luo ke ke;珂莱塔:ke lai ta;椿:chun;守岸人:shou an ren;相里要:xiang li yao;折枝:zhe zhi;长离:chang li;今汐:jin xi;鉴心:jian xin;卡卡罗:ka ka luo;安可:an ke;维里奈:wei li nai;凌阳:ling yang;卜灵:bu ling;灯灯:deng deng;秧秧:yang yang;釉瑚:you hu;白芷:bai zhi;炽霞:chi xia;散华:san hua;秋水:qiu shui;丹瑾:dan jin;莫特斐:mo te fei;渊武:yuan wu;桃祈:tao qi;漂泊者·气动:piao bo zhe qi dong`.split(';').map(row => row.split(':')))
const extra = {
  nte: { '1046':['零','主角','主角·零'], '1051':['零','主角','主角·零'] },
  wuthering_waves: {'1408':['漂泊者','气动主','风主']},
}
const pronunciationOverrides = {薄荷:'bo he',白藏:'bai zang',长离:'chang li',相里要:'xiang li yao',卜灵:'bu ling',千咲:'qian xiao'}
const aliasSyllables = {'哈妮娅':'ha ni ya','法蒂娅':'fa ti ya','异能者零男':'yi neng zhe ling nan','异能者零女':'yi neng zhe ling nv','男主':'nan zhu','女主':'nv zhu'}
const characters = []
for (const [game, catalog] of [['nte',nte],['wuthering_waves',wuwa]]) {
  const byId = new Map()
  for (const [name, value] of Object.entries(catalog.roles)) {
    const id = game === 'nte' ? value.id : value.characterId
    if (!id) continue // wikiEntry IDs are not character/form IDs.
    if (byId.has(id)) {
      const row=byId.get(id), alias=aliasSyllables[name]
      if(!alias)throw Error(`Missing alias transcription: ${name}`)
      row.aliases.push(name);row.pinyin.push(alias.replaceAll(' ',''));row.initials.push(alias.split(' ').map(p=>p[0]).join(''))
      continue
    }
    if (!syllables[name]) throw Error(`Missing reviewed transcription: ${name}`)
    const parts = syllables[name].split(' ')
    const form = game === 'nte' && ['1046','1051'].includes(id) ? (id==='1046'?'男':'女') : guides.guides.find(g=>g.id===id)?.attribute || ''
    const row = {game,character_id:id,canonical_name:name,form,aliases:[...(extra[game][id] || [])],pinyin:[parts.join('')],initials:[parts.map(p=>p[0]).join('')]}
    if (id==='1046' || id==='1051') { row.pinyin.push('ling','zhujue','zhujueling'); row.initials.push('zj','zjl') }
    if (game==='wuthering_waves' && id==='1408') { row.pinyin.push('piaobozhe','qidongzhu','fengzhu'); row.initials.push('pbz','qdz','fz') }
    byId.set(id,row)
  }
  characters.push(...byId.values())
}
const sourceFiles = ['frontend/src/nte-icon-catalog.js','frontend/src/wuwa-icon-catalog.js','frontend/src/wuwa-guides-catalog.js','src/game_assistant/nte_guides_catalog.py','src/game_assistant/wuwa_guide_updates.py']
// Hash LF content: a CRLF checkout (core.autocrlf) must not change the recorded provenance.
const lf = text => text.replaceAll('\r\n','\n')
const sha = path => createHash('sha256').update(lf(readFileSync(new URL('../'+path,import.meta.url),'utf8'))).digest('hex')
// Official wiki catalogue order (newest first): the overview role order for frontend and backend,
// so role-order.js need not import the whole icon catalogue.
const wuwaOrder = Object.keys(wuwa.roles)
const data = {schema_version:1, provenance:{sources:sourceFiles.map(path=>({path,sha256:sha(path)})),alias_policy:'Existing icon aliases; NTE guide zero aliases; Wuwa guide-title confirmed wind protagonist aliases only.',pronunciation_overrides:pronunciationOverrides,unknown_ids:'Excluded; observed roles retain their own ID/name, without borrowed aliases.'},characters,wuwa_order:wuwaOrder}
const outputs = [
  [new URL('../src/game_assistant/character-search-catalog.json',import.meta.url), JSON.stringify(data,null,2)+'\n'],
  [new URL('../frontend/src/wuwa-role-order.json',import.meta.url), JSON.stringify({schema_version:1,source:'frontend/src/wuwa-icon-catalog.js',generated_by:'scripts/generate-character-search.mjs',names:wuwaOrder},null,2)+'\n'],
]
const check = process.argv.includes('--check')
for (const [target, output] of outputs) {
  if (!check) writeFileSync(target,output)
  else if (lf(readFileSync(target,'utf8'))!==output) throw Error(`${target.pathname.split('/').at(-1)} is stale; regenerate and review.`)
}
console.log(`${characters.length} public character forms, ${wuwaOrder.length} Wuwa catalogue names; ${check?'checked':'generated'}`)
