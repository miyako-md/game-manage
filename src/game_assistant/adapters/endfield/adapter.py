"""终末地官服账号、寻访账本与官网资讯日历。

森空岛档案使用独立授权和角色选择，在 endfield_skland 中按账号隔离。
"""
import logging

from game_assistant.adapters.base import BaseGameAdapter
from game_assistant.adapters.endfield import parse
from game_assistant.adapters.endfield.data_models import EndfieldEvent
from game_assistant.adapters.endfield.hypergryph import EndfieldError, HypergryphClient
from game_assistant.config import Settings
from game_assistant.endfield_gacha import EndfieldGachaStore, store_path
from game_assistant.models import Capability, FetchResult

logger = logging.getLogger(__name__)


class EndfieldAdapter(BaseGameAdapter):
    game_id = "endfield"
    display_name = "终末地"
    section = "mobile"
    capabilities = [Capability.ACCOUNT, Capability.GACHA, Capability.NEWS, Capability.EVENTS]
    # 每次同步最多请求的页数与页间隔；首次同步没翻完的部分下次续传。
    sync_budget = 120
    sync_interval = 0.3

    def __init__(self, settings: Settings):
        self._settings = settings
        self._store: EndfieldGachaStore | None = None
        self._public = None
        self._public_force = False
        self.credentials_configured = bool(settings.endfield_hg_token)

    def prepare_refresh(self):
        self._public_force = True

    async def _public_rows(self, capability):
        from game_assistant.endfield_public import EndfieldPublicService, PublicSourceError
        if self._public is None:
            self._public = EndfieldPublicService(self._settings.db_path)
        force, self._public_force = self._public_force, False
        try:
            method = self._public.news if capability == Capability.NEWS else self._public.events
            rows = await method(force=force)
            payload = rows if capability == Capability.NEWS else [EndfieldEvent(**row) for row in rows]
            return FetchResult(ok=True, payload=payload)
        except PublicSourceError as error:
            return FetchResult(ok=False, error=str(error), error_kind='source_error')
        except ValueError:
            return FetchResult(ok=False, error='官网数据格式已变化，保留上次成功数据', error_kind='invalid_data')

    async def fetch_news(self):
        return await self._public_rows(Capability.NEWS)

    async def fetch_events(self):
        return await self._public_rows(Capability.EVENTS)

    def _credentials(self) -> tuple[str, str, str]:
        s = self._settings
        if not (s.endfield_hg_token and s.endfield_uid and s.endfield_role_id):
            raise _Unconfigured()
        return s.endfield_hg_token, s.endfield_uid, s.endfield_role_id

    def gacha_store(self) -> EndfieldGachaStore:
        if self._store is None:
            self._store = EndfieldGachaStore(store_path(self._settings.db_path))
        return self._store

    async def _guarded_run(self, run) -> FetchResult:
        try:
            return await run()
        except _Unconfigured:
            return FetchResult(ok=False, error="未登录终末地", error_kind="unconfigured")
        except parse.RoleChangedError as error:
            return FetchResult(ok=False, error=str(error), error_kind="auth_expired")
        except EndfieldError as error:
            return FetchResult(ok=False, error=error.message, error_code=error.status_code,
                               error_kind="auth_expired" if error.expired else "source_error")
        except ValueError:
            return FetchResult(ok=False, error="终末地数据格式已变化，保留上次成功数据", error_kind="invalid_data")
        except Exception as exc:
            logger.warning("终末地数据处理异常，保留上次成功数据 (%s)", type(exc).__name__)
            return FetchResult(ok=False, error="数据处理异常，请稍后重试", error_kind="invalid_data")

    async def fetch_account(self) -> FetchResult:
        async def run():
            token, _, role_id = self._credentials()
            async with HypergryphClient() as client:
                binding = await client.binding_list(await client.grant(token))
            return FetchResult(ok=True, payload=parse.parse_account(binding, expected_role_id=role_id))
        return await self._guarded_run(run)

    async def fetch_gacha(self) -> FetchResult:
        async def run():
            token, uid, role_id = self._credentials()
            store = self.gacha_store()
            async with HypergryphClient() as client:
                u8_token = await client.u8_token(uid, await client.grant(token))
                await store.sync(role_id, client, u8_token, budget=self.sync_budget, interval=self.sync_interval)
            return FetchResult(ok=True, payload=store.summary(role_id))
        return await self._guarded_run(run)


class _Unconfigured(Exception):
    pass
