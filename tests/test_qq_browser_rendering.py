import asyncio
from datetime import datetime
from io import BytesIO
from math import ceil
import os
from pathlib import Path
import time

from PIL import Image
import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq.browser_rendering import BrowserRenderer, validate_snapshot
from game_assistant.qq.client import valid_reply_image
from game_assistant.qq.render_snapshot import calendar_snapshot, role_snapshot, gacha_snapshot, project, ROLE
from game_assistant.qq.rendering import RenderQueue, RenderingUnavailable, RenderingPageUnavailable

NOW=datetime.fromisoformat('2026-10-14T12:00:00+08:00')
SCOPE=AccountScope('fixture-user','fixture-account','fixture-role')


@pytest.mark.parametrize('platform,expected',[
    ('linux',{'headless':True,'executable_path':'fixture-chromium','chromium_sandbox':True}),
    ('win32',{'headless':True,'executable_path':'fixture-chromium'}),
])
async def test_launch_enables_linux_chromium_sandbox_and_preserves_windows_options(monkeypatch,platform,expected):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import playwright.async_api
    from game_assistant.qq import browser_rendering
    browser=SimpleNamespace(is_connected=lambda:True,close=AsyncMock())
    launch=AsyncMock(return_value=browser)
    runtime=SimpleNamespace(chromium=SimpleNamespace(launch=launch),stop=AsyncMock())
    monkeypatch.setattr(playwright.async_api,'async_playwright',lambda:SimpleNamespace(start=AsyncMock(return_value=runtime)))
    monkeypatch.setattr(browser_rendering,'sys',SimpleNamespace(platform=platform),raising=False)
    renderer=BrowserRenderer(executable_path='fixture-chromium')
    try:
        await renderer._start()
        launch.assert_awaited_once_with(**expected)
        await renderer._start()
        assert launch.await_count==1
    finally:await renderer.aclose()
    assert renderer._browser is None and renderer._playwright is None
    browser.close.assert_awaited_once();runtime.stop.assert_awaited_once()


async def test_linux_sandbox_launch_failure_does_not_retry_without_sandbox(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import playwright.async_api
    from game_assistant.qq import browser_rendering
    launch=AsyncMock(side_effect=RuntimeError('fixture_sandbox_unavailable'))
    runtime=SimpleNamespace(chromium=SimpleNamespace(launch=launch),stop=AsyncMock())
    monkeypatch.setattr(playwright.async_api,'async_playwright',lambda:SimpleNamespace(start=AsyncMock(return_value=runtime)))
    monkeypatch.setattr(browser_rendering,'sys',SimpleNamespace(platform='linux'),raising=False)
    renderer=BrowserRenderer()
    try:
        with pytest.raises(RenderingUnavailable,match='^qq_browser_runtime_unavailable$'):
            await renderer._start()
        launch.assert_awaited_once_with(headless=True,chromium_sandbox=True)
        assert renderer._browser is None
    finally:await renderer.aclose()
    runtime.stop.assert_awaited_once()


def calendar(count=3):
    return calendar_snapshot({'nte':QueryResult([{'name':f'活动 {i:03}','category':'限时活动',
        'start_at':'2026-10-01T10:00:00+08:00','end_at':'2026-11-20T12:00:00+08:00',
        'source_title':'官方版本公告','source_name':'官方社区','version':'1.4'} for i in range(count)],NOW.isoformat(),'ok',False)},NOW)


def envelope(snapshot):return QueryResult({'text':'只读截图测试','render_snapshot':snapshot,'snapshot_fingerprints':['a'*64],
    'scopes':[{'account_id':SCOPE.account_id,'role_id':SCOPE.role_id,'grant_version':1}]},NOW.isoformat(),'ok',False)


def browser():
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE')
    font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:pytest.skip('Set QQ_RENDER_TEST_EXECUTABLE and QQ_RENDER_TEST_FONT for isolated real Chromium acceptance')
    return BrowserRenderer(executable_path=executable,font_path=font)


async def out_of_bounds_rows(page,selector):
    return await page.locator('.render-page').evaluate_all("""(hosts, selector) => hosts.reduce((total, host) => {
        const page = host.getBoundingClientRect();
        return total + [...host.querySelectorAll(selector)].filter(row => {
            const box = row.getBoundingClientRect();
            return box.width <= 0 || box.height <= 0 || box.left < page.left - .01 ||
                box.top < page.top - .01 || box.right > page.right + .01 || box.bottom > page.bottom + .01;
        }).length;
    }, 0)""",selector)


def test_strict_snapshot_rejects_unknown_paths_credentials_and_unbounded_data():
    value=calendar()
    for key in ('url','html','path','token'):
        with pytest.raises(RenderingUnavailable):validate_snapshot(dict(value,**{key:'private'}))
    value['display_data']['token']='private'
    with pytest.raises(RenderingUnavailable):validate_snapshot(value)
    value=calendar();value['display_data']['games'][0]['unexpected_html']='<script>secret</script>'
    with pytest.raises(RenderingUnavailable):validate_snapshot(value)
    value=calendar();value['page']=True
    with pytest.raises(RenderingUnavailable):validate_snapshot(value)
    value=calendar();value['display_data']['games']=[{}]*2001
    with pytest.raises(RenderingUnavailable):validate_snapshot(value)


def test_identical_requests_within_a_minute_build_the_same_snapshot():
    # The snapshot is part of the image cache key, and the page shows minutes only.
    from datetime import timedelta, timezone
    beijing = timezone(timedelta(hours=8))
    first = calendar_snapshot({}, datetime(2026, 10, 16, 21, 5, 3, 120000, tzinfo=beijing))
    again = calendar_snapshot({}, datetime(2026, 10, 16, 21, 5, 41, 7, tzinfo=beijing))
    assert first == again and first['as_of'] == '2026-10-16T21:05:00+08:00'


def test_projection_only_emits_component_fields_and_keeps_unknown_separate_from_zero():
    value=project({'name':'测试角色','level':0,'awaken_level':None,'uid':'private','token':'private',
        'icon_url':'https://example.com/private.png','weapon':{'name':'弧盘','password':'private'}},ROLE)
    assert value=={'name':'测试角色','level':0,'awaken_level':None,'icon_url':None,'weapon':{'name':'弧盘'}}


def test_wuwa_summary_projection_keeps_aggregate_pity_and_hides_private_provenance():
    row=QueryResult({'total':600,'gold_total':10,'limit':500,'offset':0,
        'role_id':'private-role','server_id':'private-server',
        'coverage':{'segment_count':2,'segments':[{'draw_ids':['private-draw']}],'complete':False},
        'pools':[{'pool':'1','pity':{'status':'exact','count':0,'rule_basis':'user_configured',
            'rule_version':'personal','up_guarantee':'unknown','hard_pity_remaining':70}}],
        'aggregates':{'total':1,'five_star_total':1,'items':[{'summary_id':'private-summary',
            'name':'来源五星','kind':'five_star_summary','source':'mcgf','period_count':120,
            'diagnostics':['CONTINUITY_UNVERIFIED']}]}},NOW.isoformat(),'ok',False)
    value=gacha_snapshot('wuthering_waves',row,NOW)
    import json
    assert 'private-' not in json.dumps(value)
    archive=value['display_data']['archive']
    assert archive['total']==600 and archive['limit']==500
    assert archive['pools'][0]['pity']['count']==0
    assert archive['aggregates']['items'][0]['period_count']==120


async def test_cancelled_caller_does_not_free_async_worker_before_close():
    started=asyncio.Event();finish=asyncio.Event()
    class Renderer:
        async def render_summary_async(self,*args,**kwargs):
            started.set();await finish.wait();return b'png'
    queue=RenderQueue(Renderer(),queue_limit=1)
    task=asyncio.create_task(queue.render(SCOPE,envelope(calendar()),budget_seconds=1))
    await started.wait();task.cancel()
    with pytest.raises(asyncio.CancelledError):await task
    assert queue.pending==1
    assert await queue.render(SCOPE,envelope(calendar()),budget_seconds=.01) is None
    finish.set();await queue.aclose();assert queue.pending==0


@pytest.mark.parametrize('code,exposed', [('qq_image_size_limit',True),('qq_image_pixel_limit',True),('private_runtime_error',False)])
async def test_queue_exposes_only_known_output_limits_and_preserves_generic_fallback(code,exposed):
    class Renderer:
        async def render_summary_async(self,*args,**kwargs):raise RenderingUnavailable(code)
    queue=RenderQueue(Renderer())
    result=await queue.render(SCOPE,envelope(calendar()),budget_seconds=1)
    if exposed:assert isinstance(result,RenderingUnavailable) and str(result)==code
    else:assert result is None
    assert queue.pending==0
    await queue.aclose()


async def test_real_complete_calendar_short_pages_cache_isolation_and_clean_context(tmp_path):
    renderer=browser()
    try:
        value=calendar(70)
        first=await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert 1<first.total_pages<=100 and first.page==1
        assert renderer.last_state['state']=='ready' and not renderer._browser.contexts
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        assert Image.open(BytesIO(first)).size[0]==720
        assert Image.open(BytesIO(first)).size[1]<=1440
        assert len(first)<=renderer.max_bytes
        assert renderer.cache_key(SCOPE,envelope(value))!=renderer.cache_key(AccountScope('other','fixture-account','fixture-role'),envelope(value))
        (tmp_path/('calendar-page.jpg' if first.startswith(b'\xff\xd8') else 'calendar-page.png')).write_bytes(first)
        value['page']=first.total_pages+1
        with pytest.raises(RenderingPageUnavailable) as error:await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert error.value.total_pages==first.total_pages and not renderer._browser.contexts
        renderer.invalidate_account(SCOPE.user_id,SCOPE.account_id)
        assert not renderer.cache
    finally:await renderer.aclose()


async def test_real_font_transport_uses_validated_original_file_and_keeps_ready_complete_output(monkeypatch):
    from playwright.async_api import Route
    original=Route.fulfill
    observed=[]
    async def capture(route,*args,**kwargs):
        if route.request.url.endswith('/render-font.ttf'):
            observed.append({'path':kwargs.get('path'),'inline_body':'body' in kwargs})
        return await original(route,*args,**kwargs)
    monkeypatch.setattr(Route,'fulfill',capture)
    renderer=browser()
    try:
        image=await renderer.render_summary_async(SCOPE,envelope(calendar(3)),budget_seconds=10)
        assert observed==[{'path':renderer.font_path,'inline_body':False}]
        assert renderer.last_state['state']=='ready'
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        assert image.total_pages>=1 and Image.open(BytesIO(image)).width==720
        assert not renderer._browser.contexts
    finally:await renderer.aclose()


async def test_real_calendar_many_rows_are_complete_short_pages_with_per_page_byte_limit():
    renderer=browser();renderer.max_bytes=512*1024
    try:
        for count in (30,240):
            image=await renderer.render_summary_async(SCOPE,envelope(calendar(count)),budget_seconds=10)
            assert 1<image.total_pages<=100 and len(image)<=512*1024
            assert Image.open(BytesIO(image)).width==720
            assert 0<Image.open(BytesIO(image)).height<=1440
            assert all(row['width']==720 and 0<row['height']<=1440 for row in renderer.last_state['pages'])
            assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
            assert not renderer._browser.contexts
    finally:await renderer.aclose()


async def test_real_query_service_uses_complete_calendar_projection_not_truncated_card():
    from types import SimpleNamespace
    from game_assistant.qq.query_routes import QqQueryService
    from game_assistant.qq.models import QqIdentity
    renderer=browser();queue=RenderQueue(renderer)
    row=QueryResult(calendar(70)['display_data']['snapshots']['nte']['events']['payload'],NOW.isoformat(),'ok',False)
    service=QqQueryService(None,None,SimpleNamespace(read=lambda game,cap:row),render_queue=queue,clock=lambda:NOW)
    try:
        response=await service.query_reply(QqIdentity('app','group','g','s'),'calendar','nte',image_requested=True,budget_seconds=10)
        assert 'image' in response
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        response=await service.query_reply(QqIdentity('app','group','g','s'),'calendar','nte',image_requested=True,budget_seconds=10,page=100)
        assert 'image' not in response and '超出范围' in response['text']
    finally:await queue.aclose()


@pytest.mark.parametrize('kind',['wuwa_role','nte_role','wuwa_gacha','nte_gacha'])
async def test_real_shared_component_pngs_optional_images_and_no_account_api(kind):
    renderer=browser()
    if kind=='wuwa_role':
        row=QueryResult({'role':{'role_name':'今汐','level':80,'role_icon_url':'https://web-static.kurobbs.com/fixture-missing.png'},
            'weapon_data':{'weapon':{'weapon_name':'时和岁稔','weapon_star_level':5},'level':90},
            'skill_list':[{'skill':{'name':'共鸣技能','description':'完整技能说明'},'level':8}],
            'chain_list':[{'name':'共鸣链一','unlocked':False,'description':'锁定状态不能按已解锁计算'}]},NOW.isoformat(),'ok',False)
        value=role_snapshot('wuthering_waves',row,NOW,detail=row,resolved_id='1304')
    elif kind=='nte_role':
        row=QueryResult({'schema_version':1,'entries':[{'id':'9001','name':'测试角色','quality':'S','level':0,'awaken_level':None,
            'weapon':{'name':'测试弧盘','level':50},'properties':[{'name':'攻击','value':'1234'}],
            'skills':[{'name':'战技','level':4}],'city_skills':[{'name':'城区技能','level':None}]}]},NOW.isoformat(),'ok',False)
        value=role_snapshot('nte',row,NOW)
    elif kind=='wuwa_gacha':
        row=QueryResult({'total':2,'gold_total':1,'coverage':{'message':'仅已导入窗口，完整历史未知','earliest':'2026-10-01T10:00','latest':'2026-10-14T10:00',
            'segment_count':1,'imported_at':NOW.isoformat(),'source':'json_import'},
            'pools':[{'pool':'1','name':'角色活动唤取','total':2,'rarity_distribution':{'5':1,'4':1},
                'pity':{'status':'exact','count':1,'rule_basis':'user_configured','rule_version':'合成用户配置',
                    'hard_pity_remaining':69,'up_guarantee':'unknown'}}],
            'aggregates':{'total':1,'five_star_total':1,'message':'来源自报五星周期，连续性未证实；不计入逐抽或保底',
                'items':[{'pool':'99','name':'来源五星（合成样本）','source':'mcgf','source_time':'2026-10-01',
                    'kind':'five_star_summary','period_count':120,'diagnostics':['UNKNOWN_POOL','CONTINUITY_UNVERIFIED']}]},
            'gold':[{'time':'2026-10-01T10:00','pool':'1','name':'今汐','rarity':5,'count':1}],
            'items':[{'time':'2026-10-14T10:00','pool':'1','name':'测试武器','rarity':4,'count':1}]},NOW.isoformat(),'ok',False)
        value=gacha_snapshot('wuthering_waves',row,NOW)
    else:
        row=QueryResult({'schema_version':1,'pools':[{'name':'角色池','total_draws':20,'s_count':1,'guarantee':80,'details':[{'name':'测试角色','item_id':'9001','pity':20,'obtained_at':'2026-10-14T10:00'}]},
            {'name':'弧盘池','total_draws':10,'s_count':1,'guarantee':70,'details':[{'name':'测试弧盘','item_id':'fork_1','pity':10}]}]},NOW.isoformat(),'ok',False)
        ledger=QueryResult({'total_records':1,'pools':[{'pool_id':'1','total_pulls':1,'pity':{'basis':'coverage_unknown','hard_pity_remaining':None}}]},NOW.isoformat(),'ok',False)
        value=gacha_snapshot('nte',row,NOW,ledger=ledger)
    try:
        png=await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert valid_reply_image(png,max_bytes=renderer.max_bytes) and renderer.last_state['state']=='ready'
        assert 1<=png.total_pages<=100 and png.page==1
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        value['page']=png.total_pages+1
        with pytest.raises(RenderingPageUnavailable) as error:
            await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert error.value.total_pages==png.total_pages
        assert not renderer._browser.contexts
        evidence=Path('.superpowers/sdd/2026-10-14-game-modules-phase-one/render-evidence')
        evidence.mkdir(parents=True,exist_ok=True)
        (evidence/f'{kind}.png').write_bytes(png)
    finally:await renderer.aclose()


@pytest.mark.parametrize('kind',['nte_role','nte_gacha','wuwa_gacha','wuwa_role'])
async def test_real_shared_long_records_retain_every_row_across_short_pages(kind,tmp_path):
    renderer=browser()
    texts=[]
    counts={}
    bounds={}
    outside={}
    expected_counts={'nte_role':{'.role-card':20},'nte_gacha':{'.pull-row':40},
        'wuwa_gacha':{'.wuwa-draws tbody tr':90,'.wuwa-gold-row':30},
        'wuwa_role':{'.sheet-skills > article':12,'.wuwa-chain':8}}[kind]
    original_close=renderer._bounded_close
    async def inspect_close(operation):
        if renderer._browser is not None and renderer._browser.contexts:
            page=renderer._browser.contexts[0].pages[0]
            if not page.is_closed() and renderer.last_state and renderer.last_state.get('state')=='ready':
                texts.extend(await page.locator('.render-page').all_inner_texts())
                bounds.update(await page.locator('.render-page').first.bounding_box())
                for selector in expected_counts:
                    counts[selector]=await page.locator('.render-page').locator(selector).count()
                    outside[selector]=await out_of_bounds_rows(page,selector)
        return await original_close(operation)
    renderer._bounded_close=inspect_close
    if kind=='nte_role':
        row=QueryResult({'schema_version':1,'entries':[{'id':str(9000+i),'name':f'完整角色 {i:03}','quality':'S','level':80} for i in range(20)]},NOW.isoformat(),'ok',False)
        value=role_snapshot('nte',row,NOW)
    elif kind=='nte_gacha':
        row=QueryResult({'schema_version':1,'pools':[{'name':'角色池','total_draws':600,'s_count':40,'guarantee':80,'details':[{'name':f'完整抽卡 {i:03}','item_id':str(9000+i),'pity':15,'obtained_at':'2026-10-14T10:00'} for i in range(40)]}]},NOW.isoformat(),'ok',False)
        value=gacha_snapshot('nte',row,NOW)
    elif kind=='wuwa_gacha':
        row=QueryResult({'total':60,'gold_total':30,'pools':[],
            'gold':[{'time':'2026-10-01T10:00','pool':'1','name':f'完整五星 {i:03}','rarity':5,'count':1} for i in range(30)],
            'items':[{'time':'2026-10-14T10:00','pool':'1','name':f'完整明细 {i:03}','rarity':4,'count':1} for i in range(60)]},NOW.isoformat(),'ok',False)
        value=gacha_snapshot('wuthering_waves',row,NOW)
    else:
        row=QueryResult({'role':{'role_name':'完整角色','level':80},
            'skill_list':[{'skill':{'name':f'完整技能 {i:03}','description':'完整技能说明。'*15},'level':8} for i in range(12)],
            'chain_list':[{'name':f'完整共鸣链 {i:03}','unlocked':False,'description':'完整共鸣链说明。'*15} for i in range(8)]},NOW.isoformat(),'ok',False)
        value=role_snapshot('wuthering_waves',row,NOW,detail=row,resolved_id='1304')
    try:
        image=await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert 1<image.total_pages<=100 and image.page==1
        assert len(renderer.last_state['pages'])==image.total_pages
        assert all(row['width']==720 and 0<row['height']<=1440 for row in renderer.last_state['pages'])
        geometry=renderer.last_state['pages'][0]
        with Image.open(BytesIO(image)) as picture:
            assert picture.size==(ceil(bounds['width']),ceil(bounds['height']))
            assert geometry['width']==bounds['width'] and abs(geometry['height']-bounds['height'])<1
            assert picture.width==720 and 0<picture.height<=1440
            assert picture.width*picture.height<=renderer.max_pixels
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        assert counts==expected_counts
        assert outside==dict.fromkeys(expected_counts,0)
        first,last={'nte_role':('完整角色 000','完整角色 019'),'nte_gacha':('完整抽卡 000','完整抽卡 039'),'wuwa_gacha':('完整五星 000','完整明细 059'),'wuwa_role':('完整技能 000','完整共鸣链 007')}[kind]
        assert first in '\n'.join(texts) and last in '\n'.join(texts)
        prefixes={'nte_role':[('完整角色',20)],'nte_gacha':[('完整抽卡',40)],
            'wuwa_gacha':[('完整五星',30),('完整明细',60)],'wuwa_role':[('完整技能',12),('完整共鸣链',8)]}[kind]
        for prefix,count in prefixes:
            assert all(f'{prefix} {index:03}' in '\n'.join(texts) for index in range(count))
        assert len(image)<=renderer.max_bytes and not renderer._browser.contexts
        suffix='jpg' if image.startswith(b'\xff\xd8') else 'png'
        (tmp_path/f'{kind}-long.{suffix}').write_bytes(image)
    finally:await renderer.aclose()


@pytest.mark.parametrize('kind',['nte_role','nte_gacha'])
async def test_real_large_roster_or_history_preserves_all_rows_across_bounded_pages(kind):
    renderer=browser()
    observed={}
    original_close=renderer._bounded_close
    async def inspect_close(operation):
        if renderer._browser is not None and renderer._browser.contexts and renderer.last_state and renderer.last_state.get('state')=='ready':
            page=renderer._browser.contexts[0].pages[0]
            observed['rows']=await page.locator('.render-page').locator('.role-card' if kind=='nte_role' else '.pull-row').count()
            observed['outside']=await out_of_bounds_rows(page,'.role-card' if kind=='nte_role' else '.pull-row')
            observed['text']='\n'.join(await page.locator('.render-page').all_inner_texts())
        return await original_close(operation)
    renderer._bounded_close=inspect_close
    if kind=='nte_role':
        row=QueryResult({'schema_version':1,'entries':[{'id':str(9000+i),'name':f'角色 {i:03}','level':80} for i in range(160)]},NOW.isoformat(),'ok',False)
        value=role_snapshot('nte',row,NOW)
    else:
        # A long history repeats a few dozen items. Each distinct icon is one intercepted
        # request, so 400 distinct ids spent the 10 s budget on images, not on pagination.
        row=QueryResult({'schema_version':1,'pools':[{'name':'角色池','total_draws':6000,'s_count':400,'details':[{'name':f'抽卡 {i:03}','item_id':str(9000+i%40),'pity':15} for i in range(400)]}]},NOW.isoformat(),'ok',False)
        value=gacha_snapshot('nte',row,NOW)
    try:
        image=await renderer.render_summary_async(SCOPE,envelope(value),budget_seconds=10)
        assert 1<image.total_pages<=100 and image.page==1
        assert all(row['width']==720 and 0<row['height']<=1440 for row in renderer.last_state['pages'])
        assert renderer.last_state['content_blocks']==renderer.last_state['displayed_blocks']
        count,prefix=(160,'角色') if kind=='nte_role' else (400,'抽卡')
        assert observed['rows']==count and observed['outside']==0
        assert all(f'{prefix} {index:03}' in observed['text'] for index in range(count))
        assert not renderer._browser.contexts
    finally:await renderer.aclose()


async def test_missing_font_and_timeout_never_report_success():
    renderer=browser()
    try:
        renderer.font_path=str(Path('missing-font.ttf').resolve())
        with pytest.raises(RenderingUnavailable,match='font'):await renderer.render_summary_async(SCOPE,envelope(calendar()),budget_seconds=10)
        assert renderer.last_state is None
    finally:await renderer.aclose()


async def test_real_deadline_closes_context_before_releasing_queue():
    renderer=browser();queue=RenderQueue(renderer)
    try:
        await renderer._start()
        assert await queue.render(SCOPE,envelope(calendar()),budget_seconds=.01) is None
        await queue.aclose()
        assert queue.pending==0 and renderer._browser is None
    finally:await renderer.aclose()


def test_role_continuations_use_stable_selected_id_not_roster_or_ambiguous_name():
    row=QueryResult({'schema_version':1,'entries':[{'id':'9001','name':'漂泊者'}]},NOW.isoformat(),'ok',False)
    assert role_snapshot('nte',row,NOW,resolved_id='9001')['next_command']=='异环 角色 9001'
    detail=QueryResult({'role':{'role_name':'漂泊者'}},NOW.isoformat(),'ok',False)
    assert role_snapshot('wuthering_waves',row,NOW,detail=detail,resolved_id='1501')['next_command']=='鸣潮 角色 1501'
    assert role_snapshot('wuthering_waves',row,NOW,detail=detail) is None


async def test_payload_without_shared_snapshot_is_refused():
    renderer=BrowserRenderer()
    for payload in ({'text':'角色','shared_required':True},{'text':'角色'}):
        with pytest.raises(RenderingUnavailable,match='shared_content_unavailable'):
            await renderer.render_summary_async(SCOPE,QueryResult(payload,None,'ok',False),budget_seconds=1)


async def test_hung_context_cleanup_recycles_browser_with_bounded_wait():
    renderer=BrowserRenderer();renderer.cleanup_seconds=.01
    stopped=asyncio.Event()
    class Context:
        async def close(self):await stopped.wait()
    class Browser:
        async def close(self):stopped.set()
    renderer._browser=Browser()
    started=time.monotonic()
    assert not await renderer._bounded_close(Context().close())
    await renderer._recycle()
    assert renderer._browser is None and stopped.is_set() and time.monotonic()-started<.2


async def test_unconfirmed_cleanup_disables_followup_browser_jobs():
    renderer=BrowserRenderer();renderer.cleanup_seconds=.01
    class BrokenBrowser:
        async def close(self):raise RuntimeError('fixture_close_failed')
    renderer._browser=BrokenBrowser()
    await renderer._recycle()
    assert not renderer.enabled and renderer.disabled_reason=='qq_browser_cleanup_unconfirmed'
    with pytest.raises(RenderingUnavailable,match='cleanup_unconfirmed'):
        await renderer.render_summary_async(SCOPE,envelope(calendar()),budget_seconds=1)


def build_fixture(tmp_path):
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'render.html').write_text('<!doctype html>')
    (dist / 'assets/app-abc.js').write_text('one')
    font = tmp_path / 'font.otf'
    font.write_bytes(b'OTTO' + b'\0' * 64)
    return dist, font


def test_render_cache_key_rehashes_only_files_that_changed(tmp_path, monkeypatch):
    dist, font = build_fixture(tmp_path)
    renderer = BrowserRenderer(dist_path=str(dist), font_path=str(font))
    reads = []
    read_bytes = Path.read_bytes
    monkeypatch.setattr(Path, 'read_bytes', lambda self: reads.append(self.name) or read_bytes(self))
    scope, result = AccountScope('u', 'a', 'r'), QueryResult({'text': 'x'}, None, 'ok', None)
    first = renderer.cache_key(scope, result)
    assert sorted(reads) == ['app-abc.js', 'font.otf', 'render.html']
    reads.clear()
    assert renderer.cache_key(scope, result) == first and reads == []
    (dist / 'assets/app-abc.js').write_text('two, a new build')
    assert renderer.cache_key(scope, result) != first and sorted(reads) == ['app-abc.js', 'render.html']


def test_font_sidecar_replaced_by_a_link_is_refused_after_a_cached_check(tmp_path):
    import hashlib, json
    dist, font = build_fixture(tmp_path)
    woff = dist / 'render-font.woff2'
    woff.write_bytes(b'wOF2' + b'\1' * 32)
    digest = lambda data: hashlib.sha256(data).hexdigest()
    (dist / 'render-font.json').write_text(json.dumps(dict(schema_version=1, source_sha256=digest(font.read_bytes()),
        woff2_sha256=digest(woff.read_bytes()), source_bytes=len(font.read_bytes()), woff2_bytes=len(woff.read_bytes()),
        glyph_count=1, cmap_sha256='0' * 64, glyph_order_sha256='0' * 64, hmtx_sha256='0' * 64, outline_tag='CFF ',
        outline_sha256='0' * 64, fonttools_version='4.0')))
    renderer = BrowserRenderer(dist_path=str(dist), font_path=str(font))
    assert renderer._font_resource() == (woff, 'font/woff2')
    copy = tmp_path / 'elsewhere.woff2'
    copy.write_bytes(woff.read_bytes())
    woff.unlink()
    try:
        woff.symlink_to(copy)
    except OSError:
        pytest.skip('Host does not permit creating file symlinks')
    assert renderer._font_resource() == (font, 'font/ttf')


def test_notice_snapshot_carries_the_help_group_game_and_rejects_anything_else():
    from game_assistant.qq.presentation import help_document, message
    from game_assistant.qq.render_snapshot import notice_snapshot
    snap=notice_snapshot(help_document(),NOW)
    assert [s.get('game') for s in snap['display_data']['sections']][-3:]==['wuthering_waves','nte','endfield']
    assert all('game' not in s for s in snap['display_data']['sections'][:5])
    assert 'game' not in str(notice_snapshot(message('nte','授权状态','请在网站重新授权。'),NOW)['display_data'])
    for bad in ({'game':'all'},{'game':'lol'},{'tone':'red'}):
        broken=dict(snap,display_data=dict(snap['display_data'],sections=[dict(snap['display_data']['sections'][0],**bad)]))
        with pytest.raises(RenderingUnavailable):validate_snapshot(broken)
