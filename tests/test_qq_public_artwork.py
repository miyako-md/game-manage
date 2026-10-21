"""Cached public artwork ownership, resolution and renderer delivery boundaries."""
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock

from PIL import Image
import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq import assets
from game_assistant.qq.browser_rendering import BrowserRenderer, validate_snapshot
from game_assistant.qq import render_snapshot as shared
from game_assistant.qq.models import QqIdentity
from game_assistant.qq.query_routes import QqQueryService
from game_assistant.qq.rendering import RenderedImage
from game_assistant.qq.public_asset_catalog import CATALOG

NOW=datetime.fromisoformat('2026-10-17T12:00:00+08:00')
COVER='https://bbs-upload.tajiduo.com/version.jpg'
ICON='https://webstatic.tajiduo.com/icon.png'


def row(payload, stamp='2026-10-17T11:00:00+08:00'):
    return QueryResult(payload,stamp,'ok',True)


def png(size):
    output=BytesIO();Image.new('RGB',size,'#c75b3d').save(output,'PNG');return output.getvalue()


@pytest.mark.parametrize('event,article,matched',[
    ({'source_url':'https://bbs-api.tajiduo.com/bbs/wapi/getPostFull?postId=42'},
     {'url':'https://bbs.tajiduo.com/forum/post/42'},True),
    ({'source_url':'https://www.kurobbs.com/forum/post/42'},
     {'original_links':[{'url':'https://www.kurobbs.com/forum/post/42'}]},True),
    ({'source_post_id':'42','source':'official'},{'id':42,'source':'official'},True),
    ({'source_post_id':'42','source':'official'},{'id':42,'source':'other'},False),
    ({'source_url':'https://bbs.tajiduo.com/forum/post/43','source_post_id':'42'},
     {'url':'https://bbs.tajiduo.com/forum/post/42','id':42},False),
    ({'source_url':'https://evil.invalid/post/43','source_post_id':'42'},
     {'url':'https://bbs.tajiduo.com/forum/post/42','id':42},False),
    ({'name':'相同标题','start_at':NOW.isoformat()},
     {'title':'相同标题','published_at':NOW.isoformat()},False),
])
def test_event_cover_requires_explicit_noncontradictory_source(event,article,matched):
    original=row([{'name':'活动',**event}])
    enriched=shared.events_with_artwork(original,row([{**article,'cover_url':COVER}]))
    assert enriched.payload[0].get('image_urls',[])==([COVER] if matched else [])
    assert 'image_urls' not in original.payload[0]
    snapshot=shared.calendar_snapshot({'nte':enriched},NOW)
    assert validate_snapshot(snapshot)==snapshot
    assert list(shared.asset_requests(snapshot))==([(COVER,'artwork')] if matched else [])


@pytest.mark.parametrize('version,source,matched',[
    ('1.4','start_source',True),('1.5','start_source',False),('1.4','end_source',False),
])
def test_version_cover_uses_only_exact_version_and_declared_start_notice(version,source,matched):
    event={'name':'版本活动','version':version,'version_metadata':{
        'id':'1.4',source:{'url':'https://bbs.tajiduo.com/forum/post/42'},
    }}
    enriched=shared.events_with_artwork(row([event]),row([{'url':'https://bbs.tajiduo.com/forum/post/42','image_urls':[COVER]}]))
    assert enriched.payload[0].get('image_urls',[])==([COVER] if matched else [])


def test_snapshot_version_metadata_can_supply_its_explicit_start_notice():
    @dataclass(frozen=True)
    class Versioned:
        payload:list
        fetched_at:str
        state:str
        complete:bool
        version_metadata:dict
    events=Versioned([{'name':'版本活动','version':'1.4'}],NOW.isoformat(),'ok',True,
        {'id':'1.4','start_source':{'source_post_id':'42'}})
    enriched=shared.events_with_artwork(events,row([{'id':'42','banner':COVER}]))
    assert enriched.payload[0]['image_urls']==[COVER]
    assert shared.calendar_snapshot({'nte':enriched},NOW)['display_data']['snapshots']['nte']['events']['payload'][0]['image_urls']==[COVER]


def test_event_images_keep_safe_direct_artwork_without_inventing_artwork_for_missing_sources():
    original=row([{'name':'有图活动','image_urls':[COVER,'https://evil.invalid/image.png',COVER]}, {'name':'无图活动'}])
    projected=shared.calendar_snapshot({'nte':shared.events_with_artwork(original,row([]))},NOW)
    events=projected['display_data']['snapshots']['nte']['events']['payload']
    assert events[0]['image_urls']==[COVER] and 'image_urls' not in events[1]
    assert [event['name'] for event in events]==['有图活动','无图活动']


async def test_artwork_and_icon_cache_are_separate_bounded_resolutions(monkeypatch):
    cache=assets.PublicAssetCache()
    artwork=cache.register_url(COVER,artwork=True)
    icon=cache.register_url(COVER)
    assert artwork and icon and artwork!=icon
    assert cache.register_url(COVER,artwork=True,portrait=True) is None
    assert cache.get_url_png(COVER,artwork=True) is None
    async def download(url,**kwargs):return png((1600,900))
    monkeypatch.setattr(assets,'_download',download)
    await cache.prefetch([artwork,icon],budget_seconds=2)
    assert cache.get_image(artwork).size==(1080,608)
    assert cache.get_image(icon).size==(192,108)
    assert cache.get_url_png(COVER,artwork=True)==cache.get_png(artwork)
    assert cache.get_url_png(COVER)==cache.get_png(icon)
    assert cache.url_fingerprint(COVER,artwork=True)!=cache.url_fingerprint(COVER)
    assert cache._bytes<=cache.cache_bytes
    await cache.aclose()


@pytest.mark.parametrize('url',['https://evil.invalid/banner.jpg','https://bbs-upload.tajiduo.com/banner.jpg?token=secret',
    'https://127.0.0.1/banner.jpg','https://bbs-upload.tajiduo.com/banner.svg'])
def test_artwork_mode_keeps_the_same_url_allowlist(url):
    assert assets.PublicAssetCache().register_url(url,artwork=True) is None


def test_artwork_mode_keeps_source_byte_pixel_and_animation_limits():
    with pytest.raises(ValueError,match='size_limit'):assets.sanitize_image(b'a'*(assets.MAX_ARTWORK_DOWNLOAD_BYTES+1),artwork=True)
    with pytest.raises(ValueError,match='pixels_or_animation'):assets.sanitize_image(png((4001,3000)),artwork=True)
    source=BytesIO();Image.new('RGB',(10,10),'red').save(source,'PNG',save_all=True,
        append_images=[Image.new('RGB',(10,10),'blue')],duration=100,loop=0)
    with pytest.raises(ValueError,match='pixels_or_animation'):assets.sanitize_image(source.getvalue(),artwork=True)


def test_artwork_registration_eviction_removes_its_mode_bookkeeping():
    cache=assets.PublicAssetCache()
    ref=cache.register_url(COVER,artwork=True)
    for index in range(2048):cache.register_url(f'https://bbs-upload.tajiduo.com/cover{index}.png')
    assert ref not in cache._sources and ref not in cache._artwork_refs


@pytest.mark.parametrize('game,payload,expected',[
    ('wuthering_waves',{'name':'今汐'},('role','今汐')),
    ('wuthering_waves',{'name':'苍鳞千嶂'},('weapon','苍鳞千嶂')),
    ('nte',{'reward_id':'fork_yuren'},('weapon','fork_yuren')),
    ('nte',{'item_id':'1003'},('role','1003')),
    ('endfield',{'name':'佩丽卡'},('role','佩丽卡')),
    ('endfield',{'name':'破碎君王'},('weapon','破碎君王')),
    ('endfield',{'name':'玉中身'},('weapon','玉中身')),
    ('nte',{'item_id':'1057'},('role','1057')),
    ('wuthering_waves',{'name':'莉莉'},('role','莉莉')),
    ('wuthering_waves',{'name':'玉阙玄华'},('weapon','玉阙玄华')),
])
def test_public_catalog_images_used_by_gacha_components_are_prefetched(game,payload,expected):
    snapshot={'game':game,'display_data':payload}
    url=CATALOG['games'][game][expected[0]][expected[1]]
    assert (url,'portrait' if expected[0]=='portrait' else 'icon') in set(shared.asset_requests(snapshot))
    assert not list(shared.asset_requests({'game':game,'display_data':{'name':'PRIVATE-ACCOUNT','account_id':'佩丽卡'}}))


def test_selected_nte_weapon_skill_and_endfield_component_images_are_in_prefetch():
    nte=row({'schema_version':1,'entries':[{'id':'1003','name':'早雾','weapon':{'name':'勿忘伞'},
        'skills':[{'id':'skill-999','name':'鬼郎丸头锤','level':0}]}]})
    requests=set(shared.asset_requests(shared.role_snapshot('nte',nte,NOW,resolved_id='1003')))
    assert (CATALOG['games']['nte']['weapon']['勿忘伞'],'icon') in requests
    assert (CATALOG['games']['nte']['skill']['1003::鬼郎丸头锤'],'icon') in requests
    icon='https://web.hycdn.cn/endfield/weapon.png'
    panel=shared.game_panel('endfield','skland','operator_detail',row({'operator_detail':{'name':'佩丽卡','weapon':{'icon_url':icon}}}))
    assert (icon,'icon') in set(shared.asset_requests(shared.game_snapshot([panel],NOW)))


async def test_cached_news_is_read_for_images_and_participates_in_snapshot_fingerprints():
    calls=[];captured=[];news_stamp=['2026-10-17T10:00:00+08:00']
    event={'name':'缓存活动','source_post_id':'42','start_at':'2026-10-01T00:00:00+08:00','end_at':'2026-11-01T00:00:00+08:00'}
    def read(game,cap):
        calls.append((game,cap))
        return row([event]) if cap=='events' else row([{'id':'42','image_url':COVER}],news_stamp[0])
    class Queue:
        async def render(self,scope,result,**kwargs):
            captured.append(result.payload)
            return RenderedImage(png((720,100)))
    api=QqQueryService(None,None,SimpleNamespace(read=read),render_queue=Queue(),clock=lambda:NOW)
    identity=QqIdentity('app','group','g','s')
    plain=api.query(identity,'calendar','nte')
    assert calls==[('nte','events')] and '缓存活动' in plain['text']
    for stamp in ('2026-10-17T10:00:00+08:00','2026-10-17T11:00:00+08:00'):
        news_stamp[0]=stamp
        reply=await api.query_reply(identity,'calendar','nte',image_requested=True,budget_seconds=10)
        assert 'image' in reply
    assert captured[0]['snapshot_fingerprints']!=captured[1]['snapshot_fingerprints']
    assert captured[0]['render_snapshot']['display_data']['snapshots']['nte']['events']['payload'][0]['image_urls']==[COVER]
    assert calls.count(('nte','news'))==2


async def test_browser_route_serves_prepared_cover_at_artwork_resolution(monkeypatch):
    from tests.test_qq_browser_image_encoding import renderer_boundary
    renderer,context,result,_,_=renderer_boundary(monkeypatch,{'png':200})
    cache=assets.PublicAssetCache()
    ref=cache.register_url(COVER,artwork=True)
    cache._store(ref,assets.sanitize_image(png((1600,900)),artwork=True))
    renderer.asset_cache=cache
    result.payload['render_snapshot']['display_data']['snapshots']['nte']['events']['payload']=[{'name':'封面活动','image_urls':[COVER]}]
    await renderer.render_summary_async(AccountScope('u','a','r'),result,budget_seconds=10)
    route=SimpleNamespace(request=SimpleNamespace(url=COVER,method='GET',resource_type='image'),fulfill=AsyncMock(),abort=AsyncMock())
    await context.route.call_args.args[1](route)
    supplied=route.fulfill.call_args.kwargs
    assert supplied['content_type']=='image/png'
    with Image.open(BytesIO(supplied['body'])) as image:assert image.size==(1080,608)
    route.abort.assert_not_awaited()


async def test_newly_available_public_artwork_changes_the_browser_cache_key(monkeypatch,tmp_path):
    from tests.test_qq_browser_image_encoding import renderer_boundary
    renderer,_,result,_,_=renderer_boundary(monkeypatch,{'png':200})
    (tmp_path/'render.html').write_text('<!doctype html>');renderer.dist=tmp_path
    monkeypatch.setattr(renderer,'cache_key',BrowserRenderer.cache_key.__get__(renderer))
    result.payload['text']='摘要'
    result.payload['render_snapshot']['display_data']['snapshots']['nte']['events']['payload']=[{'name':'活动','image_urls':[COVER]}]
    renderer.asset_cache=assets.PublicAssetCache()
    scope=AccountScope('u','a','r');before=renderer.cache_key(scope,result)
    ref=renderer.asset_cache.register_url(COVER,artwork=True)
    renderer.asset_cache._store(ref,assets.sanitize_image(png((1600,900)),artwork=True))
    assert renderer.cache_key(scope,result)!=before


def test_endfield_portraits_are_for_roster_cards_and_mounted_loadouts_and_follow_visible_icons():
    portrait=CATALOG['games']['endfield']['portrait']['佩丽卡']
    icon=CATALOG['games']['endfield']['role']['佩丽卡']
    roster=shared.game_panel('endfield','skland','roles',row({'operators':[{'name':'佩丽卡'}]}))
    requests=list(shared.asset_requests(shared.game_snapshot([roster],NOW)))
    assert requests.index((icon,'icon'))<requests.index((portrait,'portrait'))
    ship=shared.game_panel('endfield','skland','ship',row({'operators':[{'name':'佩丽卡'}]}))
    assert (portrait,'portrait') not in list(shared.asset_requests(shared.game_snapshot([ship],NOW)))
    detail=shared.game_panel('endfield','skland','operator_detail',row({'operator_detail':{'name':'佩丽卡'}}))
    requests=list(shared.asset_requests(shared.game_snapshot([detail],NOW)))
    assert requests.index((icon,'icon'))<requests.index((portrait,'portrait'))


async def test_service_prefetches_actual_cover_url_in_artwork_mode_before_render(monkeypatch):
    cache=assets.PublicAssetCache();downloads=[]
    async def download(url,**kwargs):downloads.append(url);return png((1600,900))
    monkeypatch.setattr(assets,'_download',download)
    def read(game,cap):
        return row([{'name':'缓存活动','source_post_id':'42'}]) if cap=='events' else row([{'id':'42','cover_url':COVER}])
    class Queue:
        async def render(self,scope,result,**kwargs):
            assert cache.get_url_png(COVER,artwork=True) is not None
            assert cache.get_url_png(COVER) is None
            return RenderedImage(png((720,100)))
    api=QqQueryService(None,None,SimpleNamespace(read=read),render_queue=Queue(),asset_cache=cache,clock=lambda:NOW)
    reply=await api.query_reply(QqIdentity('app','group','g','s'),'calendar','nte',image_requested=True,budget_seconds=10)
    assert 'image' in reply and downloads==[COVER]
    await cache.aclose()



def test_official_cover_shape_and_three_mib_body_are_artwork_only():
    output=BytesIO();Image.new('RGB',(3840,2160),'#b35027').save(output,'JPEG')
    raw=output.getvalue()
    padded=raw.ljust(3*1024*1024,b'\0')
    with Image.open(BytesIO(assets.sanitize_image(padded,artwork=True))) as image:
        assert image.size==(1080,608) and image.format=='PNG'
    for source in (raw,padded):
        for options in ({},{'portrait':True}):
            with pytest.raises(ValueError,match='size_limit|pixels_or_animation'):
                assets.sanitize_image(source,**options)


def test_artwork_source_limits_accept_exact_boundaries_and_reject_overflow():
    raw=png((4000,3000))
    with Image.open(BytesIO(assets.sanitize_image(raw,artwork=True))) as image:assert image.size==(1080,810)
    with pytest.raises(ValueError,match='pixels_or_animation'):
        assets.sanitize_image(png((4001,3000)),artwork=True)
    exact=png((720,405)).ljust(assets.MAX_ARTWORK_DOWNLOAD_BYTES,b'\0')
    assert assets.sanitize_image(exact,artwork=True)
    with pytest.raises(ValueError,match='size_limit'):assets.sanitize_image(exact+b'0',artwork=True)


def body_reader(body,mode):
    import asyncio
    reader=asyncio.StreamReader()
    if mode=='length':headers={'content-length':str(len(body))};wire=body
    elif mode=='chunked':
        headers={'transfer-encoding':'chunked'}
        parts=[body[index:index+1024*1024] for index in range(0,len(body),1024*1024)]
        wire=b''.join(f'{len(part):x}\r\n'.encode()+part+b'\r\n' for part in parts)+b'0\r\n\r\n'
    else:headers={};wire=body
    reader.feed_data(wire);reader.feed_eof()
    return reader,headers


@pytest.mark.parametrize('mode',['length','chunked','stream'])
@pytest.mark.parametrize('artwork',[False,True])
async def test_body_reader_three_mib_cover_preserves_icon_cap_in_every_framing(mode,artwork):
    body=b'x'*(3*1024*1024)
    reader,headers=body_reader(body,mode)
    if artwork:assert await assets._read_body(reader,headers,artwork=True)==body
    else:
        with pytest.raises(ValueError,match='size_limit'):await assets._read_body(reader,headers)


@pytest.mark.parametrize('mode',['length','chunked','stream'])
@pytest.mark.parametrize('artwork',[False,True])
async def test_body_reader_exact_limit_and_overflow_are_checked_for_every_mode(mode,artwork):
    limit=assets.MAX_ARTWORK_DOWNLOAD_BYTES if artwork else assets.MAX_DOWNLOAD_BYTES
    body=b'x'*limit
    reader,headers=body_reader(body,mode)
    assert await assets._read_body(reader,headers,artwork=artwork)==body
    reader,headers=body_reader(body+b'x',mode)
    with pytest.raises(ValueError,match='size_limit'):await assets._read_body(reader,headers,artwork=artwork)


@pytest.mark.parametrize('artwork',[False,True])
async def test_cache_download_receives_only_its_registered_artwork_mode(monkeypatch,artwork):
    options=[]
    async def download(url,**kwargs):options.append(kwargs);return png((100,100))
    monkeypatch.setattr(assets,'_download',download)
    cache=assets.PublicAssetCache();ref=cache.register_url(COVER,artwork=artwork)
    await cache.prefetch([ref],budget_seconds=2)
    assert options[0].get('artwork',False)==artwork
    assert cache.get_png(ref)
    await cache.aclose()



def test_real_tajiduo_hash_post_route_matches_cached_cover_without_catalog_guesses():
    url='https://www.tajiduo.com/bbs/index.html#/post?postId=494294'
    event={'name':'早雾','source_url':url,'source_post_id':'494294','source':'community'}
    article={'title':'版本公告','url':url,'id':'494294','source':'community','images':[COVER]}
    enriched=shared.events_with_artwork(row([event]),row([article]))
    assert enriched.payload[0]['image_urls']==[COVER]
    snapshot=shared.calendar_snapshot({'nte':enriched},NOW)
    assert list(shared.asset_requests(snapshot))==[(COVER,'artwork')]
    assert shared.safe_article_url(url)==url
    assert not list(shared.asset_requests(shared.calendar_snapshot({'nte':row([{'name':'早雾'}])},NOW)))


@pytest.mark.parametrize('url',[
    'https://www.tajiduo.com/other.html#/post?postId=494294',
    'https://www.tajiduo.com/bbs/index.html#/post?postId=494294&token=secret',
    'https://www.tajiduo.com/bbs/index.html#/post?postId=evil',
    'https://www.tajiduo.com/bbs/index.html#/post?postId=494294#other',
    'https://www.tajiduo.com/bbs/index.html#/other?postId=494294',
    'https://www.tajiduo.com/bbs/index.html?token=secret#/post?postId=494294',
    'https://www.tajiduo.com.evil.invalid/bbs/index.html#/post?postId=494294',
    'http://www.tajiduo.com/bbs/index.html#/post?postId=494294',
])
def test_tajiduo_fragment_identity_does_not_broaden_article_or_image_rules(url):
    assert shared.safe_article_url(url) is None
    assert shared._source_key(url) is None
    assert assets.safe_public_url(url) is None
    assert 'image_urls' not in shared.events_with_artwork(row([{'name':'早雾','source_url':url,'source_post_id':'494294'}]),
        row([{'id':'494294','url':'https://bbs.tajiduo.com/forum/post/494294','image_url':COVER}])).payload[0]


@pytest.mark.parametrize('cap',['events','recent_events'])
def test_public_event_names_never_request_character_catalog_art(cap):
    panel=shared.game_panel('nte','public',cap,row([{'name':'早雾','title':'勿忘伞'}]))
    assert not list(shared.asset_requests(shared.game_snapshot([panel],NOW)))



@pytest.mark.parametrize('artwork',[False,True])
async def test_http_download_passes_artwork_limit_to_body_reader_without_widening_icons(monkeypatch,artwork):
    import asyncio
    import socket
    body=b'x'*(3*1024*1024)
    reader=asyncio.StreamReader()
    reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Type: image/jpeg\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body)
    reader.feed_eof()
    loop=asyncio.get_running_loop()
    async def dns(*args,**kwargs):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('1.1.1.1',443))]
    class Writer:
        def write(self,data):pass
        async def drain(self):pass
        def close(self):pass
    async def connect(host,port,**kwargs):
        assert host=='1.1.1.1' and port==443 and kwargs['server_hostname']=='bbs-upload.tajiduo.com'
        return reader,Writer()
    monkeypatch.setattr(loop,'getaddrinfo',dns)
    monkeypatch.setattr(assets.asyncio,'open_connection',connect)
    if artwork:assert await assets._download(COVER,artwork=True,timeout_seconds=.5)==body
    else:
        with pytest.raises(ValueError,match='size_limit'):await assets._download(COVER,timeout_seconds=.5)



@pytest.mark.parametrize('mode,options,remaining,expected',[
    ('artwork',{},8,5),('icon',{},8,3),('portrait',{},8,3),
    ('artwork',{'artwork_request_timeout':.25},8,.25),
    ('artwork',{'request_timeout':.25},8,5),
    ('icon',{'artwork_request_timeout':.25},8,3),
    ('artwork',{},.1,.1),('icon',{},.1,.1),('portrait',{},.1,.1),
    ('artwork',{'artwork_request_timeout':99},8,5),
])
async def test_asset_download_timeout_is_mode_specific_and_bounded_by_remaining_budget(monkeypatch,mode,options,remaining,expected):
    captured=[]
    async def download(url,**kwargs):captured.append(kwargs);return png((100,100))
    monkeypatch.setattr(assets,'_download',download)
    monkeypatch.setattr(assets,'time',SimpleNamespace(monotonic=lambda:100))
    cache=assets.PublicAssetCache(**options)
    ref=cache.ref_for('endfield','portrait','佩丽卡') if mode=='portrait' else cache.register_url(COVER,artwork=mode=='artwork')
    await cache._fetch(ref,100+remaining)
    assert captured[0]['timeout_seconds']==pytest.approx(expected)
    assert captured[0].get('artwork',False)==(mode=='artwork')
    assert cache.get_png(ref)
    await cache.aclose()


async def test_artwork_prefetch_keeps_existing_total_five_second_deadline(monkeypatch):
    captured=[]
    async def download(url,**kwargs):captured.append(kwargs);return png((100,100))
    monkeypatch.setattr(assets,'_download',download)
    monkeypatch.setattr(assets,'time',SimpleNamespace(monotonic=lambda:100))
    cache=assets.PublicAssetCache()
    await cache.prefetch([cache.register_url(COVER,artwork=True)],budget_seconds=10)
    assert captured[0]['timeout_seconds']==5
    await cache.aclose()


async def test_expired_artwork_budget_starts_no_download_or_retry(monkeypatch):
    download=AsyncMock()
    monkeypatch.setattr(assets,'_download',download)
    monkeypatch.setattr(assets,'time',SimpleNamespace(monotonic=lambda:100))
    cache=assets.PublicAssetCache()
    await cache._fetch(cache.register_url(COVER,artwork=True),100)
    download.assert_not_awaited()
    await cache.aclose()


def test_gacha_projection_keeps_public_reward_identity_for_cold_cache_images():
    source=row({'gold':[{'name':'Sanhua','resource_id':'1102','resource_type':'角色','token':'PRIVATE'}]})
    snapshot=shared.gacha_snapshot('wuthering_waves',source,NOW)
    entry=snapshot['display_data']['archive']['gold'][0]
    assert entry=={'name':'Sanhua','resource_id':'1102','resource_type':'角色'}
    assert validate_snapshot(snapshot)==snapshot
    icon=CATALOG['games']['wuthering_waves']['role']['1102']
    assert (icon,'icon') in set(shared.asset_requests(snapshot))


@pytest.mark.parametrize('name,canonical',[('勿 忘伞','勿忘伞'),('「光波眩晕」','光波眩晕')])
def test_nte_projected_gacha_normalizes_only_public_catalog_weapon_names(name,canonical):
    ledger=row({'records':[{'reward_name':name,'reward_type':'arc','reward_id':'unknown','auth_token':'PRIVATE'}]})
    snapshot=shared.gacha_snapshot('nte',row({'schema_version':1,'pools':[]}),NOW,ledger=ledger)
    entry=snapshot['display_data']['ledger']['records'][0]
    assert entry['reward_type']=='arc' and 'auth_token' not in entry
    assert validate_snapshot(snapshot)==snapshot
    icon=CATALOG['games']['nte']['weapon'][canonical]
    assert (icon,'icon') in set(shared.asset_requests(snapshot))


@pytest.mark.parametrize('reward_type',['item','arc',{'name':'unknown'}])
def test_projected_nte_noncharacter_reward_does_not_borrow_a_character_image(reward_type):
    ledger=row({'records':[{'reward_name':'早雾','reward_type':reward_type}]})
    snapshot=shared.gacha_snapshot('nte',row({'schema_version':1,'pools':[]}),NOW,ledger=ledger)
    assert snapshot['display_data']['ledger']['records'][0]['reward_type']==reward_type
    assert not list(shared.asset_requests(snapshot))
