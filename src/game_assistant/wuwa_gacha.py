"""Explicit gacha imports. Authorization links are transient and never persisted."""
from collections import Counter
from datetime import datetime
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

import httpx

from game_assistant.wuwa_history import now_iso

POOL_NAMES = dict(zip(map(str, range(1, 10)), (
    '角色精准调谐', '武器精准调谐', '角色调谐（常驻池）', '武器调谐（常驻池）',
    '新手调谐', '新手自选唤取', '新手自选唤取（感恩定向唤取）', '角色新旅唤取', '武器新旅唤取')))
LINK_HOSTS = {'gmserver-api.aki-game2.com', 'gmserver-api.aki-game2.net',
              'aki-gm-resources.aki-game.com', 'aki-gm-resources.aki-game.net'}
CN_SERVER = '76402e5b20be2c39f095a152090afddc'
NET_SERVERS = {'591d6af3a3090d8ea00d8f86cf6d7501', '6eb2a235b30d05efd77bedb5cf60999e',
               '86d52186155b148b5c138ceb41be9650', '919752ae5ea09c1ced910dd668a63ffb',
               '10cd7254d57e58ae560b15d51e34b4c'}
MAX_RECORDS = 20000
MAX_RESPONSE = 8 * 1024 * 1024


def parse_link(url, account, server):
    try:
        if not isinstance(url, str) or len(url) > 8192 or any(ord(c) < 32 for c in url):
            raise ValueError
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in LINK_HOSTS
                or parsed.username or parsed.password or parsed.port not in (None, 443)):
            raise ValueError
        query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=40)
        fragment = parse_qs(parsed.fragment.split('?', 1)[1] if '?' in parsed.fragment else '',
                            keep_blank_values=True, max_num_fields=40)
        for key, values in fragment.items():
            query.setdefault(key, []).extend(values)
        def parameter(*keys):
            values = [v for k in keys for v in query.get(k, [])]
            if len(values) > 1 or (values and not values[0]):
                raise ValueError
            return values[0] if values else None
        token = parameter('record_id', 'recordId')
        player = parameter('player_id', 'playerId')
        region = parameter('server_id', 'serverId', 'svr_id')
        if not token or not re.fullmatch(r'[A-Za-z0-9_-]{1,512}', token) or player != account:
            raise ValueError
        if region is not None and region != server:
            raise ValueError
        # The active server determines region; the link cannot override it.
        suffix = 'net' if server in NET_SERVERS else 'com'
        if server == CN_SERVER and parsed.hostname.endswith('.net'):
            raise ValueError
        if server in NET_SERVERS and parsed.hostname.endswith('.com'):
            raise ValueError
        return {'recordId': token, 'playerId': account, 'serverId': server,
                'endpoint': f'https://gmserver-api.aki-game2.{suffix}/gacha/record/query'}
    except (ValueError, TypeError):
        raise ValueError('抽卡链接格式、账号或区服不匹配，请使用当前账号的官方链接') from None


def normalize_records(value, account, server):
    wrapper_account = wrapper_server = None
    if isinstance(value, dict):
        info = value.get('info', {})
        if not isinstance(info, dict):
            raise ValueError('抽卡导出信息格式错误')
        wrapper_account = info.get('uid', value.get('role_id'))
        wrapper_server = info.get('server_id', value.get('server_id'))
        rows = value.get('list', value.get('records'))
    else:
        rows = value
    if not isinstance(rows, list) or len(rows) > MAX_RECORDS:
        raise ValueError('抽卡记录须为数组，且单次不超过 20000 条')
    if wrapper_account is not None and str(wrapper_account) != account:
        raise ValueError('抽卡记录账号不匹配')
    if wrapper_server is not None and str(wrapper_server) != server:
        raise ValueError('抽卡记录区服不匹配')
    normalized = []
    aliases = {'pool': 'cardPoolType', 'resource_id': 'resourceId', 'rarity': 'qualityLevel',
               'resource_type': 'resourceType', 'name': 'name', 'count': 'count', 'time': 'time'}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError('抽卡记录格式错误')
        account_fields = [row[k] for k in ('role_id', 'uid', 'playerId', 'player_id', 'account_role_id') if k in row]
        server_fields = [row[k] for k in ('server_id', 'serverId', 'svr_id') if k in row]
        if any(str(v) != account for v in account_fields) or any(str(v) != server for v in server_fields):
            raise ValueError('抽卡记录账号或区服不匹配')
        row_account = account_fields[0] if account_fields else wrapper_account
        row_server = server_fields[0] if server_fields else wrapper_server
        if row_account is None or str(row_account) != account:
            raise ValueError('每批抽卡记录必须包含匹配的账号标识')
        if row_server is not None and str(row_server) != server:
            raise ValueError('抽卡记录区服不匹配')
        item = {key: row.get(key, row.get(alias)) for key, alias in aliases.items()}
        for key, val in item.items():
            if val is not None and (isinstance(val, (dict, list, bool)) or len(str(val)) > 512):
                raise ValueError('抽卡记录字段格式错误')
        if item['pool'] is None or item['resource_id'] is None or not item['time']:
            raise ValueError('抽卡记录缺少卡池、物品或时间')
        item['pool'] = {v: k for k, v in POOL_NAMES.items()}.get(str(item['pool']), str(item['pool']))
        item['resource_id'] = str(item['resource_id'])
        try:
            item['time'] = datetime.fromisoformat(item['time']).isoformat()
        except (ValueError, TypeError):
            raise ValueError('抽卡记录时间格式错误') from None
        if item['rarity'] is not None:
            item['rarity'] = str(item['rarity'])
        explicit_id = row.get('draw_id', row.get('id'))
        if explicit_id is not None:
            if not re.fullmatch(r'[A-Za-z0-9:_-]{1,128}', str(explicit_id)):
                raise ValueError('抽卡记录标识格式错误')
            item['draw_id'] = str(explicit_id)
        # Only whitelisted draw fields survive; recordId and URLs never reach storage.
        normalized.append(item)
    return normalized


async def fetch_official(url, account, server, *, transport=None):
    params = parse_link(url, account, server)
    endpoint = params.pop('endpoint')
    rows, failed = [], []
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, transport=transport,
                                 trust_env=False) as client:
        for pool in POOL_NAMES:
            try:
                async with client.stream('POST', endpoint, json={**params, 'cardPoolType': pool,
                                         'languageCode': 'zh-Hans'}) as response:
                    if response.status_code != 200:
                        raise ValueError
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE:
                            raise ValueError
                body = json.loads(data)
                if not isinstance(body, dict) or body.get('code') not in (0, '0') or not isinstance(body.get('data'), list):
                    raise ValueError
                pool_rows = [{**r, 'cardPoolType': pool} for r in body['data'] if isinstance(r, dict)]
                if len(pool_rows) != len(body['data']) or len(rows) + len(pool_rows) > MAX_RECORDS:
                    raise ValueError
                clean = normalize_records({'info': {'uid': account, 'server_id': server}, 'list': pool_rows}, account, server)
                rows.extend(clean)
            except (httpx.HTTPError, ValueError, TypeError):
                failed.append(pool)
    return {'records': {'role_id': account, 'server_id': server, 'list': rows},
            'failed_pools': failed, 'source': 'official_query'}


class GachaStore:
    def __init__(self, conn, lock):
        self.conn, self.lock = conn, lock
        with lock:
            conn.execute('CREATE TABLE IF NOT EXISTS wuwa_gacha ('
                'account TEXT,server TEXT,pool TEXT,draw_id TEXT,payload TEXT,time TEXT,rarity TEXT,'
                'PRIMARY KEY(account,server,pool,draw_id))')
            conn.execute('CREATE TABLE IF NOT EXISTS wuwa_gacha_imports ('
                'account TEXT,server TEXT,imported_at TEXT,source TEXT,failed_pools TEXT,'
                'PRIMARY KEY(account,server))')
            conn.commit()

    def import_records(self, value, account, server, *, source='json_import', failed_pools=None):
        rows = normalize_records(value, account, server)
        occurrences, inserted = Counter(), 0
        with self.lock:
            with self.conn:
                for row in rows:
                    raw = json.dumps(row, sort_keys=True, ensure_ascii=False)
                    digest = hashlib.sha256(raw.encode()).hexdigest()
                    occurrences[digest] += 1
                    draw_id = f'explicit:{row["draw_id"]}' if row.get('draw_id') else f'{digest}:{occurrences[digest]}'
                    cursor = self.conn.execute('INSERT OR IGNORE INTO wuwa_gacha VALUES (?,?,?,?,?,?,?)',
                        (account, server, row['pool'], draw_id, raw, row['time'], row['rarity']))
                    inserted += cursor.rowcount
                self.conn.execute('INSERT OR REPLACE INTO wuwa_gacha_imports VALUES (?,?,?,?,?)',
                    (account, server, now_iso(), source, json.dumps(failed_pools or [])))
        return {'inserted': inserted, 'received': len(rows), 'failed_pools': failed_pools or [],
                'complete': False, 'state': 'partial' if failed_pools else 'imported' if rows else 'need_import'}

    def read(self, account, server, limit=100, offset=0):
        limit, offset = min(max(int(limit), 1), 500), max(int(offset), 0)
        scope = (account, server)
        with self.lock:
            total, earliest, latest = self.conn.execute('SELECT COUNT(*),MIN(time),MAX(time) FROM wuwa_gacha '
                'WHERE account=? AND server=?', scope).fetchone()
            groups = self.conn.execute('SELECT pool,rarity,COUNT(*) FROM wuwa_gacha WHERE account=? AND server=? '
                'GROUP BY pool,rarity ORDER BY pool', scope).fetchall()
            rows = self.conn.execute('SELECT draw_id,payload FROM wuwa_gacha WHERE account=? AND server=? '
                'ORDER BY time DESC,draw_id LIMIT ? OFFSET ?', (*scope, limit, offset)).fetchall()
            gold = self.conn.execute("SELECT draw_id,payload FROM wuwa_gacha WHERE account=? AND server=? AND rarity='5' "
                'ORDER BY time DESC,draw_id LIMIT ? OFFSET ?', (*scope, limit, offset)).fetchall()
            imported = self.conn.execute('SELECT imported_at,source,failed_pools FROM wuwa_gacha_imports '
                'WHERE account=? AND server=?', scope).fetchone()
        pools = {}
        for pool, rarity, count in groups:
            p = pools.setdefault(pool, {'pool': pool, 'name': POOL_NAMES.get(pool, f'未知卡池 {pool}'),
                                        'total': 0, 'rarity_distribution': {}})
            p['total'] += count
            rarity_key = rarity if rarity is not None else 'unknown'
            p['rarity_distribution'][rarity_key] = p['rarity_distribution'].get(rarity_key, 0) + count
        unpack = lambda values: [{'draw_id': key, **json.loads(payload)} for key, payload in values]
        return {'schema_version': 1, 'role_id': account, 'server_id': server,
                'state': 'available' if total else 'need_import', 'total': total,
                'items': unpack(rows), 'gold': unpack(gold), 'gold_total': sum(p['rarity_distribution'].get('5', 0) for p in pools.values()),
                'pools': list(pools.values()), 'limit': limit, 'offset': offset,
                'coverage': {'earliest': earliest, 'latest': latest, 'complete': False,
                    'imported_at': imported[0] if imported else None, 'source': imported[1] if imported else None,
                    'failed_pools': json.loads(imported[2]) if imported else [],
                    'message': '仅代表已导入记录；官方保留期及导出范围可能不完整，无保底推断'}}
