import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI

from game_assistant.auth.store import CredentialStoreError
from game_assistant.adapters.endfield.skland_client import SklandClient, SklandError, sign_request
from game_assistant.adapters.endfield.skland_parse import parse_card, parse_challenge
from game_assistant.config import Settings
from game_assistant.endfield_skland import EndfieldSklandService
from game_assistant.endfield_skland_routes import install_endfield_skland_routes


class FakeClient:
    def __init__(self):
        self.calls = []
        self.fail_card = False
        self.fail_challenge = False

    async def refresh(self, cred):
        self.calls.append(("refresh", cred))
        if cred == "expired":
            raise SklandError("森空岛登录已失效，请重新连接", expired=True)
        return "token"

    async def binding(self, cred, token, device_id=""):
        self.calls.append(("binding", cred, device_id))
        role = "r1" if cred == "account-one" else "r2"
        return {"list": [{"appCode": "endfield", "bindingList": [{"uid": "not-role-id", "roles": [
            {"roleId": role, "serverId": "1", "nickname": f"角色{role}"},
            {"roleId": role + "b", "serverId": "2", "nickname": "备用"}]}]}]}

    async def user(self, cred, token, device_id=""):
        return {"user": {"id": "u1" if cred == "account-one" else "u2"}}

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

    async def tool(self, kind, cred, token, role_id, server_id, device_id="", *, char_id=None):
        self.calls.append(("tool", kind, role_id, char_id))
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
    assert not (await service.read_tool("rules", char_id="../etc"))["supported"]


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
