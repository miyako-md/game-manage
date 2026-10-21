from datetime import datetime, timezone, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from game_assistant.cloud_app import create_cloud_app
from game_assistant.group_settings import GroupSettings, GroupSettingsService
from game_assistant.scoped_reminders import ReminderStore
from game_assistant.qq.models import QqIdentity
from tests.test_account_queries import cloud_settings
from tests.test_identity import write

NOW = datetime(2026, 10, 14, 8, tzinfo=timezone.utc)


def test_group_policy_consumes_scope_images_limits_quiet_and_restart(tmp_path):
    store = ReminderStore(tmp_path / 'settings.db')
    service = GroupSettingsService(store, clock=lambda: NOW)
    service.save('bot', 'group-a', GroupSettings(allowed_games=['nte'], image_preference=False, requests_per_minute=1))
    a = QqIdentity('bot', 'group', 'group-a', 'sender')
    b = QqIdentity('bot', 'group', 'group-b', 'sender')
    assert not service.consume(a, 'nte', 'stamina', True)
    assert service.consume(b, 'wuthering_waves', 'stamina', True)
    with pytest.raises(HTTPException) as denied:
        service.consume(a, 'wuthering_waves', 'stamina', True)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as limited:
        GroupSettingsService(ReminderStore(tmp_path / 'settings.db'), clock=lambda: NOW).consume(a, 'nte', 'stamina', True)
    assert limited.value.status_code == 429
    service.clock = lambda: NOW + timedelta(minutes=1)
    assert not service.consume(a, 'nte', 'stamina', True)
    with pytest.raises(HTTPException):
        service.consume(a, None, 'overview', True)
    with pytest.raises(HTTPException):
        service.consume(a, None, 'status', True)
    assert not service.consume(a, None, 'retired', True)  # a fixed retired-command notice names no game data
    service.save('bot', 'group-a', GroupSettings(quiet_start='15:00', quiet_end='17:00'))
    assert service.consume(a, 'nte', 'stamina', True)  # quiet applies only to automatic delivery
    assert service.consume(a, None, 'help', True)  # can discover configuration


def test_operator_group_routes_non_admin_csrf_and_subscription_status(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    invite = app.state.identity.create_invite(admin)
    path = '/api/admin/qq/groups/group-a/settings'
    with TestClient(app, base_url='https://cloud.example') as client:
        write(client, '/api/identity/register', dict(username='alice', password='Password-alice-123', invite=invite))
        assert client.get(path).status_code == 403
        assert write(client, path, {}, 'put').status_code == 403
        write(client, '/api/identity/login', dict(username='admin', password='Admin-password-123'))
        assert client.put(path, json={}).status_code == 403
        saved = write(client, path, dict(allowed_games=['nte'], public_topics=['events'], image_preference=False), 'put')
        assert saved.status_code == 200
        assert saved.json()['external_delivery'] == 'unsupported'
        assert saved.json()['settings']['public_topics'] == ['events']
        assert client.get(path).json()['settings']['allowed_games'] == ['nte']
        assert write(client, path, dict(public_topics=['stamina']), 'put').status_code == 422
        write(client, path, dict(public_topics=[]), 'put')
        assert client.get(path).json()['settings']['public_topics'] == []


def test_owned_rules_and_read_only_inbox_routes(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    with TestClient(app, base_url='https://cloud.example') as client:
        write(client, '/api/identity/login', dict(username='admin', password='Admin-password-123'))
        # Only verified internal provider responses create scopes; never client IDs.
        row = client.portal.call(app.state.accounts.save_verified, admin, 'tajiduo', dict(center_uid='subject', role_id='r', nickname='本人角色'))
        account = row['account_id']
        role = row['role_id']
        path = f'/api/accounts/{account}/roles/{role}/reminders'
        assert client.get(path).json()['rule']['enabled'] is False
        response = write(client, path, dict(enabled=True, notify_full=True, city_threshold_percent=80), 'put')
        assert response.status_code == 200
        assert response.json()['delivery'] == 'inbox'
        assert client.get(path + '/inbox').json()['messages'] == []
        other = f'/api/accounts/not-owned/roles/{role}/reminders'
        assert write(client, other, dict(enabled=True), 'put').status_code == 404
        assert client.get(other).status_code == 404
        write(client, f'/api/accounts/{account}/authorization', method='delete')
        assert client.get(path + '/inbox').status_code == 404
        assert write(client, path, dict(enabled=True), 'put').status_code == 404
        assert write(client, path, dict(enabled=False), 'put').status_code == 200


def test_real_internal_query_route_consumes_operator_settings(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path,qq_app_id='bot',qq_service_token='test-service'),start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin','Admin-password-123')
    with TestClient(app,base_url='https://cloud.example',client=('127.0.0.1',1234)) as client:
        write(client,'/api/identity/login',dict(username='admin',password='Admin-password-123'))
        write(client,'/api/admin/qq/groups/group-a/settings',dict(allowed_games=['nte'],image_preference=False,requests_per_minute=1),'put')
        async def reply(identity,command,game,**options):
            return dict(text=f"image={options['image_requested']}")
        app.state.qq_query.query_reply = reply
        body = dict(identity=dict(app_id='bot',scene='group',group_openid='group-a',sender_openid='member'),game='nte',command='summary',image_requested=True)
        headers = {'Authorization':'Bearer test-service'}
        assert client.post('/internal/qq/query',json=body,headers=headers).json() == {'text':'image=False'}
        assert client.post('/internal/qq/query',json=dict(body,game='wuthering_waves'),headers=headers).status_code == 403
        assert client.post('/internal/qq/query',json=body,headers=headers).status_code == 429
        body['identity']['group_openid'] = 'group-b'
        assert client.post('/internal/qq/query',json=body,headers=headers).json() == {'text':'image=True'}
