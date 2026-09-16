import httpx
import pytest
from fastapi import FastAPI

from game_assistant.config import Settings
from game_assistant.nte_gacha_routes import install_nte_gacha_routes
from tests.test_nte_gacha import document


@pytest.mark.asyncio
async def test_routes_security_preview_commit_and_actual_size(tmp_path):
    app = FastAPI()
    settings = Settings(db_path=str(tmp_path/'a.db'), nte_role_id='77',
                        auth_allowed_origins=['http://testserver'])
    app.state.settings = settings
    install_nte_gacha_routes(app, settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        body = {'document': document(), 'latest_confirmed': True, 'continuity_confirmed': True}
        assert (await client.post('/api/nte/gacha/preview', json=body)).status_code == 403
        headers = {'X-Game-Assistant': '1'}
        assert (await client.post('/api/nte/gacha/preview', json=body, headers={**headers, 'Origin':'https://evil.invalid'})).status_code == 403
        preview = await client.post('/api/nte/gacha/preview', json=body, headers=headers)
        assert preview.status_code == 200
        imported = await client.post('/api/nte/gacha/import', json={**body, 'preview_id': preview.json()['preview_id']}, headers=headers)
        assert imported.status_code == 200
        assert imported.json()['imported'] == 4
        assert (await client.get('/api/nte/gacha/records')).json()['total'] == 4
        assert (await client.get('/api/nte/gacha/export')).json()['format'] == 'game-assistant-nte-gacha'
        page = (await client.get('/api/nte/gacha/export?offset=0&limit=2')).json()
        assert page['export_page'] == {'offset':0, 'limit':2, 'total':4, 'next_offset':2}
        assert 'ARCHIVE_SEGMENTED' in page['coverage'][0]['warnings']
        assert (await client.get('/api/nte/gacha/export?offset=-1&limit=2')).status_code == 422
        rule = dict(pool_id='Lottery_LimitedCharacter', s_hard_pity=90,
                    reset_reward_type='character', source_note='用户自定义规则', confirmed=True)
        assert (await client.post('/api/nte/gacha/rules', json=rule, headers=headers)).status_code == 200
        assert (await client.get('/api/nte/gacha/summary')).json()['pools'][0]['pity']['hard_pity_remaining'] == 88
        invalid = await client.post('/api/nte/gacha/preview', content=b'{secret-broken-json', headers=headers)
        assert invalid.status_code == 422 and 'secret' not in invalid.text
        assert (await client.get('/api/nte/gacha/summary', headers={'Host':'evil.invalid'})).status_code == 403
        async def oversized():
            yield b' ' * (8 * 1024 * 1024)
            yield b'{}'
        assert (await client.post('/api/nte/gacha/preview', content=oversized(), headers=headers)).status_code == 413
        settings.nte_role_id = '88'
        assert (await client.get('/api/nte/gacha/records')).json()['total'] == 0
        settings.nte_role_id = ''
        assert (await client.get('/api/nte/gacha/summary')).status_code == 409
