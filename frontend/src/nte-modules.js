export const nteModuleTitles = {account:'账号档案',stamina:'体力与日常',roles:'角色练度',progress:'成就进度',exploration:'探索进度',record:'社区名片',realestate:'房产详情',vehicles:'载具详情',teams:'官方配队',gacha:'抽卡统计',guides:'角色攻略',announcement:'公告',news:'资讯'}
const value = x => x === null || x === undefined || x === '' || (typeof x === 'number' && !Number.isFinite(x)) ? '未知' : x
export function nteModuleMetrics(cap,snap) {
  const p=snap?.payload
  if (['news','announcement'].includes(cap))return [{label:'已收录',value:Array.isArray(p)?p.length:'未知'}]
  if(cap==='guides')return [{label:'培养方案',value:'5 类推荐'},{label:'资料',value:'摘要 + 原图'}]
  if (!p || p.schema_version!==1)return []
  const metric=(label,v)=>({label,value:value(v)})
  if(cap==='account')return [metric('昵称',p.nickname),metric('等级',p.level),metric('活跃天数',p.active_days)]
  if(cap==='stamina')return [
    {label:'本性像素',current:p.current,total:p.maximum,icon:'spark'},
    {label:'都市活力',current:p.city_current,total:p.city_maximum,icon:'refresh'},
    {label:'日常活跃',current:p.daily_activity,total:100,icon:'calendar'},
  ]
  if(cap==='roles')return [metric('角色',p.entries?.length),metric('S 级',p.entries?.filter(r=>r.quality==='S').length)]
  if(cap==='progress')return [{label:'成就',current:p.completed,total:p.total,icon:'shield'},metric('金奖章',p.gold),metric('银奖章',p.silver),metric('铜奖章',p.bronze)]
  if(cap==='exploration')return (p.areas || []).map(area=>({label:area.name || '未命名区域',current:area.current,total:area.total,icon:'grid'}))
  if(cap==='record')return [metric('名片',p.cards?.length)]
  if(cap==='realestate'||cap==='vehicles')return [{label:'拥有',current:p.owned_count,total:p.total,icon:'grid'}]
  if(cap==='teams')return [metric('官方推荐',p.entries?.length)]
  if(cap==='gacha')return [metric('统计抽数',p.total_draws),metric('出 S 数',p.total_s),metric('近期评价',p.luck_title)]
  return []
}
