import httpx
import pytest
import respx

from game_assistant.adapters.wuthering_waves.kuro_client import KuroClient, KuroError

ROLE_RAW = {"code": 200, "msg": "success",
            "data": {"name": "漂泊者", "level": 80,
                     "energy": {"power": 180, "max": 240,
                                "refreshTimestamp": 1726000000000}}}


@respx.mock
async def test_get_role_data_ok():
    route = respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json=ROLE_RAW))
    client = KuroClient(token="tok", user_id="123456")
    data = await client.get_role_data()
    assert data["data"]["energy"]["power"] == 180
    req = route.calls.last.request
    assert req.headers["token"] == "tok"
    assert b"123456" in req.content


@respx.mock
async def test_error_raises_kuro_error():
    respx.post("https://api.kurobbs.com/gamer/aki/api/getRoleData").mock(
        return_value=httpx.Response(200, json={"code": 220, "msg": "登录失效"}))
    client = KuroClient(token="bad", user_id="1")
    with pytest.raises(KuroError) as ei:
        await client.get_role_data()
    assert ei.value.code == 220
