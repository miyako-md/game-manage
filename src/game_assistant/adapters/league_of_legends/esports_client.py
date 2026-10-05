"""Bounded, credential-free access to Tencent's website data files."""
import math
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import httpx

from .esports_parse import decode_public_payload, source_id

BASE = 'https://lpl.qq.com/web201612/data/'
MAX_BYTES = 8 * 1024 * 1024


class EsportsSourceError(Exception):
    def __init__(self, code: str, retry_after_seconds: int | None = None):
        self.code = code
        self.retry_after_seconds = retry_after_seconds
        super().__init__(code)


def retry_after(value):
    try:
        if str(value).isdigit():
            return max(0, int(value))
        date = parsedate_to_datetime(value)
        return max(0, math.ceil((date - datetime.now(timezone.utc)).total_seconds()))
    except (TypeError, ValueError, OverflowError):
        return None


class TencentEsportsClient:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self._owns = client is None
        self._client = client or httpx.AsyncClient(timeout=15, follow_redirects=False,
            headers={'User-Agent': 'GameAssistant/0.1 (public esports schedule)', 'Referer': 'https://lpl.qq.com/'})

    async def _get(self, filename: str) -> dict:
        try:
            async with self._client.stream('GET', BASE + filename, follow_redirects=False, timeout=15) as resp:
                if resp.status_code != 200:
                    raise EsportsSourceError(f'http_{resp.status_code}', retry_after(resp.headers.get('Retry-After')))
                body = bytearray()
                async for chunk in resp.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise EsportsSourceError('response_too_large')
                result = decode_public_payload(bytes(body).decode('utf-8-sig'))
                if result.get('status') not in ('0', 0):
                    raise EsportsSourceError('invalid_business_status')
                return result
        except httpx.HTTPError as error:
            raise EsportsSourceError('network_error') from error
        except (ValueError, UnicodeError, RecursionError) as error:
            raise EsportsSourceError('invalid_data') from error

    async def fetch_catalog(self) -> dict:
        return await self._get('LOL_MATCH2_GAME_LIST_BRIEF.js')

    async def fetch_matches(self, season_source_id: str) -> dict:
        if not source_id(season_source_id):
            raise EsportsSourceError('invalid_id')
        return await self._get(f'LOL_MATCH2_MATCH_HOMEPAGE_BMATCH_LIST_{season_source_id}.js')

    async def fetch_team(self, team_source_id: str) -> dict:
        if not source_id(team_source_id):
            raise EsportsSourceError('invalid_id')
        return await self._get(f'LOL_MATCH2_TEAM_TEAM{team_source_id}_INFO.js')

    async def aclose(self):
        if self._owns:
            await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()
