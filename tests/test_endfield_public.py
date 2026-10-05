import json
from datetime import datetime, timezone

import pytest

from game_assistant.endfield_public import (
    EndfieldPublicService, PublicSourceError, _detail, _news_list,
    _detail_content,
)


def flight(value):
    return '<script>self.__next_f.push([1,' + json.dumps(value, ensure_ascii=False) + '])</script>'


def test_official_next_flight_parsing():
    now = int(datetime.now(timezone.utc).timestamp())
    page = flight('6:{"value":{"bulletins":[{"cid":"2653","title":"「雪凇幽梦」版本更新说明","displayTime":' +
                  str(now) + ',"tab":"notices"}]}}')
    assert _news_list(page)[0]['url'].endswith('/news/2653')
    detail = flight('6:{"value":{"bulletin":{"cid":"2653"}}}') + flight(
        '<h3>■ 更新维护时间</h3><p>2026/09/02 06:00 - 2026/09/02 12:00</p>'
        '<p>1.「冬猎」特许寻访</p><p>· 开放时间：2026/09/02 12:00 - 2026/09/30 11:59</p>')
    assert '1.「冬猎」特许寻访' in _detail(detail)
    with pytest.raises(PublicSourceError):
        _news_list('<html>not a Next page</html>')


@pytest.mark.parametrize('reference', [False, True])
def test_detail_reassembles_split_flight_and_reads_only_the_article_html(reference):
    body = '<p>完整活动说明正文</p><p>最后一段报名条件😀</p><img src="https://web.hycdn.cn/a.png">'
    value = '6:' + json.dumps({'bulletin': {'cid': '5987', 'title': '不应出现在正文的元数据', 'data': '$9' if reference else body}}, ensure_ascii=False, separators=(',', ':'))
    if reference:
        value += '\n9:T' + format(len(body.encode('utf-8')), 'x') + ',' + body + '\na:metadata after article'
    page = ''.join(flight(value[i:i+50]) for i in range(0, len(value), 50))
    result = _detail_content(page, '5987')
    assert result['body'] == '完整活动说明正文\n最后一段报名条件😀'
    assert result['images'] == ['https://web.hycdn.cn/a.png']
    assert result['content_status'] == 'full'


async def test_refresh_retains_notice_full_text_and_enriches_other_articles_independently(tmp_path):
    from types import SimpleNamespace
    service = EndfieldPublicService(str(tmp_path / 'game.db'))
    now = int(datetime.now(timezone.utc).timestamp())
    page = flight('6:' + json.dumps({'bulletins': [
        {'cid': '2653', 'title': '「雪凇幽梦」版本更新说明', 'displayTime': now, 'tab': 'notices'},
        {'cid': '2654', 'title': '社区创作征集', 'displayTime': now, 'tab': 'events'},
        {'cid': '2655', 'title': '其他资讯', 'displayTime': now, 'tab': 'news'},
    ]}, ensure_ascii=False, separators=(',', ':')))
    notice = flight('6:{"bulletin":{"cid":"2653"}}') + flight('<p>「雪凇幽梦」版本更新说明</p><p>■ 更新维护时间</p><p>2026/09/02 06:00 - 2026/09/02 12:00</p><p>1.「冬猎」特许寻访</p><p>· 开放时间：2026/09/02 12:00 - 2026/09/30 11:59</p>')
    community = flight('6:{"bulletin":{"cid":"2654"}}') + flight('<p>社区创作征集完整正文</p><p>报名条件与作品要求，最后一段说明。</p>')
    async def request(url, params=None):
        if url.endswith('/2653'): return SimpleNamespace(text=notice)
        if url.endswith('/2654'): return SimpleNamespace(text=community)
        if url.endswith('/2655'): raise PublicSourceError('正文暂时不可访问')
        return SimpleNamespace(text=page)
    service._request = request
    result = await service.public(force=True)
    rows = result['news']['items']
    assert len(rows) == 3
    assert '冬猎' in rows[0]['body'] and rows[0]['content_status'] == 'full'
    assert '最后一段' in rows[1]['body']
    assert rows[2]['content_status'] == 'error'
    assert result['calendar']['version'] == '雪凇幽梦'
    previous_calendar_at = result['calendar']['fetched_at']
    async def notice_failure(url, params=None):
        if url.endswith('/2653'): raise PublicSourceError('正文暂时不可访问')
        return await request(url, params)
    service._request = notice_failure
    failed = await service.public(force=True)
    assert failed['news']['items'][0]['content_status'] == 'stale'
    assert failed['calendar']['fetched_at'] == previous_calendar_at
    assert failed['calendar']['stale'] and failed['calendar']['error']
    service.close()


@pytest.mark.parametrize('cached', [False, True])
async def test_news_updates_when_calendar_notice_detail_fails(tmp_path, cached):
    from types import SimpleNamespace
    service = EndfieldPublicService(tmp_path / 'game.db')
    if cached:
        service._put('calendar', {'version': '旧版本', 'events': [{'name': '旧活动'}]})
    now = int(datetime.now(timezone.utc).timestamp())
    page = flight('6:' + json.dumps({'bulletins': [
        {'cid': '1', 'title': '版本更新说明', 'displayTime': now, 'tab': 'notices'},
        {'cid': '2', 'title': '创作征集', 'displayTime': now, 'tab': 'events'},
    ]}, ensure_ascii=False, separators=(',', ':')))
    async def request(url, params=None):
        if url.endswith('/1'): raise PublicSourceError('正文不可访问')
        if url.endswith('/2'): return SimpleNamespace(text=flight('6:{"bulletin":{"cid":"2"}}') + flight('<p>新的创作征集全文</p>'))
        return SimpleNamespace(text=page)
    service._request = request
    result = await service.public(force=True)
    assert len(result['news']['items']) == 2
    assert result['news']['items'][1]['body'] == '新的创作征集全文'
    assert result['news']['error'] is None
    assert result['calendar']['error'] and result['calendar']['stale']
    assert result['calendar']['events'] == ([{'name': '旧活动'}] if cached else [])
    service.close()


@pytest.mark.asyncio
async def test_news_stale_cache_and_force_refresh(tmp_path):
    service = EndfieldPublicService(str(tmp_path / 'db.sqlite3'))
    service._put('news', [{'id': '1', 'title': '旧公告'}])
    service._put('calendar', {'version': '旧版本', 'events': [{'name': '旧活动'}]})

    async def failure():
        raise PublicSourceError('官网暂时不可访问')

    service._refresh_news = failure
    result = await service.public(force=True)
    assert result['news']['stale'] is True
    assert result['news']['items'][0]['title'] == '旧公告'
    assert result['calendar']['events'][0]['name'] == '旧活动'
    with pytest.raises(PublicSourceError, match='官网暂时不可访问'):
        await service.news(force=True)


@pytest.mark.asyncio
async def test_map_catalog_filter_pagination_and_stale(tmp_path):
    service = EndfieldPublicService(str(tmp_path / 'db.sqlite3'))
    tree = {'code': 0, 'data': {'maps': [{'id': 'map01', 'name': '四号谷地',
                                        'levels': [{'id': 'map01_lv001', 'name': '枢纽区'}]}]}}
    catalog = {'code': 0, 'data': {'mainTypes': [{'id': 'main', 'name': '资源', 'subTypes': [
        {'id': 'plant', 'name': '植物', 'templateIds': ['template1']}]}]}}
    points = {'code': 0, 'data': {'marks': [
        {'id': 'mark1', 'templateId': 'template1', 'pos': {'x': 1, 'y': 2, 'z': 3},
         'levelId': 'map01_lv001'},
        {'id': 'mark2', 'templateId': 'template1', 'pos': {'x': 4, 'y': 5, 'z': 6},
         'levelId': 'map01_lv001'}],
        'markTemplates': [{'id': 'template1', 'name': '晶化多齿叶', 'desc': '野外采集'}]}}

    async def fetch(path, params=None):
        assert not params or params == {'mapId': 'map01', 'levelId': 'map01_lv001'}
        return {'tree': tree, 'catalog': catalog, 'mark/list': points}[path]

    service._map_json = fetch
    result = await service.map(map_id='map01', q='多齿叶', type_id='plant', offset=1, limit=1)
    assert result['total'] == 2
    assert result['marks'][0]['id'] == 'mark2'
    assert result['marks'][0]['z'] == 6
    assert result['level_id'] == 'map01_lv001'

    # Force an expired cache, then verify that a source failure preserves it.
    service.conn.execute("UPDATE cache SET fetched_at='2000-01-01T00:00:00+00:00'")
    service.conn.commit()

    async def failed(path, params=None):
        raise PublicSourceError('官方地图暂时无法读取')

    service._map_json = failed
    stale = await service.map(map_id='map01', q='多齿叶', type_id='plant')
    assert stale['stale'] is True
    assert stale['total'] == 2
    assert stale['marks'][0]['name'] == '晶化多齿叶'


@pytest.mark.asyncio
async def test_mark_info_keeps_last_good_detail(tmp_path):
    service = EndfieldPublicService(str(tmp_path / 'db.sqlite3'))

    async def fetch(path, params=None):
        assert path == 'mark/info'
        assert params == {'mapId': 'map01', 'markId': 'mark1'}
        return {'code': 0, 'data': {'info': {'id': 'mark1', 'mapId': 'map01',
                                           'pos': {'x': 1, 'y': 2, 'z': 3},
                                           'typeSub': {'id': 'plant', 'name': '植物'}}}}

    service._map_json = fetch
    result = await service.map_mark_info('map01', 'mark1')
    assert result['info']['typeSub']['name'] == '植物'
    service.conn.execute("UPDATE cache SET fetched_at='2000-01-01T00:00:00+00:00'")
    service.conn.commit()

    async def failed(path, params=None):
        raise PublicSourceError('官方地图暂时无法读取')

    service._map_json = failed
    stale = await service.map_mark_info('map01', 'mark1')
    assert stale['stale'] is True
    assert stale['info']['pos']['z'] == 3


async def test_failed_explicit_refresh_remains_stale_on_following_reads_and_restart(tmp_path, monkeypatch):
    service = EndfieldPublicService(tmp_path / 'a.db')
    service._put('news', [{'title': '已缓存公告'}])
    original_at = service._put('calendar', {'version': '旧缓存版本', 'events': [{'name': '活动'}]})
    attempts = []

    async def fail():
        attempts.append(True)
        raise PublicSourceError('官网暂时不可用')

    monkeypatch.setattr(service, '_refresh_news', fail)
    assert (await service.public(force=True))['news']['stale']
    following = await service.public()
    assert following['calendar']['stale']
    assert following['calendar']['fetched_at'] == original_at
    with pytest.raises(PublicSourceError, match='官网暂时不可用'):
        await service.events()
    restored = EndfieldPublicService(tmp_path / 'a.db')
    restored_read = await restored.public()
    assert restored_read['calendar']['stale'] and restored_read['calendar']['error'] == '官网暂时不可用'
    assert len(attempts) == 1

    async def recover():
        service._put('news', [{'title': '更新公告'}])
        service._put('calendar', {'version': '新版本', 'events': []})

    monkeypatch.setattr(service, '_refresh_news', recover)
    assert not (await service.public(force=True))['calendar']['stale']
