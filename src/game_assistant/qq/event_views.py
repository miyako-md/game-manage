"""Source-faithful activity selection; all timestamps use Beijing boundaries.

Only explicit instants take part in countdown/current filtering. Day precision
is displayed as dates; relative starts never become midnight intervals.
"""
from datetime import datetime, time, timedelta
import re

from .commands import GAME_NAMES
from . import presentation as view


def moment(value):
    if not isinstance(value,(str,datetime)) or isinstance(value,str) and not re.search(r'[T ]\d{2}:\d{2}',value):
        return None
    try:
        stamp=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
        return stamp.replace(tzinfo=view.BEIJING) if stamp.tzinfo is None else stamp.astimezone(view.BEIJING)
    except (ValueError,TypeError):return None


def day(value):
    if not isinstance(value,str):return None
    try:return datetime.strptime(value[:10],'%Y-%m-%d').date()
    except ValueError:return None


def endpoint(item,side):
    raw=item.get(side+'_at')
    precision=item.get(side+'_precision')
    instant=moment(raw)
    if precision in ('relative','dependent','unknown'):return None
    if precision=='day':return None
    # version_end is supplied only after a real next-maintenance announcement
    # resolves end_at in the existing public source parser.
    return instant if precision in (None,'minute','version_end') else None


# 近期活动 lists what starts or ends within this many hours of the request.
RECENT_HOURS=72


def window_endpoint(item,side):
    """Boundary for the recent list: a day-precision start counts from 00:00
    and a day-precision end until 23:59:59 of that Beijing day."""
    stamp=endpoint(item,side)
    if stamp is not None or item.get(side+'_precision') not in (None,'day'):return stamp
    date=day(item.get(side+'_at') or item.get(side+'_date'))
    return None if date is None else datetime.combine(date,time(23,59,59) if side=='end' else time(),view.BEIJING)


def recent_window(item,now,hours=RECENT_HOURS):
    """Sides whose boundary lies in [now, now+hours], and whether the item only
    has unconfirmed (relative/dependent/unknown) times that may still matter."""
    limit=now+timedelta(hours=hours)
    first,last=window_endpoint(item,'start'),window_endpoint(item,'end')
    invalid=first is not None and last is not None and last<first
    sides=() if invalid else tuple(side for side,stamp in (('start',first),('end',last)) if stamp is not None and now<=stamp<=limit)
    def unconfirmed(side,stamp):
        # A vague boundary may still fall in the window unless its source date rules that out.
        if stamp is not None or not (item.get(side+'_text') or item.get(side+'_date') or item.get(side+'_at') or item.get(side+'_precision') in ('relative','dependent','unknown')):return False
        date=day(item.get(side+'_at') or item.get(side+'_date'))
        return date is None or now.astimezone(view.BEIJING).date()<=date<=limit.astimezone(view.BEIJING).date()
    unresolved=invalid or unconfirmed('start',first) or unconfirmed('end',last)
    pending=not sides and unresolved and not (last is not None and last<now) and not (first is not None and first>limit)
    return sides,pending


def boundary_text(item,side):
    raw=item.get(side+'_at');precision=item.get(side+'_precision')
    stamp=endpoint(item,side)
    if stamp:
        label=stamp.strftime('%Y-%m-%d %H:%M')
        if precision=='version_end':label+=' · '+view.text(item.get(side+'_text') or '维护前')
        return label
    date=day(raw or item.get(side+'_date'))
    detail=item.get(side+'_text')
    if precision=='relative':return (date.isoformat()+' · ' if date else '')+view.text(detail or '相对时间，时刻待确认')
    if date:return date.isoformat()+' · 时刻未确认'
    return view.text(detail or '未知')


def remaining(stamp,now):
    minutes=max(0,int((stamp-now).total_seconds()//60))
    days,rest=divmod(minutes,1440);hours,mins=divmod(rest,60)
    return ((str(days)+'天') if days else '')+((str(hours)+'小时') if hours else '')+((str(mins)+'分钟') if mins or not days and not hours else '')


def normalized(payload):
    entries=view.rows(payload) if isinstance(payload,list) else view.rows(view.obj(payload).get('events'))
    seen=set();output=[]
    for original in entries:
        phases=view.rows(original.get('phases')) or [original]
        for index,phase in enumerate(phases):
            item={**original,**phase};item.pop('phases',None)
            title=item.get('name') or item.get('title')
            if not title:continue
            if len(phases)>1:title=str(title)+' · 阶段 '+str(index+1)
            item['display_title']=title
            key=(str(title),item.get('category'),item.get('start_at'),item.get('start_date'),item.get('end_at'),item.get('end_date'),item.get('start_text'),item.get('end_text'))
            if key in seen:continue
            seen.add(key);output.append(item)
    return output


def event_row(game,item,now,*,side=None,stale=False,cache=None):
    fields=[view.field('类别',item.get('category') or '其他活动'),view.field('开始',boundary_text(item,'start')),view.field('截止',boundary_text(item,'end'))]
    if side:fields.append(view.field('剩余时间',remaining(window_endpoint(item,side),now)))
    source=' · '.join(str(item[k]) for k in ('source_name','source_title') if item.get(k))
    if not source:source={'official':'官网','community':'官方社区','bilibili':'官方 B站'}.get(item.get('source'),'来源未提供')
    fields.append(view.field('来源',source))
    if stale or item.get('source_stale'):fields.append(view.field('来源状态','陈旧快照；等待刷新'))
    row={'title':view.text(item['display_title'],90),'subtitle':GAME_NAMES[game],'fields':fields}
    return view.with_image(row,view.image_ref(cache,game,'event',None,item.get('cover_url') or item.get('image_url')))


def event_document(command,snapshots,*,now=None,asset_cache=None):
    now=(now or datetime.now(view.BEIJING)).astimezone(view.BEIJING)
    if command == 'calendar':
        return version_document(snapshots, now=now, asset_cache=asset_cache)
    sections=[];uncertain=[];states=[]
    ending=[];starting=[]
    for game,snapshot in snapshots.items():
        states.append({'title':GAME_NAMES[game],'fields':view.metadata(snapshot)})
        if snapshot.payload is None:continue
        entries=normalized(snapshot.payload)
        stale=getattr(snapshot,'stale',None)
        if type(stale) is not bool:stale=snapshot.state not in ('ok','success')
        if not entries:states[-1]['fields'].append(view.field('活动列表','成功快照：当前列表为空'))
        groups={}
        for item in entries:
            first,last=endpoint(item,'start'),endpoint(item,'end')
            # Invalid source bounds cannot be called current or drawn.
            invalid=first is not None and last is not None and last<=first
            row=event_row(game,item,now,stale=stale,cache=asset_cache)
            uncertain_time=invalid or first is None or last is None
            if command=='recent_events':
                sides,pending=recent_window(item,now)
                for side,bucket in (('start',starting),('end',ending)):
                    if side in sides:bucket.append((game,window_endpoint(item,side),event_row(game,item,now,side=side,stale=stale,cache=asset_cache)))
                # An absent endpoint alone is not necessarily a pending activity;
                # expose explicit imprecision/relative descriptions instead.
                if pending:uncertain.append(row)
            elif command=='events':
                if not invalid and first is not None and last is not None and first<=now<last:
                    groups.setdefault(item.get('category') or '其他活动',[]).append(row)
                elif uncertain_time and not (last and last<=now or first and first>now):uncertain.append(row)
        for category,items in groups.items():
            sections.append({'title':GAME_NAMES[game]+' · '+category,'game':game,'category':view.text(category),'layout':'rows','rows':items})
        if command=='events' and not groups:states[-1]['fields'].append(view.field('当前活动','无已确认正在进行的活动'))
    if command=='recent_events':
        sections=[{'title':title,'layout':'rows','rows':[r for _,_,r in sorted(items,key=lambda x:(list(GAME_NAMES).index(x[0]),x[1]))],
                   'fields':[] if items else [view.field('结果','未来 '+str(RECENT_HOURS)+' 小时内没有'+title[-2:]+'的活动')]}
                  for title,items in ((str(RECENT_HOURS)+' 小时内开始',starting),(str(RECENT_HOURS)+' 小时内结束',ending))]
    if uncertain:sections.append({'title':'时间待确认','layout':'rows','rows':uncertain})
    sections.append({'title':'公共快照状态','layout':'rows','rows':states})
    title={'recent_events':'近期活动 · 未来 '+str(RECENT_HOURS)+' 小时','events':'进行中的活动'}[command]
    card=view.document('list',next(iter(snapshots)) if len(snapshots)==1 else 'all',title,sections=sections,
        subtitle='公共活动缓存 · 北京时间',notices=['时间待确认项保留来源精度，不推算精确倒计时。'],footer='计算时间：'+now.strftime('%Y-%m-%d %H:%M'))
    card['version']=3
    return card


def version_document(snapshots, *, now, asset_cache=None):
    """Each game's version is independent; unknown boundaries never form an axis."""
    from game_assistant.version_calendar import snapshot_version, select_version_events
    sections = []
    states = []
    for game, snapshot in snapshots.items():
        entries = normalized(snapshot.payload)
        stale = getattr(snapshot, 'stale', snapshot.state not in ('ok', 'success'))
        meta = snapshot_version(game, entries, metadata=getattr(snapshot, 'version_metadata', None),
                                version=getattr(snapshot, 'version', None), stale=stale, now=now)
        entries = select_version_events(entries, meta)
        ident = meta.get('id')
        scope = ('当前版本 '+str(ident) if meta.get('status') == 'current' else
                 '来源版本 '+str(ident)+' · 当前性待核验' if ident else '版本未确认 · 已知活动汇总')
        if meta.get('status') == 'historical':
            scope = '历史/陈旧来源版本 '+str(ident)
        fields = [view.field('范围', scope), view.field('覆盖', '已公布活动汇总 · 覆盖待核验'),
                  view.field('版本开放', meta.get('start_date') or '未知'),
                  view.field('版本结束', meta.get('end_at') or meta.get('end_date') or '未知')]
        fields += [view.field('来源诊断', detail) for detail in meta.get('diagnostics', [])]
        output = []
        for item in entries:
            row = event_row(game, item, now, stale=stale, cache=asset_cache)
            first, last = endpoint(item, 'start'), endpoint(item, 'end')
            state = ('日期异常' if first and last and last < first else
                     '已结束' if last and last <= now else '未开始' if first and first > now else
                     '进行中' if first and last else '时间待确认')
            row['fields'].append(view.field('状态', state))
            if item.get('version'):
                row['fields'].append(view.field('归属版本', str(item['version'])+(' · 跨版本持续，与当前版本相交' if item.get('cross_version') else '')))
            if item.get('phase'):
                row['fields'].append(view.field('活动阶段', item['phase']))
            output.append(row)
        if not output:
            fields.append(view.field('活动列表', '当前无可用条目；请查看快照与来源诊断'))
        sections.append(dict(title=GAME_NAMES[game]+' · '+scope, game=game, layout='rows', fields=fields, rows=output))
        states.append(dict(title=GAME_NAMES[game], fields=view.metadata(snapshot)))
    sections.append(dict(title='公共快照状态', layout='rows', rows=states))
    card = view.document('list', next(iter(snapshots)) if len(snapshots)==1 else 'all', '版本活动日历',
        sections=sections, subtitle='各游戏独立版本 · 已结束、进行中与未来活动 · 北京时间',
        notices=['未知版本仅展示已公布的活动。'],
        footer='计算时间：'+now.strftime('%Y-%m-%d %H:%M'))
    card['version'] = 3
    return card
