import base64

import httpx
import pytest
import respx

from game_assistant.adapters.league_of_legends.lcu_client import (
    LcuClient, LcuError, LcuUnavailableError,
)

BASE = "https://127.0.0.1:54321"


def _client() -> LcuClient:
    return LcuClient(port="54321", token="abcTOKEN")


@respx.mock
async def test_get_with_basic_auth():
    route = respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, json={"puuid": "P1", "summonerLevel": 160}))
    data = await _client().current_summoner()
    assert data["puuid"] == "P1"
    req = route.calls.last.request
    expect = base64.b64encode(b"riot:abcTOKEN").decode()
    assert req.headers["Authorization"] == f"Basic {expect}"


@respx.mock
async def test_http_error_raises():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(404, text="nope"))
    with pytest.raises(LcuError) as ei:
        await _client().current_summoner()
    assert "404" in str(ei.value)


@respx.mock
async def test_non_json_raises():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        return_value=httpx.Response(200, text="<html>gateway</html>"))
    with pytest.raises(LcuError):
        await _client().current_summoner()


@respx.mock
async def test_network_error_is_unavailable():
    respx.get(f"{BASE}/lol-summoner/v1/current-summoner").mock(
        side_effect=httpx.ConnectError("refused"))
    with pytest.raises(LcuUnavailableError):
        await _client().current_summoner()


@respx.mock
async def test_match_history_formats_path():
    route = respx.get(f"{BASE}/lol-match-history/v1/products/lol/P1/matches").mock(
        return_value=httpx.Response(200, json={"games": {"games": []}}))
    await _client().match_history("P1", count=20)
    assert "count=20" in str(route.calls.last.request.url)
