"""Source-faithful activity selection; all timestamps use Beijing boundaries.

Only explicit instants take part in countdown/current filtering. Day precision
is displayed as dates; relative starts never become midnight intervals.
"""
from datetime import datetime, timedelta
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
    if side:fields.append(view.field('剩余时间',remaining(endpoint(item,side),now)))
    source=' · '.join(str(item[k]) for k in ('source_name','source_title') if item.get(k))
    if not source:source={'official':'官网','community':'官方社区','bilibili':'官方 B站'}.get(item.get('source'),'来源未提供')
    fields.append(view.field('来源',source))
    if stale or item.get('source_stale'):fields.append(view.field('来源状态','陈旧快照；等待刷新'))
    row={'title':view.text(item['display_title'],90),'subtitle':GAME_NAMES[game],'fields':fields}
    return view.with_image(row,view.image_ref(cache,game,'event',None,item.get('cover_url') or item.get('image_url')))


def event_document(command,snapshots,*,now=None,asset_cache=None):
    now=(now or datetime.now(view.BEIJING)).astimezone(view.BEIJING)
    start=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    end=(start.replace(year=start.year+1,month=1) if start.month==12 else start.replace(month=start.month+1))
    window=now+timedelta(hours=168);sections=[];uncertain=[];states=[]
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
                for side,stamp,bucket in (('end',last,ending),('start',first,starting)):
                    if not invalid and stamp is not None and now<stamp<=window:
                        bucket.append((game,stamp,event_row(game,item,now,side=side,stale=stale,cache=asset_cache)))
                # An absent endpoint alone is not necessarily a pending activity;
                # expose explicit imprecision/relative descriptions instead.
                if invalid or any(endpoint(item,side) is None and (item.get(side+'_text') or item.get(side+'_date') or item.get(side+'_precision') in ('relative','day','dependent','unknown')) for side in ('start','end')):
                    uncertain.append(row)
            elif command=='events':
                if not invalid and first is not None and last is not None and first<=now<last:
                    groups.setdefault(item.get('category') or '其他活动',[]).append(row)
                elif uncertain_time and not (last and last<=now or first and first>now):uncertain.append(row)
            else:
                a=first.date() if first else day(item.get('start_at') or item.get('start_date'))
                b=last.date() if last else day(item.get('end_at') or item.get('end_date'))
                relative=any(item.get(k) in ('relative','dependent','unknown') for k in ('start_precision','end_precision'))
                if invalid or a is None or b is None or relative or b<a:
                    uncertain.append(row);continue
                # A date-only end is inclusive. A midnight exact end is exclusive.
                b_exclusive=b if last and last.hour==0 and last.minute==0 else b+timedelta(days=1)
                if b_exclusive<=a:
                    uncertain.append(row);continue
                if b_exclusive<=start.date() or a>=end.date():continue
                row['timeline']={'start':max(a,start.date()).isoformat(),'end':min(b_exclusive,end.date()).isoformat(),
                    'precision':'minute' if first and last else 'day','continues_before':a<start.date(),'continues_after':b_exclusive>end.date()}
                groups.setdefault(item.get('category') or '其他活动',[]).append(row)
        for category,items in groups.items():
            sections.append({'title':GAME_NAMES[game]+' · '+category,'game':game,'category':view.text(category),'layout':'timeline' if command=='calendar' else 'rows','rows':items})
        if command=='events' and not groups:states[-1]['fields'].append(view.field('当前活动','无已确认正在进行的活动'))
    if command=='recent_events':
        sections=[{'title':title,'layout':'rows','rows':[r for _,_,r in sorted(items,key=lambda x:(list(GAME_NAMES).index(x[0]),x[1]))],
                   'fields':[] if items else [view.field('结果','未来168小时内无已确认'+title+'活动')]} for title,items in (('即将结束',ending),('即将开始',starting))]
    if uncertain:sections.append({'title':'时间待确认','layout':'rows','rows':uncertain})
    sections.append({'title':'公共快照状态','layout':'rows','rows':states})
    title={'recent_events':'近期活动','events':'进行中的活动','calendar':'活动日历'}[command]
    card=view.document('calendar' if command=='calendar' else 'list',next(iter(snapshots)) if len(snapshots)==1 else 'all',title,sections=sections,
        subtitle='公共活动缓存 · 北京时间',notices=['时间待确认项保留来源精度，不推算精确倒计时。'],footer='计算时间：'+now.strftime('%Y-%m-%d %H:%M'))
    card['version']=3
    if command=='calendar':card['timeline']={'start':start.date().isoformat(),'end':end.date().isoformat(),'today':now.date().isoformat(),'timezone':'Asia/Shanghai'}
    return card
