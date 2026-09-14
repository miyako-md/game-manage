import json

import pytest

from game_assistant.auth.store import CredentialStore, CredentialStoreError


def test_encrypted_roundtrip_and_logout_survive_restart(tmp_path):
    path = tmp_path / 'credentials.json'
    store = CredentialStore(path)
    assert store.load() == {}
    store.save({'nte': {'access_token': 'private-access', 'refresh_token': 'private-refresh'}})
    assert b'private-access' not in path.read_bytes()
    assert b'private-refresh' not in path.read_bytes()
    assert CredentialStore(path).load()['nte']['access_token'] == 'private-access'
    store.save({'nte': {'logged_out': True}})
    assert CredentialStore(path).load()['nte'] == {'logged_out': True}


def test_corrupt_store_is_not_silently_treated_as_logged_out(tmp_path):
    path = tmp_path / 'credentials.json'
    path.write_text('broken', encoding='utf-8')
    with pytest.raises(CredentialStoreError, match='凭据'):
        CredentialStore(path).load()


def test_failed_replace_preserves_old_store(tmp_path, monkeypatch):
    path = tmp_path / 'credentials.json'
    store = CredentialStore(path)
    store.save({'nte': {'access_token': 'old'}})
    old = path.read_bytes()
    def fail(*args):
        raise OSError('test disk failure')
    monkeypatch.setattr('game_assistant.auth.store.os.replace', fail)
    with pytest.raises(CredentialStoreError):
        store.save({'nte': {'access_token': 'new'}})
    assert path.read_bytes() == old
