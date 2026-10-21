"""Public, existing reviewed guide catalogs; no account or upstream access."""
from functools import lru_cache
import json
from pathlib import Path
from . import render_snapshot as shared
from . import presentation as view
from .assets import safe_public_url

@lru_cache(maxsize=1)
def catalog():
    return json.loads(Path(__file__).with_name('role_guides.json').read_text(encoding='utf-8'))

def _guide(row):
    fields=('id','name','game','attribute','element','role','status','image','aliases')
    guide={key:row[key] for key in fields if key in row}
    guide['asset_hints']=[url for url in row.get('asset_hints',[]) if safe_public_url(url)]
    guide['sources']=[{key:(str(source[key]) if key=='id' else shared.display_text(source[key])) for key in ('id','title','author','version','url') if key in source} for source in row.get('sources',[])]
    guide['sections']=[{key:(str(section[key]) if key=='sourceId' else shared.display_text(section[key])) for key in ('key','title','text','note','sourceId') if key in section} for section in row.get('sections',[])]
    return guide

def reply(game,name,now,page=1):
    command=(view.GAME_NAMES[game]+' ' if game else '')+'攻略'+(' '+name if name else '')
    rows=[g for current,items in catalog()['guides'].items() if game is None or current==game for g in items]
    title=(view.GAME_NAMES[game]+' ' if game else '')+'角色攻略'
    if name is not None:
        found=[g for g in rows if name in (g['name'],g['name']+'·'+(g.get('attribute') or g.get('element') or ''),*g.get('aliases',[]))]
        if len(found)==1:
            guide=_guide(found[0])
            card=view.document('detail',game,title+' · '+guide['name'],sections=[{'title':s['title'],'fields':[view.field('建议',s.get('text') or s.get('note') or '暂无已核验文字摘要，请查看来源原图。')]} for s in guide['sections']])
            return card,shared.snapshot('guide',game,{'guide':guide},now,page,title+' · '+guide['name'],command)
        if len(found)>1:
            text='角色名对应多个形态，请使用：'+'、'.join(g['name']+'·'+(g.get('attribute') or g.get('element') or '') for g in found)
        else:text='当前项目尚未收录可核验的'+(view.GAME_NAMES.get(game,'')+'角色攻略。')
        card=view.message(game,title,text)
        return card,shared.notice_snapshot(card,now,page,command=command)
    # No index image: a bare 攻略 points to the named form and the website list.
    text=('当前项目尚未收录可核验的终末地角色攻略。' if game=='endfield' else
          '请发送「'+(view.GAME_NAMES[game]+' 攻略 角色名」' if game else '鸣潮 攻略 角色名」或「异环 攻略 角色名」')+'查看单个角色攻略；可用角色见网站攻略页。')
    card=view.message(game,title,text)
    # 终末地 keeps its guide-status notice; an unbound query never reads a roster.
    return card,shared.notice_snapshot(card,now,page,command=command)
