from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from game_assistant.config import Settings
from game_assistant.system_update import SystemUpdateService, UpdateError, UpstreamError, CHECK_TTL_SECONDS, GITHUB_ROOT
from game_assistant.system_update_protocol import read_json, write_json_atomic, lock
from game_assistant.system_update_version import capture_version
from tests.test_system_update_version import marker, SHA, OTHER

THIRD = 'c' * 40


def upstream(relation='ahead', latest=OTHER):
    def fetch(url):
        if url.endswith('/commits/main'):
            return {'sha': latest, 'commit': {'message': '已验证的更新\n正文', 'committer': {'date': '2026-10-18T00:00:00Z'}}}
        assert url == GITHUB_ROOT + f'/compare/{SHA}...{latest}?per_page=1'
        return {'status': relation, 'base_commit': {'sha': SHA},
                'merge_base_commit': {'sha': latest if relation == 'behind' else SHA},
                'ahead_by': 0 if relation == 'behind' else 1,
                'behind_by': 0 if relation == 'ahead' else 1}
    return fetch


@pytest.fixture
def service(tmp_path):
    root = marker(tmp_path / 'installation')
    state = tmp_path / 'state'
    state.mkdir()
    settings = Settings(system_update_enabled=True, system_update_install_root=str(root), system_update_state_dir=str(state))
    now = [2000.0]
    write_json_atomic(state / 'worker.json', {'schema': 1, 'pid': 123, 'platform': 'linux', 'updated_at': now[0]})
    result = SystemUpdateService(settings, version=capture_version(root), fetch=upstream(), clock=lambda: now[0], platform_name='linux')
    return result, state, now


def test_check_compares_fixed_main_and_apply_publishes_only_the_durable_request(service):
    updater, state, _ = service
    urls = []
    fetch = updater.fetch
    updater.fetch = lambda url: (urls.append(url), fetch(url))[1]
    status = updater.check()
    assert urls == [GITHUB_ROOT + '/commits/main', GITHUB_ROOT + f'/compare/{SHA}...{OTHER}?per_page=1']
    assert status['can_apply'] and status['relation'] == 'ahead' and status['current']['sha'] == SHA
    queued = updater.apply(SHA, OTHER)
    request = read_json(state / 'request.json')
    assert set(request) == {'schema', 'job_id', 'target_sha', 'expected_sha', 'requested_at', 'source'}
    assert request['schema'] == 1 and request['source'] == 'main'
    assert request['expected_sha'] == SHA and request['target_sha'] == OTHER
    assert queued['job']['job_id'] == request['job_id'] and queued['job']['phase'] == 'queued'
    assert not (state / 'status.json').exists(), 'web process must never forge worker completion'


@pytest.mark.parametrize('relation,reason', [('behind','current_ahead'), ('diverged','history_diverged')])
def test_current_ahead_or_divergent_history_cannot_be_downgraded(service, relation, reason):
    updater, state, _ = service
    updater.fetch = upstream(relation)
    assert updater.check()['unavailable_reason'] == reason
    with pytest.raises(UpdateError, match=reason):
        updater.apply(SHA, OTHER)
    assert not (state / 'request.json').exists()


def test_equal_head_is_up_to_date_without_a_compare_request(service):
    updater, _, _ = service
    updater.fetch = upstream(latest=SHA)
    status = updater.check()
    assert status['relation'] == 'up_to_date' and not status['can_apply']
    assert status['unavailable_reason'] == 'up_to_date'


def test_missing_unknown_or_inconsistent_compare_data_is_never_a_fast_forward_proof(service):
    updater, _, _ = service
    correct = upstream()
    for response in [{}, {'status':'ahead'}, {'status':'identical'}, {'status':'ahead','base_commit':{'sha':THIRD}}]:
        updater.fetch = lambda url: correct(url) if url.endswith('/commits/main') else response
        status = updater.check()
        assert not status['can_apply'] and status['stale']
        assert status['check_error'] == 'github_invalid_response'


def test_expired_proof_changed_target_or_changed_runtime_identity_never_queues(service):
    updater, state, now = service
    updater.check()
    for expected, target, reason in [(THIRD,OTHER,'running_version_mismatch'),(SHA,THIRD,'target_changed')]:
        with pytest.raises(UpdateError, match=reason):
            updater.apply(expected, target)
    now[0] += CHECK_TTL_SECONDS + 1
    write_json_atomic(state / 'worker.json', {'schema':1, 'pid':123, 'platform':'linux', 'updated_at':now[0]})
    with pytest.raises(UpdateError, match='check_stale'):
        updater.apply(SHA, OTHER)
    assert not (state / 'request.json').exists()
    updater.fetch = upstream(latest=THIRD)
    updater.check()
    with pytest.raises(UpdateError, match='target_changed'):
        updater.apply(SHA, OTHER)


def test_failed_check_retains_previous_information_but_disables_application(service):
    updater, state, _ = service
    updater.check()
    def unavailable(_url):
        raise UpstreamError('github_unavailable')
    updater.fetch = unavailable
    result = updater.check()
    assert result['latest']['sha'] == OTHER and result['checked_at'] == 2000
    assert result['stale'] and result['check_error'] == 'github_unavailable'
    assert result['unavailable_reason'] == 'check_failed' and not result['can_apply']
    with pytest.raises(UpdateError, match='check_failed'):
        updater.apply(SHA, OTHER)
    # Failure is durable across API process restart, rather than reviving the old successful check.
    restarted = SystemUpdateService(updater.settings, version=updater.version, clock=updater.clock, platform_name='linux')
    assert restarted.status()['check_error'] == 'github_unavailable'
    assert not (state / 'request.json').exists()


def test_concurrent_apply_has_exactly_one_publication_and_restart_preserves_job(service):
    updater, state, _ = service
    updater.check()
    def apply():
        try:
            return updater.apply(SHA, OTHER)['job']['job_id']
        except UpdateError as error:
            return error.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _n: apply(), range(2)))
    request = read_json(state / 'request.json')
    assert sorted(results) == sorted([request['job_id'], 'job_active'])
    restarted = SystemUpdateService(updater.settings, version=updater.version, clock=updater.clock, platform_name='linux')
    assert restarted.status()['job']['job_id'] == request['job_id']
    assert restarted.status()['unavailable_reason'] == 'job_active'


def test_worker_status_survives_request_claim_and_critical_recovery_blocks_new_jobs(service):
    updater, state, _ = service
    updater.check()
    queued = updater.apply(SHA, OTHER)['job']
    (state / 'request.json').unlink()
    for phase in ['preparing','verifying','recovery_required','completed']:
        write_json_atomic(state / 'status.json', {**queued, 'phase':phase, 'updated_at':2000})
        status = updater.status()
        assert status['job']['phase'] == phase and not status['can_apply']
        assert status['unavailable_reason'] == ('recovery_required' if phase == 'recovery_required' else 'running_version_mismatch' if phase == 'completed' else 'job_active')


@pytest.mark.parametrize('update,reason', [({'platform':'windows'},'worker_unavailable'),({'updated_at':1969},'worker_unavailable'),({'updated_at':2100},'worker_unavailable')])
def test_missing_wrong_platform_or_stale_worker_cannot_accept_updates(service, update, reason):
    updater, state, _ = service
    updater.check()
    write_json_atomic(state / 'worker.json', {'schema':1,'pid':123,'platform':'linux','updated_at':2000,**update})
    assert updater.status()['unavailable_reason'] == reason
    with pytest.raises(UpdateError, match=reason):
        updater.apply(SHA, OTHER)


def test_changed_files_unknown_version_and_frontend_mismatch_block_update(service):
    updater, state, _ = service
    updater.check()
    (updater.version.root / 'frontend/dist/build-info.json').write_text(json.dumps({'schema':1,'source':'miyako-md/game-manage','commit':THIRD}))
    assert updater.status()['unavailable_reason'] == 'frontend_version_mismatch'
    marker(updater.version.root, THIRD)
    assert updater.status()['current']['sha'] == SHA
    assert updater.status()['unavailable_reason'] == 'running_version_mismatch'
    assert not (state / 'request.json').exists()


def test_queue_lock_busy_is_a_conflict_not_a_second_job(service):
    updater, state, _ = service
    updater.check()
    with lock(state / 'queue.lock'):
        with pytest.raises(UpdateError, match='job_active'):
            updater.apply(SHA, OTHER)
    assert not (state / 'request.json').exists()

@pytest.mark.parametrize('field,value,reason', [('startup_dirty',True,'dirty_worktree'),('commit',None,'version_unknown')])
def test_dirty_startup_or_unknown_running_code_never_applies(service,field,value,reason):
    from dataclasses import replace
    updater,state,_=service
    updater.version=replace(updater.version,**{field:value})
    updater.check()
    assert updater.status()['unavailable_reason']==reason
    assert not updater.status()['can_apply']
    assert not (state/'request.json').exists()


def test_persistence_failure_does_not_revive_a_previous_successful_check(service,monkeypatch):
    from game_assistant import system_update
    updater,state,_=service
    updater.check()
    original=system_update.write_json_atomic
    def fail(path,value):
        if path.name=='check.json':raise OSError('synthetic disk failure')
        return original(path,value)
    monkeypatch.setattr(system_update,'write_json_atomic',fail)
    result=updater.check()
    assert not result['can_apply'] and result['check_error']=='state_unavailable'
    assert not updater.status()['can_apply']
    with pytest.raises(UpdateError,match='state_unavailable'):
        updater.apply(SHA,OTHER)
    assert not (state/'request.json').exists()
