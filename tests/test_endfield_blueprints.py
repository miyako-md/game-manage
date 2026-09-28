import httpx
import pytest
from fastapi import FastAPI

from game_assistant.api_security import install_api_security
from game_assistant.config import Settings
from game_assistant.endfield_blueprint_routes import install_endfield_blueprint_routes
from game_assistant.endfield_blueprints import BlueprintInput, BlueprintStore


async def test_blueprint_roundtrip_and_local_api_boundary(tmp_path):
    app = FastAPI()
    settings = Settings(db_path=str(tmp_path / 'game.db'), auth_allowed_origins=['http://testserver'])
    install_endfield_blueprint_routes(app, settings)
    install_api_security(app, settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        body = {'name': '谷地电池', 'code': '蓝图分享码: ABC-123', 'notes': '材料自备'}
        assert (await client.post('/api/endfield/blueprints', json=body)).status_code == 403
        client.headers['X-Game-Assistant'] = '1'
        created = await client.post('/api/endfield/blueprints', json=body)
        assert created.status_code == 201
        item = created.json()
        assert item['code'] == body['code']
        assert BlueprintStore(settings.db_path).items() == [item]
        response = await client.put('/api/endfield/blueprints/' + item['id'], json={**body, 'notes': '已调整'})
        assert response.json()['created_at'] == item['created_at']
        assert response.json()['notes'] == '已调整'
        exported = await client.get('/api/endfield/blueprints/export')
        assert exported.json()['items'][0]['notes'] == '已调整'
        assert 'attachment' in exported.headers['content-disposition']
        assert (await client.get('/api/endfield/blueprints', headers={'Origin': 'https://evil.invalid'})).status_code == 403
        assert (await client.post('/api/endfield/blueprints', json={**body, 'name': '  '})).status_code == 422
        assert (await client.delete('/api/endfield/blueprints/' + item['id'])).status_code == 200
        assert (await client.delete('/api/endfield/blueprints/' + item['id'])).status_code == 404
        assert (await client.put('/api/endfield/blueprints/missing', json=body)).status_code == 404
        assert (await client.get('/api/endfield/blueprints')).json() == {'items': []}


def test_blueprint_quota_and_text_validation(tmp_path):
    store = BlueprintStore(tmp_path / 'game.db')
    store.limit = 1
    item = store.save(BlueprintInput(name='测试', code='copy me'))
    with pytest.raises(ValueError, match='1000'):
        store.save(BlueprintInput(name='另一条', code='other'))
    assert store.save(BlueprintInput(name='更新', code='new'), item['id'])['code'] == 'new'
    with pytest.raises(ValueError):
        BlueprintInput(name='测试', code='abc\x00def')
