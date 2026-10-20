"""Endfield commands cross the real local image pipeline; external I/O is mocked."""
import base64
import os
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from game_assistant.accounts.models import QueryResult
from game_assistant.cloud_app import create_cloud_app
from game_assistant.config import Settings
from game_assistant.identity.models import Principal
from game_assistant.qq import assets
from game_assistant.qq.client import InternalQqClient, OfficialQqClient, QqReply, valid_reply_image
from game_assistant.qq.models import InboundMessage, QqIdentity
from game_assistant.qq.transport import BotDispatcher, BotState
from tests.test_qq_endfield_cached_details import fixture as scoped_query_fixture
from tests.test_qq_endfield_challenges import synthetic_challenges
from tests.test_qq_endfield_reports import NOW, synthetic_account, synthetic_gacha
from tests.test_qq_endfield_visual_honor import synthetic_honor
from tests.test_qq_unified_queries import no_external_network


@pytest.mark.parametrize('raw,command,title,snapshots', [
    ('终末地 总览', 'summary', '今日总览', 2),
    ('终末地 干员 佩丽卡', 'roles', '佩丽卡', 2),
    ('终末地 练度', 'training', '全员练度', 1),
    ('终末地 地区', 'regions', '地区建设', 1),
    ('终末地 帝江号', 'ship', '帝江号', 1),
    ('终末地 寻访战报', 'gacha', '寻访战报', 1),
    ('终末地 光荣之路', 'honor', '光荣之路', 1),
    ('终末地 挑战', 'combat', '挑战记录', 3),
])
async def test_endfield_commands_render_upload_and_passively_send_once(
        tmp_path, monkeypatch, raw, command, title, snapshots):
    executable=os.environ.get('QQ_RENDER_TEST_EXECUTABLE')
    font=os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:
        pytest.skip('Endfield delivery now uses shared Vue; set QQ_RENDER_TEST_EXECUTABLE and QQ_RENDER_TEST_FONT')
    # Reuse the real scoped cache facade. Its fixture rejects credential loading,
    # service construction and operator upstream calls during a QQ query.
    query, scope, grant, private, scoped = scoped_query_fixture(tmp_path)
    account = synthetic_account()
    account['operators'][0].update(id='c1', name='佩丽卡')
    account['operators'][1]['name'] = '祀'
    account['ship'][0]['operators'][0]['charId'] = 'c1'
    account['achievements'] = synthetic_honor(4)['achievements']
    account['availability']['honor'] = True
    query.data[('sk', 'account')] = QueryResult(account, NOW, 'ok', None)
    query.add('endfield', 'hypergryph', 'hg', {'gacha': synthetic_gacha()})
    query.accounts.describe = lambda checked: {
        **query.describe(checked), 'game': 'endfield',
        'provider': 'skland' if checked.account_id == 'sk' else 'hypergryph',
        'grant_id': grant['id'] if checked.account_id == 'sk' else 'grant-hg',
    }
    scoped._service._operator_cache['c1']['operator']['tactical_item'] = {
        'name': '已观测战术道具', 'rarity': 0,
        'active_effect': '合成效果 {value} 保留原始参数。', 'passive_effect': None,
        'icon_url': None,
    }
    scoped._service._challenge_cache.update({
        (kind, None, None, None): value for kind, value in synthetic_challenges().items()
    })

    app = create_cloud_app(Settings(
        cloud_db_path=str(tmp_path / 'cloud.db'), cloud_allowed_origins=['https://cloud.example'],
        qq_app_id='app', qq_service_token='fixture-service', qq_images_enabled=True,
        qq_image_font_path=font,qq_image_max_bytes=1048576,qq_browser_render_executable_path=executable), start_scheduler=False)
    service = app.state.qq_query
    service.clock = lambda: datetime.fromisoformat(NOW)
    service.query_service = query
    query.accounts._listeners.append(service.invalidate)
    identity = QqIdentity('app', 'group', 'fixture-group', 'fixture-sender')
    with service.bindings.store.connect(write=True) as db:
        db.execute("INSERT INTO users(user_id,username,password_hash) VALUES('u','fixture','fixture')")
    service.bindings.redeem_link_code(identity,
        service.bindings.create_link_code(Principal('u', False))['code'], 'fixture-binding')

    # Mock only the public network boundary; registration, bounded prefetch,
    # sanitization, image fingerprints and renderer asset reads remain real.
    source = BytesIO()
    Image.new('RGBA', (72, 72), (120, 180, 200, 255)).save(source, format='PNG')
    downloads = []
    async def download(url, **kwargs):
        assert assets.safe_public_url(url) == url
        downloads.append(url)
        return source.getvalue()
    monkeypatch.setattr(assets, '_download', download)

    render_calls = []
    queue = service.render_queue
    original_render = queue.render
    async def render(checked, result, *, budget_seconds):
        render_calls.append((checked, deepcopy(result.payload)))
        assert 0 < budget_seconds <= 10
        return await original_render(checked, result, budget_seconds=budget_seconds)
    monkeypatch.setattr(queue, 'render', render)
    assert queue.renderer.budget_seconds == 8
    assert queue.renderer.max_bytes == 1048576

    requests, replies, uploads, sends, operations = [], [], [], [], []
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 1234)))
    class Internal(InternalQqClient):
        async def post(self, path, body):
            requests.append((path, deepcopy(body)))
            return await super().post(path, body)
    internal = Internal('http://127.0.0.1:8020', 'fixture-service', internal_host='cloud.example',
                        http=http, images_enabled=True)
    class Business:
        async def execute(self, message):
            reply = await internal.execute(message)
            replies.append(reply)
            return reply
    class API:
        def __init__(self, *args, **kwargs): pass
        def setup(self, http): pass
        async def request(self, method, path, body, **kwargs):
            assert method == 'POST'
            operations.append(path)
            if path == '/v2/groups/fixture-group/files':
                assert set(body) == {'file_type', 'file_name', 'file_data', 'srv_send_msg'}
                assert body['file_type'] == 1 and body['srv_send_msg'] is False
                image = base64.b64decode(body['file_data'], validate=True)
                assert valid_reply_image(image, max_bytes=1048576)
                with Image.open(BytesIO(image)) as picture:
                    picture.load()
                    assert body['file_name'] == ('reply.png' if picture.format=='PNG' else 'reply.jpg')
                    assert 0 < picture.width <= 1080 and 0 < picture.height <= 16000
                media = 'fixture-media-' + str(len(uploads))
                uploads.append((image, media))
                return {'file_info': media}
            assert path == '/v2/groups/fixture-group/messages'
            sends.append(deepcopy(body))
            return {'id': 'fixture-message-' + str(len(sends))}
    sender = OfficialQqClient('app', 'fixture-secret', None, None, sdk=SimpleNamespace(QQApiClient=API))
    state = BotState(tmp_path / 'bot.db')
    dispatcher = BotDispatcher(Business(), sender, state)
    now = datetime.now(timezone.utc)
    def message(message_id):
        return InboundMessage(identity, message_id, raw, now.isoformat(),
                              (now + timedelta(minutes=5)).isoformat())
    try:
        await dispatcher.handle_message(message('first'))
        assert len(replies) == len(render_calls) == len(uploads) == len(sends) == 1
        assert isinstance(replies[0], QqReply) and uploads[0][0] == replies[0].image
        assert title in replies[0].text and '图片暂不可用' not in replies[0].text
        path, body = requests[0]
        assert path == '/internal/qq/query'
        assert (body['command'], body['game'], body['image_requested']) == (command, 'endfield', True)
        assert body.get('role_name') == ('佩丽卡' if command == 'roles' else None)
        payload = render_calls[0][1]
        assert payload['card']['title'] == '终末地 · ' + title
        assert len(payload['snapshot_fingerprints']) == snapshots
        assert NOW in payload['snapshot_times'] or command in ('gacha', 'combat')
        if command == 'roles':
            assert render_calls[0][1]['render_snapshot']['display_data']['panels'][0]['snapshot']['payload']['operator_detail']['tactical_item']['name']=='已观测战术道具'
            assert '2026-10-14T00:00:00Z' in payload['snapshot_times']
        if command == 'combat':
            assert payload['snapshot_times'] == [value['fetched_at'] for value in synthetic_challenges().values()]
            assert render_calls[0][1]['render_snapshot']['display_data']['panels'][0]['snapshot']['payload']['reports'][1]['stale'] is True
        assert sends[0] == {'msg_type': 7, 'media': {'file_info': uploads[0][1]},
                            'msg_id': 'first', 'msg_seq': 1}

        # Redelivery of an inbound ID cannot query, upload or send twice. A new
        # passive message reuses only rendered bytes, never platform media info.
        cold_downloads = list(downloads)
        await dispatcher.handle_message(message('first'))
        assert len(requests) == len(render_calls) == len(uploads) == len(sends) == 1
        await dispatcher.handle_message(message('second'))
        assert len(requests) == len(render_calls) == len(uploads) == len(sends) == 2
        assert uploads[0][0] == uploads[1][0] and uploads[0][1] != uploads[1][1]
        assert sends[1] == {'msg_type': 7, 'media': {'file_info': uploads[1][1]},
                            'msg_id': 'second', 'msg_seq': 1}
        assert downloads == cold_downloads
        assert operations == ['/v2/groups/fixture-group/files', '/v2/groups/fixture-group/messages'] * 2
        assert [row[0] for row in state.connection.execute('SELECT state FROM replies')] == ['sent', 'sent']
        assert query.refreshes == [] and not private.private_root.exists()
    finally:
        state.close()
        scoped.close()
        await http.aclose()
        await sender.aclose()
        await service.aclose()
