"""终末地寻访记录本地账本：官方接口增量同步，按角色隔离，seqId 去重。

官方只能查到约 90 天，账本从第一次同步开始累积。每次“游走”从某个游标向更早翻页：
从最新一页开始的游走碰到已保存记录就说明衔接上了；预算耗尽或出错时在最后一页的底部
记一个断档，下次从那里续传；翻到官方窗口尽头仍没衔接上、而本地还有更早的记录时，
记一个永久断档。统计只在连续记录内给出确定值，跨过断档一律降级为“至少”。
"""
import asyncio
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from game_assistant.adapters.endfield import parse
from game_assistant.adapters.endfield.data_models import (
    EndfieldGacha, EndfieldGachaPool, EndfieldPity, EndfieldSixStar,
)
from game_assistant.adapters.endfield.endpoints import CHAR_POOL_TYPES

EXPORT_FORMAT = "game-assistant-endfield-gacha"
HISTORY_LIMIT = 50


def store_path(db_path: str) -> Path:
    return Path(db_path).with_suffix(".endfield-gacha.sqlite3")


class EndfieldGachaStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS records (
                  role TEXT NOT NULL, pool_key TEXT NOT NULL, seq_id INTEGER NOT NULL, payload TEXT NOT NULL,
                  PRIMARY KEY(role, pool_key, seq_id));
                CREATE TABLE IF NOT EXISTS pools (
                  role TEXT NOT NULL, pool_key TEXT NOT NULL, kind TEXT NOT NULL, label TEXT NOT NULL,
                  last_sync_at TEXT, PRIMARY KEY(role, pool_key));
                CREATE TABLE IF NOT EXISTS breaks (
                  role TEXT NOT NULL, pool_key TEXT NOT NULL, seq_id INTEGER NOT NULL, permanent INTEGER NOT NULL,
                  PRIMARY KEY(role, pool_key, seq_id));
            """)

    @contextmanager
    def _db(self):
        db = sqlite3.connect(str(self.path), timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    # ---- 同步 ----

    async def sync(self, role: str, client, u8_token: str, *, budget: int = 120, interval: float = 0.3,
                   sleep=asyncio.sleep) -> int:
        """按预算同步全部卡池，返回实际请求页数。先抓各池最新记录，再用剩余预算续传断档。"""
        if not role:
            raise ValueError("缺少终末地角色")

        def char_fetch(pool_type):
            async def fetch(cursor):
                return parse.record_page(await client.char_records(u8_token, pool_type, cursor), "character")
            return fetch

        def weapon_fetch(pool_id):
            async def fetch(cursor):
                return parse.record_page(await client.weapon_records(u8_token, pool_id, cursor), "weapon")
            return fetch

        pools = [(key, label, "character", char_fetch(key)) for key, label in CHAR_POOL_TYPES.items()]
        weapons = parse.weapon_pools(await client.weapon_pools(u8_token))
        used = 1
        pools += [(f"weapon:{pool_id}", name, "weapon", weapon_fetch(pool_id)) for pool_id, name in weapons]
        with self._db() as db:
            for key, label, kind, _ in pools:
                db.execute("INSERT INTO pools (role, pool_key, kind, label) VALUES (?,?,?,?)"
                           " ON CONFLICT(role, pool_key) DO UPDATE SET label=excluded.label",
                           (role, key, kind, label))
        synced_at = datetime.now(timezone.utc).isoformat()
        for key, _, _, fetch in pools:
            if used >= budget:
                break
            used, outcome = await self._walk(role, key, fetch, None, used, budget, interval, sleep)
            if outcome in ("overlap", "end"):
                with self._db() as db:
                    db.execute("UPDATE pools SET last_sync_at=? WHERE role=? AND pool_key=?", (synced_at, role, key))
        for key, _, _, fetch in pools:
            for seq in self._open_breaks(role, key):
                if used >= budget:
                    return used
                used, _ = await self._walk(role, key, fetch, seq, used, budget, interval, sleep)
        return used

    async def _walk(self, role, key, fetch, start, used, budget, interval, sleep):
        cursor = str(start) if start is not None else None
        bottom, outcome = start, "budget"
        try:
            while used < budget:
                rows, has_more = await fetch(cursor)
                used += 1
                if not rows:
                    outcome = "end"
                    break
                known = self._known(role, key, [row["seq_id"] for row in rows])
                fresh = [row for row in rows if row["seq_id"] not in known]
                self._add(role, key, fresh)
                bottom = rows[-1]["seq_id"]
                # 游标是否包含自身尚未实测：游标那条已保存不代表衔接上了更早的记录。
                if known - {int(cursor or 0)}:
                    outcome = "overlap"
                    break
                if not has_more:
                    outcome = "end"
                    break
                cursor = str(bottom)
                await sleep(interval)
        except BaseException:
            outcome = "error"
            raise
        finally:
            self._settle(role, key, start, bottom, outcome)
        return used, outcome

    def _settle(self, role, key, start, bottom, outcome):
        with self._db() as db:
            if start is not None:
                db.execute("DELETE FROM breaks WHERE role=? AND pool_key=? AND seq_id=?", (role, key, start))
            if bottom is None or outcome == "overlap":
                return
            if outcome == "end":
                older = db.execute("SELECT 1 FROM records WHERE role=? AND pool_key=? AND seq_id<? LIMIT 1",
                                   (role, key, bottom)).fetchone()
                if older:
                    db.execute("INSERT OR REPLACE INTO breaks VALUES (?,?,?,1)", (role, key, bottom))
                return
            # 预算耗尽或请求出错：底部以下尚未核对，留待下次续传。
            db.execute("INSERT OR REPLACE INTO breaks VALUES (?,?,?,0)", (role, key, bottom))

    def _known(self, role, key, seqs) -> set[int]:
        if not seqs:
            return set()
        marks = ",".join("?" * len(seqs))
        with self._db() as db:
            rows = db.execute(f"SELECT seq_id FROM records WHERE role=? AND pool_key=? AND seq_id IN ({marks})",
                              (role, key, *seqs)).fetchall()
        return {row[0] for row in rows}

    def _add(self, role, key, rows):
        if not rows:
            return
        with self._db() as db:
            db.executemany("INSERT OR IGNORE INTO records VALUES (?,?,?,?)",
                           [(role, key, row["seq_id"], json.dumps(row, ensure_ascii=False)) for row in rows])

    def _open_breaks(self, role, key) -> list[int]:
        with self._db() as db:
            rows = db.execute("SELECT seq_id FROM breaks WHERE role=? AND pool_key=? AND permanent=0"
                              " ORDER BY seq_id DESC", (role, key)).fetchall()
        return [row[0] for row in rows]

    # ---- 读取 ----

    def summary(self, role: str) -> EndfieldGacha:
        with self._db() as db:
            meta = db.execute("SELECT pool_key, kind, label, last_sync_at FROM pools WHERE role=?", (role,)).fetchall()
            pools = []
            for key, kind, label, last_sync_at in meta:
                rows = [json.loads(p) for (p,) in db.execute(
                    "SELECT payload FROM records WHERE role=? AND pool_key=? ORDER BY seq_id", (role, key))]
                if not rows:
                    continue
                breaks = dict(db.execute("SELECT seq_id, permanent FROM breaks WHERE role=? AND pool_key=?",
                                         (role, key)).fetchall())
                pools.append(_pool_summary(key, kind, label, last_sync_at, rows, breaks))
        order = list(CHAR_POOL_TYPES)
        pools.sort(key=lambda p: (order.index(p.key) if p.key in order else len(order), -(p.newest_at or 0)))
        return EndfieldGacha(role_id=role, total=sum(p.total for p in pools),
                             complete=not any(p.pending for p in pools), pools=pools)

    def records(self, role: str, pool_key: str | None = None, limit: int = 100, offset: int = 0) -> dict:
        where, args = "role=?", [role]
        if pool_key:
            where, args = where + " AND pool_key=?", args + [pool_key]
        with self._db() as db:
            total = db.execute(f"SELECT COUNT(*) FROM records WHERE {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT pool_key, payload FROM records WHERE {where} ORDER BY seq_id DESC"
                              " LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return {"role_id": role, "total": total,
                "records": [_public_record(key, payload) for key, payload in rows]}

    def export(self, role: str) -> dict:
        with self._db() as db:
            pools = db.execute("SELECT pool_key, kind, label, last_sync_at FROM pools WHERE role=?"
                               " ORDER BY pool_key", (role,)).fetchall()
            rows = db.execute("SELECT pool_key, payload FROM records WHERE role=? ORDER BY seq_id DESC",
                              (role,)).fetchall()
            breaks = db.execute("SELECT pool_key, seq_id, permanent FROM breaks WHERE role=?", (role,)).fetchall()
        return {"format": EXPORT_FORMAT, "format_version": 1, "role_id": role,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "pools": [dict(zip(("key", "kind", "label", "last_sync_at"), row)) for row in pools],
                "gaps": [{"pool_key": k, "below_seq_id": str(s), "permanent": bool(p)} for k, s, p in breaks],
                "records": [_public_record(key, payload) for key, payload in rows]}


def _public_record(pool_key: str, payload: str) -> dict:
    row = json.loads(payload)
    # seqId 超出 JS 安全整数时前端会丢精度，统一以字符串输出。
    return {**row, "seq_id": str(row["seq_id"]), "pool_key": pool_key}


def _pool_summary(key, kind, label, last_sync_at, rows, breaks) -> EndfieldGachaPool:
    count, exact, free_in_count = 0, False, False
    history: list[EndfieldSixStar] = []
    for row in rows:  # 由旧到新
        if row["seq_id"] in breaks:  # 这一条之前可能缺记录
            count, exact, free_in_count = 0, False, False
        if row.get("is_free") is True:
            free_in_count = True
        else:
            count += 1
        if row.get("rarity") == 6:
            history.append(EndfieldSixStar(
                name=row.get("name"), pool_name=row.get("pool_name"), obtained_at=row.get("gacha_ts"),
                pulls=count, status="exact" if exact and not free_in_count else "lower_bound"))
            count, exact, free_in_count = 0, True, False
    times = [row["gacha_ts"] for row in rows if row.get("gacha_ts")]
    return EndfieldGachaPool(
        key=key, label=label, kind=kind, total=len(rows),
        six_star=sum(row.get("rarity") == 6 for row in rows), five_star=sum(row.get("rarity") == 5 for row in rows),
        free=sum(row.get("is_free") is True for row in rows),
        since_last_six=EndfieldPity(count=count, status="exact" if exact and not free_in_count else "lower_bound"),
        history=list(reversed(history))[:HISTORY_LIMIT],
        newest_at=max(times, default=None), oldest_at=min(times, default=None),
        gaps=len(breaks), pending=any(not permanent for permanent in breaks.values()), last_sync_at=last_sync_at)

