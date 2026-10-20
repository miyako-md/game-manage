"""Endfield's six reports, projected from shared domain facts into safe QQ cards.

This module never reads credentials, contacts upstream services or joins game
identities. Only existing scoped snapshots and the public image cache enter it.
"""
import re

from game_assistant.endfield_reports import build_endfield_report, build_gacha_report

from . import presentation as view

SLOTS = {'bodyEquip': '护甲', 'armEquip': '护手', 'firstAccessory': '配件一', 'secondAccessory': '配件二'}


def _tactical_effect_text(raw):
    # Observed game color spans are formatting, not part of the effect prose.
    # Keep unknown markup and parameter placeholders; never interpret HTML.
    return re.sub(r'<@(?:ba\.vup|tips\.(?:purple|orange))>([^<>]*)</>', r'\1', raw)


def _image(cache, kind, item):
    # Game instance IDs and official-site catalog keys are separate namespaces.
    # Exact public names provide a fallback, never fuzzy aliases or a guessed
    # gender for the default Endministrator name.
    # Portraits are reviewed catalog assets, never an enlarged avatar URL.
    if kind == 'portrait':
        for identity in (item.get('char_id'), item.get('id'), item.get('name')):
            if identity is not None:
                ref = view.image_ref(cache, 'endfield', kind, identity)
                if ref:
                    return ref
        return _image(cache, 'role', item)
    ref = view.image_ref(cache, 'endfield', kind, url=item.get('avatar_url') or item.get('icon_url'))
    if ref:
        return ref
    for identity in (item.get('char_id'), item.get('id'), item.get('name')):
        if identity is not None:
            ref = view.image_ref(cache, 'endfield', kind, identity)
            if ref:
                return ref
    return None


def _metric(label, data, current='current', maximum='total'):
    return view.metric_field(label, data.get(current), data.get(maximum))


def _footer(snapshot, report=None):
    footer = '更新时间：' + view.format_time(snapshot.fetched_at)
    if report and report.get('observed_at'):
        footer += ' · 观测时间：' + view.format_time(report['observed_at'])
    return footer + ' · 北京时间'


def _notice(snapshot):
    return [view.metadata(snapshot)[0]['value']]


def _section(title, *, fields=None, rows=None, layout='stats', category=None):
    section = {'title': title, 'layout': layout, 'fields': fields or [], 'rows': rows or []}
    if category:
        section['category'] = category
    return section


def _missing(snapshot, key, label):
    if view.obj(view.obj(snapshot.payload).get('availability')).get(key) is not True:
        return label + '尚未采集；请在网站采集后查询。'
    return '本次成功快照的' + label + '列表为空。'


def _challenge_budget(sections):
    """Reserve for measured typography before the generic long-card limits.

    Details have at most four rows per section. The CJK-width estimate is
    deliberately conservative, including long names and wrapped field labels.
    No final normalizer may remove a field that the coverage counts promise.
    """
    from math import ceil
    if len(sections)>34:return False
    fields=rows=characters=0
    height=850  # report heading, notices and footer

    def lines(value,size,width):
        return max(1,ceil(len(value)*size/width))

    def field_height(items, *, tiles):
        if not items:return 0
        columns=min(3,len(items))
        if len(items) in (2,4):
            columns=4 if len(items)==4 and all(len(item['value'])<=10 for item in items) else 2
        elif len(items)==8:columns=4
        if any(len(item['value'])>24 for item in items):columns=min(columns,2)
        width=(972-16*(columns-1))//columns-24
        total=0
        for index in range(0,len(items),columns):
            group=items[index:index+columns]
            total+=max(20+lines(item['label'],22,width)*30+
                       lines(item['value'],36 if tiles and len(item['value'])<=12 else 26,width)*
                       (44 if tiles and len(item['value'])<=12 else 34)+8 for item in group)+12
        return total

    for section in sections:
        height+=110+lines(section['title'],30,918)*38+field_height(section['fields'],tiles=True)
        characters+=len(section['title'])+8
        fields+=len(section['fields'])
        characters+=sum(len(item['label'])+len(item['value'])+8 for item in section['fields'])
        for row in section['rows']:
            rows+=1;fields+=len(row['fields'])
            characters+=len(row['title'])+len(row.get('subtitle',''))+12
            characters+=sum(len(item['label'])+len(item['value'])+8 for item in row['fields'])
            height+=lines(row['title'],28,972)*36+field_height(row['fields'],tiles=False)+42
    return fields<=350 and rows<=250 and characters<=21000 and height<=12200


def challenge_document(reports):
    """Three independently timed summaries, then fairly budgeted observations."""
    labels={'war':'战争','monument':'丰碑','crisis':'危机'}
    units={'war':('赛季','周次','关卡组','荣誉'),'monument':('记录','关卡组'),'crisis':('记录',)}
    summaries=[];details=[];totals=[];available=[]

    def title(item, fallback):
        value=item.get('name')
        if value is None or value=='':value=item.get('id')
        return view.text(value) if value is not None else fallback

    def passed(value):
        return '已通关' if value is True else '未通关' if value is False else '未知'

    def group_rows(groups):
        return [{'title':title(group,'未命名关卡组'), 'fields':[
            view.field('星数',group.get('stars'))]+[
            view.field(stage['difficulty']+' · '+view.text(stage.get('name')),passed(stage.get('passed')))
            for stage in group['stages']]} for group in groups]

    for report in reports:
        kind=report.get('kind')
        if kind not in labels:continue
        label=labels[kind];category='ef_'+kind
        state=('当前分类不支持' if report['supported'] is False else
               '最近读取失败，显示旧观测' if report['available'] and report['stale'] else
               '已采集观测；非实时状态' if report['available'] else
               '最近读取失败，尚无成功观测' if report['stale'] else '尚未采集；请在网站查看此挑战分类')
        summary=report['summary']
        fields=[view.field('状态',state),view.time_field('本分类抓取时间',report['fetched_at']),
                view.field('已采集记录',summary['listed_count'])]
        if kind=='crisis':
            fields += [view.field('最高值',summary['highest']),view.field('挑战次数',summary['challenge_count'])]
        if report['available'] and report['supported'] is not False and not report['records']:
            fields.append(view.field('记录说明','当前快照没有挑战记录'))
        summaries.append(_section(label+' · 缓存状态',fields=fields,category='ef_challenge'))
        available.append(report['available'] and report['supported'] is not False)
        counts={unit:0 for unit in units[kind]};entries=[]

        def add(name, *, fields=None, rows=None, increments=None, row_unit=None):
            rows=rows or []
            for index in range(0,max(1,len(rows)),4):
                chunk=rows[index:index+4]
                count=dict(increments or {}) if index==0 else {}
                if row_unit:count[row_unit]=len(chunk)
                for key,value in count.items():counts[key]+=value
                suffix=' · 续 '+str(index//4+1) if index else ''
                entries.append((_section(view.text(name,80)+suffix,fields=fields if index==0 else [],
                    rows=chunk,layout='rows' if chunk else 'stats',category=category),count))

        for record in report['records']:
            record_title=label+' · '+title(record,'未命名记录')
            fields=[]
            if kind!='crisis':
                fields=[view.time_field('开始时间',record['start_at']),view.time_field('结束时间',record['end_at'])]
            if kind=='war':
                fields.append(view.field('赛季星数',record['stars']))
                add(record_title,fields=fields,increments={'赛季':1})
                for week in record['weeks']:
                    add(record_title+' · '+title(week,'未命名周次'),fields=[view.field('周星数',week['stars'])],
                        rows=group_rows(week['groups']),increments={'周次':1},row_unit='关卡组')
            elif kind=='monument':
                add(record_title,fields=fields,rows=group_rows(record['groups']),increments={'记录':1},row_unit='关卡组')
            else:
                add(record_title,fields=[view.field('通关状态',passed(record['passed'])),
                    view.field('记录结果',record['result'])],increments={'记录':1})
        if report['honors']:
            add('战争 · 已观测荣誉',rows=[{'title':title(item,'未命名荣誉'),'fields':[
                view.field('星数',item['stars']),view.time_field('首次通关',item['first_pass_at'])]} for item in report['honors']],
                row_unit='荣誉')
        details.append(entries);totals.append(counts)

    selected=[[] for _ in details]

    def compose(candidate):
        from copy import deepcopy
        output=deepcopy(summaries)
        for index,entries in enumerate(candidate):
            for unit,total in totals[index].items():
                shown=sum(count.get(unit,0) for _,count in entries)
                output[index]['fields'].append(view.field(unit+'（本图 / 已观测）',
                    str(shown)+' / '+str(total) if available[index] else '未知 / 未采集'))
        # All three statuses and times are above any detail, regardless of size.
        return output+[section for entries in candidate for section,_ in entries]

    # Whole bounded chunks are allocated in turns. A long first category can
    # neither erase later summaries nor consume their first observation slots.
    blocked=set()
    while True:
        progressed=False
        for index,entries in enumerate(details):
            if index in blocked or len(selected[index])==len(entries):continue
            candidate=[list(items) for items in selected]
            candidate[index].append(entries[len(selected[index])])
            if _challenge_budget(compose(candidate)):
                selected=candidate;progressed=True
            else:blocked.add(index)
        if not progressed:break
    sections=compose(selected)
    notices=['仅复用网站已查看的各分类默认查询缓存；未采集分类请在网站分别查看。',
             '各分类更新时间独立。']
    if any(len(chosen)<len(entries) for chosen,entries in zip(selected,details)):
        notices.append('明细按各分类本图 / 已观测数量展示；超限部分已省略，完整内容请到网站查看。')
    return view.document('list','endfield','终末地 · 挑战记录',sections=sections,
        subtitle='森空岛档案 · 本人默认角色 · 战争 / 丰碑 / 危机',notices=notices,
        footer='时间均为北京时间')


def overview_document(snapshot, asset_cache=None, *, focus=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    overview = report['overview']; base = overview['base']; stamina = overview['stamina']
    fields = [_metric('理智', stamina, maximum='maximum'), view.time_field('恢复满时间', stamina.get('expected_full_at'))]
    if focus != 'progress':
        fields += [view.field('账号等级', base.get('level')), view.field('探索等级', base.get('world_level'))]
    sections = [_section('森空岛档案 · ' + view.text(base.get('name')), fields=fields, category='ef_overview')]
    if focus != 'stamina':
        tasks = []
        for item in overview['progress']:
            values = [_metric('进度', item, current='cur'), view.field('剩余', item.get('remaining'))]
            tasks.append({'title': view.text(item.get('name')), 'fields': values})
        sections.append(_section('日常与通行证', rows=tasks, layout='rows', category='ef_tasks'))
        todos = overview['todos']
        task_progress = [item for item in overview['progress'] if item['id'] in ('daily', 'weekly')]
        known_ids = {item['id'] for item in task_progress if item['remaining'] is not None}
        empty_status = ('已同步的每日与每周任务已完成' if known_ids == {'daily', 'weekly'} else
                        '已同步任务暂无待办，部分进度未知' if known_ids else '任务进度未知')
        sections.append(_section('已知待办', fields=[view.field(view.text(item.get('name')), '还差 ' + view.text(item.get('remaining')))
                                                   for item in todos] or [view.field('状态', empty_status)], category='ef_todos'))
    if focus is None:
        training = report['training']['summary']; regions = report['regions']['summary']; ship = report['ship']['summary']
        sections.append(_section('干员与建设', fields=[view.field('已采集干员', training.get('listed_count')),
            view.field('平均等级（已知）', training.get('average_level')), view.field('地区', regions.get('region_count')),
            view.field('据点', regions.get('settlement_count')), view.field('舱室', ship.get('room_count')),
            view.field('有驻守的舱室', ship.get('staffed_rooms'))], category='ef_infrastructure'))
    title = '终末地 · 理智' if focus == 'stamina' else '终末地 · 日常进度' if focus == 'progress' else '终末地 · 今日总览'
    return view.document('summary', 'endfield', title, sections=sections, notices=_notice(snapshot),
                         subtitle='森空岛档案 · 本人默认角色', footer=_footer(snapshot, report))


def training_document(snapshot, asset_cache=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    training = report['training']; summary = training['summary']; entries = training['items']
    values = [view.field('已采集干员', summary.get('listed_count')), view.field('账号声明干员数', summary.get('declared_count')),
              view.field('等级已知', summary.get('known_levels')), view.field('平均等级（已知）', summary.get('average_level'))]
    items = []
    for item in entries:
        row = {'title': view.text(item.get('name'),96), 'subtitle': '稀有度 ' + view.text(item.get('rarity')),
               'fields': [view.field('等级', item.get('level')), view.field('精英阶段', item.get('evolve_phase')),
                          view.field('潜能', item.get('potential'))]}
        items.append(view.with_image(row, _image(asset_cache, 'role', item)))
    notices = _notice(snapshot)
    if not items: notices.append(_missing(snapshot, 'operators', '干员'))
    return view.document('list', 'endfield', '终末地 · 全员练度', sections=[_section('练度统计', fields=values, category='ef_training'),
        _section('全部干员 · 等级降序', rows=items, layout='grid', category='ef_roster')], notices=notices,
        subtitle='森空岛档案 · 等级、精英阶段与潜能固定展示', footer=_footer(snapshot, report))


def operator_document(snapshot, name, asset_cache=None, *, detail=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    matches = [item for item in report['training']['items'] if item.get('name') == name]
    if len(matches) != 1:
        explanation = ('缓存存在同名角色，无法确定唯一详情；请在网站核对角色。' if matches else
                       '本人角色缓存中未找到该角色；请核对精确名称或在网站采集。')
        return view.message('endfield', '终末地 · 干员详情', explanation)
    item = matches[0]
    equipment_source=item
    detail_fields=[]
    detail_notice='未找到独立详情缓存，当前配装取自档案快照。'
    if detail is not None:
        cached=view.obj(detail.payload)
        same_id=bool(item.get('id')) and cached.get('id')==item['id']
        if same_id:
            # Basic stats and acquisition time stay anchored to the account observation.
            # Only equipment fields come from this separately-timed detail.
            equipment_source={**item,**{key:cached[key] for key in ('weapon','equipment','skills','tactical_item') if key in cached}}
            # Legacy independent details predate this field. Do not relabel an
            # account-snapshot item with the independent detail's older time.
            equipment_source['tactical_item']=cached.get('tactical_item')
            observed=view.format_time(detail.fetched_at);account_time=view.format_time(snapshot.fetched_at)
            older=observed!='未知' and account_time!='未知' and observed<account_time
            state=('最近读取失败，显示旧详情' if detail.state not in ('ok','success') else
                   '已观测详情；早于当前档案' if older else '已观测详情；非实时状态')
            detail_fields=[view.time_field('档案抓取时间',snapshot.fetched_at),view.time_field('配装抓取时间',detail.fetched_at),
                           view.field('配装状态',state)]
            detail_notice='基础资料与获得时间来自档案；配装来自同一干员的独立详情。'
        elif detail.payload is None:
            detail_fields=[view.field('配装状态','最近读取失败，未取得独立详情'),view.time_field('配装抓取时间',detail.fetched_at)]
            detail_notice='独立详情尚无成功观测；当前配装仍取自档案快照。'
        else:
            detail_notice='独立详情与所选干员标识不匹配，已忽略；当前配装取自档案快照。'
    weapon = view.obj(equipment_source.get('weapon')); gem = view.obj(weapon.get('gem'))
    fields = [view.field(label, item.get(key)) for key, label in (
        ('level', '等级'), ('rarity', '稀有度'), ('evolve_phase', '精英阶段'), ('potential', '潜能'),
        ('profession', '职业'), ('property', '属性'))]
    fields.append(view.time_field('获得时间', item.get('obtained_at')))
    portrait = _image(asset_cache, 'portrait', item)
    # Keep a separately-prefetched small avatar as the portrait failure fallback.
    sections = [view.with_image(_section('干员资料', fields=fields, layout='detail', category='ef_operator'), _image(asset_cache, 'role', item))]
    if detail_fields:sections.append(_section('配装观测来源',fields=detail_fields, category='ef_provenance'))
    if weapon:
        sections.append(view.with_image(_section('武器 · ' + view.text(weapon.get('name')), layout='equipment', fields=[
            view.field('等级', weapon.get('level')), view.field('精炼', weapon.get('refine_level')),
            view.field('突破', weapon.get('breakthrough_level')), view.field('稀有度', weapon.get('rarity'))], category='ef_weapon'),
            _image(asset_cache, 'weapon', weapon)))
    else: sections.append(_section('武器', fields=[view.field('状态', '未采集')], category='ef_weapon'))
    if gem:
        sections.append(view.with_image(_section('基质 · ' + view.text(gem.get('name')), layout='equipment',
            rows=[{'title': view.text(term.get('name')), 'fields': [view.field('原始数值', term.get('cost'))]}
                  for term in view.rows(gem.get('terms'))], category='ef_gem'), _image(asset_cache, 'gem', gem)))
    else: sections.append(_section('基质', fields=[view.field('状态', '未采集')], category='ef_gem'))
    equipment = view.rows(equipment_source.get('equipment')); gear = []
    for key, label in SLOTS.items():
        found = [entry for entry in equipment if entry.get('slot') == key]
        if not found:
            gear.append({'title': label, 'subtitle': '未采集', 'fields': []}); continue
        for entry in found:
            gear.append(view.with_image({'title': view.text(entry.get('name')), 'subtitle': label,
                'fields': [view.field('等级', entry.get('level')), view.field('稀有度', entry.get('rarity'))]},
                _image(asset_cache, 'equipment', entry)))
    # Unfamiliar saved slots remain visible after the four known assembly slots.
    # Their names/artwork cannot be discarded or assigned to a guessed position.
    for entry in equipment:
        if entry.get('slot') not in SLOTS:
            gear.append(view.with_image({'title': view.text(entry.get('name')),
                'subtitle': '槽位 · '+view.text(entry.get('slot')),
                'fields': [view.field('等级', entry.get('level')), view.field('稀有度', entry.get('rarity'))]},
                _image(asset_cache, 'equipment', entry)))
    sections.append(_section('四件装备', rows=gear, layout='equipment', category='ef_equipment'))
    skills = view.rows(equipment_source.get('skills'))
    sections.append(_section('技能', layout='skills', rows=[view.with_image({'title': view.text(skill.get('name')),
        'fields': [view.field('等级', skill.get('level'))]+([view.field('专精',skill['mastery'])] if skill.get('mastery') is not None else [])}, _image(asset_cache, 'skill', skill)) for skill in skills],
        fields=[] if skills else [view.field('状态', '未采集')], category='ef_skills'))
    tactical=view.obj(equipment_source.get('tactical_item'))
    tactical_clipped=False
    if tactical:
        fields=[view.field('稀有度',tactical.get('rarity'))]
        for key,label in (('active_effect','主动效果'),('passive_effect','被动效果')):
            raw=tactical.get(key)
            effect=view.text(_tactical_effect_text(raw),641) if isinstance(raw,str) and raw.strip() else '未采集'
            tactical_clipped=tactical_clipped or len(effect)>640
            effect=effect[:640]
            for index in range(0,len(effect),160):
                fields.append({'label':label+(' · 续 '+str(index//160+1) if index else ''),'value':effect[index:index+160]})
        sections.append(view.with_image(_section('战术道具 · '+view.text(tactical.get('name')),fields=fields,
            category='ef_tactical'),_image(asset_cache,'tactical',tactical)))
    else:
        sections.append(_section('战术道具',fields=[view.field('状态','未采集')],category='ef_tactical'))
    notices=[view.metadata(snapshot)[0]['value'],
        '部分部位暂无配装数据。',detail_notice]
    if tactical:
        notices[1]+='战术效果保留原文与参数。'+('过长效果已省略尾部，完整内容请到网站查看。' if tactical_clipped else '')
    card = view.document('detail', 'endfield', '终末地 · ' + view.text(name), sections=sections,
        notices=notices,
        subtitle='森空岛档案 · 干员与已观测配装', footer=_footer(snapshot, report))
    return view.with_image(card, portrait)


def regions_document(snapshot, asset_cache=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    regions = report['regions']; sections = [_section('地区建设概况', fields=[
        view.field('地区', regions['summary'].get('region_count')), view.field('据点', regions['summary'].get('settlement_count'))], category='ef_regions')]
    for region in regions['items']:
        fields = [view.field('地区等级', region.get('level')), _metric('总调度券', view.obj(region.get('money')))]
        settlement_rows = []
        for settlement in view.rows(region.get('settlements')):
            officers = view.rows(settlement.get('officers'))
            names = '、'.join(view.text(officer.get('name') or officer.get('id')) for officer in officers)
            values = [view.field('据点等级', settlement.get('level')), _metric('基地调度券', view.obj(settlement.get('coupon'))),
                      view.field('派驻干员', names or ('无派驻' if settlement.get('officers_available') is True else '未知'))]
            settlement_rows.append({'title': view.text(settlement.get('name')), 'fields': values})
        sections.append(_section(view.text(region.get('name')) + ' · 据点', fields=fields, rows=settlement_rows, layout='rows', category='ef_settlements'))
        areas = []
        for area in view.rows(region.get('areas')):
            values = []
            for collection in view.rows(area.get('collections')):
                value = _metric(view.text(collection.get('label')), collection)
                if collection.get('remaining') is not None:
                    value['value'] += ' · 缺 ' + view.text(collection['remaining'])
                values.append(value)
            areas.append({'title': view.text(area.get('name') or area.get('id')), 'fields': values})
        if areas: sections.append(_section(view.text(region.get('name')) + ' · 收集', rows=areas, layout='rows', category='ef_collections'))
    notices = _notice(snapshot)
    if not regions['items']: notices.append(_missing(snapshot, 'regions', '地区'))
    return view.document('list', 'endfield', '终末地 · 地区建设', sections=sections, notices=notices,
        subtitle='森空岛档案 · 调度券、派驻与收集差额', footer=_footer(snapshot, report))


def ship_document(snapshot, asset_cache=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    ship = report['ship']; summary = ship['summary']
    sections = [_section('帝江号概况', fields=[view.field('舱室', summary.get('room_count')),
        view.field('有驻守的舱室', summary.get('staffed_rooms')), view.field('已采集驻守人次', summary.get('operator_slots'))], category='ef_ship')]
    for room in ship['rooms']:
        operators = view.rows(room.get('operators'))
        items = [view.with_image({'title': view.text(item.get('name') or item.get('id')), 'fields': [
            _percent_field('心情',item.get('mood_percent'),100),_percent_field('信赖',item.get('trust_percent'),200),
            view.field('信赖阶段',item.get('trust_level_name')),
            view.field('心情原始值', item.get('mood_raw')), view.field('信赖原始值', item.get('trust_raw'))]},
            _image(asset_cache, 'role', item)) for item in operators]
        sections.append(_section(view.text(room.get('name')), fields=[view.field('舱室等级', room.get('level'))] +
            ([] if operators else [view.field('驻守', '无驻守' if room.get('operators_available') is True else '未采集')]), rows=items, layout='rows', category='ef_room'))
    notices = _notice(snapshot) + ['心情与信赖为抓取时的记录值。']
    if not ship['rooms']: notices.append(_missing(snapshot, 'ship', '舱室'))
    return view.document('list', 'endfield', '终末地 · 帝江号', sections=sections, notices=notices,
        subtitle='森空岛档案 · 舱室与驻守', footer=_footer(snapshot, report))


def _percent_field(label,value,maximum):
    from math import floor
    number=view.number(value)
    if number is not None and number>maximum:number=None
    display='未知' if number is None else f'{floor(number*10+0.5)/10:g}%'
    return {'label':label,'value':display,'metric':{'current':number,'maximum':maximum}}


def _honor_budget(sections):
    """Bound category grids before normalization, including future cached art."""
    from math import ceil
    fields=rows=characters=0;height=900;encoded=60000
    if len(sections)>34:return False
    for section in sections:
        characters+=len(section['title'])+8
        fields+=len(section['fields'])
        characters+=sum(len(item['label'])+len(item['value'])+8 for item in section['fields'])
        height+=160+ceil(len(section['fields'])/2)*125
        entries=section['rows'];rows+=len(entries)
        fields+=sum(len(row['fields']) for row in entries)
        characters+=sum(len(row['title'])+len(row.get('subtitle',''))+12+
                        sum(len(item['label'])+len(item['value'])+8 for item in row['fields']) for row in entries)
        if not entries:continue
        columns=min(4,len(entries));cell=(972-16*(columns-1))//columns
        encoded+=sum(6000 if row.get('image') else 1800 for row in entries)
        for index in range(0,len(entries),columns):
            group=entries[index:index+columns]
            header=max(max(88 if row.get('image') else 0,
                ceil(len(row['title'])*24/(cell-112 if row.get('image') else cell-28))*32) for row in group)
            height+=50+header+sum(max(ceil((len(row['fields'][slot]['label'])+len(row['fields'][slot]['value'])+1)*22/(cell-28))*30
                                      for row in group) for slot in range(3))
    return fields<=350 and rows<=250 and characters<=21000 and height<=12000 and encoded<=460000


def honor_document(snapshot, asset_cache=None):
    report = build_endfield_report(view.obj(snapshot.payload), fetched_at=snapshot.fetched_at)
    honor = report['honor']; summary = honor['summary']
    groups={}
    for medal in honor['items']:
        category=medal.get('category')
        category=category.strip() if isinstance(category,str) and category.strip() else '分类未知'
        row=view.with_image({'title':view.text(medal.get('name') or medal.get('id'),64),
            'fields':[view.field('等级',medal.get('level')),view.field('镀层',medal.get('is_plated')),
                      view.time_field('获得时间',medal.get('obtained_at'))]},_image(asset_cache,'medal',medal))
        groups.setdefault(category,[]).append(row)
    # Statistics are always ahead of detail grids. A hard category cap is
    # explicitly reported; missing categories are never described as complete.
    displayed=list(groups.items())[:16];counts=[0]*len(displayed)

    def compose(allocated):
        sections=[_section('勋章概况',fields=[view.field('账号声明勋章数',summary.get('declared_count')),
            view.field('已采集勋章',summary.get('listed_count')),
            view.field('已观测分类',len(groups) if honor['available'] is True else None),
            view.field('本图分类',str(len(displayed))+' / '+str(len(groups)) if honor['available'] is True else '未知'),
            view.field('本图勋章',str(sum(allocated))+' / '+view.text(summary.get('listed_count')) if honor['available'] is True else '未知')],category='ef_honor')]
        if displayed:
            sections.append(_section('分类覆盖 · 本图 / 已采集',fields=[
                view.field(name,str(count)+' / '+str(len(entries))) for (name,entries),count in zip(displayed,allocated)],
                category='ef_honor_groups'))
        sections.extend(_section(view.text(name,72)+' · '+str(count)+' / '+str(len(entries)),rows=entries[:count],
            layout='grid',category='ef_medals') for (name,entries),count in zip(displayed,allocated) if count)
        return sections

    while True:
        candidate=[min(count+1,len(entries)) for count,(_,entries) in zip(counts,displayed)]
        if candidate==counts or not _honor_budget(compose(candidate)):break
        counts=candidate
    notices=_notice(snapshot)+['仅展示已同步勋章。']
    clipped=len(displayed)<len(groups) or any(count<len(entries) for count,(_,entries) in zip(counts,displayed))
    if clipped:
        notices.append('本图分类 '+str(len(displayed))+' / '+str(len(groups))+'；各类按覆盖数量展示，超限勋章或分类已省略，完整内容请到网站查看。')
    if not groups:
        notices.append('本次成功快照的勋章列表为空。' if honor.get('available') is True else '勋章尚未采集；请在网站采集后查询。')
    return view.document('list','endfield','终末地 · 光荣之路',sections=compose(counts),notices=notices,
        subtitle='森空岛档案 · 按已观测分类整理',footer=_footer(snapshot,report))


def _boundary(count, status):
    if status not in ('exact', 'lower_bound') or count is None: return '未知'
    return ('至少 ' if status == 'lower_bound' else '') + view.text(count)


def _gacha_budget(sections):
    """Reserve readable four-column rows within the existing card limits.

    A conservative text measurement also reserves space for images that may be
    prefetched later. Whole rounds preserve fair coverage across all pools.
    """
    from math import ceil
    fields=rows=characters=0; height=1000; encoded_reserve=60000
    for section in sections:
        characters+=len(section['title'])+8
        height+=140
        for field in section['fields']:
            fields+=1;characters+=len(field['label'])+len(field['value'])+8
        height+=ceil(len(section['fields'])/3)*130
        entries=section['rows'];rows+=len(entries)
        for row in entries:
            characters+=len(row['title'])+len(row.get('subtitle',''))+12
            for field in row['fields']:
                fields+=1;characters+=len(field['label'])+len(field['value'])+8
        if section.get('category')=='ef_gacha_pools':
            height+=len(entries)*400
            encoded_reserve+=len(entries)*16000
        else:
            # A catalog thumbnail can arrive after document preparation. Reserve
            # its entropy even before prefetch, while text-only rows stay cheap.
            encoded_reserve+=sum(4500 if row.get('image') else 1500 for row in entries)
            for index in range(0,len(entries),4):
                group=entries[index:index+4]
                header=max(max(88,ceil(len(row['title'])/4)*32+ceil(len(row.get('subtitle',''))/4)*30) for row in group)
                height+=header+230
    return fields<=350 and rows<=250 and characters<=21000 and height<=13700 and encoded_reserve<=480000


def gacha_document(snapshot, asset_cache=None, *, compact=False):
    report = build_gacha_report(view.obj(snapshot.payload))
    fields = [view.field(label, report.get(key)) for key, label in (
        ('total', '已记录抽数'), ('six_star', '6 星'), ('five_star', '5 星'), ('free', '免费抽'),
        ('gaps', '已知缺口'), ('average_exact_pulls', '报告准确区间均抽'))]
    fields += [view.field('准确区间样本数', report.get('known_exact_intervals'))]
    fields += [view.field('同步状态', '无待续传记录' if report.get('complete') is True else
                         '仍有待续传记录' if report.get('complete') is False else '未知')]
    state=('账本缓存 · 最近查询成功' if snapshot.state in ('ok','success') else
           '最近查询失败或待刷新，显示已保存账本' if snapshot.state not in ('unknown','never') else
           '同步状态未确认，显示已保存账本')
    sections = [_section('鹰角寻访 · 本人账本', fields=fields + [view.field('数据状态',state),
        view.time_field('最新成功扫描',snapshot.fetched_at)], category='ef_gacha')]
    # Pool summaries precede every historical row; no early pool can consume a
    # later pool's statistics. More than 16 pools is an explicit resource cut.
    pools=report['pools'][:16];counts=[0]*len(pools);summaries=[];histories=[]
    for pool in pools:
        pity = view.obj(pool.get('since_last_six'))
        status='待续传' if pool.get('pending') is True else '无待续传' if pool.get('pending') is False else '未知'
        values=[view.field('已记录抽数',pool.get('total')),
            view.field('稀有度',' / '.join(label+' '+view.text(pool.get(key)) for key,label in
                (('six_star','6★'),('five_star','5★'),('four_star','4★'),('unknown_rarity','其他或未知')))),
            view.field('免费抽',pool.get('free')),
            view.field('距上次 6 星',_boundary(pity.get('count'),pity.get('status'))),
            view.field('扫描与缺口',status+' · 缺口 '+view.text(pool.get('gaps'))),
            view.field('账本时间范围',view.format_time(pool.get('oldest_at'))+' 至 '+view.format_time(pool.get('newest_at'))),
            view.time_field('本池成功扫描',pool.get('last_sync_at')),view.field('6 星覆盖','待分配')]
        summaries.append({'title':view.text(pool.get('label') or pool.get('key')), 'fields':values})
        entries = []
        if not compact:
            for item in view.rows(pool.get('history')):
                entries.append(view.with_image({'title': view.text(item.get('name'),40),
                    'subtitle':view.text(item['pool_name'],64) if item.get('pool_name') else '', 'fields': [
                    view.field('该次 6 星抽数', _boundary(item.get('pulls'), item.get('status'))+' · '+
                        {'exact':'记录内准确','lower_bound':'记录下限'}.get(item.get('status'),'边界未知')),
                    view.time_field('获取时间', item.get('obtained_at'))]}, _image(asset_cache,
                        'weapon' if pool.get('kind') == 'weapon' else 'role', item)))
        histories.append(entries)

    def compose(allocated):
        for index,(pool,row) in enumerate(zip(pools,summaries)):
            value='本图 '+str(allocated[index])+' / 报告 '+str(pool['history_available'])+' / 账本 '+view.text(pool['history_total'])
            if pool['history_limit'] is not None:value+=' · 报告上限 '+view.text(pool['history_limit'])
            if allocated[index]<pool['history_available'] or pool['history_truncated'] is True:value+=' · 有省略'
            row['fields'][-1]=view.field('6 星覆盖',value)
        output=sections+([_section('各卡池统计 · 全部优先',rows=summaries,layout='rows',category='ef_gacha_pools')] if summaries else [])
        return output+[_section(summaries[index]['title']+' · 最近 6 星',rows=histories[index][:count],layout='grid',category='ef_gacha_pool')
                       for index,count in enumerate(allocated) if count]

    if not compact:
        while True:
            candidate=[min(count+1,len(entries)) for count,entries in zip(counts,histories)]
            if candidate==counts or not _gacha_budget(compose(candidate)):break
            counts=candidate
    sections=compose(counts)
    notices = [state, '仅统计已同步的寻访记录。',
               '均抽来自报告中准确区间，不随图片裁减重算；免费抽与缺口不当作确定垫抽。']
    gifts = sum(pool.get('gifts') or 0 for pool in report['pools'])
    unverified = sum(pool.get('unverified_records') or 0 for pool in report['pools'])
    if gifts:
        notices.append(f'另有 {gifts} 条额外奖励保留在网站明细中，不计抽数、出货和垫抽。')
    if unverified:
        notices.append(f'另有 {unverified} 条旧武器记录缺少奖励类型，暂不计入统计；超出官方查询期限的原记录仍会保留。')
    clipped=len(pools)<len(report['pools']) or any(count<len(entries) for count,entries in zip(counts,histories))
    if clipped or any(pool['history_truncated'] is True for pool in pools):
        notices.append('6 星明细按各池覆盖数展示；更早或超限内容已省略，完整逐抽请到网站查看或导出。')
    if len(pools)<len(report['pools']):
        notices[-1]='本图卡池 '+str(len(pools))+' / '+str(len(report['pools']))+'；'+notices[-1]
    if not report['pools']:
        notices.append('本次账本记录为空。' if report.get('total') == 0 else '暂无已采集寻访记录；请在网站同步本人记录。')
    return view.document('list', 'endfield', '终末地 · 寻访战报', sections=sections, notices=notices,
        subtitle='鹰角寻访授权 · 与森空岛档案独立', footer=_footer(snapshot))
