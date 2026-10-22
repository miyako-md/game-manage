"""Public guide catalogs plus a cache-only overlay of the shared guide checks; no account or upstream access."""
from functools import lru_cache
import json
from pathlib import Path
import sqlite3
from . import render_snapshot as shared
from . import presentation as view
from .assets import safe_public_url

ENDFIELD_TEXT='暂未收录可核验的终末地角色攻略；可在 B 站搜索 猫冬MT「终末地攻略合集」。'
DRAFT_MARK='自动提炼·待校对'
WUWA_TITLES={'weapons':'武器推荐','teams':'配队推荐','echo_sets':'声骸配装','echo_stats':'声骸词条','skill_priority':'技能加点优先级'}
# The extractor keeps at most this many image references of a post.
WUWA_IMAGE_LIMIT=10
# Section → public icon buckets, as tokenizeGuide (wuwa-icons.js) matches them.
WUWA_ICON_BUCKETS={'weapons':('weapon',),'teams':('role',),'echo_sets':('set','echo'),'echo_stats':('stat',)}
WUWA_HINT_LIMIT=48
CACHE_ERRORS=(AttributeError,KeyError,TypeError,ValueError,sqlite3.Error)

@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('role_guides.json').read_text(encoding='utf-8'))

class GuideSources:
    """The shared guide services, read only through their synchronous cache methods.

    Live state is read on every reply (never cached here); a missing service or
    contract method keeps the static catalog reply unchanged.
    """
    def __init__(self,wuwa=None,nte=None):
        self.wuwa,self.nte=wuwa,nte

    def wuwa_state(self,character_id):
        reader=getattr(self.wuwa,'cached_by_id',None)
        if reader is None:return None
        try:value=reader(str(character_id))
        except CACHE_ERRORS:return None
        return value if isinstance(value,dict) else None

    def nte_state(self,post_id):
        reader=getattr(self.nte,'status',None)
        if reader is None or type(post_id) is not int:return None
        try:
            status=reader(post_id)
            if not isinstance(status,dict):return None
            cached=self.nte.cached(post_id) if hasattr(self.nte,'cached') else None
        except CACHE_ERRORS:return None
        images=cached.get('images') if isinstance(cached,dict) else None
        return {**status,'image_count':len(images) if isinstance(images,list) else None}

def _pending(character_id,state):
    from game_assistant.guide_jobs import pending_candidate
    candidates=state.get('candidates')
    return pending_candidate(character_id,{**state,'candidates':[c for c in candidates if isinstance(c,dict)] if isinstance(candidates,list) else []})

def _roster():
    from game_assistant.guide_jobs import guide_roster
    return guide_roster()

def _guide(row):
    fields=('id','name','game','attribute','element','role','status','image','aliases')
    guide={key:row[key] for key in fields if key in row}
    guide['asset_hints']=[url for url in row.get('asset_hints',[]) if safe_public_url(url)]
    # A missing version stays null: str(None) printed "VNone" in the image.
    guide['sources']=[{key:(str(source[key]) if key=='id' else None if source[key] is None else shared.display_text(source[key])) for key in ('id','title','author','version','url') if key in source} for source in row.get('sources',[])]
    guide['sections']=[{key:(str(section[key]) if key=='sourceId' else shared.display_text(section[key])) for key in ('key','title','text','note','sourceId') if key in section} for section in row.get('sections',[])]
    return guide

def _live_row(base,live):
    """A stored extraction projected onto the static entry shape (titles as the website names them)."""
    titles={s.get('key'):s.get('title') for s in base.get('sections',[])}
    sections=[{key:s[key] for key in ('key','text','note','sourceId') if isinstance(s.get(key),str)}|{'title':titles.get(s.get('key')) or WUWA_TITLES.get(s.get('key'),'培养建议')}
              for s in live['sections'] if isinstance(s,dict)]
    sources=[{key:s.get(key) for key in ('id','title','author','version','url')} for s in live['sources'] if isinstance(s,dict)]
    return {**base,'sources':sources,'sections':sections}

def _reviewed(live):
    return isinstance(live,dict) and isinstance(live.get('sections'),list) and len(live['sections'])==5 and all(isinstance(s,dict) and s.get('status')=='reviewed' for s in live['sections'])

def _usable(live,character_id):
    return isinstance(live,dict) and str(live.get('id'))==str(character_id) and isinstance(live.get('sections'),list) and isinstance(live.get('sources'),list)

def _checked(value):
    text=view.format_time(value)
    return None if text=='未知' else text

def _wuwa_hints(guide):
    """Icon URLs the page's tokenizer can show for live text: a superset by name, never by position.

    Static entries carry hints exported with the catalog; live extractions get them here from the
    public icon catalog and the exported aliases, so their QQ image matches the website.
    """
    from .public_asset_catalog import CATALOG
    icons=CATALOG['games']['wuthering_waves'];aliases=(catalog().get('wuwa_guide_aliases') or {}).get('sections',{})
    urls=[guide.get('image')]
    for section in guide['sections']:
        key,text=section.get('key'),section.get('text') or ''
        if key=='skill_priority':
            prefix=str(guide['id'])+'::'
            urls+=[url for name,url in icons.get('skill',{}).items() if name.startswith(prefix)]
            continue
        for bucket in WUWA_ICON_BUCKETS.get(key,()):
            entries=icons.get(bucket,{})
            urls+=[url for name,url in entries.items() if not name.isdigit() and name in text]
            urls+=[entries[name] for alias,name in (aliases.get(key) or {}).items() if alias in text and name in entries]
    return [url for url in dict.fromkeys(urls) if url and safe_public_url(url)][:WUWA_HINT_LIMIT]

def _wuwa_overlay(row,state,*,draft):
    """Static base (or the live draft) plus the freshness lines of one cached check."""
    live=state.get('active_guide')
    shown=row
    if draft:shown=_live_row(row,live)
    elif _usable(live,row['id']) and _reviewed(live):
        # Same replacement rule as the website: only a fully reviewed extraction replaces the catalog.
        shown=_live_row(row,live)
    guide=_guide(shown)
    if shown is not row:
        from .public_asset_catalog import CATALOG
        roles=CATALOG['games']['wuthering_waves'].get('role',{})
        guide['image']=row.get('image') or roles.get(str(row['id'])) or roles.get(row['name'])
        if not guide['image']:guide.pop('image')
        guide['asset_hints']=_wuwa_hints(guide)
    checked=_checked(state.get('checked_at'))
    lines=[]
    # A preferred post newer than the shown guide stays 待核查 until reviewed (same rule as the admin card).
    if _pending(row['id'],state):
        lines.append('库街区有新攻略帖，待核查'+('（检查于 '+checked+'）' if checked else ''))
    elif checked:lines.append('攻略检查于 '+checked)
    images=live.get('images') if shown is not row and isinstance(live,dict) else None
    if isinstance(images,list) and images:
        count=len(images)
        lines.append(('原帖共 %d 张图' if count<WUWA_IMAGE_LIMIT else '原帖至少 %d 张图')%count+'，可在网站攻略页「查看原帖」查看')
    return guide,lines

def _nte_overlay(row,state):
    guide=_guide(row);lines=[]
    if state.get('summary_changed') is True:lines.append('原帖有更新，摘要待复核')
    checked=_checked(state.get('fetched_at'))
    if checked:lines.append('攻略检查于 '+checked)
    if state.get('image_count'):lines.append('原帖共 %d 张图，可在网站「原图与来源」查看'%state['image_count'])
    return guide,lines

def _draft(name,sources):
    """A WuWa role without a static entry: its stored extraction, resolved by name through the roster."""
    if sources is None:return None
    matches=[r for r in _roster() if r.get('static') is False and name in (r.get('name'),str(r.get('name'))+'·'+str(r.get('attribute') or ''))]
    if len(matches)!=1:return None
    role=matches[0];state=sources.wuwa_state(role.get('character_id'))
    if state is None or not _usable(state.get('active_guide'),role.get('character_id')):return None
    base={'id':str(role['character_id']),'name':str(role['name']),'game':'wuthering_waves','attribute':str(role.get('attribute') or '')}
    return (*_wuwa_overlay(base,state,draft=True),_reviewed(state['active_guide']))

def reply(game,name,now,page=1,sources=None):
    command=(view.GAME_NAMES[game]+' ' if game else '')+'攻略'+(' '+name if name else '')
    rows=[g for current,items in catalog()['guides'].items() if game is None or current==game for g in items]
    title=(view.GAME_NAMES[game]+' ' if game else '')+'角色攻略'
    if name is not None:
        found=[g for g in rows if name in (g['name'],g['name']+'·'+(g.get('attribute') or g.get('element') or ''),*g.get('aliases',[]))]
        overlay=mark=None
        if len(found)==1:
            row=found[0]
            if sources is not None and row.get('game')=='wuthering_waves':
                state=sources.wuwa_state(row['id'])
                overlay=_wuwa_overlay(row,state,draft=False) if state is not None else None
            elif sources is not None and row.get('game')=='nte':
                state=sources.nte_state(row.get('source_id'))
                overlay=_nte_overlay(row,state) if state is not None else None
            guide,lines=overlay or (_guide(row),[])
        elif not found and game=='wuthering_waves':
            overlay=_draft(name,sources)
            # A fully reviewed extraction (e.g. a registered fingerprint) is not a draft.
            if overlay:guide,lines,reviewed=overlay;mark=None if reviewed else DRAFT_MARK
        if len(found)==1 or overlay:
            if lines or mark:guide['freshness']={'mark':mark,'lines':lines}
            heading=title+' · '+guide['name']+(' · '+mark if mark else '')
            card=view.document('detail',game,heading,sections=[{'title':s['title'],'fields':[view.field('建议',s.get('text') or s.get('note') or '暂无已核验文字摘要，请查看来源原图。')]} for s in guide['sections']],
                               notices=([mark+'：内容由原帖自动提炼，未经人工核对。'] if mark else [])+lines)
            return card,shared.snapshot('guide',game,{'guide':guide},now,page,heading,command)
        if len(found)>1:
            text='角色名对应多个形态，请使用：'+'、'.join(g['name']+'·'+(g.get('attribute') or g.get('element') or '') for g in found)
        elif game=='endfield':text=ENDFIELD_TEXT
        else:text='当前项目尚未收录可核验的'+(view.GAME_NAMES.get(game,'')+'角色攻略。')
        card=view.message(game,title,text)
        return card,shared.notice_snapshot(card,now,page,command=command)
    # No index image: a bare 攻略 points to the named form and the website list.
    text=(ENDFIELD_TEXT if game=='endfield' else
          '请发送「'+(view.GAME_NAMES[game]+' 攻略 角色名」' if game else '鸣潮 攻略 角色名」或「异环 攻略 角色名」')+'查看单个角色攻略；可用角色见网站攻略页。')
    card=view.message(game,title,text)
    # 终末地 keeps its guide-status notice; an unbound query never reads a roster.
    return card,shared.notice_snapshot(card,now,page,command=command)
