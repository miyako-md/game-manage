"""NTE overview versus selected detail, using a production-sized synthetic roster."""
from datetime import datetime
from io import BytesIO
import os

from PIL import Image
import pytest

from game_assistant.accounts.models import AccountScope, QueryResult
from game_assistant.qq.browser_rendering import BrowserRenderer
from game_assistant.qq.render_snapshot import role_snapshot
from game_assistant.qq.rendering import RenderingUnavailable

NOW = datetime.fromisoformat('2026-10-15T12:00:00+08:00')
SCOPE = AccountScope('fixture-user', 'fixture-account', 'fixture-role')


def rich_roster():
    properties = [{'id': str(i), 'name': f'属性{i}', 'value': '1234'} for i in range(10)]
    equipment = [{'id': str(i), 'name': '合成装备', 'level': 0,
        'main_properties': properties[:2], 'properties': properties[:4]} for i in range(6)]
    entries = [{'id': str(9001 + n), 'name': f'合成角色{n}', 'quality': 'S', 'level': 0, 'awaken_level': None,
        'weapon': {'id': '1', 'name': '合成弧盘', 'level': 50, 'description': '资料' * 200,
            'buff_description': '效果' * 200, 'properties': properties},
        'suit': {'name': '合成套装', 'description_two': '二件' * 80, 'description_four': '四件' * 80,
            'core': equipment[:4], 'pie': equipment[4:]},
        'skills': [{'id': str(i), 'name': f'技能{i}', 'level': 4,
            'items': [{'title': '说明', 'desc': '连续伤害与技能描述。' * 59}]} for i in range(6)],
        'properties': properties,
        'city_skills': [{'id': str(i), 'name': '城区技能', 'level': None,
            'items': [{'title': '说明', 'desc': '城区描述' * 30}]} for i in range(3)]} for n in range(21)]
    return QueryResult({'schema_version': 1, 'entries': entries}, NOW.isoformat(), 'ok', False)


def test_selected_role_projection_filters_the_roster_and_keeps_unknown_values():
    row = rich_roster()
    value = role_snapshot('nte', row, NOW, resolved_id='9008')
    data = value['display_data']['snapshot']
    assert data['display_mode'] == 'detail'
    assert [entry['id'] for entry in data['payload']['entries']] == ['9008']
    assert data['payload']['entries'][0]['level'] == 0
    assert data['payload']['entries'][0]['awaken_level'] is None
    assert len(row.payload['entries']) == 21
    assert value['next_command'] == '异环 角色 9008'
    with pytest.raises(RenderingUnavailable):
        role_snapshot('nte', row, NOW, resolved_id='absent')


@pytest.mark.parametrize('selected', [False, True])
def test_query_routes_preserve_roster_and_selected_character_semantics(selected):
    from tests.test_qq_unified_queries import CachedQuery, IDENTITY, service
    query = CachedQuery()
    query.add('nte', 'tajiduo', 'fixture-role', {'roles': rich_roster().payload})
    context = {}
    reply = service(query).query(IDENTITY, 'roles', 'nte', role_name='9008' if selected else None, image_context=context)
    assert context['render_snapshot']['kind'] == 'nte_role'
    data = context['render_snapshot']['display_data']['snapshot']
    assert data['display_mode'] == ('detail' if selected else 'roster')
    assert len(data['payload']['entries']) == (1 if selected else 21)
    if not selected:
        assert all('weapon' not in entry and 'skills' not in entry and 'assessment' not in entry for entry in data['payload']['entries'])
    if selected:
        assert data['payload']['entries'][0]['id'] == '9008'
        assert context['render_snapshot']['next_command'] == '异环 角色 9008'
    assert reply['text']


@pytest.mark.parametrize('code', ['qq_image_pixel_limit', 'qq_image_size_limit'])
async def test_query_reply_explains_image_limits_without_showing_internal_codes(code):
    from types import SimpleNamespace
    from game_assistant.qq.models import QqIdentity
    from game_assistant.qq.query_routes import QqQueryService
    class Queue:
        async def render(self, *args, **kwargs):
            return RenderingUnavailable(code)
    row=QueryResult([],NOW.isoformat(),'ok',False)
    service=QqQueryService(None,None,SimpleNamespace(read=lambda game,cap:row),render_queue=Queue(),clock=lambda:NOW)
    reply=await service.query_reply(QqIdentity('fixture-app','group','fixture-group','fixture-sender'),
        'calendar','nte',image_requested=True,budget_seconds=10)
    assert 'image' not in reply and '未截断' in reply['text'] and '看板' in reply['text']
    assert code not in reply['text']


@pytest.mark.parametrize('selected', [False, True])
async def test_real_production_sized_nte_roster_and_selected_detail(selected, tmp_path):
    executable, font = os.environ.get('QQ_RENDER_TEST_EXECUTABLE'), os.environ.get('QQ_RENDER_TEST_FONT')
    if not executable or not font:
        pytest.skip('Explicit isolated Chromium/font required')
    class InspectableRenderer(BrowserRenderer):
        page_texts = None
        async def _bounded_close(self, operation):
            if self._browser is not None and self._browser.contexts:
                page = self._browser.contexts[0].pages[0]
                if not page.is_closed() and self.last_state and self.last_state.get('state') == 'ready':
                    self.page_texts = await page.locator('.render-page').all_inner_texts()
            return await super()._bounded_close(operation)
    renderer = InspectableRenderer(executable_path=executable, font_path=font,
        dist_path=os.environ.get('QQ_RENDER_TEST_DIST', ''), template='pages')
    value = role_snapshot('nte', rich_roster(), NOW, resolved_id='9008' if selected else None)
    envelope = QueryResult({'text': '合成角色渲染验证', 'shared_required': True, 'render_snapshot': value,
        'scopes': [{'account_id': SCOPE.account_id, 'role_id': SCOPE.role_id, 'grant_version': 1}]}, NOW.isoformat(), 'ok', False)
    try:
        png = await renderer.render_summary_async(SCOPE, envelope, budget_seconds=10)
        assert renderer.last_state['state'] == 'ready'
        assert renderer.last_state['displayed_blocks'] == renderer.last_state['content_blocks']
        assert renderer.last_state['content_blocks'] == (8 if selected else 21)
        assert 1<=png.total_pages<=100
        assert all(row['width']==720 and 0<row['height']<=1440 for row in renderer.last_state['pages'])
        assert Image.open(BytesIO(png)).width == 720
        if selected:
            assert '合成角色7' in '\n'.join(renderer.page_texts)
            for text in ('Lv0', '觉醒', '未提供', '合成弧盘', '属性0', '技能0', '城区技能', '合成套装', '合成装备'):
                assert text in '\n'.join(renderer.page_texts)
        else:
            assert any(f'合成角色{i}' in '\n'.join(renderer.page_texts) for i in range(21))
            assert '合成角色0' in '\n'.join(renderer.page_texts)
            assert '合成角色20' in '\n'.join(renderer.page_texts)
        # Skill, city skill, 弧盘 and suit effect texts are never part of the image.
        for text in ('连续伤害与技能描述。', '城区描述', '资料资料', '效果效果', '二件二件', '四件四件', '战技说明'):
            assert text not in '\n'.join(renderer.page_texts)
        assert not renderer._browser.contexts
        (tmp_path / ('selected.png' if selected else 'roster.png')).write_bytes(png)
    finally:
        await renderer.aclose()
