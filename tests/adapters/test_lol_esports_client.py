import httpx
import pytest
import respx

from game_assistant.adapters.league_of_legends.esports_client import TencentEsportsClient, EsportsSourceError

BASE = 'https://lpl.qq.com/web201612/data/'


@respx.mock
async def test_client_reads_only_fixed_public_routes():
    routes = [respx.get(BASE + path).respond(200, text='var Data={"status":"0","msg":{}};')
              for path in ('LOL_MATCH2_GAME_LIST_BRIEF.js', 'LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_237.js', 'LOL_MATCH2_TEAM_TEAM1_INFO.js')]
    async with TencentEsportsClient() as client:
        await client.fetch_catalog()
        await client.fetch_matches('237')
        await client.fetch_team('1')
    assert all(r.called for r in routes)
    for call in respx.calls:
        assert 'cookie' not in call.request.headers and 'authorization' not in call.request.headers


@respx.mock
async def test_client_rejects_redirect_and_bad_ids():
    respx.get(BASE + 'LOL_MATCH2_GAME_LIST_BRIEF.js').respond(302, headers={'Location': 'https://example.org'})
    async with TencentEsportsClient() as client:
        with pytest.raises(EsportsSourceError):
            await client.fetch_catalog()
        for sid in ('../1', '1?x=2', '', '0', '１'):
            with pytest.raises(EsportsSourceError):
                await client.fetch_team(sid)
    assert len(respx.calls) == 1


@pytest.mark.parametrize('payload', ['<html>login</html>', 'var A={"status":"1","msg":{}};', '[]'])
@respx.mock
async def test_client_invalid_payload(payload):
    respx.get(BASE + 'LOL_MATCH2_GAME_LIST_BRIEF.js').respond(200, text=payload)
    async with TencentEsportsClient() as client:
        with pytest.raises(EsportsSourceError):
            await client.fetch_catalog()


@respx.mock
async def test_client_limits_and_retry_after():
    route = respx.get(BASE + 'LOL_MATCH2_GAME_LIST_BRIEF.js')
    route.respond(429, headers={'Retry-After': '120'})
    async with TencentEsportsClient() as client:
        with pytest.raises(EsportsSourceError) as exc:
            await client.fetch_catalog()
        assert exc.value.retry_after_seconds == 120
        assert client._client.timeout.read == 15
        route.respond(200, content=b'x' * (8 * 1024 * 1024 + 1))
        with pytest.raises(EsportsSourceError) as exc:
            await client.fetch_catalog()
        assert exc.value.code == 'response_too_large'
        route.mock(side_effect=httpx.ReadTimeout('test'))
        with pytest.raises(EsportsSourceError) as exc:
            await client.fetch_catalog()
        assert exc.value.code == 'network_error'
