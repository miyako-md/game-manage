"""Admin-gated update checks and a durable queue for an external update worker.

No web route builds, installs, checks out code, stops services or runs client input.
The repository, branch and upstream endpoints are constants, not request options.
"""
import math
import asyncio
from contextlib import asynccontextmanager, suppress
import os
from pathlib import Path
import re
import sys
import threading
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .system_update_protocol import (ACTIVE_PHASES, PHASES, LockBusyError,
    ProtocolError, lock, read_json, safe_path, valid_sha, write_json_atomic)
from .system_update_version import (REPOSITORY, capture_version, git_state,
                                     release_root_matches)

BRANCH = 'main'
GITHUB_ROOT = f'https://api.github.com/repos/{REPOSITORY}'
CHECK_TTL_SECONDS = 120
WORKER_TTL_SECONDS = 30
MAX_UPSTREAM_BYTES = 1048576
RELATIONS = frozenset({'unknown', 'up_to_date', 'ahead', 'behind', 'diverged'})


class UpdateError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class UpstreamError(UpdateError):
    def __init__(self, code='github_unavailable'):
        super().__init__(code, 503)


def _time(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _job_id(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{32}', value) is not None


def _job(raw):
    if (type(raw.get('schema')) is not int or raw['schema'] != 1
            or not _job_id(raw.get('job_id')) or not valid_sha(raw.get('target_sha'))
            or not valid_sha(raw.get('previous_sha')) or not isinstance(raw.get('phase'), str)
            or raw['phase'] not in PHASES
            or not _time(raw.get('updated_at'))):
        raise ProtocolError('invalid_update_status')
    result = {name: raw[name] for name in ('schema', 'job_id', 'target_sha', 'previous_sha', 'phase', 'updated_at')}
    if 'finished_at' in raw:
        if not _time(raw['finished_at']):
            raise ProtocolError('invalid_update_status')
        result['finished_at'] = raw['finished_at']
    if 'error_code' in raw:
        code = raw['error_code']
        if code is not None and (not isinstance(code, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,79}', code)):
            raise ProtocolError('invalid_update_status')
        result['error_code'] = code
    return result


def _pending(raw):
    if (type(raw.get('schema')) is not int or raw['schema'] != 1
            or not _job_id(raw.get('job_id')) or raw.get('source') != BRANCH
            or not valid_sha(raw.get('target_sha')) or not valid_sha(raw.get('expected_sha'))
            or not _time(raw.get('requested_at'))):
        raise ProtocolError('invalid_update_request')
    return {'schema': 1, 'job_id': raw['job_id'], 'target_sha': raw['target_sha'],
            'previous_sha': raw['expected_sha'], 'phase': 'queued', 'updated_at': raw['requested_at']}


def _optional(path):
    try:
        return read_json(path)
    except FileNotFoundError:
        return None


class SystemUpdateService:
    def __init__(self, settings, *, version=None, fetch=None, clock=time.time, platform_name=None):
        self.settings = settings
        self.version = version if version is not None else capture_version()
        self.fetch = fetch if fetch is not None else self._fetch
        self.clock = clock
        platform = platform_name if platform_name is not None else sys.platform
        self.platform = 'windows' if platform in ('win32', 'windows') else 'linux' if platform == 'linux' else 'unsupported'
        self._memory_check = None
        self._persistence_failed = False
        self._check_lock = threading.Lock()

    def state_dir(self):
        if not self.settings.system_update_state_dir:
            return None
        try:
            path = safe_path(self.settings.system_update_state_dir)
            return path if path.is_absolute() and path.is_dir() else None
        except (OSError, ValueError):
            return None

    def _read_check(self):
        state = self.state_dir()
        raw = _optional(state / 'check.json') if state else self._memory_check
        if raw is None:
            return None
        if (type(raw.get('schema')) is not int or raw['schema'] != 1 or raw.get('repository') != REPOSITORY or raw.get('branch') != BRANCH
                or raw.get('relation') not in RELATIONS
                or raw.get('current_sha') != self.version.commit
                or (raw.get('checked_at') is not None and not _time(raw['checked_at']))):
            return None
        latest = raw.get('latest')
        if latest is not None:
            if (not isinstance(latest, dict) or not valid_sha(latest.get('sha'))
                    or not isinstance(latest.get('message'), str) or len(latest['message']) > 200
                    or not isinstance(latest.get('committed_at'), str) or len(latest['committed_at']) > 40
                    or latest.get('url') != f"https://github.com/{REPOSITORY}/commit/{latest['sha']}"):
                return None
        if raw.get('check_error') not in (None, 'github_unavailable', 'github_rate_limited', 'github_invalid_response', 'compare_unavailable', 'state_unavailable'):
            return None
        return raw

    def _save_check(self, result):
        state = self.state_dir()
        if state is not None:
            with lock(state / 'queue.lock'):
                write_json_atomic(state / 'check.json', result)
        self._memory_check = result
        self._persistence_failed = False

    def _read_job(self, state):
        if state is None:
            return None, False
        request = _optional(state / 'request.json')
        status = _optional(state / 'status.json')
        pending = _pending(request) if request is not None else None
        job = _job(status) if status is not None else None
        if pending is not None and (job is None or job['job_id'] != pending['job_id']):
            job = pending
        return job, pending is not None

    def _worker(self, state):
        if state is None:
            return False
        worker = _optional(state / 'worker.json')
        return bool(worker and worker.get('schema') == 1
                    and type(worker.get('pid')) is int and worker['pid'] > 0
                    and worker.get('platform') == self.platform
                    and _time(worker.get('updated_at'))
                    and -5 <= self.clock() - worker['updated_at'] <= WORKER_TTL_SECONDS)

    def status(self):
        current = self.version.public()
        cache = None
        job = None
        has_request = False
        worker = False
        state_error = self._persistence_failed
        try:
            cache = self._read_check()
            state = self.state_dir()
            job, has_request = self._read_job(state)
            worker = self._worker(state)
        except (OSError, ValueError):
            state_error = True
        checked = cache.get('checked_at') if cache else None
        stale = not cache or cache.get('stale') is True or not _time(checked) or not -5 <= self.clock()-checked <= CHECK_TTL_SECONDS
        relation = cache.get('relation', 'unknown') if cache else 'unknown'
        reason = None
        # Runtime identity is captured once; disk identity must still agree before queuing.
        disk_sha, _ = self.version.disk_state()
        if not self.settings.system_update_enabled:
            reason = 'disabled'
        elif self.platform == 'unsupported':
            reason = 'unsupported_platform'
        elif not release_root_matches(self.version.root, self.settings.system_update_install_root):
            reason = 'install_root_unavailable'
        elif not valid_sha(self.version.commit):
            reason = 'version_unknown'
        elif disk_sha != self.version.commit:
            reason = 'running_version_mismatch'
        elif not self.version.ready:
            reason = 'frontend_version_mismatch'
        elif current['dirty'] is not False:
            reason = 'dirty_worktree'
        elif self.version.root != Path(self.settings.system_update_install_root).absolute() and git_state(self.settings.system_update_install_root)[1] is True:
            reason = 'dirty_worktree'
        elif state_error or self.state_dir() is None:
            reason = 'state_unavailable'
        elif job and job['phase'] == 'completed' and job['target_sha'] != self.version.commit:
            reason = 'running_version_mismatch'
        elif job and job['phase'] == 'recovery_required':
            reason = 'recovery_required'
        elif has_request or job and job['phase'] in ACTIVE_PHASES:
            reason = 'job_active'
        elif not worker:
            reason = 'worker_unavailable'
        elif cache is None:
            reason = 'check_required'
        elif cache.get('check_error'):
            reason = 'check_failed'
        elif stale:
            reason = 'check_stale'
        elif relation != 'ahead':
            reason = {'up_to_date': 'up_to_date', 'behind': 'current_ahead',
                      'diverged': 'history_diverged'}.get(relation, 'relationship_unknown')
        return {'repository': REPOSITORY, 'branch': BRANCH, 'current': current,
                'latest': cache.get('latest') if cache else None, 'relation': relation,
                'checked_at': checked, 'check_error': cache.get('check_error') if cache else None,
                'stale': stale, 'can_apply': reason is None, 'unavailable_reason': reason,
                'job': job, 'worker_available': worker}

    def check(self):
        # Serialize checks in this process so a slower earlier response cannot win.
        with self._check_lock:
            now = self.clock()
            try:
                previous = self._read_check()
            except (OSError, ValueError):
                previous = None
            result = {'schema': 1, 'repository': REPOSITORY, 'branch': BRANCH,
                      'current_sha': self.version.commit, 'latest': None, 'relation': 'unknown',
                      'checked_at': None, 'attempted_at': now, 'check_error': None, 'stale': False}
            try:
                latest = self.fetch(GITHUB_ROOT + '/commits/main')
                sha = latest.get('sha')
                commit = latest.get('commit')
                if not valid_sha(sha) or not isinstance(commit, dict):
                    raise UpstreamError('github_invalid_response')
                committed = commit.get('committer') or {}
                message = commit.get('message')
                if not isinstance(message, str) or not isinstance(committed, dict):
                    raise UpstreamError('github_invalid_response')
                sha = sha.lower()
                result['latest'] = {'sha': sha, 'message': message.split('\n', 1)[0][:200],
                                    'committed_at': str(committed.get('date') or '')[:40],
                                    'url': f'https://github.com/{REPOSITORY}/commit/{sha}'}
                if self.version.commit == sha:
                    result['relation'] = 'up_to_date'
                elif valid_sha(self.version.commit):
                    comparison = self.fetch(GITHUB_ROOT + f'/compare/{self.version.commit}...{sha}?per_page=1')
                    relation = comparison.get('status')
                    base = comparison.get('base_commit') or {}
                    merge = comparison.get('merge_base_commit') or {}
                    ahead, behind = comparison.get('ahead_by'), comparison.get('behind_by')
                    valid_counts = type(ahead) is int and type(behind) is int
                    if (relation not in ('ahead', 'behind', 'diverged')
                            or not isinstance(base, dict) or base.get('sha') != self.version.commit
                            or not isinstance(merge, dict) or not valid_sha(merge.get('sha'))
                            or not valid_counts
                            or relation == 'ahead' and not (ahead > 0 and behind == 0 and merge['sha'] == self.version.commit)
                            or relation == 'behind' and not (behind > 0 and ahead == 0 and merge['sha'] == sha)
                            or relation == 'diverged' and not (ahead > 0 and behind > 0)):
                        raise UpstreamError('github_invalid_response')
                    result['relation'] = relation
                result['checked_at'] = now
            except (UpstreamError, httpx.HTTPError, OSError, ValueError, TypeError, AttributeError) as error:
                if previous:
                    result.update({key: previous.get(key) for key in ('latest', 'relation', 'checked_at')})
                result['check_error'] = error.code if isinstance(error, UpstreamError) else 'github_unavailable'
                result['stale'] = True
            try:
                self._save_check(result)
            except (OSError, ValueError):
                # Keep the failed persistence visible; never issue an apply based on memory alone.
                self._persistence_failed = True
                self._memory_check = {**result, 'check_error': 'state_unavailable', 'stale': True}
                return {**self.status(), 'latest': result['latest'], 'relation': result['relation'],
                        'checked_at': result['checked_at'], 'check_error': 'state_unavailable',
                        'stale': True, 'can_apply': False, 'unavailable_reason': 'state_unavailable'}
            return self.status()

    def apply(self, expected_sha, target_sha):
        if not valid_sha(expected_sha) or not valid_sha(target_sha):
            raise UpdateError('invalid_request', 422)
        state = self.state_dir()
        if state is None:
            raise UpdateError('state_unavailable', 503)
        try:
            with lock(state / 'queue.lock'):
                snapshot = self.status()
                if snapshot['current']['sha'] != expected_sha.lower():
                    raise UpdateError('running_version_mismatch')
                latest = snapshot['latest']
                if not latest or latest['sha'] != target_sha.lower():
                    raise UpdateError('target_changed')
                if not snapshot['can_apply']:
                    reason = snapshot['unavailable_reason'] or 'update_unavailable'
                    raise UpdateError(reason, 503 if reason in ('worker_unavailable', 'state_unavailable', 'disabled') else 409)
                write_json_atomic(state / 'request.json', {
                    'schema': 1, 'job_id': uuid.uuid4().hex, 'target_sha': target_sha.lower(),
                    'expected_sha': expected_sha.lower(), 'requested_at': self.clock(), 'source': BRANCH,
                })
                return self.status()
        except LockBusyError as error:
            raise UpdateError('job_active') from error
        except (OSError, ProtocolError) as error:
            raise UpdateError('state_unavailable', 503) from error

    @staticmethod
    def _fetch(url):
        # Callers above construct only these two fixed endpoint forms.
        allowed = re.fullmatch(re.escape(GITHUB_ROOT) + r'/(?:commits/main|compare/[0-9a-f]{40}\.\.\.[0-9a-f]{40}\?per_page=1)', url)
        if allowed is None:
            raise UpstreamError('github_invalid_response')
        with httpx.Client(timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False) as client:
            with client.stream('GET', url, headers={'Accept': 'application/vnd.github+json',
                    'User-Agent': 'Game-Manage-Updater', 'X-GitHub-Api-Version': '2022-11-28'}) as response:
                if response.status_code != 200:
                    raise UpstreamError('github_rate_limited' if response.status_code == 429 else 'github_unavailable')
                raw = bytearray()
                for chunk in response.iter_bytes(chunk_size=65536):
                    raw.extend(chunk)
                    if len(raw) > MAX_UPSTREAM_BYTES:
                        raise UpstreamError('github_invalid_response')
                import json
                try:
                    value = json.loads(raw)
                except (UnicodeError, ValueError, RecursionError) as error:
                    raise UpstreamError('github_invalid_response') from error
                if not isinstance(value, dict):
                    raise UpstreamError('github_invalid_response')
                return value


MAINTENANCE_PHASES = frozenset({'stopping', 'backing_up', 'activating', 'restarting',
                               'verifying', 'recovery_required'})
BACKGROUND_START_POLL_SECONDS = 0.2


def maintenance_active(service):
    """One conservative cutover decision for HTTP and background startup."""
    if not service.settings.system_update_enabled:
        return False
    try:
        state = service.state_dir()
        if state is None and service.settings.system_update_state_dir:
            state = Path(service.settings.system_update_state_dir).absolute()
        raw = _optional(state / 'status.json') if state else None
        return raw is not None and _job(raw)['phase'] in MAINTENANCE_PHASES
    except (OSError, ValueError):
        # An existing unreadable/unknown status cannot prove cutover ended.
        # A genuinely absent initial file still permits ordinary startup.
        return True


@asynccontextmanager
async def background_start_after_maintenance(service, start):
    """Serve readiness first; own and cancel any deferred startup with lifespan."""
    task = None
    if not maintenance_active(service):
        start()
    else:
        async def wait_and_start():
            while maintenance_active(service):
                await asyncio.sleep(BACKGROUND_START_POLL_SECONDS)
            start()
        task = asyncio.create_task(wait_and_start(), name='system-update-background-start')
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


class UpdateMaintenanceGate:
    """A durable worker phase, never a browser flag, gates cutover writes/reads.

    Installed inside CloudBoundary, so session/CSRF/origin enforcement remains
    outside this gate. Only liveness and the still-admin-gated update GET survive.
    """
    def __init__(self, app, service):
        self.app, self.service = app, service

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and self.service.settings.system_update_enabled:
            path = scope.get('path', '')
            protected = path == '/api' or path.startswith('/api/') or path == '/internal' or path.startswith('/internal/')
            exempt = scope.get('method') == 'GET' and path in ('/api/health', '/api/system/update')
            if protected and not exempt:
                if maintenance_active(self.service):
                    await JSONResponse({'detail': 'update_in_progress', 'error_code': 'update_in_progress'},
                                       status_code=503, headers={'Retry-After': '2'})(scope, receive, send)
                    return
        await self.app(scope, receive, send)


class _EmptyBody(BaseModel):
    model_config = ConfigDict(extra='forbid')


class _ApplyBody(_EmptyBody):
    expected_sha: str = Field(pattern=r'^[0-9a-fA-F]{40}$', strict=True)
    target_sha: str = Field(pattern=r'^[0-9a-fA-F]{40}$', strict=True)


def install_system_update(app, settings, *, cloud=False, version=None):
    service = SystemUpdateService(settings, version=version)
    app.state.system_update = service
    app.state.running_version = service.version
    app.add_middleware(UpdateMaintenanceGate, service=service)
    dependencies = []
    if cloud:
        from .identity.dependencies import require_user
        def require_admin(principal=Depends(require_user)):
            if not principal.is_admin:
                raise HTTPException(403, 'admin_required')
            return principal
        dependencies = [Depends(require_admin)]
    router = APIRouter(prefix='/api/system/update', dependencies=dependencies)

    def no_query(request):
        if request.query_params:
            raise UpdateError('invalid_request', 400)

    async def respond(request, operation, *args):
        try:
            no_query(request)
            return await run_in_threadpool(operation, *args)
        except UpdateError as error:
            return JSONResponse({'detail': error.code, 'error_code': error.code}, status_code=error.status)

    @router.get('')
    async def get_status(request: Request):
        return await respond(request, service.status)

    @router.post('/check')
    async def check(request: Request, body: _EmptyBody):
        return await respond(request, service.check)

    @router.post('/apply')
    async def apply(request: Request, body: _ApplyBody):
        return await respond(request, service.apply, body.expected_sha, body.target_sha)

    app.include_router(router)
    if cloud:
        from .cloud_app import allow_cloud_route
        allow_cloud_route(app, '/api/system/update', ['GET'])
        allow_cloud_route(app, '/api/system/update/check', ['POST'])
        allow_cloud_route(app, '/api/system/update/apply', ['POST'])
    return service
