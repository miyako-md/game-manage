"""Selected long-image behavior and lifetime boundaries, without private data."""
import asyncio
from datetime import datetime
from io import BytesIO
import os
import threading

from PIL import Image
import pytest

from game_assistant.accounts.models import AccountScope,QueryResult
from game_assistant.qq.browser_rendering import BrowserRenderer
from game_assistant.qq.render_snapshot import asset_requests,game_panel,game_snapshot,calendar_snapshot
from game_assistant.qq.rendering import RenderingPageUnavailable

NOW=datetime.fromisoformat('2026-10-18T12:00:00+08:00')


def test_visible_operator_roster_does_not_download_hidden_medals_and_equipment():
    raw={'report':{'schema_version':1,'training':{'items':[{'name':'伊冯','avatar_url':'https://bbs.hycdn.cn/visible.png',
        'equipment':[{'icon_url':'https://bbs.hycdn.cn/hidden-equipment.png'}]}]},
        'honor':{'items':[{'icon_url':f'https://bbs.hycdn.cn/hidden-medal-{i}.png'} for i in range(300)]}}}
    panel=game_panel('endfield','skland','roles',QueryResult(raw,NOW.isoformat(),'ok',True))
    urls={url for url,_ in asset_requests(game_snapshot([panel],NOW))}
    assert 'https://bbs.hycdn.cn/visible.png' in urls
    assert not any('hidden-' in url for url in urls)
    panel['capability']='honor'
    urls={url for url,_ in asset_requests(game_snapshot([panel],NOW))}
    assert 'https://bbs.hycdn.cn/hidden-medal-299.png' in urls
    assert 'https://bbs.hycdn.cn/visible.png' not in urls


def test_team_diagrams_keep_artwork_resolution_and_skip_other_guide_pages():
    from game_assistant.qq.assets import sanitize_image
    raw={'entries':[{'name':'合成配队','image_urls':['https://webstatic.tajiduo.com/peidui.png',
         'https://webstatic.tajiduo.com/skill-guide.png']}]}
    panel=game_panel('nte','public','teams',QueryResult(raw,NOW.isoformat(),'ok',True))
    requests=list(asset_requests(game_snapshot([panel],NOW)))
    assert ('https://webstatic.tajiduo.com/peidui.png','artwork') in requests
    assert not any('skill-guide' in url for url,_ in requests)
    image=BytesIO();Image.new('RGB',(1200,800),'white').save(image,'PNG')
    assert Image.open(BytesIO(sanitize_image(image.getvalue(),artwork=True))).size==(1080,720)


def test_team_prefetch_skips_duplicate_names_like_the_rendered_image():
    raw={'entries':[{'name':'主角·零','image_urls':['https://webstatic.tajiduo.com/peidui-male.png']},
         {'name':'主角·零','image_urls':['https://webstatic.tajiduo.com/peidui-female.png']},
         {'name':'合成配队','image_urls':['https://webstatic.tajiduo.com/peidui-other.png']}]}
    panel=game_panel('nte','public','teams',QueryResult(raw,NOW.isoformat(),'ok',True))
    urls={url for url,_ in asset_requests(game_snapshot([panel],NOW))}
    assert {'https://webstatic.tajiduo.com/peidui-male.png','https://webstatic.tajiduo.com/peidui-other.png'}<=urls
    assert 'https://webstatic.tajiduo.com/peidui-female.png' not in urls


async def test_cancelled_encoder_owns_its_cpu_worker_until_finished(monkeypatch):
    from game_assistant.qq import a_rendering
    started=threading.Event();finish=threading.Event()
    def encode(*args):
        started.set();finish.wait(2)
        return b'fixture',{}
    monkeypatch.setattr(a_rendering,'encode',encode)
    renderer=BrowserRenderer(template='a')
    task=asyncio.create_task(renderer._a_encode(b'fixture'))
    try:
        assert await asyncio.to_thread(started.wait,1)
        task.cancel();await asyncio.sleep(.01)
        assert not task.done()
        finish.set()
        with pytest.raises(asyncio.CancelledError):await task
    finally:
        finish.set();await asyncio.gather(task,return_exceptions=True)
        await renderer.aclose()


async def test_real_a_calendar_one_image_cached_and_account_context_disposed():
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Set isolated Chromium/font paths for native acceptance')
    renderer=BrowserRenderer(template='a',executable_path=executable,font_path=font)
    scope=AccountScope('fixture-a','account-a','role-a')
    events=[{'name':f'完整活动 {i}','category':'限时活动','start_at':'2026-10-01T00:00:00+08:00',
             'end_at':'2026-11-20T00:00:00+08:00','source_name':'官方公告'} for i in range(12)]
    snap=calendar_snapshot({'nte':QueryResult(events,NOW.isoformat(),'ok',True)},NOW)
    value=QueryResult({'text':'合成检查','render_snapshot':snap,'snapshot_fingerprints':['a'*64]},NOW.isoformat(),'ok',True)
    try:
        image=await renderer.render_summary_async(scope,value,budget_seconds=10)
        assert image.page==image.total_pages==1
        assert Image.open(BytesIO(image)).size[0]<=1080
        assert renderer.last_state['layout_issues']==0 and not renderer.last_state['missing_assets']
        assert await renderer._a_page.locator('#app').inner_text()==''
        assert await renderer.render_summary_async(scope,value,budget_seconds=10) is image
        other=AccountScope('fixture-b','account-b','role-b')
        assert renderer.cache_key(other,value)!=renderer.cache_key(scope,value)
        snap['page']=2
        with pytest.raises(RenderingPageUnavailable):await renderer.render_summary_async(scope,value,budget_seconds=10)
        renderer.invalidate_account(scope.user_id,scope.account_id)
        assert not renderer.cache
    finally:await renderer.aclose()
    assert renderer._browser is None and renderer._a_page is None


async def test_real_a_house_cover_sits_beside_its_name():
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Set isolated Chromium/font paths for native acceptance')
    houses={'schema_version':1,'owned_count':1,'total':2,'entries':[
        {'id':'bigword_house_1','name':'合成公寓','owned':True,'resident_ids':['1019'],'furniture':[{'id':'f','name':'椅子','owned':True}]},
        {'id':'bigword_house_2','name':'合成空馆','owned':False,'resident_ids':[],'furniture':[]}]}
    snap=game_snapshot([game_panel('nte','tajiduo','realestate',QueryResult(houses,NOW.isoformat(),'ok',True))],NOW,title='异环 · 房产',command='异环 房产')
    renderer=BrowserRenderer(template='a',executable_path=executable,font_path=font,dist_path=os.environ.get('QQ_RENDER_TEST_DIST',''))
    # The same per-render state _render_a prepares; the DOM is read before disposal.
    renderer._a_images={};renderer._a_forbidden=[];renderer._a_asset_misses=[]
    try:
        async with asyncio.timeout(30):
            await renderer._a_ready()
            await renderer._a_page.evaluate('(input)=>window.mountLongRender(input)',{'snapshot':snap,'asset_urls':[],'job_id':'house','input_fingerprint':'house'})
            assert (await renderer._a_page.evaluate('window.__LONG_RENDER_STATE__'))['state']=='ready'
            boxes=await renderer._a_page.evaluate("""()=>[...document.querySelectorAll('.asset-grid .asset')].map(asset=>{
                const cover=asset.querySelector('.asset-cover').getBoundingClientRect(),name=asset.querySelector('.asset-name').getBoundingClientRect()
                return {cover:[cover.left,cover.right,cover.width],name:[name.left,name.right]}})""")
            assert len(boxes)==2
            for box in boxes:
                # The 104px cover keeps its own column; the name starts after it instead of under it.
                assert box['cover'][2]>=100 and box['name'][0]>=box['cover'][1],box
    finally:await renderer.aclose()


@pytest.mark.parametrize('case',['help','help_endfield','guide_hint','retired'])
async def test_real_a_registry_help_bare_guide_and_retired_notices_render_one_clean_image(case,tmp_path):
    from game_assistant.qq.guides import reply
    from game_assistant.qq.commands import retired_reply
    from game_assistant.qq.presentation import help_document, message
    from game_assistant.qq.render_snapshot import notice_snapshot
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE');font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Set isolated Chromium/font paths for native acceptance')
    if case=='guide_hint':_,snap=reply(None,None,NOW)
    elif case=='retired':snap=notice_snapshot(message('endfield','指令已下线',retired_reply('training','endfield')),NOW)
    else:snap=notice_snapshot(help_document('endfield' if case=='help_endfield' else None),NOW)
    value=QueryResult({'text':'合成检查','render_snapshot':snap,'snapshot_fingerprints':['a'*64]},NOW.isoformat(),'ok',True)
    renderer=BrowserRenderer(template='a',executable_path=executable,font_path=font)
    try:
        image=await renderer.render_summary_async(AccountScope('fixture','account','role'),value,budget_seconds=10)
        assert image.page==image.total_pages==1
        assert Image.open(BytesIO(image)).size[0]<=1080
        state=renderer.last_state
        assert state['state']=='ready' and not state['overflow'] and state['layout_issues']==0 and not state['missing_assets']
        (tmp_path/f'{case}.png').write_bytes(bytes(image))
    finally:await renderer.aclose()
