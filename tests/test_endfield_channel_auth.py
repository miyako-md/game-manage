"""Channel ownership across login, encrypted grants, runtime and derived grants."""
import pytest

from game_assistant.accounts.runtime import AccountRuntime
from game_assistant.auth.service import LoginError, ScopedLoginService
from game_assistant.auth.store import CredentialStoreError
from game_assistant.config import Settings
from game_assistant.identity.models import Principal
from tests.test_account_auth import setup
from tests.test_auth_routes import HEADERS, client_for
from tests.test_cloud_skland_passport import cloud, Client, connect, parent

P = Principal('a', False)


@pytest.mark.parametrize('channel', ['official', 'bilibili'])
def test_cloud_runtime_allows_channel_metadata_but_rejects_local_tokens(tmp_path, channel):
    from game_assistant.cloud_runtime import load_runtime, RuntimeConfigurationError
    from tests.test_cloud_operations import fixture
    _, _, _, config = fixture(tmp_path)
    original = config.read_text()
    config.write_text('endfield_channel="' + channel + '"\n' + original)
    assert load_runtime(config).settings.endfield_channel == channel
    config.write_text('endfield_hg_token="synthetic-secret"\n' + config.read_text())
    with pytest.raises(RuntimeConfigurationError, match='local_credentials_forbidden'):
        load_runtime(config)


class ChannelProvider:
    async def start_context(self):
        return {}

    async def send_sms(self, context, mobile, captcha=None):
        pass

    async def login(self, context, mobile, code):
        return {'hg_token': 'test-secret', 'uid': 'hg-user', 'role_id': 'role',
                'server_id': '1', 'channel': context['channel']}


def test_local_channel_is_pinned_at_session_creation_and_restored(tmp_path):
    client, service, _, _ = client_for(tmp_path)
    service.providers['endfield'] = ChannelProvider()
    bad = client.post('/api/auth/endfield/sessions', headers=HEADERS, json={'channel': 'untrusted'})
    assert bad.status_code == 422
    assert 'untrusted' not in bad.text
    sid = client.post('/api/auth/endfield/sessions', headers=HEADERS,
                      json={'channel': 'bilibili'}).json()['session_id']
    body = {'session_id': sid, 'mobile': '13800000000'}
    assert client.post('/api/auth/endfield/sms', headers=HEADERS, json=body).status_code == 200
    result = client.post('/api/auth/endfield/login', headers=HEADERS,
                         json={**body, 'code': '123456', 'channel': 'official'})
    assert result.status_code == 200
    assert result.json()['account']['channel'] == 'bilibili'
    assert service.settings.endfield_channel == 'bilibili'
    assert service.store.load()['endfield']['channel'] == 'bilibili'
    assert 'test-secret' not in result.text
    default = client.post('/api/auth/endfield/sessions', headers=HEADERS).json()['session_id']
    assert service._sessions[default]['context']['channel'] == 'official'


async def test_cloud_channel_session_is_owned_and_other_games_reject_bilibili(tmp_path):
    db, store, accounts, _ = setup(tmp_path)
    login = ScopedLoginService(accounts, providers={'hypergryph': ChannelProvider(), 'tajiduo': ChannelProvider()})
    with pytest.raises(LoginError):
        await login.start(P, 'tajiduo', channel='bilibili')
    sid = (await login.start(P, 'hypergryph', channel='bilibili'))['session_id']
    with pytest.raises(LoginError):
        await login.sms(Principal('b', False), 'hypergryph', sid, '13800000000')
    await login.sms(P, 'hypergryph', sid, '13800000000')
    result = await login.login(P, 'hypergryph', sid, '13800000000', '123456')
    item = accounts.list_accounts(P)[0]
    assert (item['channel'], item['server']) == ('bilibili', '1')
    saved = store.load_grant('a', result['grant_id'])
    assert saved['_verified_roles'][0]['channel'] == 'bilibili'
    assert accounts.list_accounts(Principal('b', False)) == []
    scope = accounts.require_scope(P, result['account_id'], result['role_id'])
    runtime = AccountRuntime(accounts, Settings(), tmp_path / 'runtime', login=login)
    settings = runtime.for_scope(scope).get('endfield')._settings
    assert (settings.endfield_channel, settings.endfield_server_id) == ('bilibili', '1')
    await runtime.aclose()


def test_same_role_and_server_in_distinct_channels_never_share_account_scope(tmp_path):
    db, store, accounts, _ = setup(tmp_path)
    result = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'test-cred',
        'role_id': 'same-role', 'server_id': '1', 'channel': 'bilibili',
        'roles': [{'role_id': 'same-role', 'server_id': '1', 'channel': channel}
                  for channel in ('official', 'bilibili')]})
    items = accounts.list_accounts(P)
    assert {row['channel'] for row in items} == {'official', 'bilibili'}
    assert len({row['account_id'] for row in items}) == 2
    assert len({row['roles'][0]['role_id'] for row in items}) == 2
    chosen = next(row for row in items if row['account_id'] == result['account_id'])
    assert chosen['channel'] == 'bilibili'
    assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_new_verified_channel_does_not_relabel_or_reuse_legacy_scope(tmp_path):
    db, store, accounts, _ = setup(tmp_path)
    old = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'old-cred',
        'role_id': 'role', 'server_id': '1'})
    scope = accounts.require_scope(P, old['account_id'], old['role_id'])
    new = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'new-cred',
        'role_id': 'role', 'server_id': '1', 'channel': 'bilibili'})
    assert new['account_id'] != old['account_id']
    with pytest.raises(LookupError):
        accounts.describe(scope)
    old_item = next(row for row in accounts.list_accounts(P) if row['account_id'] == old['account_id'])
    assert old_item['state'] == 'role_unavailable'
    assert old_item['roles'] == []


async def test_bilibili_passport_derives_only_matching_channel(cloud, monkeypatch):
    db, store, accounts, login = cloud
    hg = parent(accounts, channel='bilibili')

    async def binding(self, *args):
        return {'list': [{'appCode': 'endfield', 'bindingList': [
            {'uid': 'hg-user', 'channelMasterId': 2, 'isOfficial': False, 'channelName': 'bilibili服',
             'roles': [{'roleId': 'role', 'serverId': '1'}]}]}]}

    monkeypatch.setattr(Client, 'binding', binding)
    linked = await connect(login, hg)
    saved = store.load_grant('a', linked['grant_id'])
    assert saved['channel'] == saved['_parent']['channel'] == 'bilibili'
    item = next(row for row in accounts.list_accounts(P) if row['account_id'] == linked['account_id'])
    assert item['channel'] == 'bilibili'
    altered = {**saved['_parent'], 'channel': 'official'}
    with pytest.raises(CredentialStoreError):
        store.validate_parent('a', altered)


@pytest.mark.parametrize('channel', ['official', 'unknown'])
async def test_bilibili_passport_rejects_wrong_or_unproven_skland_channel(cloud, monkeypatch, channel):
    db, store, accounts, login = cloud
    hg = parent(accounts, channel='bilibili')

    async def binding(self, *args):
        metadata = {'channelMasterId': 1, 'isOfficial': True} if channel == 'official' else {}
        return {'list': [{'appCode': 'endfield', 'bindingList': [
            {**metadata, 'roles': [{'roleId': 'role', 'serverId': '1'}]}]}]}

    monkeypatch.setattr(Client, 'binding', binding)
    with pytest.raises(LoginError) as failure:
        await connect(login, hg)
    assert failure.value.error_kind == 'skland_role_mismatch'
    assert db.execute("SELECT count(*) FROM grants WHERE provider='skland'").fetchone()[0] == 0


@pytest.mark.parametrize('metadata', [{}, {'channelMasterId': 2, 'isOfficial': True}])
async def test_official_passport_rejects_unknown_and_conflicting_channel(cloud, monkeypatch, metadata):
    db, _, accounts, login = cloud
    hg = parent(accounts)

    async def binding(self, *args):
        return {'list': [{'appCode': 'endfield', 'bindingList': [
            {**metadata, 'roles': [{'roleId': 'role', 'serverId': '1'}]}]}]}

    monkeypatch.setattr(Client, 'binding', binding)
    with pytest.raises(LoginError) as failure:
        await connect(login, hg)
    assert failure.value.error_kind == 'skland_role_mismatch'
    assert db.execute("SELECT count(*) FROM grants WHERE provider='skland'").fetchone()[0] == 0


async def test_manual_skland_unknown_channel_is_preserved_as_unknown(cloud, monkeypatch):
    _, _, accounts, login = cloud

    async def binding(self, *args):
        return {'list': [{'appCode': 'endfield', 'bindingList': [
            {'roles': [{'roleId': 'role', 'serverId': '1'}]}]}]}

    monkeypatch.setattr(Client, 'binding', binding)
    result = await login.connect_skland(P, 'test-cred')
    row = next(item for item in accounts.list_accounts(P) if item['account_id'] == result['account_id'])
    assert row['channel'] == 'unknown'


def strip_channel(store, grant, parent_channel=False):
    """Rewrite a grant as saved before channel storage (d9a0f4e)."""
    saved = store.load_grant('a', grant['grant_id'])
    saved.pop('channel')
    saved['_verified_roles'] = [{k: v for k, v in role.items() if k != 'channel'} for role in saved['_verified_roles']]
    if '_parent' in saved and not parent_channel:
        saved['_parent'].pop('channel')
    store.save_grant('a', grant['grant_id'], saved, grant['version'])


async def test_legacy_passport_skland_reports_parent_channel_and_pairs(cloud):
    _, store, accounts, login = cloud
    hg = parent(accounts)
    sk = await connect(login, hg)
    strip_channel(store, sk)
    rows = {row['account_id']: row for row in accounts.list_accounts(P)}
    item = rows[sk['account_id']]
    assert item['state'] == 'active' and item['roles']
    assert item['channel'] == rows[hg['account_id']]['channel'] == 'official'
    assert (item['authorization_source'], item['parent_account_id']) == ('passport', hg['account_id'])
    assert item['server'] == rows[hg['account_id']]['server']
    assert item['roles'][0]['game_uid'] == rows[hg['account_id']]['roles'][0]['game_uid']


async def test_legacy_passport_skland_follows_explicit_parent_channel(cloud, monkeypatch):
    db, store, accounts, login = cloud
    hg = parent(accounts, channel='bilibili')

    async def binding(self, *args):
        return {'list': [{'appCode': 'endfield', 'bindingList': [
            {'uid': 'hg-user', 'channelMasterId': 2, 'isOfficial': False, 'channelName': 'bilibili服',
             'roles': [{'roleId': 'role', 'serverId': '1'}]}]}]}

    monkeypatch.setattr(Client, 'binding', binding)
    sk = await connect(login, hg)
    strip_channel(store, sk, parent_channel=True)
    # Pre-channel storage scoped every skland row under 'official'.
    db.execute('BEGIN')
    db.execute('PRAGMA defer_foreign_keys=ON')
    db.execute("UPDATE accounts SET channel='official' WHERE account_id=?", (sk['account_id'],))
    db.execute("UPDATE roles SET channel='official' WHERE account_id=?", (sk['account_id'],))
    db.commit()
    item = next(row for row in accounts.list_accounts(P) if row['account_id'] == sk['account_id'])
    assert item['state'] == 'active' and item['channel'] == 'bilibili'


def test_legacy_manual_skland_without_channel_stays_unknown(tmp_path):
    _, store, accounts, _ = setup(tmp_path)
    manual = accounts.save_verified(P, 'skland', {'user_id': 'sk-user', 'cred': 'manual',
        'role_id': 'role', 'server_id': '1'})
    strip_channel(store, manual)
    item = next(row for row in accounts.list_accounts(P) if row['account_id'] == manual['account_id'])
    assert item['state'] == 'active' and item['channel'] == 'unknown'
    assert item['authorization_source'] == 'manual' and 'parent_account_id' not in item
