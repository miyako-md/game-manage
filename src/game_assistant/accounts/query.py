"""The cached read/refresh contract shared by website and QQ clients."""
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException

from game_assistant.auth.service import PUBLIC_CAPABILITIES
from game_assistant.auth.store import CredentialStoreError
from game_assistant.models import Capability, FetchResult
from .models import QueryResult
from .store import AccountNotFoundError


def completeness(payload):
    if isinstance(payload, dict):
        for key in ('complete', 'history_complete'):
            if type(payload.get(key)) is bool:
                return payload[key]
    return None


class AccountQuery:
    def __init__(self, accounts, runtime, snapshots, *, scheduler=None, private=None):
        self.accounts, self.runtime, self.snapshots = accounts, runtime, snapshots
        self.scheduler, self.private = scheduler, private

    def adapter(self, scope):
        info = self.accounts.describe(scope)
        return self.runtime.for_scope(scope).get(info['game'])

    def capabilities(self, scope):
        adapter = self.adapter(scope)
        return [cap.value for cap in adapter.capabilities
                if cap not in PUBLIC_CAPABILITIES.get(adapter.game_id, ())
                and cap not in (Capability.NEWS, Capability.ANNOUNCEMENT, Capability.EVENTS)]

    def validate(self, scope, capability):
        info = self.accounts.describe(scope)
        if capability not in self.capabilities(scope):
            raise AccountNotFoundError()
        return info

    def _poll_status(self, scope, capability, version, generation):
        stored = self.snapshots.get_poll_status_scoped(scope, capability,
            grant_version=version, minimum_version=generation)
        if (stored and stored['state'] == 'auth_expired' and
                self.snapshots.get_poll_status_scoped(scope, capability, grant_version=version) is None):
            # The old token's failure remains in storage; it says nothing about
            # the replacement token. Keep the last data while awaiting its first read.
            return {**stored, 'state':'never', 'error':None, 'error_kind':None,
                    'consecutive_failures':0, 'refresh_required':True}
        return stored

    def read(self, scope, capability):
        info = self.validate(scope, capability)
        generation = self.accounts.snapshot_generation(scope, info['version'])
        snapshot = self.snapshots.get_scoped(scope, capability, grant_version=info['version'], minimum_version=generation)
        status = self._poll_status(scope, capability, info['version'], generation)
        payload = json.loads(snapshot['payload']) if snapshot else None
        return QueryResult(payload, snapshot['fetched_at'] if snapshot else None,
                           status['state'] if status else 'never', completeness(payload))

    def status(self, scope, capability):
        info = self.validate(scope, capability)
        generation = self.accounts.snapshot_generation(scope, info['version'])
        stored = self._poll_status(scope, capability, info['version'], generation)
        return {**(stored or dict(state='never', last_attempt_at=None, last_success_at=None,
                                 consecutive_failures=0, error=None, error_kind=None)),
                'refresh_state': self.scheduler.refresh_state(scope, capability) if self.scheduler else 'idle',
                'observed_at': datetime.now(timezone.utc).isoformat()}

    def request_refresh(self, scope, capability):
        self.validate(scope, capability)
        if self.scheduler is None:
            raise HTTPException(503, 'scheduler_unavailable')
        return self.scheduler.request_refresh(scope, capability)

    def list_accounts(self, principal):
        result = self.accounts.list_accounts(principal)
        for account in result:
            if account['state'] != 'active' or not account['roles']:
                # A revoked grant cannot resolve a runtime or reveal old private data.
                account['capabilities'] = []
                continue
            role = next((r for r in account['roles'] if r['is_default']), account['roles'][0])
            scope = self.accounts.require_scope(principal, account['account_id'], role['role_id'])
            try:
                account['capabilities'] = self.capabilities(scope)
                account['display_name'] = self.adapter(scope).display_name
            except CredentialStoreError:
                account['capabilities'] = []
                account['query_state'] = 'credential_unavailable'
        return result


@dataclass(frozen=True, slots=True)
class PublicQueryResult(QueryResult):
    stale: bool
    poll_status: dict
    primary_source: str
    version: str | None
    bilibili_status: dict | None
    version_metadata: dict | None = None
    artwork_sources: list[dict] | None = None
    artwork_status: dict | None = None


class CloudPublicQuery:
    """One credential-free public registry and optional Bilibili collector."""
    def __init__(self, registry, snapshots, *, bilibili=None, settings=None):
        from game_assistant.config import Settings
        self.registry, self.snapshots, self.bilibili = registry, snapshots, bilibili
        self.settings = settings or getattr(bilibili, 'settings', None) or Settings()
        self.sources = [adapter.game_id for adapter in registry.all()]

    def provider(self, game):
        return 'public_sources'

    async def poll(self, game):
        from fastapi.encoders import jsonable_encoder
        from game_assistant.sources.article_content import retain_article_bodies
        adapter = self.registry.get(game)
        # The collector is scheduled once per game, never once per user/capability.
        if self.bilibili and game in self.bilibili.sources:
            await self.bilibili.run(game)
        for cap in (Capability.NEWS, Capability.ANNOUNCEMENT, Capability.EVENTS, Capability.TEAMS):
            if cap not in adapter.capabilities:
                continue
            try:
                result = await adapter.fetch(cap)
            except Exception:
                result = FetchResult(ok=False, error='公共数据源请求失败', error_kind='source_error')
            if result.ok:
                payload = jsonable_encoder(result.payload)
                if cap in (Capability.NEWS, Capability.ANNOUNCEMENT) and isinstance(payload, list):
                    previous = self.snapshots.get(game, cap.value)
                    payload = retain_article_bodies(payload, json.loads(previous['payload']) if previous else [])
                self.snapshots.save(game, cap.value, json.dumps(payload, ensure_ascii=False))
            self.snapshots.record_poll(game, cap.value, result)

    def read(self, game, capability):
        from game_assistant.sources.public_snapshot import read_public_snapshot
        if game == 'nte' and capability == 'teams' and game in self.sources:
            # Teams are public in PUBLIC_CAPABILITIES, so private refreshes
            # deliberately omit them. Keep one public cache for website and QQ.
            from game_assistant.sources.public_snapshot import expired
            from game_assistant.scheduler import interval_for
            now = datetime.now(timezone.utc)
            snapshot = self.snapshots.get(game, capability)
            status = self.snapshots.get_poll_status(game, capability) or dict(
                game_id=game, capability=capability, state='never', last_attempt_at=None,
                last_success_at=snapshot['fetched_at'] if snapshot else None,
                consecutive_failures=0, error=None, error_kind=None)
            payload = json.loads(snapshot['payload']) if snapshot else None
            stale = bool(snapshot and (expired(snapshot['fetched_at'],
                interval_for(Capability.TEAMS, self.settings), now)
                or status['state'] in ('error', 'auth_expired')))
            return PublicQueryResult(payload=payload,
                fetched_at=snapshot['fetched_at'] if snapshot else None,
                state=status['state'], complete=completeness(payload), stale=stale,
                poll_status={**status, 'stale':stale, 'observed_at':now.isoformat()},
                primary_source='official', version=None, bilibili_status=None)
        if game not in self.sources or capability not in ('news', 'events'):
            raise AccountNotFoundError()
        data = read_public_snapshot(self.snapshots, game, capability, self.settings, self.bilibili)
        return PublicQueryResult(state=data['poll_status']['state'], **data)

    async def aclose(self):
        try:
            if self.bilibili:
                await self.bilibili.close()
        finally:
            for adapter in self.registry.all():
                public = getattr(adapter, '_public', None)
                if public is not None:
                    public.close()
