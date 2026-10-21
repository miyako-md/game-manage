"""Role-specific adapter contexts, backed only by cloud grant ciphertext."""
from datetime import datetime, timezone
from pathlib import Path

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.auth.service import FIELDS, LoginError, PUBLIC_CAPABILITIES
from game_assistant.auth.store import CredentialStoreError
from game_assistant.identity.models import Principal
from game_assistant.models import Capability, FetchResult
from .store import AccountNotFoundError
from .identities import has_verified_role


class SklandAccountAdapter(BaseGameAdapter):
    game_id = 'endfield'
    capabilities = [Capability.ACCOUNT, Capability.COMBAT]
    credentials_configured = True

    def __init__(self, settings):
        self._settings = settings
        self._credentials = {}

    async def fetch_account(self):
        from game_assistant.adapters.endfield.skland_client import SklandClient, SklandError
        from game_assistant.adapters.endfield.skland_parse import parse_card, obj
        try:
            s = self._credentials
            client = SklandClient()
            token = await client.refresh(s['cred'])
            detail = await client.card(s['cred'],token,s['role_id'],s['server_id'],s['user_id'],s.get('device_id',''))
            if str(obj(detail.get('base')).get('roleId') or '') != s['role_id']:
                raise ValueError('role mismatch')
            return FetchResult(ok=True,payload=parse_card(detail,fetched_at=datetime.now(timezone.utc).isoformat()))
        except SklandError as error:
            return FetchResult(ok=False,error='森空岛查询失败',error_kind='auth_expired' if error.expired else 'source_error')
        except (ValueError,TypeError,KeyError):
            return FetchResult(ok=False,error='森空岛角色数据不匹配',error_kind='invalid_data')

    async def fetch_combat(self):
        """One signing refresh, then the three default challenge reads in order.

        Only the allowlisted projection is returned. A failed kind is reported as
        a failed observation; the scheduler keeps its last successful report.
        """
        from game_assistant.adapters.endfield.skland_client import SklandClient, SklandError
        from game_assistant.adapters.endfield.skland_parse import parse_challenge
        from game_assistant.endfield_challenges import CHALLENGE_KINDS, build_challenge_report
        s = self._credentials
        client = SklandClient()
        try:
            token = await client.refresh(s['cred'])
        except SklandError as error:
            return FetchResult(ok=False,error='森空岛查询失败',error_code=error.status,failure_codes=f'refresh:{error.code or "unknown"}',
                               error_kind='auth_expired' if error.expired else 'source_error')
        # failed: '<kind>:<short code>' per failed kind, for the scheduler's log line only.
        reports,codes,failed = [],[],[]
        for kind in CHALLENGE_KINDS:
            try:
                data = await client.challenge(kind,s['cred'],token,s['role_id'],s['server_id'],s['user_id'],s.get('device_id',''))
                value = {**parse_challenge(kind,data),'fetched_at':datetime.now(timezone.utc).isoformat(),'stale':False}
            except SklandError as error:
                failed.append(f'{kind}:{error.code or "unknown"}')
                if error.expired:
                    return FetchResult(ok=False,error='森空岛查询失败',error_code=error.status,error_kind='auth_expired',failure_codes=','.join(failed))
                codes.append(error.status)
                value = {'supported':True,'kind':kind,'fetched_at':None,'stale':True}
            except (ValueError,TypeError,KeyError,AttributeError) as error:
                failed.append(f'{kind}:parse:{type(error).__name__}')
                codes.append(None)
                value = {'supported':True,'kind':kind,'fetched_at':None,'stale':True}
            reports.append(build_challenge_report(value,kind=kind))
        # 429 wins so rate limiting stays visible even when another kind failed differently.
        code = 429 if 429 in codes else next((c for c in codes if c is not None),None)
        if len(codes) == len(CHALLENGE_KINDS):
            return FetchResult(ok=False,error='森空岛挑战查询失败',error_code=code,error_kind='source_error',failure_codes=','.join(failed))
        return FetchResult(ok=True,payload={'schema_version':1,'reports':reports},error_code=code,failure_codes=','.join(failed) or None)


class AccountRuntime:
    def __init__(self, accounts, settings, root_path, *, login=None):
        self.accounts, self.template, self.root_path, self.login = accounts, settings, Path(root_path), login
        self._registries = {}
        self._closed = False
        accounts._listeners.append(self.invalidate)

    def for_scope(self, scope):
        if self._closed:
            raise RuntimeError('Account runtime is closed')
        info = self.accounts.describe(scope)
        # Loading on each resolution detects missing key/corruption even for cached adapters.
        credentials = self.accounts.credentials.load_grant(scope.user_id,info['grant_id'])
        if not has_verified_role(credentials, info['game_uid'], info['server'], info['channel']):
            raise AccountNotFoundError()
        existing = self._registries.get(scope)
        if existing and existing[0] == info['version']:
            return existing[1]
        settings = self.template.model_copy(deep=True)
        for mapping in FIELDS.values():
            for field in mapping.values():
                setattr(settings,field,'')
        settings.wuwa_app_token = settings.notify_send_key = ''
        settings.auth_store_path = ''
        settings.lol_enabled = False
        from game_assistant.private_data import scope_directory
        settings.db_path = str(scope_directory(self.root_path,scope) / 'private.db')
        from game_assistant.registry import build_account_registry
        registry = build_account_registry(settings,info['game'],provider=info['provider'])
        if info['provider']=='hypergryph':
            from game_assistant.endfield_gacha import EndfieldGachaStore
            ledger = EndfieldGachaStore.for_scope(scope,self.root_path,role_uid=info['game_uid'],server_id=info['server'])
            registry.get('endfield')._store = _ScopedLegacyLedger(ledger,scope,info['game_uid'])
        guard = _GrantGuard(self,scope,registry,info,credentials)
        for adapter in registry.all():
            adapter._auth = guard
        self._registries[scope] = (info['version'],registry,info['grant_id'])
        return registry

    def invalidate(self, user_id, grant_id):
        for scope,value in list(self._registries.items()):
            if scope.user_id == user_id and value[2] == grant_id:
                self._registries.pop(scope,None)

    async def aclose(self):
        self._closed = True
        self.accounts._listeners.remove(self.invalidate)
        # Current adapters create HTTP clients in async-with blocks per request.
        # No credential-bearing global pool or session survives this runtime.
        self._registries.clear()


class _ScopedLegacyLedger:
    """Bridge adapter role arguments to Task 5's checked scope operations."""
    def __init__(self,ledger,scope,role_uid):
        self.ledger,self.scope,self.role_uid = ledger,scope,role_uid

    def __getattr__(self,name):
        method = getattr(self.ledger,name)
        def call(role_uid,*args,**kwargs):
            if role_uid!=self.role_uid:
                raise PermissionError('Ledger role does not match the account scope')
            return method(self.scope,*args,**kwargs)
        return call


class _GrantGuard:
    def __init__(self,runtime,scope,registry,info,credentials):
        self.runtime,self.scope,self.registry = runtime,scope,registry
        self.info = info
        self.apply(credentials,info['version'])

    def apply(self,credentials,version):
        self.credentials = credentials
        self.info['version'] = version
        for adapter in self.registry.all():
            if self.info['provider'] == 'skland':
                adapter._credentials = {**credentials,'role_id':self.info['game_uid'],'server_id':self.info['server']}
                continue
            settings = adapter._settings
            for key,field in FIELDS[self.info['game']].items():
                setattr(settings,field,str(credentials.get(key) or ''))
            setattr(settings,FIELDS[self.info['game']]['role_id'],self.info['game_uid'])
            if 'server_id' in FIELDS[self.info['game']]:
                setattr(settings,FIELDS[self.info['game']]['server_id'],self.info['server'])
            if self.info['provider'] == 'hypergryph':
                settings.endfield_channel = self.info['channel']
            adapter.credentials_configured = True
            if self.info['game'] == 'wuthering_waves':
                from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient
                adapter._client = KuroClient(settings.wuwa_token,did=settings.wuwa_did,source=settings.wuwa_token_source)
            adapter.prepare_refresh()

    async def fetch(self,game,capability,action):
        try:
            if self.runtime._closed:
                raise AccountNotFoundError()
            info = self.runtime.accounts.describe(self.scope)
            if info['version'] != self.info['version']:
                raise AccountNotFoundError()
            if self.runtime.login and game=='wuthering_waves' and self.credentials.get('role_id')!=info['game_uid']:
                updated,version = await self.runtime.login.renew(Principal(self.scope.user_id,False),info['grant_id'],
                    role_id=info['game_uid'],server_id=info['server'])
                self.apply(updated,version)
            if self.runtime.login and game == 'nte' and capability not in PUBLIC_CAPABILITIES.get(game,()) and (
                    not self.credentials.get('access_token') or
                    self.runtime.login.clock()-self.credentials.get('_updated_at',self.runtime.login.clock())>=3600):
                updated,version = await self.runtime.login.renew(Principal(self.scope.user_id,False),info['grant_id'])
                self.apply(updated,version)
            version = self.info['version']
            result = await action()
            if self.runtime.accounts.describe(self.scope)['version'] != version:
                raise AccountNotFoundError()
            if not result.ok and result.error_kind == 'auth_expired' and self.runtime.login and info['provider'] == 'skland' and self.credentials.get('_parent'):
                updated,version = await self.runtime.login.renew_skland(Principal(self.scope.user_id,False),info['grant_id'],
                    expected_version=version,role_id=info['game_uid'],server_id=info['server'])
                self.apply(updated,version)
                result = await action()
                if self.runtime.accounts.describe(self.scope)['version'] != version:
                    raise AccountNotFoundError()
            rolebox = capability in (Capability.ROLES,Capability.EXPLORATION,Capability.CALABASH,Capability.STAMINA,
                                    Capability.PROGRESS,Capability.COMBAT,Capability.ACTIVITIES,Capability.RESOURCES) or result.error_source=='rolebox'
            invalid = (result.error_code in (10900,10901,10903) or rolebox and result.error_code in (401,403)) if game=='wuthering_waves' else result.error_code in (401,402,403)
            if not result.ok and invalid and self.runtime.login and game in ('nte','wuthering_waves'):
                updated,version = await self.runtime.login.renew(Principal(self.scope.user_id,False),info['grant_id'],
                    **({'role_id':info['game_uid'],'server_id':info['server']} if game=='wuthering_waves' else {}))
                self.apply(updated,version)
                result = await action()
                if self.runtime.accounts.describe(self.scope)['version'] != version:
                    raise AccountNotFoundError()
            result.credential_version = version
            return result
        except (AccountNotFoundError,CredentialStoreError):
            return FetchResult(ok=False,error='授权已失效，请重新授权',error_kind='auth_expired')
        except LoginError as error:
            return FetchResult(ok=False,error=error.message,error_kind=error.error_kind or 'source_error')
