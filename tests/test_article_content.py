import json

import httpx
import respx
import pytest

from game_assistant.adapters.neverness.tajiduo import parse_official_posts
from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability, FetchResult
from game_assistant.scheduler import PollingScheduler
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry
from game_assistant.adapters.base import BaseGameAdapter


@respx.mock
async def test_malformed_detail_is_isolated_from_other_articles():
    respx.post('https://api.kurobbs.com/forum/companyEvent/findEventList').respond(200, json={'code': 200, 'data': {'list': [{'postId': '42', 'postTitle': '正常公告'}, {'postId': '43', 'postTitle': '异常公告'}]}})
    def detail(request):
        if 'postId=42' in request.content.decode():
            return httpx.Response(200, json={'code': 200, 'data': {'postDetail': {'postId': '42', 'postH5Content': '<p>完整正文</p>'}}})
        return httpx.Response(200, json={'code': 200, 'data': ['unexpected']})
    respx.post('https://api.kurobbs.com/forum/getPostDetail').mock(side_effect=detail)
    adapter, cap = WutheringWavesAdapter(Settings(wuwa_token='synthetic', wuwa_user_id='42')), Capability.ANNOUNCEMENT
    result = await adapter.fetch(cap)
    assert result.ok
    assert result.payload[0].body == '完整正文'
    assert result.payload[1].content_status == 'error'


def test_tajiduo_retains_full_text_separate_from_excerpt_and_ignores_executable_html():
    body = '<p>第一段正文</p><script>秘密脚本()</script><p>' + '后续内容' * 100 + '</p>'
    item = parse_official_posts({'data': {'posts': [{'postId': 42, 'subject': '版本更新说明', 'content': body}]}})[0]
    assert '后续内容' * 100 in item.body
    assert '秘密脚本' not in item.body
    assert len(item.summary) < len(item.body)
    assert item.content_status == 'full'


@respx.mock
async def test_wuwa_enriches_each_list_article_and_keeps_list_on_one_failed_detail():
    respx.post('https://api.kurobbs.com/forum/companyEvent/findEventList').respond(200, json={'code': 200, 'data': {'list': [{'postId': '42', 'postTitle': '角色活动唤取'}, {'postId': '43', 'postTitle': '维护公告'}]}})
    def detail(request):
        if 'postId=42' in request.content.decode():
            return httpx.Response(200, json={'code': 200, 'data': {'postDetail': {'postId': '42', 'postH5Content': '<p>正文第一段</p><p>正文最后一段</p>'}}})
        return httpx.Response(503)
    respx.post('https://api.kurobbs.com/forum/getPostDetail').mock(side_effect=detail)
    adapter = WutheringWavesAdapter(Settings(wuwa_token='synthetic', wuwa_user_id='42'))
    result = await adapter.fetch(Capability.ANNOUNCEMENT)
    assert result.ok and len(result.payload) == 2
    assert result.payload[0].body == '正文第一段\n正文最后一段'
    assert result.payload[0].summary
    assert result.payload[1].content_status == 'error'
    assert result.payload[1].title == '维护公告'


async def test_partial_refresh_retains_last_successful_body_without_overwriting_fresh_title(tmp_path):
    settings = Settings(db_path=str(tmp_path / 'game.db'))
    store = SnapshotStore(settings.db_path)
    store.save('fake', 'announcement', json.dumps([{'id': '42', 'title': '旧标题', 'url': 'https://example.com/42', 'body': '已有完整正文', 'summary': '已有节选', 'content_status': 'full'}]))
    adapter = BaseGameAdapter()
    adapter.game_id = 'fake'
    async def fetch():
        return FetchResult(ok=True, payload=[{'id': '42', 'title': '新标题', 'url': 'https://example.com/42', 'body': '', 'content_status': 'error', 'content_error': '正文读取失败'}])
    adapter.fetch_announcement = fetch
    adapter.capabilities = [Capability.ANNOUNCEMENT]
    scheduler = PollingScheduler(FakeRegistry(adapter), store, settings)
    assert (await scheduler.poll_once('fake', Capability.ANNOUNCEMENT)).ok
    row = json.loads(store.get('fake', 'announcement')['payload'])[0]
    assert row['title'] == '新标题'
    assert row['body'] == '已有完整正文'
    assert row['content_status'] == 'stale'
    assert row['content_error']


def test_tajiduo_normalizes_native_image_objects_with_plain_text_placeholders():
    item = parse_official_posts({'data': {'posts': [{'postId': 514677,
        'subject': '轨外之境「澄明环线」特别路线即将开启', 'content': '[图片]\n活动正文',
        'images': [{'url': '//bbs-upload.tajiduo.com/source.jpeg', 'width': 1920},
                   {'url': 'javascript:bad'}, {'url': 'https://bbs-upload.tajiduo.com/source.jpeg'},
                   {'url': 'https://user:password@example.com/private.jpeg'}]}]}})[0]
    assert item.images == ['https://bbs-upload.tajiduo.com/source.jpeg']
    assert item.body == '[图片]\n活动正文'


@respx.mock
async def test_wuwa_keeps_list_cover_on_successful_or_failed_detail():
    respx.post('https://api.kurobbs.com/forum/companyEvent/findEventList').respond(200, json={
        'code': 200, 'data': {'list': [
            {'postId': '42', 'postTitle': '活动', 'coverUrl': '//img.kurobbs.com/42.jpg'},
            {'postId': '43', 'postTitle': '维护', 'coverUrl': 'https://img.kurobbs.com/43.jpg'}]}})
    def detail(request):
        if 'postId=42' in request.content.decode():
            return httpx.Response(200, json={'code': 200, 'data': {'postDetail': {
                'postId': '42', 'postH5Content': '<p>完整正文</p><img src="https://img.kurobbs.com/body.jpg">'}}})
        return httpx.Response(503)
    respx.post('https://api.kurobbs.com/forum/getPostDetail').mock(side_effect=detail)
    result = await WutheringWavesAdapter(Settings()).fetch(Capability.ANNOUNCEMENT)
    assert result.ok
    assert result.payload[0].images == ['https://img.kurobbs.com/42.jpg', 'https://img.kurobbs.com/body.jpg']
    assert result.payload[1].images == ['https://img.kurobbs.com/43.jpg']
    assert result.payload[1].content_status == 'error'
