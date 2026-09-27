"""Local LCU game archive, partitioned by summoner; no credentials are stored."""
import json
import math
from datetime import datetime, timezone


GAME_FIELDS = ('gameId', 'gameCreation', 'gameDuration', 'gameVersion', 'queueId',
               'gameMode', 'mapId', 'teams', 'participants', 'participantIdentities')


def owns_game(game, puuid):
    if not puuid or not isinstance(game, dict):
        return False
    identities = game.get('participantIdentities') or []
    participants = game.get('participants') or []
    if not isinstance(identities, list) or not isinstance(participants, list):
        return False
    ids = {i.get('participantId') for i in identities if isinstance(i, dict)
           and isinstance(i.get('player'), dict) and i['player'].get('puuid') == puuid}
    ids.discard(None)
    return any(isinstance(p, dict) and (p.get('puuid') == puuid or
               p.get('participantId') in ids) for p in participants)


def detail_quality(game):
    participants = [p for p in game.get('participants', []) if isinstance(p, dict)]
    return len(participants) * 10000 + sum(
        sum(v is not None for v in (p.get('stats') or {}).values())
        for p in participants if isinstance(p.get('stats'), dict))


def is_complete(game):
    fields = ('kills', 'deaths', 'assists', 'totalDamageDealtToChampions',
              'goldEarned', 'totalDamageTaken', 'timeCCingOthers')
    from game_assistant.adapters.league_of_legends.analysis import participant_outcome
    identities = {i.get('participantId') for i in (game or {}).get('participantIdentities', [])
                  if isinstance(i, dict) and (i.get('player') or {}).get('puuid')}
    return bool(game and len(game.get('participants') or []) == 10 and all(
        isinstance(p, dict) and isinstance(p.get('stats'), dict) and all(p['stats'].get(k) is not None for k in fields)
        and p.get('participantId') in identities and participant_outcome(game, p) is not None
        for p in game['participants']))


def merge_game(old, new, prefer_old=False):
    """Fill omitted fields without erasing richer immutable game facts."""
    result = dict(old)
    keyed = {'participants':'participantId', 'participantIdentities':'participantId', 'teams':'teamId'}
    for key, value in new.items():
        previous = result.get(key)
        if value is None or value == '' or value == []:
            continue
        if key.lower().startswith(('playeraugment', 'augment')) and value == 0 and previous:
            continue
        if key in keyed and isinstance(value, list):
            index = {str(v.get(keyed[key])): v for v in previous or [] if isinstance(v, dict)}
            for entry in value:
                if not isinstance(entry, dict) or entry.get(keyed[key]) is None:
                    continue
                entry_id = str(entry[keyed[key]])
                index[entry_id] = merge_game(index.get(entry_id, {}), entry, prefer_old)
            result[key] = list(index.values())
        elif isinstance(value, dict) and isinstance(previous, dict):
            result[key] = merge_game(previous, value, prefer_old)
        elif not prefer_old or previous is None:
            result[key] = value
    return result


class LolArchive:
    def __init__(self, conn, lock):
        self.conn, self.lock = conn, lock
        with lock:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS lol_accounts (
                    puuid TEXT PRIMARY KEY, nickname TEXT, level INTEGER, collected_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lol_matches (
                    puuid TEXT NOT NULL, match_id TEXT NOT NULL, creation REAL NOT NULL,
                    quality INTEGER NOT NULL, payload TEXT NOT NULL, collected_at TEXT NOT NULL,
                    PRIMARY KEY (puuid, match_id));
                CREATE INDEX IF NOT EXISTS lol_matches_date ON lol_matches(puuid, creation DESC);
            ''')
            columns = {row[1] for row in conn.execute('PRAGMA table_info(lol_accounts)')}
            if 'seen_at' not in columns:
                conn.execute("ALTER TABLE lol_accounts ADD COLUMN seen_at TEXT NOT NULL DEFAULT ''")
                conn.execute('UPDATE lol_accounts SET seen_at=collected_at')
            conn.commit()

    def save(self, summoner, games, collected_at=None, *, history_observed=True):
        puuid = summoner.get('puuid')
        if not isinstance(puuid, str) or not puuid or len(puuid) > 256:
            return 0
        instant = datetime.fromisoformat(collected_at) if collected_at else datetime.now(timezone.utc)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        stamp = instant.astimezone(timezone.utc).isoformat(timespec='microseconds')
        valid = []
        for game in games:
            if not owns_game(game, puuid):
                continue
            match_id = str(game.get('gameId') or '')
            creation = game.get('gameCreation')
            if (not match_id.isascii() or not match_id.isdecimal() or len(match_id) > 32 or
                    not isinstance(creation, (int, float)) or isinstance(creation, bool) or
                    not math.isfinite(creation) or not 0 < creation < 32503680000000):
                continue
            try:
                payload = json.dumps({k: game[k] for k in GAME_FIELDS if k in game},
                                     ensure_ascii=False, allow_nan=False)
                quality = detail_quality(game)
            except (TypeError, ValueError):
                continue
            valid.append((puuid, match_id, creation, quality, payload, stamp))
        with self.lock, self.conn:
            self.conn.execute('''INSERT INTO lol_accounts(puuid,nickname,level,collected_at,seen_at) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(puuid) DO UPDATE SET
                    nickname=CASE WHEN excluded.seen_at>=lol_accounts.seen_at THEN excluded.nickname ELSE lol_accounts.nickname END,
                    level=CASE WHEN excluded.seen_at>=lol_accounts.seen_at THEN excluded.level ELSE lol_accounts.level END,
                    collected_at=MAX(excluded.collected_at,lol_accounts.collected_at),
                    seen_at=MAX(excluded.seen_at,lol_accounts.seen_at)''',
                (puuid, summoner.get('gameName') or summoner.get('displayName') or '召唤师',
                 summoner.get('summonerLevel'), stamp if history_observed else '', stamp))
            for row in valid:
                previous = self.conn.execute('SELECT quality,payload,collected_at FROM lol_matches WHERE puuid=? AND match_id=?', row[:2]).fetchone()
                if previous:
                    raw = merge_game(json.loads(previous[1]), json.loads(row[4]),
                                     prefer_old=row[3] < previous[0] or stamp < previous[2])
                    row = (*row[:3], detail_quality(raw), json.dumps(raw, ensure_ascii=False, allow_nan=False), max(stamp, previous[2]))
                self.conn.execute('INSERT OR REPLACE INTO lol_matches VALUES (?, ?, ?, ?, ?, ?)', row)
        return len({r[1] for r in valid})

    def account(self):
        with self.lock:
            row = self.conn.execute('SELECT puuid,nickname,level,collected_at FROM lol_accounts '
                                    'ORDER BY seen_at DESC,puuid LIMIT 1').fetchone()
        if not row:
            return None
        result = dict(zip(('puuid', 'nickname', 'level', 'collected_at'), row))
        result['collected_at'] = result['collected_at'] or None
        return result

    def records(self, puuid):
        with self.lock:
            rows = self.conn.execute('SELECT payload FROM lol_matches WHERE puuid=? '
                                     'ORDER BY creation DESC,match_id DESC', (puuid,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def detail(self, puuid, match_id):
        with self.lock:
            row = self.conn.execute('SELECT payload FROM lol_matches WHERE puuid=? AND match_id=?',
                                    (puuid, match_id)).fetchone()
        return json.loads(row[0]) if row else None
