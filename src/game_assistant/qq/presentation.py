"""Explicit cached payload projections into the common display-only card model.

Only named, existing source fields cross this boundary. Missing values remain
unknown; role caches represent observed equipment, never complete inventories.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import math
import re

from .cards import validate_card_document
from .commands import GAME_NAMES, safe_text

BEIJING = timezone(timedelta(hours=8))
PRIVATE_LABELS = re.compile(r'score|rank|rating|token|secret|password|credential|authorization|uid|评分|评级|排名|伤害估算|凭据|密码|令牌',re.I)
LABELS = {'account':'账号', 'stamina':'体力', 'roles':'角色', 'exploration':'探索',
          'combat':'挑战', 'progress':'进度', 'gacha':'抽卡', 'record':'档案', 'events':'活动', 'news':'公告',
          'calabash':'数据坞','activities':'活动进度','resources':'资源','realestate':'房产','vehicles':'车辆','teams':'队伍'}
PROVIDERS = {'hypergryph':'鹰角寻访', 'skland':'森空岛档案'}


def text(value, limit=72):
    if value is None or not isinstance(value, (str, int, float, bool)):
        return '未知'
    if isinstance(value, float) and not math.isfinite(value):
        return '未知'
    if type(value) is bool:
        value = '是' if value else '否'
    clean = safe_text(str(value)).replace('\n', ' ').strip() or '未知'
    return clean if len(clean)<=limit else clean[:limit-1]+'…'


def field(label, value):
    output={'label': text(label, 32), 'value': text(value)}
    if type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**12:
        output['metric']={'current':value,'maximum':None}
    return output


def format_time(value):
    """Explicit time fields only: ISO/epoch -> Beijing minutes; absence stays unknown."""
    if isinstance(value,bool) or value is None:return '未知'
    try:
        if isinstance(value,(int,float)):
            if not math.isfinite(value) or value<=0:return '未知'
            moment=datetime.fromtimestamp(value/1000 if value>=10**11 else value,timezone.utc)
        elif isinstance(value,datetime):moment=value
        elif isinstance(value,str):
            if re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}',value):
                moment=datetime.strptime(value,'%Y-%m-%d %H:%M').replace(tzinfo=BEIJING)
            else:
                if not re.search(r'[T ]\d{2}:\d{2}',value):return '未知'
                moment=datetime.fromisoformat(value.replace('Z','+00:00'))
        else:return '未知'
        if moment.tzinfo is None:moment=moment.replace(tzinfo=timezone.utc)
        return moment.astimezone(BEIJING).strftime('%Y-%m-%d %H:%M')
    except (ValueError,TypeError,OverflowError,OSError):return '未知'


def time_field(label,value):
    return field(label,format_time(value))


def number(value):
    return value if type(value) in (int,float) and math.isfinite(value) and 0<=value<=10**12 else None


def metric_field(label,current,maximum):
    output=field(label,pair(current,maximum))
    output['metric']={'current':number(current),'maximum':number(maximum)}
    return output


def image_ref(cache,game,kind,identifier=None,url=None):
    if cache is None:return None
    if url:
        ref=cache.register_url(url)
        if ref:return ref
    return cache.ref_for(game,kind,identifier) if identifier is not None else None


def with_image(target,ref):
    if ref:target['image']=ref
    return target


def pair(current, maximum):
    return text(current)+'/'+text(maximum)


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def label(game, provider=''):
    return GAME_NAMES[game]+(' · '+PROVIDERS[provider] if provider in PROVIDERS else '')


def metadata(snapshot):
    if snapshot.payload is None:
        state = '暂无成功快照；请发送「刷新 游戏」或在网站采集'
    elif snapshot.state not in ('ok', 'success'):
        sources = getattr(snapshot, 'poll_status', {}).get('source_statuses', {})
        state = ('部分来源不可用，显示可用来源数据' if getattr(snapshot, 'stale', None) is False
                 and any(obj(s).get('state') in ('error', 'auth_expired') for s in sources.values())
                 else '当前查询失败或待刷新，显示旧快照')
    elif getattr(snapshot, 'stale', False):
        state = '数据可能过期'
    else:
        state = '缓存快照'
    complete = '不完整' if snapshot.complete is False else '完整' if snapshot.complete is True else '未知'
    return [field('数据状态', state), time_field('更新时间', snapshot.fetched_at), field('完整性', complete)]


def document(kind, game, title, *, sections=None, notices=None, footer='', subtitle=''):
    return dict(version=3, kind=kind, game=game or 'all', title=text(title, 90), subtitle=text(subtitle, 170) if subtitle else '',
                sections=sections or [], notices=notices or [], footer=text(footer,170) if footer else '')


def message(game, title, explanation, *, kind='status'):
    return document(kind, game, title, notices=[text(explanation,170)], subtitle='')


def help_document(game=None):
    """Every line comes from the command registry, so help matches the parser."""
    from .commands import ALL_GAMES, REGISTRY
    prefix=GAME_NAMES.get(game,'游戏')
    grouped={};owners={}
    for entry in REGISTRY:
        if game is not None and entry.games and game not in entry.games:continue
        name=prefix if game is not None or len(entry.games)!=1 else GAME_NAMES[entry.games[0]]
        description=entry.description
        if game is None and 1<len(entry.games)<len(ALL_GAMES):description+='（'+'、'.join(GAME_NAMES[g] for g in entry.games)+'）'
        grouped.setdefault(entry.section,[]).append(field(description,entry.syntax.replace('游戏',name)))
        owners.setdefault(entry.section,set()).add(entry.games[0] if len(entry.games)==1 else None)
    # A group whose every line belongs to one game names it, so the image can tint that group.
    sections=[{'title':title,'layout':'help','fields':fields,**({'game':next(iter(owners[title]))} if owners[title]!={None} and len(owners[title])==1 else {})}
              for title,fields in grouped.items()]
    card=document('help',game or 'all',prefix+' · 帮助' if game else '帮助 · 游戏管家',subtitle='游戏前缀：鸣潮、异环、终末地；公共单游戏活动无需绑定',sections=sections,
        notices=['先登录网站生成绑定码，再发送绑定指令；收到成功回复即完成。','不写游戏名时，活动按已授权的游戏分别显示；近期活动列出即将开始或结束的活动。'])
    card['version']=3
    return card


def account_fields(game, provider, payload):
    data = obj(payload)
    base = obj(data.get('base')) if provider=='skland' else data
    out = [field('昵称', base.get('name') if provider=='skland' else base.get('nickname')), field('等级', base.get('level'))]
    for key,title in (('server_name','服务器'),('world_level','世界等级'),('active_days','活跃天数')):
        if key in base: out.append(field(title,base[key]))
    if game=='nte':
        for key,title in (('tycoon_level','大亨等级'),('character_count','角色数'),('achievement_count','成就数')):
            if key in data:out.append(field(title,data[key]))
        for current,maximum,title in (('achievement_count','achievement_total','成就'),('house_count','house_total','房产'),('vehicle_count','vehicle_total','车辆')):
            if current in data or maximum in data:out.append(metric_field(title,data.get(current),data.get(maximum)))
    if game=='wuthering_waves':
        profile=obj(obj(data.get('extra')).get('profile'))
        for key,title in (('world_level','世界等级'),('active_days','活跃天数'),('achievement_count','成就数')):
            if key in profile:out.append(field(title,profile[key]))
        for key,title in (('achievement_star','成就星数'),('big_count','大信标'),('small_count','小信标')):
            if key in profile:out.append(field(title,profile[key]))
        for key,title in (('box_list','收集'),('treasure_box_list','宝箱'),('phantom_box_list','声骸收集')):
            for item in rows(profile.get(key)):
                if 'num' in item:out.append(field(title+' · '+text(item.get('name') or item.get('box_name'),22),item.get('num')))
    if provider=='skland' and isinstance(data.get('stamina'),dict):
        stamina=data['stamina']; out.append(metric_field('体力',stamina.get('current'),stamina.get('maximum')))
    return out


def overview_roles(game,provider,snapshot,asset_cache=None,*,details=None):
    entries=role_entries(game,snapshot.payload,provider)
    output=[]
    for entry in entries[:6]:
        values=[];weapon=obj(entry.get('weapon'));equipment=[]
        def add_equipment(name,level,kind,url=None):
            if not name:return
            item={'title':text(name),'subtitle':'等级 '+text(level)}
            with_image(item,image_ref(asset_cache,game,kind,name,url));equipment.append(item)
        if weapon:
            values+=[field('已知武器',weapon.get('name')),field('武器等级',weapon.get('level'))]
            add_equipment(weapon.get('name'),weapon.get('level'),'weapon',weapon.get('icon_url'))
        for item in rows(entry.get('equipment'))[:5]:
            values.append(field('已知装备 '+text(item.get('slot'),16),item.get('name')))
            add_equipment(item.get('name'),item.get('level'),'equipment',item.get('icon_url'))
        if game=='wuthering_waves':
            detail=obj(obj(details).get(str(entry.get('role_id'))));observed_weapon=obj(detail.get('weapon_data'));info=obj(observed_weapon.get('weapon'))
            if observed_weapon:
                values+=[field('已知武器',info.get('weapon_name')),field('武器等级',observed_weapon.get('level'))]
                add_equipment(info.get('weapon_name'),observed_weapon.get('level'),'weapon',info.get('weapon_icon'))
            echoes=rows(obj(detail.get('phantom_data')).get('equip_phantom_list'))[:5]
            if echoes:values.append(field('已采集声骸',len(echoes)))
            for echo in echoes:
                info=obj(echo.get('phantom_prop'));add_equipment(info.get('name'),echo.get('level'),'echo',info.get('icon_url'))
        shown=equipment[:6]
        if shown:
            names={item['title'] for item in shown}
            levels={item['subtitle'] for item in shown}
            weapon_shown=any(item['label']=='已知武器' and item['value'] in names for item in values)
            values=[item for item in values if not (
                (item['label']=='已知武器' or item['label'].startswith('已知装备 ')) and item['value'] in names
                or item['label']=='武器等级' and weapon_shown and '等级 '+item['value'] in levels)]
        row={'title':text(entry.get('name')),'subtitle':'等级 '+text(entry.get('level')),
             'fields':values if shown else values or [field('装备','未采集')]}
        if shown:row['equipment']=shown
        with_image(row,image_ref(asset_cache,game,'role',entry.get('id') or entry.get('role_id') or entry.get('name'),entry.get('icon_url') or entry.get('avatar_url')))
        output.append(row)
    if not output:return []
    return [{'title':label(game,provider)+' · 角色装备速览（'+str(min(6,len(entries)))+'/'+str(len(entries))+'）','layout':'equipment','rows':output,
             'fields':[field('范围','仅已采集配装；完整角色请发送「'+GAME_NAMES[game]+' 角色」')]}]


def gacha_document(game,provider,snapshot,asset_cache=None,*,ledger=None):
    """NTE community window is distinct from the optional imported ledger."""
    if game!='nte':
        return record_gacha_document(game,provider,snapshot,asset_cache)
    data=obj(snapshot.payload);sections=[]
    fields=[field('统计来源','塔吉多社区 · 统计窗口内数据'),field('总抽数',data.get('total_draws')),field('出 S 数量',data.get('total_s'))]
    if data.get('schema_version')==1 and data.get('luck_title'):fields.append(field('塔吉多近期评价',data['luck_title']))
    code=data.get('luck_type')
    tone='green' if type(code) is int and 1<=code<=5 else 'yellow' if type(code) is int and 6<=code<=10 else 'red' if type(code) is int and 11<=code<=15 else 'unknown'
    sections.append({'title':'社区统计','layout':'stats','tone':tone,'fields':fields+metadata(snapshot)})
    if snapshot.payload is not None and data.get('schema_version')!=1:
        sections.append({'title':'社区统计格式','fields':[field('状态','格式已升级；请在网站刷新后查询')]})
    else:
        for pool in rows(data.get('pools')):
            values=[field('抽数',pool.get('total_draws')),field('出 S 数量',pool.get('s_count')),field('S 级平均',pool.get('average'))]
            if pool.get('guarantee') is not None:values.append(field('本池标尺',pool['guarantee']))
            entries=[]
            for detail in rows(pool.get('details')):
                code=detail.get('lucky_type') if type(detail.get('lucky_type')) is int else None
                color={0:'yellow',1:'green',2:'green',3:'yellow',4:'red'}.get(code,'unknown')
                lucky={1:'超欧',2:'欧',3:'非',4:'超非'}.get(code,'')
                draws=number(detail.get('pity'));guarantee=number(pool.get('guarantee'))
                draws=int(draws) if draws is not None and int(draws)==draws else None
                guarantee=int(guarantee) if guarantee is not None and int(guarantee)==guarantee and guarantee>0 else None
                obtained=detail.get('obtained_at')
                # NTE source strings without a zone are explicitly Beijing.
                if isinstance(obtained,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?',obtained):obtained=obtained.replace(' ','T')+'+08:00'
                item={'title':text(detail.get('name') or detail.get('item_id')),'fields':[field('本次出 S 抽数',draws),time_field('获取时间',obtained)],
                      'gacha':{'draws':draws,'guarantee':guarantee,'lucky_type':code,'color':color,'lucky_text':lucky}}
                ref=image_ref(asset_cache,game,'role',detail.get('item_id')) or image_ref(asset_cache,game,'weapon',detail.get('item_id'))
                with_image(item,ref)
                entries.append(item)
            sections.append({'title':text(pool.get('name') or '未命名卡池'),'layout':'gacha','fields':values,'rows':entries})
    if ledger is None:
        sections.append({'title':'本人逐抽账本','fields':[field('导入状态','未导入')]})
    else:
        section=capability_section(game,provider,'gacha',ledger,asset_cache)
        section['title']='本人逐抽账本';section['fields']+=metadata(ledger);sections.append(section)
    card=document('list',game,label(game,provider)+' · 抽卡',sections=sections,footer='更新时间：'+format_time(snapshot.fetched_at))
    card['version']=3
    return card


def record_gacha_document(game,provider,snapshot,asset_cache=None):
    data=obj(snapshot.payload);sections=[]
    sections.append({'title':'已记录抽卡','layout':'stats','fields':[field(title,data[key]) for key,title in (('total','记录数'),('gold_total','5星数量')) if key in data]+metadata(snapshot)})
    notices=['仅展示已导入或已同步的抽卡记录。']
    for pool in rows(data.get('pools')):
        values=[];entries=[]
        for key,title in (('total','记录数'),('six_star','6星'),('five_star','5星'),('free','免费抽取'),('gaps','已知记录缺口'),('pending','待同步')):
            if key in pool:values.append(field(title,pool[key]))
        if game=='wuthering_waves':
            values += [field(str(rarity)+'星',count) for rarity,count in obj(pool.get('rarity_distribution')).items() if rarity in ('3','4','5','unknown')]
            for item in rows(data.get('gold')):
                if str(item.get('pool'))!=str(pool.get('pool')):continue
                entries.append(with_image({'title':text(item.get('name')),'fields':[field('类型',item.get('resource_type')),time_field('获取时间',item.get('time'))]},image_ref(asset_cache,game,'role',item.get('name'))))
        else:
            pity=obj(pool.get('since_last_six'))
            if pity:
                values.append(field('距上次6星（记录边界）',('至少 ' if pity.get('status')=='lower_bound' else '')+text(pity.get('count')) if pity.get('status') in ('exact','lower_bound') else '未知'))
            for item in rows(pool.get('history')):
                count=text(item.get('pulls'));count=('至少 '+count) if item.get('status')=='lower_bound' else count
                entries.append(with_image({'title':text(item.get('name')),'fields':[field('该次6星抽数',count),field('记录边界',{'exact':'记录内准确','lower_bound':'下限'}.get(item.get('status'),'未知')),time_field('获取时间',item.get('obtained_at'))]},image_ref(asset_cache,game,'role',item.get('name'))))
        sections.append({'title':text(pool.get('label') or pool.get('name') or pool.get('key') or pool.get('pool')),'layout':'rows','fields':values,'rows':entries})
    coverage=obj(data.get('coverage'))
    if game=='wuthering_waves':
        sections.append({'title':'导入范围','fields':[time_field('最早记录',coverage.get('earliest')),time_field('最新记录',coverage.get('latest')),field('完整历史','不完整' if coverage.get('complete') is False else '未知')]})
        if number(data.get('gold_total')) is not None and data['gold_total']>len(rows(data.get('gold'))):notices.append('出货详情超过本次读取范围；仅展示最新500条，完整内容请在网站查看。')
    if data.get('state')=='need_import':notices.append('尚未导入本人抽卡记录；请在网站导入。')
    return document('list',game,label(game,provider)+' · 抽卡',sections=sections,notices=notices,footer='更新时间：'+format_time(snapshot.fetched_at))


def role_entries(game, payload, provider=''):
    if game=='nte':return rows(obj(payload).get('entries'))
    if game=='endfield':return rows(obj(payload).get('operators')) if provider=='skland' else []
    return rows(payload) if isinstance(payload,list) else rows(obj(payload).get('roles'))


def role_sections(game, entry, asset_cache=None):
    common=[field('等级',entry.get('level'))]
    mappings = {
        'wuthering_waves': [('attribute','属性'),('chain','共鸣链'),('breach','突破'),('star_level','稀有度'),('weapon','武器类型')],
        'nte': [('quality','稀有度'),('element','属性'),('awaken_level','觉醒'),('mix_level','共鸣'),('affinity_exp','好感')],
        'endfield': [('rarity','稀有度'),('potential','潜能'),('evolve_phase','精英化'),('profession','职业'),('property','属性')],
    }
    for key,title in mappings[game]:
        common.append(field(title,entry.get(key)))
    sections=[with_image({'title':'角色资料','layout':'detail', 'fields':common},image_ref(asset_cache,game,'role',entry.get('id') or entry.get('role_id') or entry.get('name'),entry.get('icon_url') or entry.get('avatar_url')))]
    weapon=obj(entry.get('weapon'))
    if weapon:
        fields=[field('名称',weapon.get('name')),field('等级',weapon.get('level'))]
        for key,title in (('mix_level','叠加'),('refine_level','精炼'),('breakthrough_level','突破')):
            if key in weapon:fields.append(field(title,weapon[key]))
        sections.append(with_image({'title':'当前装备 · 武器','layout':'equipment', 'fields':fields},image_ref(asset_cache,game,'weapon',weapon.get('name'),weapon.get('icon_url'))))
    equipment=rows(entry.get('equipment'))
    if equipment:
        sections.append({'title':'当前装备 · 护具','layout':'equipment', 'rows':[with_image({'title':text(item.get('name')), 'subtitle':text(item.get('slot')),
             'fields':[field('等级',item.get('level'))]},image_ref(asset_cache,game,'equipment',item.get('name'),item.get('icon_url'))) for item in equipment]})
    for key,title in (('skills','技能'),('city_skills','都市技能')):
        found=rows(entry.get(key))
        if found:sections.append({'title':title,'layout':'skills','rows':[with_image({'title':text(item.get('name')),'fields':[field('等级',item.get('level'))]},
            image_ref(asset_cache,game,'skill',str(entry.get('id') or entry.get('role_id') or '')+'::'+str(item.get('name') or ''),item.get('icon_url'))) for item in found]})
    properties=rows(entry.get('properties'))
    if properties:
        sections.append({'title':'缓存属性','layout':'stats','fields':[field(item.get('name'),item.get('value')) for item in properties
            if isinstance(item.get('name'),str) and not PRIVATE_LABELS.search(item['name'])]})
    return sections


def resolve_role(game, provider, snapshot, name):
    from ..character_search import resolve_character
    return resolve_character(game, name, role_entries(game, snapshot.payload, provider))


def role_card(game, provider, snapshot, name=None, asset_cache=None, *, resolution=None):
    entries=role_entries(game,snapshot.payload,provider)
    common=dict(footer='更新时间：'+format_time(snapshot.fetched_at)+' · 完整性：'+metadata(snapshot)[2]['value'])
    state=metadata(snapshot)[0]['value']
    if name is not None:
        resolution = resolution if resolution is not None else resolve_role(game,provider,snapshot,name)
        if resolution['status']=='none':
            card=message(game,label(game,provider)+' · 角色','本人角色缓存中未找到该角色；可按名称、别名、拼音或首字母搜索，或在网站采集。')
            card['notices'].append(state)
            card['footer']=common['footer']
            return card
        if resolution['status']!='resolved':
            from ..character_search import character_label
            candidates=resolution['candidates'][:12]
            notice='缓存存在同名角色，无法确定唯一详情。' if resolution['status']=='ambiguous' else '未找到精确匹配，以下仅为候选。'
            return document('list',game,label(game,provider)+' · 角色候选',sections=[{'title':'本人已授权角色候选','layout':'grid','rows':[
                {'title':character_label(game,item['entry']), 'fields':[field('角色标识',item['character_id'] or '未提供')]} for item in candidates]}],
                notices=[state,notice,'请发送完整角色名称与形态，或在网站点击确认。'],**common)
        entry=resolution['entry']
        return with_image(document('detail',game,label(game,provider)+' · '+text(entry.get('name')),sections=role_sections(game,entry,asset_cache),
            notices=[state],**common),image_ref(asset_cache,game,'role',entry.get('id') or entry.get('role_id') or name,entry.get('icon_url') or entry.get('avatar_url')))
    out=[]
    for entry in entries:
        fields=[field('等级',entry.get('level'))]
        for key,title in (('attribute','属性'),('element','属性'),('chain','共鸣链'),('potential','潜能')):
            if key in entry:fields.append(field(title,entry[key]))
        out.append(with_image({'title':text(entry.get('name')), 'fields':fields},image_ref(asset_cache,game,'role',entry.get('id') or entry.get('role_id') or entry.get('name'),entry.get('icon_url') or entry.get('avatar_url'))))
    return document('list',game,label(game,provider)+' · 角色',sections=[{'title':f'本人角色列表 · {len(entries)} 位','layout':'grid', 'rows':out}],
        notices=[state]+(['当前列表为空。' if snapshot.payload is not None else '暂无数据；请在网站采集角色缓存。'] if not entries else []),**common)


def wuwa_detail_sections(payload,asset_cache=None):
    """getRoleDetail archive shape, kept separate from basic roleData fields."""
    data=obj(payload);sections=[]
    weapon=obj(data.get('weapon_data'));info=obj(weapon.get('weapon'))
    if weapon:
        sections.append(with_image({'title':'当前装备 · 武器','layout':'equipment','fields':[field('名称',info.get('weapon_name')),field('等级',weapon.get('level')),
            field('突破',weapon.get('breach')),field('谐振',weapon.get('reson_level'))]},image_ref(asset_cache,'wuthering_waves','weapon',info.get('weapon_name'),info.get('weapon_icon'))))
    for key,title in (('role_attribute_list','观测属性'),('equip_phantom_attribute_list','声骸属性'),('equip_phantom_add_prop_list','声骸汇总词条')):
        values=[field(item.get('attribute_name'),item.get('attribute_value')) for item in rows(data.get(key))
                if isinstance(item.get('attribute_name'),str) and not PRIVATE_LABELS.search(item['attribute_name'])]
        if values:sections.append({'title':title,'layout':'stats','fields':values})
    skills=rows(data.get('skill_list'))
    if skills:sections.append({'title':'技能','layout':'skills','rows':[with_image({'title':text(obj(item.get('skill')).get('name')),
                  'fields':[field('等级',item.get('level'))]},image_ref(asset_cache,'wuthering_waves','skill',obj(item.get('skill')).get('name'),obj(item.get('skill')).get('icon_url'))) for item in skills]})
    phantom=obj(data.get('phantom_data'))
    if phantom:
        echo_sections=[{'title':'当前装备 · 声骸','layout':'equipment','fields':[field('总 COST',phantom.get('cost'))]}]
        for item in rows(phantom.get('equip_phantom_list')):
            info=obj(item.get('phantom_prop'));fetter=obj(item.get('fetter_detail'))
            values=[field('等级',item.get('level')),field('COST',item.get('cost')),field('套装',fetter.get('name'))]
            for key,prefix in (('main_props','主词条'),('sub_props','副词条')):
                values.extend(field(prefix+' '+text(p.get('attribute_name'),24),p.get('attribute_value')) for p in rows(item.get(key))
                              if isinstance(p.get('attribute_name'),str) and not PRIVATE_LABELS.search(p['attribute_name']))
            echo_sections.append(with_image({'title':'声骸 · '+text(info.get('name')),'layout':'equipment','fields':values},image_ref(asset_cache,'wuthering_waves','echo',info.get('name'),info.get('icon_url'))))
        sections.extend(echo_sections)
    return sections


def capability_section(game, provider, capability, snapshot,asset_cache=None):
    data=obj(snapshot.payload)
    fields=[]; found=[]
    if capability in ('calabash','activities','resources','realestate','vehicles','teams'):
        from .extras import extra_section
        section=extra_section(game,capability,snapshot.payload)
        if section is not None:
            section['title']=label(game,provider)+' · '+LABELS[capability]
            section['layout']='stats' if capability=='calabash' else 'rows'
            for item in section.get('fields',[]):
                if item['label']=='报告更新时间':item['value']=format_time(obj(data.get('current')).get('fetched_at'))
            return section
    if capability=='account':
        fields=account_fields(game,provider,snapshot.payload)
    elif capability=='stamina':
        fields=[metric_field('体力',data.get('current'),data.get('maximum')),time_field('预计回满',data.get('expected_full_at'))]
        if game=='nte':
            fields += [metric_field('都市体力',data.get('city_current'),data.get('city_maximum')),field('每日活跃',data.get('daily_activity')),
                       field('周本剩余',data.get('weekly_remaining'))]
    elif capability=='gacha':
        keys=(('total_records','记录数'),('total_draws','抽取次数'),('total','记录数'),('total_s','S 数量'),('gold_total','5星数量'))
        fields=[field(title,data[key]) for key,title in keys if key in data]
        for pool in rows(data.get('pools')):
            pf=[]
            for key,title in (('total_draws','抽取次数'),('total_records','记录数'),('total_pulls','抽取次数'),('total','记录数'),('s_count','S 数量'),('six_star','6星数量')):
                if key in pool:pf.append(field(title,pool[key]))
            found.append({'title':text(pool.get('name') or pool.get('label') or pool.get('pool_id')),'fields':pf[:4]})
        if not fields:fields=[field('抽卡缓存','未知；请在网站导入本人记录')]
    elif capability=='exploration':
        if game=='wuthering_waves':
            for group in rows(data.get('country_groups')):
                progress=group.get('progress')
                metric=metric_field('探索度',progress,100);metric['value']='未知' if progress is None else text(progress)+'%'
                found.append({'title':text(group.get('name')),'fields':[metric]})
                for area in rows(group.get('areas')):
                    progress=area.get('progress')
                    metric=metric_field('探索度',progress,100);metric['value']='未知' if progress is None else text(progress)+'%'
                    found.append({'title':text(area.get('name')),'fields':[metric]})
        elif game=='nte':
            for area in rows(data.get('areas')):
                found.append({'title':text(area.get('name')),'fields':[metric_field('进度',area.get('current'),area.get('total'))]})
                found.extend({'title':text(a.get('name')),'fields':[metric_field('进度',a.get('current'),a.get('total'))]} for a in rows(area.get('details')))
        else:
            for region in rows(data.get('regions')):
                found.append({'title':text(region.get('name')), 'fields':[field('地区等级',region.get('level'))]})
                for area in rows(region.get('levels')):
                    af=[]
                    for key,title in (('puzzles','解谜'),('chests','宝箱'),('equipment_chests','装备箱'),('pieces','碎片'),('blackboxes','黑箱')):
                        counts=obj(area.get(key))
                        if counts:af.append(metric_field(title,counts.get('count'),counts.get('total')))
                    found.append({'title':text(area.get('name')),'fields':af})
    elif capability=='progress':
        if game=='nte':
            fields=[metric_field('成就',data.get('completed'),data.get('total')),field('铜',data.get('bronze')),field('银',data.get('silver')),field('金',data.get('gold'))]
            found=[{'title':text(item.get('name')),'fields':[metric_field('进度',item.get('current'),item.get('total'))]} for item in rows(data.get('categories'))]
        else:
            entries=rows(snapshot.payload) if isinstance(snapshot.payload,list) else rows(data.get('progress'))
            found=[{'title':text(item.get('name')),'fields':[metric_field('进度',item.get('cur'),item.get('total')),time_field('刷新时间',item.get('refresh_at'))]} for item in entries]
    elif capability=='combat' and game=='wuthering_waves':
        for key,title in (('tower','逆境深塔'),('hologram','战术全息'),('slash','冥歌海墟')):
            source=obj(data.get(key)); detail=obj(source.get('data'))
            pf=[field('来源状态','可用' if source.get('state')=='ok' else '不可用'),time_field('更新时间',source.get('fetched_at'))]
            for count_key,count_title in (('star','星数'),('max_star','总星数'),('season_end_at','周期截止')):
                if count_key in detail:pf.append(time_field(count_title,detail[count_key]) if count_key=='season_end_at' else field(count_title,detail[count_key]))
            found.append({'title':title,'fields':pf})
            if key=='tower':
                for difficulty in rows(detail.get('difficulty_list')):
                    for area in rows(difficulty.get('tower_area_list')):
                        found.append({'title':text(area.get('area_name') or difficulty.get('name') or '深塔分区'),
                                      'fields':[metric_field('星数',area.get('star'),area.get('max_star'))]})
    elif capability=='record':
        found=[{'title':text(item.get('nickname')),'fields':[field('等级',item.get('level')),field('服务器',item.get('server_name'))]} for item in rows(data.get('cards'))]
    elif capability in ('events','news'):
        entries=rows(snapshot.payload) if isinstance(snapshot.payload,list) else rows(data.get('events'))
        for item in entries:
            pf=[time_field('截止' if capability=='events' else '发布时间',item.get('end_at') if capability=='events' else item.get('published_at'))]
            if capability=='events':
                pf.insert(0,time_field('开始',item.get('start_at')))
                if item.get('start_text'):pf.append(field('开始说明',item['start_text']))
            found.append({'title':text(item.get('title') or item.get('name')),'fields':pf})
    if not fields and not found:fields=[field('数据','暂无数据' if snapshot.payload is None else '当前缓存没有已采集字段')]
    return {'title':label(game,provider)+' · '+LABELS.get(capability,capability),'layout':'stats' if fields and not found else 'rows', 'fields':fields, 'rows':found}


def snapshot_card(game, provider, capability, snapshot,asset_cache=None):
    if capability=='gacha':return gacha_document(game,provider,snapshot,asset_cache)
    section=capability_section(game,provider,capability,snapshot,asset_cache)
    notices=[metadata(snapshot)[0]['value'], '完整性：'+metadata(snapshot)[2]['value']]
    if capability=='gacha':
        notices.append('仅代表已采集或已导入记录；不推算保底、评分或排名。')
        if obj(snapshot.payload).get('state')=='need_import':notices.append('尚未导入本人抽卡记录；请在网站导入。')
    return document('list' if section['rows'] else 'summary',game,label(game,provider)+' · '+LABELS.get(capability,capability),
       sections=[section],notices=notices,footer='更新时间：'+format_time(snapshot.fetched_at))


def long_document(card, requested_page=1,asset_cache=None):
    """Keep complete bounded content on one document; mark every hard-limit omission."""
    output=deepcopy(card);output.pop('page',None)
    output['notices']=output.get('notices',[])[:4]
    if requested_page!=1:output['notices'].append('已改为一次显示完整长图，无需翻页；旧页码指令仍可使用。')
    if asset_cache is not None and output['kind']!='detail' and not output.get('image'):
        with_image(output,image_ref(asset_cache,output['game'],'game',output['game']))
    row_count=field_count=characters=0;clipped=False;sections=[]
    def allowed_fields(items,maximum):
        nonlocal field_count,characters,clipped
        selected=[]
        for item in items:
            cost=len(item['label'])+len(item['value'])+8
            if len(selected)>=maximum or field_count>=360 or characters+cost>22000:
                clipped=True;continue
            selected.append(item);field_count+=1;characters+=cost
        return selected
    for section in output.get('sections',[]):
        if len(sections)>=36:clipped=True;break
        target={key:value for key,value in section.items() if key not in ('fields','rows')}
        characters+=len(target.get('title',''))+8
        target['fields']=allowed_fields(section.get('fields',[]),48)
        target['rows']=[]
        for row in section.get('rows',[]):
            cost=len(row.get('title',''))+len(row.get('subtitle',''))+12
            if row_count>=256 or characters+cost>22000:clipped=True;break
            characters+=cost;row_count+=1
            child={key:value for key,value in row.items() if key!='fields'}
            child['fields']=allowed_fields(row.get('fields',[]),8)
            target['rows'].append(child)
        sections.append(target)
    output['sections']=sections
    if clipped:output['notices'].append('内容超过单张长图显示上限；部分条目或字段已省略，完整内容请到网站查看。')
    return validate_card_document(output)


def asset_refs(card):
    refs={card['image']} if card.get('image') else set()
    for section in card.get('sections',[]):
        if section.get('image'):refs.add(section['image'])
        refs.update(row['image'] for row in section.get('rows',[]) if row.get('image'))
        refs.update(item['image'] for row in section.get('rows',[]) for item in row.get('equipment',[]) if item.get('image'))
    return refs
