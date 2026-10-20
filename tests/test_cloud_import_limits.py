"""The cloud transport accepts its own bounded exports without relaxing other writes."""
import json

from fastapi.testclient import TestClient

from game_assistant.cloud_app import create_cloud_app
from game_assistant.identity.models import Principal
from game_assistant.private_routes import NTE_IMPORT_BODY_LIMIT
from tests.test_account_queries import cloud_settings
from tests.test_identity import write
from tests.test_private_data_isolation import nte_doc


def test_cloud_export_preview_import_and_bounded_authenticated_transport(tmp_path):
    app = create_cloud_app(cloud_settings(tmp_path), start_scheduler=False)
    admin = app.state.identity.bootstrap_admin('admin', 'Admin-password-123')
    with TestClient(app, base_url='https://cloud.example') as client:
        write(client, '/api/identity/login', {'username':'admin','password':'Admin-password-123'})
        def account(user):
            row = app.state.accounts.save_verified(Principal(user, False), 'tajiduo',
                {'center_uid':'verified-user','role_id':'77','access_token':'test-token','device_id':'device'})
            return f"/api/accounts/{row['account_id']}/roles/{row['role_id']}/nte/gacha"
        prefix = client.portal.call(account, admin.user_id)
        document = nte_doc()
        document['records'] = [{**document['records'][0], 'uid':str(i)} for i in range(500)]
        body = {'document':document}
        assert len(json.dumps(body).encode()) > 65536
        preview = write(client, prefix+'/preview', body)
        assert preview.status_code == 200, preview.text
        imported = write(client, prefix+'/import', {**body,'preview_id':preview.json()['preview_id']})
        assert imported.status_code == 200, imported.text
        assert imported.json()['imported'] == 500
        exported = client.get(prefix+'/export')
        assert exported.status_code == 200 and len(exported.content) > 65536
        # A second owned ledger restores the actual HTTP export, not a hand-built copy.
        invite = app.state.identity.create_invite(admin)
        user = write(client, '/api/identity/register', {'username':'restore',
            'password':'Restore-password-123','invite':invite}).json()['user_id']
        restored_prefix = client.portal.call(account, user)
        body = {'document':exported.json()}
        preview = write(client, restored_prefix+'/preview', body)
        assert preview.status_code == 200, preview.text
        imported = write(client, restored_prefix+'/import', {**body,'preview_id':preview.json()['preview_id']})
        assert imported.status_code == 200 and imported.json()['imported'] == 500
        assert client.get(restored_prefix+'/summary').json()['total_records'] == 500
        assert write(client, prefix+'/preview', body).status_code == 404
        assert client.post(restored_prefix+'/preview', json=body).status_code == 403
        token = client.get('/api/identity/csrf').json()['csrf_token']
        encoded = json.dumps({**body, 'padding':''}, separators=(',',':')).encode()
        exact = encoded[:-2] + b'x'*(NTE_IMPORT_BODY_LIMIT-len(encoded)) + encoded[-2:]
        assert len(exact) == NTE_IMPORT_BODY_LIMIT
        assert client.post(restored_prefix+'/preview', content=exact,
            headers={'X-CSRF-Token':token}).status_code == 200
        def chunks():
            for _ in range(NTE_IMPORT_BODY_LIMIT // 65536 + 1):
                yield b'x'*65536
        assert client.post(restored_prefix+'/preview', content=chunks(),
            headers={'X-CSRF-Token':token,'Content-Length':'1'}).status_code == 413
        assert client.post('/api/identity/login', content=b'x'*65537,
            headers={'X-CSRF-Token':token}).status_code == 413
        client.cookies.clear()
        assert client.post(restored_prefix+'/preview', json=body).status_code == 401
