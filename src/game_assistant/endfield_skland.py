"""Private, account-scoped Skland state for Endfield CN."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from game_assistant.auth.store import CredentialStore, CredentialStoreError
from game_assistant.adapters.endfield.hypergryph import EndfieldError, HypergryphClient
from game_assistant.adapters.endfield.skland_client import PASSPORT_REJECTED, SklandClient, SklandError, TOOLS
from game_assistant.adapters.endfield.skland_parse import (
    obj, parse_attendance, parse_attendance_calendar, parse_card, parse_challenge, parse_operator, parse_roles, parse_user_id,
)

PASSPORT_REQUIRED = "请先在「社区账号」登录终末地"
PASSPORT_EXPIRED = "鹰角通行证登录已失效，请在「社区账号」重新登录"
PASSPORT_CHANGED = "鹰角通行证账号已变化，请重新连接森空岛"


def credential_path(db_path: str) -> Path:
    return Path(db_path).with_suffix(".endfield-skland.credentials.json")


def _safe_public_data(value):
    """Never pass session fields through an upstream data envelope."""
    if isinstance(value, dict):
        return {k: _safe_public_data(v) for k, v in value.items()
                if str(k).lower() not in {"cred", "token", "did", "deviceid", "device_id", "signtoken"}}
    if isinstance(value, list):
        return [_safe_public_data(v) for v in value]
    return value


class EndfieldSklandService:
    ttl_seconds = 120

    @classmethod
    def for_scope(cls, scope, session, *, client=None, clock=None, grant_guard=None, grant_renew=None):
        """Read-only cloud service; credentials come from the resolved grant."""
        from .private_data import validate_scope
        validate_scope(scope)
        if not isinstance(session, dict) or any(not isinstance(session.get(k),str) or not session[k]
                for k in ('cred','user_id','role_id','server_id')):
            raise ValueError('A verified Skland session is required')
        service=cls('',store=_GrantSession(session),client=client,clock=clock)
        service._cloud_renew = grant_renew
        service._cloud_guard = grant_guard
        return ScopedSkland(scope,service)

    def __init__(self, db_path: str, *, client: SklandClient | None = None,
                 store: CredentialStore | None = None, clock=None, passport=None, hypergryph=None):
        self.client = client or SklandClient()
        # passport() → (通行证令牌, uid, role_id, channel, server_id)，旧三字段仅用于官服兼容。
        self._passport_reader = passport or (lambda: ("", "", ""))
        self._hypergryph = hypergryph or HypergryphClient
        self.store = store or CredentialStore(credential_path(db_path))
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = asyncio.Lock()
        self._storage_error = None
        try:
            saved = self.store.load().get("session", {})
        except CredentialStoreError:
            saved = {}
            self._storage_error = "本机森空岛凭据文件无法读取，请重新连接"
        self._session = saved if isinstance(saved, dict) and isinstance(saved.get("cred"), str) else {}
        self._version = 0
        self._cache = None
        self._challenge_cache = {}
        self._operator_cache = {}
        self._tool_cache = {}
        self._last_attendance = None

    def status(self) -> dict:
        session = self._session
        connected = bool(session.get("cred")) and self._belongs_to_passport(session)
        return {"connected": connected, "source": (session.get("source") or "manual") if connected else None,
                "passport_available": self._passport() is not None,
                "roles": session.get("roles", []) if connected else [],
                "selected_role_id": session.get("role_id") if connected else None,
                "selected_server_id": session.get("server_id") if connected else None,
                "error": self._storage_error}

    def _passport(self) -> dict | None:
        values = tuple(str(value or "") for value in self._passport_reader())
        if len(values) == 3:
            values += ("official", "1")
        if len(values) != 5:
            return None
        token, uid, role_id, channel, server_id = values
        server_id = server_id or "1"
        if not token or not uid or not role_id or channel not in ("official", "bilibili") or server_id != "1":
            return None
        return {"token": token, "uid": uid, "role_id": role_id,
                "channel": channel, "server_id": server_id}

    def _belongs_to_passport(self, session: dict) -> bool:
        """Manual sessions are independent; derived sessions follow the complete parent identity."""
        if session.get("source") != "passport":
            return True
        passport = self._passport()
        return bool(passport) and (
            session.get("passport_uid"), session.get("passport_role_id"),
            session.get("passport_channel", "official"), session.get("passport_server_id", "1")) == (
                passport["uid"], passport["role_id"], passport["channel"], passport["server_id"])

    @staticmethod
    def _role_matches_passport(role: dict, passport: dict) -> bool:
        return (role.get("role_id") == passport["role_id"]
                and role.get("server_id") == passport["server_id"]
                and role.get("channel") == passport["channel"]
                and (not role.get("uid") or role["uid"] == passport["uid"]))

    def _save(self, session: dict, *, clear_cache: bool = True):
        try:
            self.store.save({"session": session} if session else {})
        except CredentialStoreError:
            raise SklandError("本机森空岛凭据保存失败，原连接已保留") from None
        self._session = session
        self._storage_error = None
        self._version += 1
        if clear_cache:
            self._cache = None
            self._challenge_cache = {}
            self._operator_cache = {}
            self._tool_cache = {}
            self._last_attendance = None

    async def _validated(self, cred: str, device_id: str = "") -> tuple[dict, str]:
        """Check a session before it may replace the saved one; returns (session, signing token)."""
        token = await self.client.refresh(cred)
        try:
            roles = parse_roles(await self.client.binding(cred, token, device_id))
            user_id = parse_user_id(await self.client.user(cred, token, device_id))
        except (TypeError, ValueError, KeyError, AttributeError):
            raise SklandError('森空岛绑定资料格式已变化，原连接已保留') from None
        if not user_id:
            raise SklandError("森空岛未提供账号标识，连接未保存")
        if not roles:
            raise SklandError("森空岛账号没有可用的国服终末地角色")
        return {"cred": cred, "device_id": device_id, "roles": roles,
                "user_id": user_id, "role_id": None, "server_id": None}, token

    async def connect(self, cred: str, device_id: str = "") -> dict:
        if not isinstance(cred, str) or not 1 <= len(cred.strip()) <= 4096 or any(ord(c) < 32 for c in cred):
            raise SklandError("请输入有效的森空岛会话凭据")
        if not isinstance(device_id, str) or len(device_id) > 512 or any(ord(c) < 32 for c in device_id):
            raise SklandError("设备标识格式不正确")
        cred, device_id = cred.strip(), device_id.strip()
        async with self._lock:
            session, _ = await self._validated(cred, device_id)
            # Validation completes before old account is replaced.
            self._save({**session, "source": "manual"})
            return self.status()

    async def _passport_session(self, passport: dict, keep: tuple | None = None) -> tuple[dict, str]:
        """Exchange the passport token for a new Skland session (no device id) and pick its role."""
        try:
            async with self._hypergryph() as client:
                code = await client.skland_code(passport["token"])
        except EndfieldError as error:
            if error.expired:
                raise SklandError(PASSPORT_EXPIRED, expired=True) from None
            temporary = error.status_code is None or error.message.startswith("HTTP ")
            raise SklandError("森空岛暂时无法连接，请稍后重试" if temporary else PASSPORT_REJECTED) from None
        session, token = await self._validated(await self.client.cred_by_code(code))
        roles = session["roles"]
        role = next((r for r in roles if self._role_matches_passport(r, passport)
                     and (keep is None or (r["role_id"], r["server_id"]) == keep)), None)
        if role is None:
            raise SklandError("森空岛未绑定当前终末地渠道的同一角色，原连接已保留")
        # Only this verified parent identity can be selected in a derived session.
        return {**session, "roles": [role], "source": "passport", "passport_uid": passport["uid"],
                "passport_role_id": passport["role_id"], "passport_channel": passport["channel"],
                "passport_server_id": passport["server_id"],
                "role_id": role["role_id"], "server_id": role["server_id"]}, token

    async def connect_with_passport(self) -> dict:
        async with self._lock:
            passport = self._passport()
            if not passport:
                raise SklandError(PASSPORT_REQUIRED)
            session, _ = await self._passport_session(passport)
            # Validation completes before the saved session is replaced.
            self._save(session)
            return self.status()

    async def on_passport_changed(self, game: str) -> None:
        """Run after a passport login or logout: drop a passport session that no longer matches."""
        if game != "endfield":
            return
        async with self._lock:
            if self._session.get("cred") and not self._belongs_to_passport(self._session):
                self._save({})

    async def select_role(self, role_id: str, server_id: str) -> dict:
        if not isinstance(role_id, str) or not isinstance(server_id, str):
            raise SklandError("角色参数不正确")
        async with self._lock:
            session = self._connected()
            if session.get("source") == "passport":
                passport = self._passport()
                if not passport or (role_id, server_id) != (passport["role_id"], passport["server_id"]):
                    raise SklandError("该连接仅对应当前鹰角角色，其他角色请使用手动授权")
            if not any(r["role_id"] == role_id and r["server_id"] == server_id for r in session.get("roles", [])):
                raise SklandError("该角色不在当前绑定列表中")
            self._save({**session, "role_id": role_id, "server_id": server_id})
            return self.status()

    async def disconnect(self) -> dict:
        async with self._lock:
            self._save({})
            return self.status()

    def _connected(self):
        s = self._session
        if not s.get("cred"):
            raise SklandError("请先连接森空岛")
        if not self._belongs_to_passport(s):
            # Backstop for a missed login/logout notification: never read another account's data.
            self._save({})
            raise SklandError(PASSPORT_CHANGED)
        return s

    def _selected(self):
        s = self._connected()
        if not s.get("role_id") or not s.get("server_id"):
            raise SklandError("请先选择终末地角色")
        if s.get("source") == "passport":
            passport = self._passport()
            if not passport or (s["role_id"], s["server_id"]) != (passport["role_id"], passport["server_id"]):
                raise SklandError("森空岛角色与当前终末地登录不一致，请重新连接")
        return s

    async def _token(self, s):
        """Returns (session, token). The short-lived token is never persisted or returned.

        An expired passport session is exchanged again once with the current passport login.
        """
        try:
            return s, await self.client.refresh(s["cred"])
        except SklandError as error:
            if error.expired and getattr(self,'_cloud_renew',None) and s.get('_parent'):
                renewed = await self._cloud_renew()
                self._session = renewed
                self._version += 1
                return renewed, await self.client.refresh(renewed['cred'])
            if not error.expired or s.get("source") != "passport":
                raise
        passport = self._passport()
        if not passport:
            raise SklandError(PASSPORT_CHANGED)
        selected = (s.get("role_id"), s.get("server_id"))
        renewed, token = await self._passport_session(passport, keep=selected)
        # Same role: keep the last good data as the stale fallback if the next request fails.
        self._save(renewed, clear_cache=(renewed["role_id"], renewed["server_id"]) != selected)
        if not renewed["role_id"]:
            raise SklandError("请先选择终末地角色")
        return renewed, token

    async def read_card(self, force: bool = False) -> dict:
        async with self._lock:
            s = self._selected()
            if self._cache and not force:
                age = (self.clock() - datetime.fromisoformat(self._cache["fetched_at"])).total_seconds()
                if age < self.ttl_seconds and not self._cache["stale"]:
                    return self._cache.copy()
            try:
                s, token = await self._token(s)
                detail = await self.client.card(s["cred"], token, s["role_id"], s["server_id"],
                                                s["user_id"], s.get("device_id", ""))
                if not isinstance(detail, dict):
                    raise SklandError("森空岛角色卡格式已变化")
                # A valid card must belong to the selected role. Do not cache mismatched data.
                actual = str(obj(detail.get("base")).get("roleId") or "")
                if actual != s["role_id"]:
                    raise SklandError("森空岛返回了其他角色的数据")
                now = self.clock().isoformat()
                result = {"payload": parse_card(detail, fetched_at=now), "fetched_at": now,
                          "stale": False, "error": None}
                self._cache = result
                return result.copy()
            except SklandError as exc:
                error = str(exc)
            except (TypeError, ValueError, KeyError):
                error = "森空岛角色卡格式已变化"
            if self._cache:
                self._cache = {**self._cache, "stale": True, "error": error}
                return self._cache.copy()
            return {"payload": None, "fetched_at": None, "stale": True, "error": error}

    async def attendance_status(self) -> dict:
        async with self._lock:
            s = self._selected()
            try:
                result = await self._read_attendance_unlocked(s)
                self._last_attendance = result
                return result.copy()
            except SklandError as exc:
                previous = self._last_attendance
                if previous:
                    return {**previous, "stale": True, "error": str(exc)}
                return {"supported": True, "status": "unknown", "awards": [], "signed_at": None,
                        "calendar": [], "today_award": None, "records": [], "first": [], "activity": None,
                        "updated_at": None, "stale": True, "error": str(exc)}

    async def read_operator(self, char_id: str) -> dict:
        if not isinstance(char_id, str) or not char_id or len(char_id) > 80 or not char_id.replace('-', '').replace('_', '').isalnum():
            raise SklandError('干员编号不正确')
        async with self._lock:
            s = self._selected()
            try:
                s, token = await self._token(s)
                detail = await self.client.operator(s['cred'], token, s['role_id'], s['server_id'],
                                                     s['user_id'], char_id, s.get('device_id', ''))
                operator = parse_operator(detail)
                if operator['id'] != char_id:
                    raise SklandError('森空岛未返回所选干员的配装详情')
                result = {'operator': operator, 'fetched_at': self.clock().isoformat(), 'stale': False, 'error': None}
                self._operator_cache[char_id] = result
                return result.copy()
            except (ValueError, TypeError, KeyError, AttributeError, SklandError) as exc:
                error = str(exc) if isinstance(exc, SklandError) else '森空岛干员详情格式已变化'
                previous = self._operator_cache.get(char_id)
                if previous:
                    result = {**previous, 'stale': True, 'error': error}
                else:
                    result = {'operator': None, 'fetched_at': None, 'stale': True, 'error': error}
                # Preserve the last successful observation time together with
                # its latest failure state for offline website/QQ consumers.
                self._operator_cache[char_id] = result
                return result.copy()

    async def _read_attendance_unlocked(self, session: dict) -> dict:
        session, token = await self._token(session)
        calendar = await self.client.attendance_calendar(session["cred"], token, session["role_id"],
                                                         session["server_id"], session.get("device_id", ""))
        records = await self.client.attendance_records(session["cred"], token, session["role_id"],
                                                       session["server_id"], session.get("device_id", ""))
        try:
            return {**parse_attendance_calendar(calendar, records), "stale": False}
        except (TypeError, ValueError, KeyError, AttributeError):
            raise SklandError('森空岛签到资料格式已变化') from None

    async def sign_attendance(self) -> dict:
        async with self._lock:
            s = self._selected()
            s, token = await self._token(s)
            response = await self.client.attendance(s["cred"], token, s["role_id"], s["server_id"],
                                                    s.get("device_id", ""))
            try:
                result = parse_attendance(response)
            except (TypeError, ValueError, KeyError, AttributeError):
                raise SklandError('签到已提交，但返回的奖励格式无法识别，请刷新状态核对') from None
            try:
                current = await self._read_attendance_unlocked(s)
                self._last_attendance = current
                return current.copy()
            except SklandError as exc:
                self._last_attendance = {**result, "calendar": [], "today_award": None,
                                         "records": [], "first": [], "activity": None,
                                         "updated_at": None, "stale": True, "error": str(exc)}
                return self._last_attendance.copy()

    async def read_challenges(self, kind: str, *, season_id: str | None = None,
                              contract_id: str | None = None, record_id: str | None = None) -> dict:
        if kind not in ("war", "monument", "crisis"):
            return {"supported": False, "kind": kind, "records": [], "summary": {},
                    "fetched_at": None, "stale": False,
                    "error": "该挑战类型暂无已核实的森空岛接口"}
        for item in (season_id, contract_id, record_id):
            if item is not None and (not isinstance(item, str) or len(item) > 80 or
                                     not item.replace("-", "").replace("_", "").isalnum()):
                raise SklandError("挑战参数不正确")
        async with self._lock:
            s = self._selected()
            key = (kind, season_id, contract_id, record_id)
            try:
                s, token = await self._token(s)
                data = await self.client.challenge(kind, s["cred"], token, s["role_id"], s["server_id"],
                                                   s["user_id"], s.get("device_id", ""),
                                                   season_id=season_id, contract_id=contract_id, record_id=record_id)
                try:
                    parsed = parse_challenge(kind, data)
                except (TypeError, ValueError, KeyError, AttributeError):
                    raise SklandError('森空岛挑战记录格式已变化') from None
                result = {**parsed, "fetched_at": self.clock().isoformat(), "stale": False}
                from .endfield_challenges import build_challenge_report
                result['report'] = build_challenge_report(result)
                self._challenge_cache[key] = result
                return result.copy()
            except SklandError as exc:
                result = self._challenge_cache.get(key)
                if result:
                    result = {**result, "stale": True, "error": str(exc)}
                else:
                    result = {"supported": True, "kind": kind, "records": [], "summary": {},
                              "fetched_at": None, "stale": True, "error": str(exc)}
                from .endfield_challenges import build_challenge_report
                result['report'] = build_challenge_report(result)
                self._challenge_cache[key] = result
                return result.copy()

    async def read_tool(self, kind: str) -> dict:
        if kind not in TOOLS:
            return {"supported": False, "kind": kind, "payload": None,
                    "fetched_at": None, "stale": False, "error": "工具类型不受支持"}
        async with self._lock:
            s = self._selected()
            try:
                s, token = await self._token(s)
                data = await self.client.tool(kind, s["cred"], token, s.get("device_id", ""))
                field = {'characters': 'chars', 'weapons': 'weapons', 'equipment': 'equips',
                         'tactical': 'tacticalItems', 'materials': 'materials'}[kind]
                expected = dict if kind == 'materials' else list
                if not isinstance(data, dict) or not isinstance(data.get(field), expected):
                    raise SklandError('森空岛图鉴目录格式已变化')
                result = {"supported": True, "kind": kind, "payload": _safe_public_data(data),
                          "fetched_at": self.clock().isoformat(), "stale": False, "error": None}
                self._tool_cache[kind] = result
                return result.copy()
            except SklandError as exc:
                result = self._tool_cache.get(kind)
                if result:
                    return {**result, "stale": True, "error": str(exc)}
                return {"supported": True, "kind": kind, "payload": None,
                        "fetched_at": None, "stale": True, "error": str(exc)}


class _GrantSession:
    """Ephemeral view of an existing cloud grant; never creates a credential file."""
    def __init__(self, session):
        from copy import deepcopy
        self.session=deepcopy(session)

    def load(self):
        return {'session': self.session}

    def save(self, value):
        raise PermissionError('Cloud Skland grants must use AccountService')


class ScopedSkland:
    METHODS=frozenset(('status','read_card','attendance_status','read_operator','read_challenges','read_tool'))

    def __init__(self,scope,service):
        self.scope,self._service=scope,service

    def _check(self,scope,*,active=True):
        from .private_data import validate_scope
        validate_scope(scope)
        if scope!=self.scope:
            raise PermissionError('Private scope does not match')
        guard = getattr(self._service,'_cloud_guard',None)
        if guard and active:
            guard()

    @property
    def grant_version(self):
        guard = getattr(self._service,'_cloud_guard',None)
        return guard() if guard else None

    def __getattr__(self,name):
        if name not in self.METHODS:
            raise AttributeError(name)
        if name=='status':
            def status(scope):
                self._check(scope)
                return self._service.status()
            return status
        async def read(scope,*args,**kwargs):
            self._check(scope)
            result=await getattr(self._service,name)(*args,**kwargs)
            try:
                self._check(scope)
            except Exception:
                # A response already in flight may refill a cache after close().
                self.clear(scope)
                raise
            return result
        return read

    def cached_operator(self,scope,char_id):
        """Read an existing observation only; never refresh or touch credentials."""
        from copy import deepcopy
        self._check(scope)
        if (not isinstance(char_id,str) or not char_id or len(char_id)>80
                or not char_id.replace('-','').replace('_','').isalnum()):
            return None
        # close() can run while a former request is finishing. A late result
        # must not make a cleared service readable again.
        if not self._service._session.get('cred'):
            return None
        value=self._service._operator_cache.get(char_id)
        return deepcopy(value) if isinstance(value,dict) else None

    def clear(self,scope):
        self._check(scope,active=False)
        service=self._service
        service._cache=None
        service._challenge_cache.clear()
        service._operator_cache.clear()
        service._tool_cache.clear()
        service._last_attendance=None

    def close(self):
        self.clear(self.scope)
        self._service._session={}
        self._service.store.session={}
