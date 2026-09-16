import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

class BilibiliStore:
    def __init__(self, path):
        self.conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self.lock = threading.RLock()
        with self.conn:
            self.conn.execute('CREATE TABLE IF NOT EXISTS bili_posts (game TEXT, uid TEXT, id TEXT, published TEXT, decision TEXT, payload TEXT, PRIMARY KEY(game,uid,id))')
            self.conn.execute('CREATE TABLE IF NOT EXISTS bili_state (game TEXT, uid TEXT, payload TEXT, PRIMARY KEY(game,uid))')

    def save_rows(self, game, uid, rows):
        with self.lock, self.conn:
            preserved = []
            for row in rows:
                if row['reason'] == 'incomplete':
                    old = self.conn.execute('SELECT payload FROM bili_posts WHERE game=? AND uid=? AND id=?', (game, uid, row['id'])).fetchone()
                    if old:
                        previous = json.loads(old[0])
                        if previous['reason'] != 'incomplete':
                            row = {**previous, 'last_observation_error': '本次正文获取不完整，保留上次完整记录', 'last_observed_at': row.get('fetched_at')}
                preserved.append(row)
            self.conn.executemany('INSERT INTO bili_posts VALUES (?,?,?,?,?,?) ON CONFLICT(game,uid,id) DO UPDATE SET published=excluded.published,decision=excluded.decision,payload=excluded.payload',
                [(game, uid, r['id'], r['published_at'], r['decision'], json.dumps(r, ensure_ascii=False)) for r in preserved])

    def rows(self, game, uid, decision=None, *, days=60, limit=500):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        sql = 'SELECT payload FROM bili_posts WHERE game=? AND uid=? AND published>=?'
        args = [game, uid, cutoff]
        if decision:
            sql += ' AND decision=?'; args.append(decision)
        sql += ' ORDER BY published DESC,id DESC LIMIT ?'; args.append(limit)
        with self.lock:
            return [json.loads(r[0]) for r in self.conn.execute(sql, args)]

    def state(self, game, uid):
        with self.lock:
            row = self.conn.execute('SELECT payload FROM bili_state WHERE game=? AND uid=?', (game, uid)).fetchone()
        return json.loads(row[0]) if row else {'game_id': game, 'uid': uid, 'status': 'idle', 'history_complete': False}

    def set_state(self, game, uid, **values):
        with self.lock, self.conn:
            data = {**self.state(game, uid), **values}
            self.conn.execute('INSERT INTO bili_state VALUES (?,?,?) ON CONFLICT(game,uid) DO UPDATE SET payload=excluded.payload', (game, uid, json.dumps(data, ensure_ascii=False)))
        return data

    def close(self):
        self.conn.close()
