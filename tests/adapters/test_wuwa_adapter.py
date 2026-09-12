import httpx
import respx

from game_assistant.adapters.wuthering_waves.adapter import WutheringWavesAdapter
from game_assistant.config import Settings
from game_assistant.models import Capability

ROLE_RAW = {"code": 200, "msg": "success",
            "data": {"name": "漂泊者", "level": 80,
                     "energy": {"power": 180, "max": 240}}}


def _unconfigured():
    return WutheringWavesAdapter(Settings(wuwa_enabled=True))


async def test_unconfigured_reports_error():
    a = _unconfigured()
    assert a.credentials_configured is False
    for cap in a.capabilities:
        r = await a.fetch(cap)
        assert r.ok is False and "未配置凭据" in r.error


@respx.mock
async def test_fetch_stamina_ok():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is True and r.payload.current == 180


@respx.mock
async def test_fetch_account_ok():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="123"))
    r = await a.fetch(Capability.ACCOUNT)
    assert r.ok is True and r.payload.nickname == "漂泊者"


@respx.mock
async def test_kuro_error_wrapped():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    a = WutheringWavesAdapter(Settings(wuwa_token="bad", wuwa_user_id="1"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is False and "登录失效" in r.error


@respx.mock
async def test_malformed_payload_returns_fetch_error():
    # 200 但 data 结构畸形：power 为字符串使 int("x") 抛 ValueError（非 KuroError），
    # 解析异常必须被 _guarded_run 拦下转为失败结果，而不是穿透 fetch 破坏失效隔离
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(
            200, json={"code": 200, "data": {"energy": {"power": "x", "max": 240}}}))
    a = WutheringWavesAdapter(Settings(wuwa_token="tok", wuwa_user_id="1"))
    r = await a.fetch(Capability.STAMINA)
    assert r.ok is False and "数据解析异常" in r.error
