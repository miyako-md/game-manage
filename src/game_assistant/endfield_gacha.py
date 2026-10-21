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
    EndfieldGacha, EndfieldGachaBanner, EndfieldGachaError, EndfieldGachaPool, EndfieldPity, EndfieldSixStar,
)
from game_assistant.adapters.endfield.hypergryph import EndfieldError
from game_assistant.adapters.endfield.endpoints import CHAR_POOL_TYPES

EXPORT_FORMAT = "game-assistant-endfield-gacha"
HISTORY_LIMIT = 50
# 武器池列表读取失败时记在这一行，下次列表读取成功即删除；它没有记录，不会出现在卡池统计里。
WEAPON_LIST_KEY = "weapon:*"


def _classified_weapon_record(row):
    record_kind = row.get("record_kind")
    return record_kind == "draw" or isinstance(record_kind, str) and record_kind.startswith("gift")


def store_path(db_path: str) -> Path:
    return Path(db_path).with_suffix(".endfield-gacha.sqlite3")


def local_ledger_role(role_id: str, channel: str | None) -> str:
    """本地单文件账本的角色键：官服保持原角色 ID（旧数据无需迁移），其他渠道加前缀，
    避免官服与 B 服 role_id 撞号时合并历史、按 seqId 吞掉记录。云端每个授权独立建库，不经过这里。"""
    role_id = str(role_id or "").strip()
    channel = str(channel or "").strip() or "official"
    return role_id if channel == "official" else f"{channel}:{role_id}"


def _public_role(role: str) -> str:
    return role.rpartition(":")[2]


class EndfieldGachaStore:
    @classmethod
    def for_scope(cls, scope, private_root, *, role_uid, server_id):
        """Cloud factory: scope is mandatory and no local data is adopted."""
        from game_assistant.private_data import scoped_ledger
        return scoped_ledger(cls, 'endfield_gacha', scope, private_root,
                             role_uid=role_uid, server_id=server_id)

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
                  last_sync_at TEXT, scan_pending INTEGER, PRIMARY KEY(role, pool_key));
                CREATE TABLE IF NOT EXISTS breaks (
                  role TEXT NOT NULL, pool_key TEXT NOT NULL, seq_id INTEGER NOT NULL, permanent INTEGER NOT NULL,
                  PRIMARY KEY(role, pool_key, seq_id));
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(pools)")}
            if "scan_pending" not in columns:
                db.execute("ALTER TABLE pools ADD COLUMN scan_pending INTEGER")
                # A prior successful head walk is evidence of a scanned pool.
                # Legacy rows without that evidence remain unknown, not empty.
                db.execute("UPDATE pools SET scan_pending=0 WHERE last_sync_at IS NOT NULL")
            if "last_error" not in columns:
                db.execute("ALTER TABLE pools ADD COLUMN last_error TEXT")

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
        """按预算同步全部卡池，返回实际请求页数。先抓各池最新记录，再用剩余预算续传断档。

        单个卡池（或武器池列表）读取失败只记在该池上，其余卡池照常同步；登录失效立即中止。
        本轮尝试过的卡池全部失败时抛出第一个错误，让轮询状态显示失败。
        """
        if not role:
            raise ValueError("缺少终末地角色")

        def char_fetch(pool_type):
            async def fetch(cursor):
                return parse.record_page(await client.char_records(u8_token, pool_type, cursor), "character")
            return fetch

        def weapon_fetch(pool_id):
            async def fetch(cursor):
                rows, has_more = parse.record_page(await client.weapon_records(u8_token, pool_id, cursor), "weapon")
                if any(row["pool_id"] != pool_id for row in rows):
                    raise ValueError("武器记录所属卡池不一致，请刷新重试")
                return rows, has_more
            return fetch

        pools = [(key, label, "character", char_fetch(key)) for key, label in CHAR_POOL_TYPES.items()]
        # Mark the new attempt before discovery/network I/O. In particular, a
        # failed weapon-pool listing must not leave the previous run "complete".
        self._mark_pending(role, pools)
        failures, succeeded = [], 0
        try:
            weapons = parse.weapon_pools(await client.weapon_pools(u8_token))
        except (EndfieldError, ValueError) as error:
            if getattr(error, "expired", False):
                raise
            # Character pools still sync; the listing stays pending until it succeeds.
            self._mark_pending(role, [(WEAPON_LIST_KEY, "武器池列表", "weapon", None)])
            self._fail(role, WEAPON_LIST_KEY, error)
            failures.append(error)
            weapons = []
        else:
            with self._db() as db:
                db.execute("DELETE FROM pools WHERE role=? AND pool_key=?", (role, WEAPON_LIST_KEY))
        used = 1
        weapon_jobs = [(f"weapon:{pool_id}", name, "weapon", weapon_fetch(pool_id)) for pool_id, name in weapons]
        self._mark_pending(role, weapon_jobs)
        pools += weapon_jobs
        synced_at = datetime.now(timezone.utc).isoformat()
        for key, _, _, fetch in pools:
            if used >= budget:
                break
            used, outcome, error = await self._walk(role, key, fetch, None, used, budget, interval, sleep)
            if error is not None:
                failures.append(error)
                continue
            succeeded += 1
            if outcome in ("overlap", "end"):
                with self._db() as db:
                    db.execute("UPDATE pools SET last_sync_at=?, scan_pending=0 WHERE role=? AND pool_key=?",
                               (synced_at, role, key))
        for key, _, _, fetch in pools:
            for seq in self._open_breaks(role, key):
                if used >= budget:
                    break
                used, _, error = await self._walk(role, key, fetch, seq, used, budget, interval, sleep)
                if error is not None:
                    failures.append(error)
                    break
        if failures and not succeeded:
            raise failures[0]
        return used

    def _fail(self, role, key, error):
        with self._db() as db:
            db.execute("UPDATE pools SET last_error=? WHERE role=? AND pool_key=?", (str(error)[:200], role, key))

    def _mark_pending(self, role, pools):
        with self._db() as db:
            for key, label, kind, _ in pools:
                db.execute("INSERT INTO pools (role, pool_key, kind, label, scan_pending) VALUES (?,?,?,?,1)"
                           " ON CONFLICT(role, pool_key) DO UPDATE SET label=excluded.label, scan_pending=1, last_error=NULL",
                           (role, key, kind, label))

    async def _walk(self, role, key, fetch, start, used, budget, interval, sleep):
        """返回 (请求页数, 结果, 错误)。卡池自身的读取错误只记在该池上，登录失效照常抛出。"""
        cursor = str(start) if start is not None else None
        bottom, outcome, failure = start, "budget", None
        try:
            while used < budget:
                used += 1  # Count the request once, including parse/network failures.
                rows, has_more = await fetch(cursor)
                if not rows:
                    # 参考实现都把空页当作到底；续传途中的空页却声明还有后续时不当作到底，
                    # 留下可续传的断档下次再试，不记永久缺口。
                    outcome = "budget" if has_more and cursor is not None else "end"
                    break
                known = self._known(role, key, [row["seq_id"] for row in rows])
                # Refresh saved payloads too: old weapon ledgers dropped the
                # official gift kind and must be repaired without deleting history.
                self._add(role, key, rows)
                bottom = rows[-1]["seq_id"]
                # 游标是否包含自身尚未实测：游标那条已保存不代表衔接上了更早的记录。
                if known - {int(cursor or 0)}:
                    outcome = "overlap"
                    break
                if not has_more or bottom == 0:
                    outcome = "end"
                    break
                if cursor is not None and bottom >= int(cursor):
                    raise ValueError("寻访记录分页未向前推进，请刷新重试")
                cursor = str(bottom)
                await sleep(interval)
        except (EndfieldError, ValueError) as error:
            outcome = "error"
            if getattr(error, "expired", False):
                raise
            failure = error
        except BaseException:
            outcome = "error"
            raise
        finally:
            self._settle(role, key, start, bottom, outcome)
        if failure is not None:
            self._fail(role, key, failure)
        return used, outcome, failure

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
            rows = db.execute(f"SELECT seq_id,payload FROM records WHERE role=? AND pool_key=? AND seq_id IN ({marks})",
                              (role, key, *seqs)).fetchall()
        # A legacy weapon row proves that we saved it, but not that it was a
        # draw rather than a gift. Keep paging until classified records overlap.
        return {seq for seq, payload in rows if not key.startswith("weapon:")
                or _classified_weapon_record(json.loads(payload))}

    def _add(self, role, key, rows):
        if not rows:
            return
        with self._db() as db:
            db.executemany("INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(role,pool_key,seq_id)"
                           " DO UPDATE SET payload=excluded.payload",
                           [(role, key, row["seq_id"], json.dumps(row, ensure_ascii=False)) for row in rows])

    def _open_breaks(self, role, key) -> list[int]:
        with self._db() as db:
            rows = db.execute("SELECT seq_id FROM breaks WHERE role=? AND pool_key=? AND permanent=0"
                              " ORDER BY seq_id DESC", (role, key)).fetchall()
        return [row[0] for row in rows]

    # ---- 读取 ----

    def summary(self, role: str) -> EndfieldGacha:
        with self._db() as db:
            meta = db.execute("SELECT pool_key, kind, label, last_sync_at, scan_pending FROM pools WHERE role=?",
                              (role,)).fetchall()
            errors = [EndfieldGachaError(key=key, label=label, message=message) for key, label, message in db.execute(
                "SELECT pool_key, label, last_error FROM pools WHERE role=? AND last_error IS NOT NULL ORDER BY pool_key", (role,))]
            pools = []
            has_pending = False
            for key, kind, label, last_sync_at, scan_pending in meta:
                breaks = dict(db.execute("SELECT seq_id, permanent FROM breaks WHERE role=? AND pool_key=?",
                                         (role, key)).fetchall())
                pending = True if scan_pending == 1 or any(not permanent for permanent in breaks.values()) else False if scan_pending == 0 else None
                has_pending = has_pending or pending is True
                rows = [json.loads(p) for (p,) in db.execute(
                    "SELECT payload FROM records WHERE role=? AND pool_key=? ORDER BY seq_id", (role, key))]
                if not rows:
                    continue
                item = _pool_summary(key, kind, label, last_sync_at, rows, breaks)
                item.pending = pending
                pools.append(item)
        order = list(CHAR_POOL_TYPES)
        pools.sort(key=lambda p: (order.index(p.key) if p.key in order else len(order), -(p.newest_at or 0)))
        from game_assistant.endfield_reports import build_gacha_report
        coverage_known = (set(CHAR_POOL_TYPES).issubset({row[0] for row in meta})
                          and all(row[4] == 0 for row in meta))
        # Empty/unvisited pools participate in coverage even though the UI's
        # record list continues to contain only pools with saved pulls.
        complete = False if has_pending else True if coverage_known else None
        summary = EndfieldGacha(role_id=_public_role(role), total=sum(p.total for p in pools), complete=complete, pools=pools,
                                errors=errors)
        summary.report = build_gacha_report(summary)
        return summary

    def records(self, role: str, pool_key: str | None = None, limit: int = 100, offset: int = 0,
                *, kind: str | None = None) -> dict:
        if kind not in (None, "character", "weapon"):
            raise ValueError("寻访记录类别不正确")
        where, args = "role=?", [role]
        if pool_key:
            where, args = where + " AND pool_key=?", args + [pool_key]
        if kind is not None:
            where += " AND pool_key IN (SELECT pool_key FROM pools WHERE role=? AND kind=?)"
            args += [role, kind]
        with self._db() as db:
            total = db.execute(f"SELECT COUNT(*) FROM records WHERE {where}", args).fetchone()[0]
            rows = db.execute(f"SELECT pool_key, payload FROM records WHERE {where} ORDER BY seq_id DESC"
                              " LIMIT ? OFFSET ?", (*args, limit, offset)).fetchall()
        return {"role_id": _public_role(role), "total": total,
                "records": [_public_record(key, payload) for key, payload in rows]}

    def export(self, role: str) -> dict:
        with self._db() as db:
            pools = db.execute("SELECT pool_key, kind, label, last_sync_at FROM pools WHERE role=? AND pool_key<>?"
                               " ORDER BY pool_key", (role, WEAPON_LIST_KEY)).fetchall()
            rows = db.execute("SELECT pool_key, payload FROM records WHERE role=? ORDER BY seq_id DESC",
                              (role,)).fetchall()
            breaks = db.execute("SELECT pool_key, seq_id, permanent FROM breaks WHERE role=?", (role,)).fetchall()
        return {"format": EXPORT_FORMAT, "format_version": 1, "role_id": _public_role(role),
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
    draws, gifts, unverified = [], 0, 0
    pool_version = None
    for row in rows:  # 由旧到新
        if row["seq_id"] in breaks:  # 这一条之前可能缺记录
            count, exact, free_in_count = 0, False, False
        if str(row.get("record_kind") or "").startswith("gift"):
            gifts += 1
            continue  # A bonus, including a six-star weapon, never resets pity.
        if kind == "weapon" and not _classified_weapon_record(row):
            unverified += 1
            count, exact, free_in_count = 0, False, False
            continue
        draws.append(row)
        version = row.get("pool_version")
        if kind == "weapon" and version is not None:
            if pool_version is not None and version != pool_version:
                count, exact, free_in_count = 0, False, False
            pool_version = version
        if row.get("rarity") is None:
            # This pull could itself have been a six-star: only later known
            # pulls are a defensible lower bound for the next interval.
            count, exact, free_in_count = 0, False, False
            continue
        if kind != "weapon" and row.get("is_free") is not False:
            # Missing free/paid status cannot be counted as a paid pull.
            free_in_count = True
        else:
            count += 1
        if row.get("rarity") == 6:
            history.append(EndfieldSixStar(
                name=row.get("name"), pool_id=row.get("pool_id"), pool_name=row.get("pool_name"), obtained_at=row.get("gacha_ts"),
                pulls=count, status="exact" if exact and not free_in_count else "lower_bound"))
            count, exact, free_in_count = 0, True, False
    # Gifts and unverified records are no pulls: a gift-only pool has no draw time range.
    times = [row["gacha_ts"] for row in draws if row.get("gacha_ts")]
    return EndfieldGachaPool(
        key=key, label=label, kind=kind, total=len(draws),
        six_star=sum(row.get("rarity") == 6 for row in draws), five_star=sum(row.get("rarity") == 5 for row in draws),
        four_star=sum(row.get("rarity") == 4 for row in draws),
        unknown_rarity=sum(row.get("rarity") not in (4, 5, 6) for row in draws),
        free=sum(row.get("is_free") is True for row in draws), gifts=gifts, unverified_records=unverified,
        since_last_six=(EndfieldPity(count=count, status="exact" if exact and not free_in_count else "lower_bound")
                        if draws else EndfieldPity()),
        history=list(reversed(history))[:HISTORY_LIMIT],
        history_total=len(history), history_available=min(len(history), HISTORY_LIMIT),
        history_limit=HISTORY_LIMIT, history_truncated=len(history)>HISTORY_LIMIT,
        newest_at=max(times, default=None), oldest_at=min(times, default=None),
        gaps=len(breaks), pending=any(not permanent for permanent in breaks.values()), last_sync_at=last_sync_at,
        banners=_banners(draws))


def _banners(rows) -> list[EndfieldGachaBanner]:
    """同类卡池按官方 poolId 拆成各期，计数只看这一期内的记录（抽数区间仍按同类连续计算）。"""
    banners: dict[str, EndfieldGachaBanner] = {}
    for row in rows:
        key = row.get("pool_id") or row.get("pool_name") or ""
        banner = banners.setdefault(key, EndfieldGachaBanner(pool_id=row.get("pool_id"), name=row.get("pool_name")))
        banner.name = banner.name or row.get("pool_name")
        banner.total += 1
        rarity = row.get("rarity")
        field = {6: "six_star", 5: "five_star", 4: "four_star"}.get(rarity, "unknown_rarity")
        setattr(banner, field, getattr(banner, field) + 1)
        banner.free += row.get("is_free") is True
        if row.get("gacha_ts"):
            banner.newest_at = max(banner.newest_at or 0, row["gacha_ts"])
            banner.oldest_at = min(banner.oldest_at or row["gacha_ts"], row["gacha_ts"])
    return sorted(banners.values(), key=lambda banner: -(banner.newest_at or 0))

