import catalog from './nte-icon-catalog.js'

export function safeNteIcon(value) {
  if (typeof value !== 'string') return ''
  try {
    const url=new URL(value)
    return url.protocol==='https:' && ['webstatic.tajiduo.com','bbs-upload.tajiduo.com'].includes(url.hostname)
      && !url.username && !url.password && !url.search && !url.hash && (!url.port || url.port==='443')
      && /\.(png|webp|jpe?g)$/i.test(url.pathname) ? value : ''
  } catch { return '' }
}
const normalized = value => String(value).replace(/[·：:\s「」『』]/g,'')
export function nteRole(nameOrId) {
  return catalog.roles[nameOrId] || Object.values(catalog.roles).find(role=>String(role.id)===String(nameOrId))
}
export const nteRoleIcon = nameOrId => safeNteIcon(nteRole(nameOrId)?.icon)
export function nteNamedIcon(bucket,name) {
  const entries=catalog[bucket] || {}, exact=entries[name]
  if(exact)return safeNteIcon(exact.icon)
  const matches=Object.entries(entries).filter(([key])=>normalized(key)===normalized(name))
  return matches.length===1 ? safeNteIcon(matches[0][1].icon) : ''
}
export function nteSkillIcon(nameOrId,skill) {
  const id=nteRole(nameOrId)?.id || nameOrId, entries=catalog.skills[String(id)] || {}
  const exact=entries[skill] || Object.values(entries).find(entry=>entry.name===skill)
  return safeNteIcon(exact?.icon)
}

export function tokenizeNteGuide(text,sectionKey,roleName) {
  const source=String(text || ''), bucket={weapons:'weapons',teams:'roles',sets:'sets'}[sectionKey]
  const candidates=new Map(Object.entries(catalog[bucket] || {}).map(([name,entry])=>[name,{name,icon:safeNteIcon(entry.icon),kind:bucket}]))
  if(sectionKey==='sets') {
    for(const [name,entry] of Object.entries(catalog.sets)) {
      for(const alias of [name.replace(/[:：]/g,'·'),name.replace(/·/g,':')])candidates.set(alias,{name,icon:safeNteIcon(entry.icon),kind:'sets'})
    }
  }
  if(sectionKey==='weapons') {
    const full=Object.keys(catalog.weapons).find(name=>name.startsWith('光波眩晕'))
    if(full)candidates.set('光波眩晕',{name:full,icon:nteNamedIcon('weapons',full),kind:'weapons'})
  }
  if(sectionKey==='skills') {
    const id=nteRole(roleName)?.id, skills=catalog.skills[String(id)] || {}
    for(const [name,entry] of Object.entries(skills)) candidates.set(name,{name:entry.name || name,icon:safeNteIcon(entry.icon),kind:'skills'})
    for(const [alias,name] of Object.entries({普攻:'普通攻击',终结:'极轨终结',技能:'变轨技能',援护:'援护技','被动 1':'被动1','被动 2':'被动2'})) {
      if(skills[name])candidates.set(alias,{name:skills[name].name || name,icon:safeNteIcon(skills[name].icon),kind:'skills'})
    }
  }
  const names=[...candidates.keys()].filter(Boolean).sort((a,b)=>b.length-a.length)
  const tokens=[];let offset=0,plain=''
  while(offset<source.length) {
    const name=names.find(name=>source.startsWith(name,offset) && ((name.length>1 && name!=='技能') || (!/[\p{L}\p{N}]/u.test(source[offset-1] || '') && !/[\p{L}\p{N}]/u.test(source[offset+name.length] || ''))))
    if(!name){plain+=source[offset++];continue}
    if(plain){tokens.push({text:plain});plain=''}
    tokens.push({text:name,...candidates.get(name),entity:true});offset+=name.length
  }
  if(plain)tokens.push({text:plain})
  return tokens
}
