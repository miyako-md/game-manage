"""Read-only personal analysis and explicit, bounded local-client collection."""
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException, Query
from starlette.concurrency import run_in_threadpool

from game_assistant.adapters.league_of_legends.champions import ChampionCatalog
from game_assistant.adapters.league_of_legends.lcu_client import LcuClient, LcuError
from game_assistant.adapters.league_of_legends.matches import parse_match_detail
from game_assistant.lol_archive import LolArchive, detail_quality, is_complete, merge_game, owns_game


def has_own_augments(game, owner):
    if game.get('queueId') != 2400:
        return True
    own_ids = {i.get('participantId') for i in game.get('participantIdentities', [])
               if (i.get('player') or {}).get('puuid') == owner}
    for participant in game.get('participants', []):
        if participant.get('participantId') not in own_ids and participant.get('puuid') != owner:
            continue
        stats = participant.get('stats') or {}
        return any(f'playerAugment{i}' in stats for i in range(1, 7)) or isinstance(
            stats.get('augments', participant.get('augments')), list)
    return False


def install_lol_routes(app):
    archive = LolArchive(app.state.store._conn, app.state.store._lock)
    app.state.lol_archive = archive
    collect_lock = asyncio.Lock()
    try:
        app.state.registry.get('league_of_legends').history = archive
    except KeyError:
        pass
    catalog = ChampionCatalog(cache_path=str(Path(app.state.settings.db_path).parent / 'champions.json'))

    def adapter():
        try:
            return app.state.registry.get('league_of_legends')
        except KeyError:
            raise HTTPException(404, '英雄联盟未启用') from None

    @app.middleware('http')
    async def private_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/lol/'):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @app.get('/api/lol/analysis')
    async def analysis(days: int = Query(90, ge=0, le=365),
                       queue_id: int | None = Query(None, ge=0, le=100000)):
        from game_assistant.adapters.league_of_legends.analysis import analyze_matches
        adapter()
        if days not in (0, 7, 30, 90, 365):
            raise HTTPException(422, '时间范围须为 7、30、90、365 天或全部')
        account = archive.account()
        records = archive.records(account['puuid']) if account else []
        # Reading the dashboard never needs the client or a public network fetch.
        names, _ = catalog._read_cache()
        payload = await run_in_threadpool(analyze_matches, records, account['puuid'] if account else '',
                                         names, days=days, queue_id=queue_id)
        return {**payload, 'account': {k: account[k] for k in ('nickname', 'level')} if account else None,
                'collected_at': account['collected_at'] if account else None,
                'source': 'local_lcu_archive'}

    @app.get('/api/lol/matches/{match_id}')
    async def detail(match_id: str):
        adapter()
        account = archive.account()
        raw = archive.detail(account['puuid'], match_id) if account else None
        if raw is None:
            raise HTTPException(404, '当前账号未归档这场对局')
        names, _ = catalog._read_cache()
        return {'payload': parse_match_detail(raw, account['puuid'], names).model_dump(mode='json')}

    @app.post('/api/lol/collect')
    async def collect():
        selected = adapter()
        if collect_lock.locked():
            raise HTTPException(409, '正在读取客户端战绩，请等待本次采集完成')
        async with collect_lock:
            started_at = datetime.now(timezone.utc).isoformat()
            try:
                port, token = selected._discover()
                async with asyncio.timeout(100), LcuClient(port=port, token=token) as lcu:
                    summoner = await lcu.current_summoner()
                    owner = summoner.get('puuid')
                    if not isinstance(owner, str) or not owner:
                        raise HTTPException(409, '请先在英雄联盟客户端完成登录')
                    history = await lcu.match_history(owner)
                    entries = (history.get('games') or {}).get('games') or []
                    if not isinstance(entries, list):
                        raise HTTPException(502, '客户端战绩结构异常，请稍后重试')
                    games = {}
                    for item in entries[:20]:
                        if not isinstance(item, dict):
                            continue
                        mid = str(item.get('gameId') or '')
                        if mid.isascii() and mid.isdecimal() and len(mid) <= 32 and owns_game(item, owner):
                            games[mid] = item
                    semaphore = asyncio.Semaphore(4)

                    async def enrich(mid, raw):
                        stored = archive.detail(owner, mid)
                        if stored:
                            raw = merge_game(stored, raw, prefer_old=detail_quality(stored)>detail_quality(raw))
                        if is_complete(raw) and has_own_augments(raw, owner):
                            return mid, raw, False
                        async with semaphore:
                            try:
                                full = await lcu.game_detail(mid)
                                if str(full.get('gameId')) != mid or not owns_game(full, owner):
                                    return mid, raw, True
                                return mid, full, not is_complete(full)
                            except LcuError:
                                return mid, raw, True

                    results = await asyncio.gather(*(enrich(mid, raw) for mid, raw in games.items()))
                    # Reject a result that raced a logout/account switch.
                    if (await lcu.current_summoner()).get('puuid') != owner:
                        raise HTTPException(409, '采集期间客户端账号已变化，请重新读取')
                    saved = archive.save(summoner, [raw for _, raw, _ in results], started_at)
                    return {'games': saved, 'details': sum(is_complete(raw) for _, raw, _ in results),
                            'failed_details': sum(failed for _, _, failed in results),
                            'collected_at': started_at}
            except LcuError:
                raise HTTPException(503, '英雄联盟客户端未运行、未登录或暂时无法读取；已归档战绩仍可查看') from None
            except TimeoutError:
                raise HTTPException(504, '读取客户端超时，已有档案已保留，请稍后重试') from None
