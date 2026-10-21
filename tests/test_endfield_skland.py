import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI

from fastapi.testclient import TestClient

from game_assistant.api import create_app
from game_assistant.auth.store import CredentialStore, CredentialStoreError
from game_assistant.adapters.endfield.hypergryph import EXPIRED_MESSAGE, EndfieldError
from game_assistant.adapters.endfield.skland_client import PASSPORT_REJECTED, SklandClient, SklandError, sign_request
from game_assistant.adapters.endfield.skland_parse import parse_card
from game_assistant.config import Settings
from game_assistant.endfield_skland import (
    PASSPORT_CHANGED, PASSPORT_EXPIRED, EndfieldSklandService, credential_path,
)
from game_assistant.endfield_skland_routes import install_endfield_skland_routes
from game_assistant.snapshots import SnapshotStore
from tests.test_api import FakeRegistry
from tests.test_registry import DummyAdapter


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail_card = False
        self.fail_challenge = False
        self.fail_exchange = False
        self.exchanges = 0
        self.expired_creds = set()

    async def cred_by_code(self, code):
        self.calls.append(("cred_by_code", code))
        if self.fail_exchange:
            raise SklandError(PASSPORT_REJECTED)
        self.exchanges += 1
        # Every exchange is a new server-side session of the passport's account.
        account = {"code:hg-one": "account-one", "code:hg-two": "account-two"}.get(code, "account-other")
        return f"{account}#{self.exchanges}"

    async def refresh(self, cred):
        self.calls.append(("refresh", cred))
        if cred == "expired" or cred in self.expired_creds:
            raise SklandError("森空岛登录已失效，请重新连接", expired=True)
        return "token"

    async def binding(self, cred, token, device_id=""):
        self.calls.append(("binding", cred, device_id))
        role = "r1" if cred.split("#")[0] == "account-one" else "r2"
        return {"list": [{"appCode": "endfield", "bindingList": [{"uid": "uid-1" if role == "r1" else "uid-2", "isOfficial": True, "channelMasterId": 1, "roles": [
            {"roleId": role, "serverId": "1", "nickname": f"角色{role}"},
            {"roleId": role + "b", "serverId": "2", "nickname": "备用"}]}]}]}

    async def user(self, cred, token, device_id=""):
        return {"user": {"id": "u1" if cred.split("#")[0] == "account-one" else "u2"}}

    async def card(self, cred, token, role_id, server_id, user_id, device_id=""):
        self.calls.append(("card", cred, role_id, server_id, user_id))
        if self.fail_card:
            raise SklandError("网络失败")
        return {"base": {"roleId": role_id, "name": cred, "level": 22},
                "dungeon": {"curStamina": "10", "maxStamina": "200", "maxTs": "1780000000"},
                "chars": [{"id": "c1", "level": 60, "potentialLevel": 2,
                           "charData": {"name": "佩丽卡", "rarity": {"value": "六星"},
                                        "skills": [{"id": "s1", "name": "战技"}]},
                           "userSkills": {"s1": {"level": 7}},
                           "weapon": {"weaponData": {"name": "武器"}, "level": 40}}],
                "dailyMission": {"dailyActivation": 20, "maxDailyActivation": 100},
                "bpSystem": {"curLevel": 3, "maxLevel": 50},
                "domain": [{"domainId": "d1", "name": "四号谷地", "settlements": [{"id": "base1", "level": 2}]}],
                "spaceShip": {"rooms": [{"id": "room1", "level": 3}]}}

    async def attendance(self, cred, token, role_id, server_id, device_id=""):
        self.calls.append(("attendance", role_id, server_id))
        return {"awardIds": [{"id": "a1"}], "resourceInfoMap": {"a1": {"name": "道具", "count": 2}}}

    async def attendance_calendar(self, cred, token, role_id, server_id, device_id=""):
        self.calls.append(("calendar", role_id, server_id))
        return {"hasToday": any(c[0] == "attendance" for c in self.calls),
                "calendar": [{"awardId": "a1", "done": any(c[0] == "attendance" for c in self.calls),
                              "available": True}], "resourceInfoMap": {"a1": {"name": "道具", "count": 2}}}

    async def attendance_records(self, cred, token, role_id, server_id, device_id=""):
        self.calls.append(("records", role_id, server_id))
        return {"records": [], "resourceInfoMap": {}}

    async def challenge(self, kind, cred, token, role_id, server_id, user_id, device_id="", **kwargs):
        self.calls.append(("challenge", kind, role_id, kwargs))
        if self.fail_challenge:
            raise SklandError("网络失败")
        if kind == "war":
            return {"seasons": [{"id": "s1", "name": "第一季", "weeks": [{"id": "w1", "stars": 3}]}], "achieves": []}
        if kind == "monument":
            return {"indieHardGroups": [{"id": "i1", "name": "丰碑", "dungeonGroups": []}]}
        return {"status": {"id": "c1", "highest": 10}, "history": {"records": [{"id": "r1", "isPass": True}]}}

    async def tool(self, kind, cred, token, device_id=""):
        self.calls.append(("tool", kind))
        return {"chars": [{"id": "c1", "token": "must-not-leak"}], "cred": "must-not-leak"}


async def connected_service(tmp_path, cred="account-one"):
    fake = FakeClient()
    service = EndfieldSklandService(str(tmp_path / "a.db"), client=fake)
    await service.connect(cred)
    await service.select_role("r1" if cred == "account-one" else "r2", "1")
    return service, fake


def test_signature_matches_independent_reference():
    path, query, token, ts, did = "/api/v1/game/endfield/card/detail", "roleId=1&serverId=2", "secret", 1780000000, "native-did"
    fields = {"platform": "3", "timestamp": str(ts), "dId": did, "vName": "1.0.0"}
    source = path + query + str(ts) + json.dumps(fields, separators=(",", ":"))
    expected = hashlib.md5(hmac.new(token.encode(), source.encode(), hashlib.sha256).hexdigest().encode()).hexdigest()
    signature, headers = sign_request(token, path, query, timestamp=ts, device_id=did)
    assert signature == expected and headers == fields


async def test_http_client_only_official_host_and_no_error_echo():
    observed = []
    def handle(request):
        observed.append(request)
        if request.url.path.endswith("refresh"):
            return httpx.Response(200, json={"code": 0, "data": {"token": "token"}})
        return httpx.Response(200, json={"code": 10000, "message": "SECRET-CRED and SECRET-TOKEN"})
    client = SklandClient(httpx.MockTransport(handle))
    assert await client.refresh("SECRET-CRED") == "token"
    with pytest.raises(SklandError) as error:
        await client.binding("SECRET-CRED", "SECRET-TOKEN")
    assert "SECRET" not in str(error.value)
    assert all(req.url.host == "zonai.skland.com" for req in observed)
    assert observed[1].headers["cred"] == "SECRET-CRED"
    assert error.value.status is None  # business codes are not HTTP statuses


@pytest.mark.parametrize("status,expired", [(429, False), (503, False), (401, True), (403, True)])
async def test_http_rejection_keeps_only_the_status(status, expired):
    client = SklandClient(httpx.MockTransport(lambda request: httpx.Response(status, text="SECRET-BODY")))
    with pytest.raises(SklandError) as error:
        await client.challenge("war", "SECRET-CRED", "SECRET-TOKEN", "role", "1", "user")
    assert (error.value.status, error.value.expired) == (status, expired)
    assert "SECRET" not in str(error.value)


async def test_official_attendance_methods_and_role_header():
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"hasToday": False}})
    client = SklandClient(httpx.MockTransport(handle))
    await client.attendance_calendar("cred", "token", "role", "server", "native-id")
    await client.attendance_records("cred", "token", "role", "server", "native-id")
    await client.attendance("cred", "token", "role", "server", "native-id")
    assert [(r.method, r.url.path) for r in seen] == [
        ("GET", "/web/v1/game/endfield/attendance"),
        ("GET", "/web/v1/game/endfield/attendance/record"),
        ("POST", "/web/v1/game/endfield/attendance")]
    assert all(r.headers["sk-game-role"] == "3_role_server" and r.headers["did"] == "native-id" for r in seen)
    assert seen[-1].content == b""


async def test_account_and_role_switch_clear_private_cache(tmp_path):
    service, fake = await connected_service(tmp_path)
    first = await service.read_card()
    assert first["payload"]["base"]["name"] == "account-one"
    await service.select_role("r1b", "2")
    second = await service.read_card()
    assert second["payload"]["base"]["role_id"] == "r1b"
    await service.connect("account-two")
    assert service.status()["selected_role_id"] is None
    with pytest.raises(SklandError):
        await service.read_card()
    await service.select_role("r2", "1")
    third = await service.read_card()
    assert third["payload"]["base"]["name"] == "account-two"
    await service.disconnect()
    assert not service.status()["connected"]
    with pytest.raises(SklandError):
        await service.read_card()
    assert fake.calls[-1][0] == "card"


async def test_failed_refresh_uses_stale_cache_without_credential_leak(tmp_path):
    service, fake = await connected_service(tmp_path)
    good = await service.read_card()
    fake.fail_card = True
    old = await service.read_card(force=True)
    assert old["stale"] and old["fetched_at"] == good["fetched_at"]
    assert old["payload"] == good["payload"]
    assert "account-one" not in old["error"]


async def test_expired_connect_keeps_existing_account(tmp_path):
    service, _ = await connected_service(tmp_path)
    with pytest.raises(SklandError) as error:
        await service.connect("expired")
    assert error.value.expired and service.status()["selected_role_id"] == "r1"
    reloaded = EndfieldSklandService(str(tmp_path / "a.db"), client=FakeClient())
    assert reloaded.status()["selected_role_id"] == "r1"
    assert b"account-one" not in (tmp_path / "a.endfield-skland.credentials.json").read_bytes()


async def test_card_and_challenge_parsing(tmp_path):
    service, fake = await connected_service(tmp_path)
    card = (await service.read_card())["payload"]
    assert card["stamina"]["current"] == 10
    assert card["operators"][0]["potential"] == 2
    assert card["operators"][0]["skills"][0]["level"] == 7
    assert card["regions"][0]["settlements"][0]["level"] == 2
    assert card["ship"][0]["id"] == "room1"
    assert [p["cur"] for p in card["progress"]] == [20, None, 3]
    assert (await service.read_challenges("war"))["records"][0]["weeks"][0]["stars"] == 3
    assert (await service.read_challenges("monument"))["records"][0]["name"] == "丰碑"
    assert (await service.read_challenges("crisis", contract_id="c1"))["records"][0]["id"] == "r1"
    assert not (await service.read_challenges("other"))["supported"]
    assert (await service.attendance_status())["status"] == "unsigned"
    signed = await service.sign_attendance()
    assert signed["awards"][0]["count"] == 2 and signed["today_award"]["day"] == 1
    assert (await service.attendance_status())["status"] == "signed"
    assert ("attendance", "r1", "1") in fake.calls


async def test_challenge_stale_and_switch_isolation(tmp_path):
    service, fake = await connected_service(tmp_path)
    old = await service.read_challenges("war")
    fake.fail_challenge = True
    stale = await service.read_challenges("war")
    assert stale["stale"] and stale["fetched_at"] == old["fetched_at"]
    assert stale["records"] == old["records"]
    await service.select_role("r1b", "2")
    fresh = await service.read_challenges("war")
    assert fresh["stale"] and fresh["records"] == []


async def test_calendar_parsing_and_stale_account_isolation(tmp_path):
    service, fake = await connected_service(tmp_path)
    fresh = await service.attendance_status()
    assert fresh["status"] == "unsigned" and fresh["today_award"]["name"] == "道具"
    async def fail(*args, **kwargs):
        raise SklandError("临时失败")
    fake.attendance_calendar = fail
    stale = await service.attendance_status()
    assert stale["stale"] and stale["calendar"] == fresh["calendar"]
    await service.select_role("r1b", "2")
    fresh_other_role = await service.attendance_status()
    assert fresh_other_role["status"] == "unknown" and fresh_other_role["calendar"] == []


async def test_fixed_tool_routes_and_redaction(tmp_path):
    service, fake = await connected_service(tmp_path)
    payload = (await service.read_tool("characters"))["payload"]
    assert payload == {"chars": [{"id": "c1"}]}
    assert not (await service.read_tool("arbitrary-path"))["supported"]
    assert not (await service.read_tool("rules"))["supported"]


async def test_corrupt_store_and_save_failure_do_not_break_service(tmp_path):
    class BrokenStore:
        def load(self):
            raise CredentialStoreError("raw secret must not be shown")

        def save(self, value):
            raise CredentialStoreError("raw secret must not be shown")

    service = EndfieldSklandService(str(tmp_path / "a.db"), client=FakeClient(), store=BrokenStore())
    assert "无法读取" in service.status()["error"]
    with pytest.raises(SklandError) as error:
        await service.connect("account-one")
    assert "raw secret" not in str(error.value)
    assert not service.status()["connected"]


async def test_bad_card_identity_never_cached(tmp_path):
    service, fake = await connected_service(tmp_path)
    original = fake.card
    async def missing_identity(*args, **kwargs):
        result = await original(*args, **kwargs)
        result["base"].pop("roleId")
        return result
    fake.card = missing_identity
    result = await service.read_card()
    assert result["payload"] is None and result["stale"]


async def test_wrong_type_card_response_is_safe(tmp_path):
    service, fake = await connected_service(tmp_path)
    async def wrong(*args, **kwargs):
        return {"base": ["unexpected"], "chars": "unexpected"}
    fake.card = wrong
    result = await service.read_card()
    assert result["payload"] is None and result["stale"]
    assert "格式" in result["error"] or "其他角色" in result["error"]


async def test_concurrent_account_change_cannot_publish_old_card(tmp_path):
    service, fake = await connected_service(tmp_path)
    started, resume = asyncio.Event(), asyncio.Event()
    original = fake.card
    async def slow_card(*args, **kwargs):
        started.set()
        await resume.wait()
        return await original(*args, **kwargs)
    fake.card = slow_card
    read = asyncio.create_task(service.read_card(force=True))
    await started.wait()
    replace = asyncio.create_task(service.connect("account-two"))
    await asyncio.sleep(0)
    resume.set()
    assert (await read)["payload"]["base"]["name"] == "account-one"
    await replace
    assert service.status()["selected_role_id"] is None
    with pytest.raises(SklandError):
        await service.read_card()


async def test_routes_do_not_echo_invalid_secret(tmp_path):
    app = FastAPI()
    install_endfield_skland_routes(app, Settings(db_path=str(tmp_path / "api.db")))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/api/endfield/skland/connect", json={"cred": "X" * 5000, "device_id": "D"})
        assert response.status_code == 400
        assert "XXX" not in response.text
        response = await client.post("/api/endfield/skland/connect", content='{"cred": "SECRET",')
        assert response.status_code == 400
        assert "SECRET" not in response.text
        response = await client.post("/api/endfield/skland/connect", content='{"cred":"' + 'X' * 17000 + '"}')
        assert response.status_code == 413
        # Within the 16 KiB limit, yet deeper than Python 3.11's JSON decoder allows.
        response = await client.post("/api/endfield/skland/connect", content='[' * 8000 + ']' * 8000)
        assert response.status_code == 400
        assert (await client.get("/api/endfield/skland/card")).status_code == 409


async def test_malformed_card_and_challenge_keep_last_success(tmp_path):
    service, fake = await connected_service(tmp_path)
    card = await service.read_card()
    war = await service.read_challenges('war')

    async def malformed_card(*args, **kwargs):
        return {'base': {'roleId': 'r1'}, 'chars': 'not-list', 'dungeon': 'not-dict'}

    async def malformed_war(*args, **kwargs):
        return {'seasons': 'not-list'}

    fake.card, fake.challenge = malformed_card, malformed_war
    bad_card = await service.read_card(force=True)
    bad_war = await service.read_challenges('war')
    assert bad_card['stale'] and bad_card['payload'] == card['payload']
    assert bad_card['fetched_at'] == card['fetched_at']
    assert bad_war['stale'] and bad_war['records'] == war['records']
    assert bad_war['fetched_at'] == war['fetched_at']


async def test_documented_scalar_officer_card_can_refresh_and_invalid_shape_keeps_it(tmp_path):
    service, fake = await connected_service(tmp_path)
    source = {'base': {'roleId': 'r1'},
              'domain': [{'settlements': [{'officerCharIds': 'char1'}]}]}

    async def card(*args, **kwargs):
        return source

    fake.card = card
    good = await service.read_card(force=True)
    assert good['stale'] is False and good['error'] is None
    assert good['payload']['regions'][0]['settlements'][0]['officer_char_ids'] == ['char1']
    source['domain'][0]['settlements'][0]['officerCharIds'] = {'unexpected': 'char1'}
    bad = await service.read_card(force=True)
    assert bad['stale'] is True
    assert bad['payload'] == good['payload']
    assert bad['fetched_at'] == good['fetched_at']


async def test_malformed_attendance_cannot_replace_valid_status(tmp_path):
    service, fake = await connected_service(tmp_path)
    signed = await service.sign_attendance()

    async def malformed(*args, **kwargs):
        return {'hasToday': 'yes', 'calendar': 'not-list'}

    fake.attendance_calendar = malformed
    result = await service.attendance_status()
    assert result['stale'] and result['status'] == signed['status']
    assert result['calendar'] == signed['calendar']


@pytest.mark.parametrize('field,value', [('chars', ['invalid']), ('dungeon', {'curStamina': True}),
                                       ('domain', [{'settlements': 'changed'}]), ('spaceShip', {'rooms': 3})])
def test_present_invalid_fields_are_not_silently_normalized(field, value):
    with pytest.raises((TypeError, ValueError)):
        parse_card({'base': {'roleId': 'r1'}, field: value}, fetched_at='2026-09-28T00:00:00Z')


async def test_operator_detail_uses_official_char_endpoint_and_selected_role():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json={'code': 0, 'data': {'detail': {'id': 'c1', 'charData': {'name': '干员'}}}})
    client = SklandClient(httpx.MockTransport(handle))
    detail = await client.operator('cred', 'token', 'r1', '1', 'u1', 'c1')
    assert detail['id'] == 'c1'
    request = requests[0]
    assert request.url.path == '/api/v1/game/endfield/card/char'
    assert dict(request.url.params) == {'roleId': 'r1', 'serverId': '1', 'userId': 'u1', 'charId': 'c1'}


async def test_operator_detail_equipment_stale_and_role_isolation(tmp_path):
    service, fake = await connected_service(tmp_path)
    async def detail(*args, **kwargs):
        return {'id': 'c1', 'charData': {'name': '佩丽卡', 'skills': [{'id': 's1', 'name': '战技'}]},
                'level': 80, 'userSkills': {'s1': {'level': 8}},
                'bodyEquip': {'equipId': 'eq1', 'equipData': {'name': '护甲'}},
                'weapon': {'weaponData': {'name': '武器'}, 'level': 60, 'breakthroughLevel': 3,
                           'gem': {'gemData': {'name': '基质'}, 'terms': [{'name': '意志', 'cost': '3'}]}}}
    fake.operator = detail
    data = await service.read_operator('c1')
    assert data['operator']['weapon']['gem']['terms'][0]['cost'] == 3
    assert data['operator']['equipment'][0]['name'] == '护甲'
    assert data['operator']['skills'][0]['level'] == 8
    async def wrong(*args, **kwargs):
        return {'id': 'other', 'charData': {'name': 'other'}}
    fake.operator = wrong
    stale = await service.read_operator('c1')
    assert stale['stale'] and stale['operator'] == data['operator']
    await service.select_role('r1b', '2')
    assert (await service.read_operator('c1'))['operator'] is None


# ---- 用鹰角通行证一键连接 ----

def passport_service(tmp_path, identity=("hg-one", "uid-1", "r1"), grant_error=None):
    """森空岛服务 + 可变的通行证身份（模拟 LoginService 写入的设置）+ 记录授权调用的假通行证客户端。"""
    fake = FakeClient()
    current = {"identity": identity}
    grants = []

    class Hypergryph:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return None

        async def skland_code(self, token):
            grants.append(token)
            if grant_error:
                raise grant_error
            return f"code:{token}"

    def build():
        return EndfieldSklandService(str(tmp_path / "a.db"), client=fake,
                                     passport=lambda: current["identity"], hypergryph=Hypergryph)
    return build(), fake, current, grants, build


async def test_cred_by_code_is_unsigned_and_sends_no_session_or_device_headers():
    seen = []
    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"cred": "new-cred", "token": "t", "userId": "u"}})
    client = SklandClient(httpx.MockTransport(handle))
    assert await client.cred_by_code("grant-code") == "new-cred"
    request = seen[0]
    assert (request.method, request.url.host, request.url.path) == (
        "POST", "zonai.skland.com", "/api/v1/user/auth/generate_cred_by_code")
    assert json.loads(request.content) == {"kind": 1, "code": "grant-code"}
    assert not {"cred", "sign", "did"} & {key.lower() for key in request.headers.keys()}


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"code": 10001, "message": "设备信息无效 SECRET-CODE"}),
    httpx.Response(401, json={}),
    httpx.Response(200, json={"code": 0, "data": {"token": "no-cred"}}),
])
async def test_cred_by_code_rejection_is_safe_and_not_an_expired_login(response):
    client = SklandClient(httpx.MockTransport(lambda request: response))
    with pytest.raises(SklandError) as error:
        await client.cred_by_code("SECRET-CODE")
    assert str(error.value) == PASSPORT_REJECTED and not error.value.expired


async def test_passport_connect_selects_same_role_and_never_stores_passport_token(tmp_path):
    service, fake, current, grants, build = passport_service(tmp_path)
    status = await service.connect_with_passport()
    assert status["connected"] and status["source"] == "passport" and status["passport_available"]
    assert (status["selected_role_id"], status["selected_server_id"]) == ("r1", "1")
    assert grants == ["hg-one"] and ("cred_by_code", "code:hg-one") in fake.calls
    saved = service.store.load()["session"]
    assert (saved["passport_uid"], saved["passport_role_id"], saved["device_id"]) == ("uid-1", "r1", "")
    assert "hg-one" not in json.dumps(saved)
    assert (await service.read_card())["payload"]["base"]["role_id"] == "r1"
    # A restart reuses the saved session instead of creating another one upstream.
    assert build().status()["source"] == "passport" and fake.exchanges == 1


async def test_passport_connect_requires_login_and_failure_keeps_manual_session(tmp_path):
    service, fake, current, grants, _ = passport_service(tmp_path, identity=("", "", ""))
    await service.connect("account-two")
    assert not service.status()["passport_available"]
    with pytest.raises(SklandError, match="请先在「社区账号」登录终末地"):
        await service.connect_with_passport()
    current["identity"] = ("hg-one", "uid-1", "r1")
    fake.fail_exchange = True
    with pytest.raises(SklandError) as error:
        await service.connect_with_passport()
    assert str(error.value) == PASSPORT_REJECTED
    status = service.status()
    assert status["source"] == "manual" and status["roles"][0]["role_id"] == "r2"


async def test_passport_role_missing_from_skland_is_not_auto_selected(tmp_path):
    service, *_ = passport_service(tmp_path, identity=("hg-one", "uid-1", "r9"))
    with pytest.raises(SklandError, match="同一角色.*原连接已保留"):
        await service.connect_with_passport()
    assert service.store.load() == {}


@pytest.mark.parametrize("grant_error, message, expired", [
    (EndfieldError(EXPIRED_MESSAGE, status_code=401, expired=True), PASSPORT_EXPIRED, True),
    (EndfieldError("接口错误 status=1", status_code=1), PASSPORT_REJECTED, False),
    (EndfieldError("网络错误: ConnectError"), "森空岛暂时无法连接，请稍后重试", False),
])
async def test_passport_grant_errors_are_mapped_without_saving(tmp_path, grant_error, message, expired):
    service, *_ = passport_service(tmp_path, grant_error=grant_error)
    with pytest.raises(SklandError) as error:
        await service.connect_with_passport()
    assert (str(error.value), error.value.expired) == (message, expired)
    assert not service.status()["connected"] and service.store.load() == {}


async def test_passport_logout_or_switch_clears_only_passport_session(tmp_path):
    service, fake, current, _, _ = passport_service(tmp_path)
    await service.connect_with_passport()
    await service.read_card()
    current["identity"] = ("hg-one-relogin", "uid-1", "r1")  # same account, new token
    await service.on_passport_changed("endfield")
    assert service.status()["connected"]
    current["identity"] = ("", "", "")  # LoginService has applied the logout
    assert not service.status()["connected"]  # reported at once, without a network call
    await service.on_passport_changed("endfield")
    assert service.store.load() == {}
    await service.connect("account-two")
    current["identity"] = ("hg-two", "uid-2", "r2")
    await service.on_passport_changed("endfield")
    assert service.status()["source"] == "manual"


async def test_reads_refuse_a_passport_session_after_a_missed_switch(tmp_path):
    service, fake, current, _, _ = passport_service(tmp_path)
    await service.connect_with_passport()
    current["identity"] = ("hg-two", "uid-2", "r2")
    with pytest.raises(SklandError, match=PASSPORT_CHANGED):
        await service.read_card(force=True)
    assert service.store.load() == {} and not any(call[0] == "card" for call in fake.calls)


async def test_expired_passport_session_is_renewed_once_and_keeps_chosen_role(tmp_path):
    service, fake, current, grants, _ = passport_service(tmp_path)
    await service.connect_with_passport()
    with pytest.raises(SklandError, match="仅对应当前鹰角角色.*手动授权"):
        await service.select_role("r1b", "2")
    first = service.store.load()["session"]["cred"]
    fake.expired_creds.add(first)
    card = await service.read_card(force=True)
    assert card["error"] is None and card["payload"]["base"]["role_id"] == "r1"
    renewed = service.store.load()["session"]
    assert renewed["cred"] != first and (renewed["role_id"], renewed["server_id"]) == ("r1", "1")
    assert grants == ["hg-one", "hg-one"]


async def test_failed_renewal_keeps_stale_card_and_manual_sessions_never_renew(tmp_path):
    service, fake, current, grants, _ = passport_service(tmp_path)
    await service.connect_with_passport()
    good = await service.read_card()
    fake.expired_creds.add(service.store.load()["session"]["cred"])
    fake.fail_exchange = True
    card = await service.read_card(force=True)
    assert card["stale"] and card["error"] == PASSPORT_REJECTED and card["payload"] == good["payload"]
    manual, manual_fake = await connected_service(tmp_path / "manual")
    manual_fake.expired_creds.add("account-one")
    result = await manual.read_card(force=True)
    assert result["stale"] and not any(call[0] == "cred_by_code" for call in manual_fake.calls)


async def test_passport_logout_waits_for_in_flight_read_then_drops_session(tmp_path):
    service, fake, current, _, _ = passport_service(tmp_path)
    await service.connect_with_passport()
    started, resume = asyncio.Event(), asyncio.Event()
    original = fake.card
    async def slow_card(*args, **kwargs):
        started.set()
        await resume.wait()
        return await original(*args, **kwargs)
    fake.card = slow_card
    read = asyncio.create_task(service.read_card(force=True))
    await started.wait()
    current["identity"] = ("", "", "")
    change = asyncio.create_task(service.on_passport_changed("endfield"))
    await asyncio.sleep(0)
    assert not change.done()
    resume.set()
    assert (await read)["payload"]["base"]["role_id"] == "r1"  # requested before the logout
    await change
    assert service.store.load() == {}
    with pytest.raises(SklandError):
        await service.read_card()


async def test_saved_session_without_source_is_a_manual_session(tmp_path):
    CredentialStore(credential_path(str(tmp_path / "a.db"))).save({"session": {
        "cred": "account-one", "device_id": "", "user_id": "u1", "role_id": "r1", "server_id": "1",
        "roles": [{"role_id": "r1", "server_id": "1", "nickname": "角色r1"}]}})
    service = EndfieldSklandService(str(tmp_path / "a.db"), client=FakeClient())
    status = service.status()
    assert status["connected"] and status["source"] == "manual" and not status["passport_available"]


def test_installer_follows_login_service_and_passport_route_is_protected(tmp_path):
    settings = Settings(db_path=str(tmp_path / "db"))
    app = create_app(registry=FakeRegistry(DummyAdapter()), store=SnapshotStore(settings.db_path),
                     settings=settings, start_scheduler=False)
    assert app.state.auth._account_listeners == [app.state.endfield_skland.on_passport_changed]
    client = TestClient(app, base_url="http://127.0.0.1:8010")
    assert client.post("/api/endfield/skland/passport").status_code == 403
    response = client.post("/api/endfield/skland/passport", headers={"X-Game-Assistant": "1"})
    assert response.status_code == 409 and "社区账号" in response.json()["detail"]
    assert client.get("/api/endfield/skland/status").json()["passport_available"] is False
    settings.endfield_hg_token, settings.endfield_uid, settings.endfield_role_id = "hg", "uid", "r1"
    assert client.get("/api/endfield/skland/status").json()["passport_available"] is True


def test_disconnect_reports_a_failed_credential_save(tmp_path):
    settings = Settings(db_path=str(tmp_path / "db"))
    app = create_app(registry=FakeRegistry(DummyAdapter()), store=SnapshotStore(settings.db_path),
                     settings=settings, start_scheduler=False)
    service = app.state.endfield_skland
    service.client = FakeClient()
    client = TestClient(app, base_url="http://127.0.0.1:8010", raise_server_exceptions=False)
    headers = {"X-Game-Assistant": "1"}
    assert client.post("/api/endfield/skland/connect", headers=headers, json={"cred": "account-one"}).status_code == 200

    def locked(_value):
        raise CredentialStoreError("locked")
    service.store.save = locked
    response = client.delete("/api/endfield/skland/connection", headers=headers)
    assert response.status_code == 400
    assert response.json() == {"detail": "本机森空岛凭据保存失败，原连接已保留"}
    assert client.get("/api/endfield/skland/status").json()["connected"] is True



@pytest.mark.parametrize("metadata", [
    {"uid": "wrong-uid", "channelMasterId": 2},
    {"uid": "bili-uid", "channelMasterId": 1, "isOfficial": True},
    {"uid": "bili-uid"},
    {"uid": "bili-uid", "channelMasterId": 2, "isOfficial": True},
    {"uid": "bili-uid", "channelMasterId": 2, "serverId": "2"},
])
async def test_bilibili_passport_refuses_other_identity_and_keeps_manual_session(tmp_path, metadata):
    service, fake, *_ = passport_service(tmp_path, identity=("hg-one", "bili-uid", "r1", "bilibili", "1"))
    await service.connect("account-two")
    await service.select_role("r2", "1")
    good = await service.read_card()
    saved = service.store.load()
    async def binding(*args):
        account = {key: value for key, value in metadata.items() if key != "serverId"}
        account["roles"] = [{"roleId": "r1", "serverId": metadata.get("serverId", "1")}]
        return {"list": [{"appCode": "endfield", "bindingList": [account]}]}
    fake.binding = binding
    with pytest.raises(SklandError, match="同一角色.*原连接已保留"):
        await service.connect_with_passport()
    assert service.store.load() == saved
    assert service._cache == good and service.status()["source"] == "manual"


@pytest.mark.parametrize("uid", ["bili-uid", None])
async def test_bilibili_passport_accepts_verified_channel_with_matching_or_unprovided_uid(tmp_path, uid):
    service, fake, *_ = passport_service(tmp_path, identity=("hg-one", "bili-uid", "r1", "bilibili", "1"))
    async def binding(*args):
        return {"list": [{"appCode": "endfield", "bindingList": [
            {"uid": "wrong-uid", "isOfficial": True, "roles": [{"roleId": "r1", "serverId": "1"}]},
            {"uid": uid, "channelMasterId": 2, "roles": [{"roleId": "r1", "serverId": "1"}]}]}]}
    fake.binding = binding
    await service.connect_with_passport()
    saved = service.store.load()["session"]
    assert saved["passport_uid"] == "bili-uid" and saved["passport_channel"] == "bilibili"
    assert saved["passport_server_id"] == "1" and saved["roles"][0]["channel"] == "bilibili"
    assert len(saved["roles"]) == 1


async def test_passport_renewal_rejects_channel_change_and_retains_authorization_and_cache(tmp_path):
    service, fake, *_ = passport_service(tmp_path)
    await service.connect_with_passport()
    good = await service.read_card()
    saved = service.store.load()
    fake.expired_creds.add(saved["session"]["cred"])
    async def binding(*args):
        return {"list": [{"appCode": "endfield", "bindingList": [
            {"uid": "uid-1", "channelMasterId": 2, "roles": [{"roleId": "r1", "serverId": "1"}]}]}]}
    fake.binding = binding
    card = await service.read_card(force=True)
    assert card["stale"] and "同一角色" in card["error"] and card["payload"] == good["payload"]
    assert service.store.load() == saved


async def test_passport_role_selection_rejection_preserves_selected_role_and_cache(tmp_path):
    service, *_ = passport_service(tmp_path)
    await service.connect_with_passport()
    good = await service.read_card()
    saved = service.store.load()
    with pytest.raises(SklandError, match="其他角色请使用手动授权"):
        await service.select_role("r1b", "2")
    assert service.store.load() == saved and service._cache == good


@pytest.mark.parametrize("changed", [
    ("hg-one", "uid-1", "r1", "bilibili", "1"),
    ("hg-one", "uid-1", "r1", "official", "2"),
    ("hg-one", "different", "r1", "official", "1"),
])
async def test_saved_passport_session_is_bound_to_full_parent_identity(tmp_path, changed):
    service, fake, current, *_ = passport_service(tmp_path)
    await service.connect_with_passport()
    current["identity"] = changed
    assert service.status()["connected"] is False
    before = list(fake.calls)
    with pytest.raises(SklandError, match=PASSPORT_CHANGED):
        await service.read_card()
    assert fake.calls == before


async def test_legacy_official_passport_session_defaults_parent_channel_and_server_only(tmp_path):
    service, fake, current, _, build = passport_service(tmp_path)
    await service.connect_with_passport()
    saved = service.store.load()["session"]
    saved.pop("passport_channel")
    saved.pop("passport_server_id")
    service.store.save({"session": saved})
    assert build().status()["connected"] is True
    current["identity"] = ("hg-one", "uid-1", "r1", "bilibili", "1")
    assert build().status()["connected"] is False


def test_local_route_passport_reader_includes_channel_and_server(tmp_path):
    settings = Settings(db_path=str(tmp_path / "db"), endfield_hg_token="hg", endfield_uid="bili-uid",
                        endfield_role_id="r", endfield_channel="bilibili", endfield_server_id="1")
    app = FastAPI()
    install_endfield_skland_routes(app, settings)
    assert app.state.endfield_skland._passport() == {
        "token": "hg", "uid": "bili-uid", "role_id": "r", "channel": "bilibili", "server_id": "1"}
